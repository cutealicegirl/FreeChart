# -*- coding: utf-8 -*-
"""v4 回归：搜索添加、品种图标、全部/自选子菜单、托盘价格、自启隐藏、
图表自由平移 / 年份标签 / 缩到全部历史。

全部离线（假行情 + 假 K 线），使用临时 APPDATA，绝不污染真实配置。
"""
import math
import os
import re
import sys
import tempfile
import time
from unittest.mock import patch

_TMP = tempfile.mkdtemp(prefix="ct_v4_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QFontDatabase, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QScrollArea

import data.klines as klines
from core.config import Config
from data.klines import Candle, fetch_klines_before
from data.universe import all_of
from ui.chart_view import CandleChart
from ui.main_window import MARKET_GROUPS, PAGE_SIZE, MainWindow
from ui.search_panel import SearchResultRow
from ui.ticker_widget import TickerWidget

app = QApplication([])


def pump_rows(window, key, timeout=8.0):
    """驱动事件循环直到「全部」页分批建行结束（每帧 80 行）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        QApplication.processEvents()
        if key not in window._filling_all and \
                len(window.all_rows[key]) >= len(all_of(key)):
            QApplication.processEvents()
            return
        time.sleep(0.005)
    QApplication.processEvents()


def make_candles(n=200):
    out, price = [], 60000.0
    for i in range(n):
        delta = math.sin(i / 7.0) * 180 + math.cos(i / 3.0) * 60
        o, c = price, price + delta
        out.append(Candle(ts=1700000000 + i * 86400,
                          time_label=f"11-{(i % 28) + 1:02d}",
                          open=o, high=max(o, c) + 120,
                          low=min(o, c) - 120, close=c,
                          volume=1000 + i * 3.0))
        price = c
    return out


def wheel(delta_y, x=400):
    return QWheelEvent(QPointF(x, 300), QPointF(x, 300),
                       QPoint(0, 0), QPoint(0, delta_y),
                       Qt.NoButton, Qt.NoModifier,
                       Qt.NoScrollPhase, False)


def mouse(kind, pos, buttons=Qt.NoButton):
    p = QPointF(pos)
    return QMouseEvent(kind, p, p, Qt.LeftButton, buttons, Qt.NoModifier)


def fake_ticker(symbol, price=67000.0, change=3.24):
    return type("T", (), {
        "symbol": symbol, "name": symbol, "last_price": price,
        "change_pct": change, "high_24h": price * 1.02,
        "low_24h": price * 0.98, "quote_volume_24h": 1.2e9})()


# ================= 1. 币安字体 + 爱心机制移除 =================
cfg = Config()
w = MainWindow(cfg)
# 离屏回归必须完全离线：真实网络后台线程在 offscreen 事件循环里会让
# 进程以 127 退出（Qt 平台限制，非业务 bug）。行情由下方 fake 数据驱动。
w.scheduler.stop()
w.scheduler.refresh_now = lambda: None
w.show()
QApplication.processEvents()

families = QFontDatabase.families()
assert "IBM Plex Sans" in families and "IBM Plex Mono" in families, \
    "内置 IBM Plex（币安同源）字体未加载"
print("1a. IBM Plex 字体加载 OK")

row = TickerWidget("BTC", "Bitcoin")
assert not hasattr(row, "btn_heart") and not hasattr(row, "set_hearted")
assert not hasattr(row, "heart_callback")
assert row.icon.pixmap() is not None and not row.icon.pixmap().isNull(), \
    "每行应显示品种专属图标"
for f in ("ticker_widget.py", "search_panel.py", "main_window.py"):
    src = open(os.path.join(_ROOT, "ui", f), encoding="utf-8").read()
    assert "♥" not in src and "♡" not in src, f"{f} 仍残留爱心图标"
print("1b. 爱心机制已移除、品种图标生效 OK")

# ================= 2. 搜索结果可加入自选（核心 bug）=================
fake = [{"symbol": "ADA", "name": "Cardano", "kind": "加密货币"},
        {"symbol": "SH:600036", "name": "招商银行", "kind": "沪市A股"}]
panel = w.search_panel
panel.show_results(fake, set(w.rows))
# v31 起搜索结果是 QStackedWidget 里的独立页面：show_results 只负责
# 渲染内容，是否可见由主窗口切页决定，不再要求它嵌在行情列表页里可见。
assert panel is w.search_panel
first = panel._layout.itemAt(0).widget()
assert isinstance(first, SearchResultRow)
assert first.layout().indexOf(first.btn_add) >= 0, \
    "添加按钮必须真实加入布局（此前缺失导致搜索后无法添加）"
first.btn_add.click()
assert "ADA" in w.rows, "点击搜索结果『＋ 添加』应加入自选"
assert "ADA" in (cfg.get("symbols") or []), "加入后应写入配置"
first.btn_add.click()
assert "ADA" not in w.rows, "再次点击应移出自选"
# v31 起点击整行是「进入图表」，默认不再改自选；收藏只由 ＋ 按钮触发
assert "点击进入图表" in first.toolTip(), "点击整行应进入图表而非默认收藏"
assert "ADA" not in w.rows, "第二次点击 ＋ 后应已移出自选"
print("2. 搜索结果显式添加 / 移出自选 OK（点行进图表）")

# ================= 3. 每个市场的「自选 / 全部」子菜单 =================
assert set(w.sub_tabs.buttons) == {"watch", "all"}
assert len(w.rows) == 17
lay = w.pages["crypto"]["layout"]
watch_count = sum(1 for i in range(lay.count())
                  if lay.itemAt(i).widget() is not None
                  and hasattr(lay.itemAt(i).widget(), "symbol"))
assert watch_count == 17
w._switch_sub("all")
QApplication.processEvents()
pump_rows(w, "crypto")
assert w._sub_tabs["crypto"] == "all"
assert cfg.get("sub_tabs")["crypto"] == "all", "子页应持久化"
all_count = sum(1 for i in range(lay.count())
                if lay.itemAt(i).widget() is not None
                and hasattr(lay.itemAt(i).widget(), "symbol"))
# 阶段 2：首屏只挂载一页（按需加载），行对象仍全量准备、滚动再追加
assert all_count == min(PAGE_SIZE, len(all_of("crypto"))), all_count
assert len(w.all_rows["crypto"]) == len(all_of("crypto")), \
    "行对象应齐备，虚拟化只作用于布局挂载"
assert all(w.all_rows["crypto"][s].btn_action is not None
           for s in all_of("crypto"))
target = next(s for s in all_of("crypto") if s not in w.rows)
w.all_rows["crypto"][target].btn_action.click()
assert target in w.rows, "全部页按钮应能加入自选"
w.all_rows["crypto"][target].btn_action.click()
assert target not in w.rows
w._switch_sub("watch")
QApplication.processEvents()
w._switch_market("cn")
w._switch_sub("all")
QApplication.processEvents()
pump_rows(w, "cn")
assert len(w.all_rows["cn"]) == len(all_of("cn")), len(w.all_rows["cn"])
assert all(isinstance(w.stack.widget(i), QScrollArea)
           for i in range(len(MARKET_GROUPS)))
w._switch_market("crypto")
print("3. 四市场分页 + 自选/全部子菜单 OK")

# ================= 4. 托盘价格 / 开机自启隐藏 =================
tickers = {"BTC": fake_ticker("BTC"), "ETH": fake_ticker("ETH", 3200.0, -1.2)}
w._on_fetched(tickers, "test", time.time())
QApplication.processEvents()
assert not w.tray.icon().isNull()
assert "BTC" in w.act_price.text() and "67,000" in w.act_price.text()
assert "67,000" in w.tray.toolTip()
w.set_tray_symbol("ETH")
w._on_fetched(tickers, "test", time.time())
assert "ETH" in w.act_price.text() and "3,200" in w.act_price.text()
assert Config().get("tray_symbol") == "ETH", "托盘品种应持久化"
assert w.tray_symbol_menu.actions(), "托盘应有品种切换子菜单"
w._set_tray_price_enabled(False)
assert "未启用" in w.act_price.text()
w._set_tray_price_enabled(True)
w.set_tray_symbol("BTC")

from core.autostart import _command
assert "--minimized" in _command(), "开机自启命令必须带最小化参数"
assert cfg.get("start_in_tray") is True
w.start_minimized()
QApplication.processEvents()
assert w.isHidden(), "自启后应隐藏到右下角托盘"
main_src = open(os.path.join(_ROOT, "main.py"), encoding="utf-8").read()
assert "--minimized" in main_src and "start_minimized" in main_src
print("4. 托盘实时价格 / 品种切换 / 自启隐藏 OK")

# ================= 5. 图表整体平移（非右侧固定）=================
chart = CandleChart()
chart.resize(1000, 640)
chart.set_data(make_candles())
chart.interval = "1d"
assert chart._pan == 0 and chart._bars()[-1] is chart.candles[-1]
g0 = chart._geom()
assert abs(g0["bar_x0"] - g0["x0"]) < 1.0
p = QPoint(int(g0["x0"] + 300), int(g0["price"].top() + 50))
chart.set_tool("none")
chart.mousePressEvent(mouse(QEvent.MouseButtonPress, p, Qt.LeftButton))
chart.mouseMoveEvent(mouse(QEvent.MouseMove,
                           QPoint(p.x() - 140, p.y()), Qt.LeftButton))
chart.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease,
                              QPoint(p.x() - 140, p.y())))
assert chart._pan < -1, f"向左拖应让整图左移并右侧留白: {chart._pan}"
g1 = chart._geom()
assert g1["bar_x0"] < g1["x0"] - 1, "K 线应整体左移，而非右端钉死"
assert chart._bars()[-1] is chart.candles[-1], "右侧留白时最后一根仍是最新"
chart.mousePressEvent(mouse(QEvent.MouseButtonPress, p, Qt.LeftButton))
chart.mouseMoveEvent(mouse(QEvent.MouseMove,
                           QPoint(p.x() + 260, p.y()), Qt.LeftButton))
chart.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease,
                              QPoint(p.x() + 260, p.y())))
assert chart._pan > 0, "向右拖应回看更早历史"
assert chart._bars()[-1].ts < chart.candles[-1].ts
chart.reset_view()
print("5. 左键整体平移（可右侧留白 / 可回看历史）OK")

# ================= 6. 时间轴带年份 =================
labels = chart._time_axis_labels(chart._geom())
assert labels
assert all(re.search(r"\d{4}", text) for _r, text, _x in labels), \
    "时间轴标签必须带年份"
assert re.search(r"\d{4}-\d{2}-\d{2}",
                 chart._axis_full(chart.candles[0])), \
    "十字光标气泡应显示完整日期"
chart.interval = "1M"
assert re.fullmatch(r"\d{4}-\d{2}", chart._axis_date(chart.candles[0]))
chart.interval = "1y"
assert re.fullmatch(r"\d{4}", chart._axis_date(chart.candles[0]))
chart.interval = "15m"
assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}",
                    chart._axis_full(chart.candles[0]))
print("6. 时间轴年份 / 月K / 年K / 分钟气泡 OK")

# ================= 7. 滚轮可缩到全部生命周期 =================
chart.history_exhausted = True       # 离线测试不触发网络分页
seen = []
chart.need_history.connect(lambda: seen.append(1))
chart.reset_view()
for _ in range(14):
    chart.wheelEvent(wheel(-120, x=500))
assert chart._view_count >= len(chart.candles), \
    f"应能缩到全部已加载 K 线: {chart._view_count}"
assert chart._visible_range() == (0, len(chart.candles)), \
    "全部已加载 K 线必须都在屏内"
assert chart._view_count > 150
while chart._view_count >= len(chart.candles):
    chart.wheelEvent(wheel(120, x=500))
assert chart._view_count < len(chart.candles)
chart.history_exhausted = False
chart._view_count = len(chart.candles)
chart.wheelEvent(wheel(-120, x=500))
assert seen, "缩到数据尽头应发出加载更早历史的请求"
print("7. 滚轮缩到全部历史 + 自动回溯信号 OK")

# ================= 8. 历史分页函数 =================
# A 股现在也支持按结束日期翻页（测试全程 mock，不能联网）
old_candles = [Candle(ts=c.ts - 100_000_000, time_label=c.time_label,
                      open=c.open, high=c.high, low=c.low,
                      close=c.close, volume=c.volume)
               for c in make_candles(10)]
with patch.object(klines, "_tencent_rows", return_value=[["2023-01-03"]]), \
        patch.object(klines, "_parse_stock_rows",
                     return_value=old_candles):
    older, exhausted = fetch_klines_before("SH:600519", "day", 1700000000)
    assert isinstance(older, list) and len(older) > 0
    assert exhausted is False, "A 股也应能继续往前翻页"
raw = make_candles(1000)
with patch.object(klines, "_fetch_crypto_raw", return_value=raw) as m:
    older, exhausted = fetch_klines_before("BTC", "1d", 1800000000)
    assert m.call_args.kwargs.get("end_time_ms") == 1799999999999
    assert exhausted is False and len(older) > 0
# 短页不再被误判为「到头」：只有接口完全没有更早数据才结束
with patch.object(klines, "_fetch_crypto_raw", return_value=raw[:5]):
    _older, exhausted = fetch_klines_before("BTC", "1d", 1800000000)
    assert exhausted is False
with patch.object(klines, "_fetch_crypto_raw", return_value=[]):
    older, exhausted = fetch_klines_before("BTC", "1d", 1800000000)
    assert exhausted is True and older == []
print("8. K 线历史分页 / 生命周期终点判断 OK")

# ================= 9. 配置持久化 =================
cfg2 = Config()
assert cfg2.get("tray_symbol") == "BTC"
assert cfg2.get("start_in_tray") is True
assert cfg2.get("sub_tabs")["crypto"] == "watch"
assert cfg2.get("max_history") == 0, "0 = 不限根数，一路回溯到上市首根"
print("9. 新配置持久化 OK")

w.quit_app()
QTimer.singleShot(50, app.quit)
app.exec()
print("\nv4 全部回归测试通过 ✅")
