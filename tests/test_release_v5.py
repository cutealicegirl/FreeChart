# -*- coding: utf-8 -*-
"""v5 回归：行内信息、300 品类、官方图标、单击排序、页签、托盘价格、
全历史一屏、智能线、史高史低、光标倍数、数字随缩放。

完全离线（假行情 + 假 K 线 + 临时 APPDATA），不启动任何网络线程。
"""
import math
import os
import re
import sys
import tempfile
import time
from unittest.mock import patch

_TMP = tempfile.mkdtemp(prefix="ct_v5_")
os.environ["APPDATA"] = _TMP
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

from core.config import Config
from data.api_base import Ticker
from data.klines import Candle
from data.universe import TOP_N, all_of, names
from ui.chart_view import CandleChart, ChartView
from ui.icons import icon_file, symbol_icon, tray_price_icon
from ui.main_window import MainWindow, PAGE_SIZE, SORT_MODES, SortCycleButton
from ui.ticker_widget import TickerWidget

app = QApplication([])


def pump_rows(window, key, timeout=8.0):
    """驱动事件循环直到「全部」页首屏建行结束（按页按需，同步完成）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        QApplication.processEvents()
        if key not in window._filling_all:
            QApplication.processEvents()
            return
        time.sleep(0.005)
    QApplication.processEvents()


def fake_ticker(symbol, price=67000.0, change=3.24):
    return Ticker(symbol, symbol, price, change, price * 1.02,
                  price * 0.98, 1.2e9)


def make_candles(n=300):
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


# ================= 1. 名字只显示一次 + 高低额英文大字号 =================
row = TickerWidget("BTC", "Bitcoin")
assert row.lbl_symbol.text() == "BTC"
assert row.lbl_name.text() == "Bitcoin"
row.update_ticker(fake_ticker("BTC"))
assert row.lbl_name.text() == "Bitcoin", \
    "行情源返回的重复代码名 BTC 不应覆盖项目名"
assert row.lbl_high.text().startswith("H ")
assert row.lbl_low.text().startswith("L ")
assert row.lbl_vol.text().startswith("V ")
assert "font-size:11px" in row.lbl_high.styleSheet(), \
    "高低额字号需从 9px 提升到 11px"
assert "最高价" in row.lbl_high.toolTip(), "完整数值应保留在 tooltip"

dup = TickerWidget("DEGO", "DEGO")
assert dup.lbl_name.isHidden(), "名称与代码相同时应隐藏，不再重复显示"
stock = TickerWidget("SH:600519", "贵州茅台")
stock.update_ticker(Ticker("SH:600519", "贵州茅台", 1700, 1, 1710,
                           1690, 1e8))
assert stock.lbl_name.text() == "贵州茅台"
print("1. 名字去重 / H·L·V 英文大字号 OK")

# ================= 2. 官方原图标 / 项目原图标 =================
assert icon_file("BTC"), "BTC 应命中内置官方 logo"
bpm = symbol_icon("BTC", 30)
assert not bpm.isNull() and bpm.width() == 30
assert not symbol_icon("US:AAPL", 30).isNull(), \
    "股票使用项目原图标（市场色）回退"
icons_src = open(os.path.join(_ROOT, "ui", "icons.py"),
                 encoding="utf-8").read()
assert "code[:1]" not in icons_src, "不得再用首字母拼图标"
print("2. 品种官方图标 / 项目原图标 OK")

# ================= 3. 每市场品类数量（按总市值降序）=================
EXPECT = {"crypto": 200, "cn": 100, "hk": 200, "us": 500}
for key in ("crypto", "cn", "hk", "us"):
    syms = all_of(key)
    assert len(syms) == EXPECT[key], (key, len(syms))
    assert len(set(syms)) == EXPECT[key], (key, "有重复代码")
    assert names(key).get(syms[0])
print("3. 四市场 200/100/200/500 个品类 OK")

# ================= 4. 排序单击循环切换 =================
btn = SortCycleButton(SORT_MODES, "custom")
seen = [btn.currentData()]
for _ in range(len(SORT_MODES)):
    btn.click()
    seen.append(btn.currentData())
assert seen == [m[0] for m in SORT_MODES] + ["custom"], seen
assert btn.findData("price_desc") == 3
btn.setCurrentIndex(btn.findData("amount_desc"))
assert btn.currentData() == "amount_desc"
assert "排序 ·" in btn.text()
print("4. 单击循环切换排序 OK")

# ================= 5. 主窗口：页签去数字 / 300 行 / 托盘价格 =================
cfg = Config()
w = MainWindow(cfg)
w.scheduler.stop()
w.scheduler.refresh_now = lambda: None
w.show()
QApplication.processEvents()

for key, title in (("crypto", "加密货币"), ("cn", "A股"),
                   ("hk", "港股"), ("us", "美股")):
    assert w.tabs.buttons[key].text() == title, \
        f"页签不应显示数量数字: {w.tabs.buttons[key].text()}"

w._switch_sub("all")
QApplication.processEvents()
pump_rows(w, "crypto")
# 按页按需：行对象只建首屏一页；计数仍显示全市场数量
assert len(w.all_rows["crypto"]) == min(PAGE_SIZE, len(all_of("crypto"))), \
    len(w.all_rows["crypto"])
assert w.lbl_count.text() == "200"

tickers = {"BTC": fake_ticker("BTC"), "ETH": fake_ticker("ETH", 3200.0)}
w._on_fetched(tickers, "test", time.time())
assert not w.tray.icon().isNull()
assert "67,000" in w.windowTitle(), "窗口标题/任务栏需带实时价格"
assert "BTC" in w.windowTitle()
assert cfg.get("sort_mode") == "custom"

# 单击排序按钮后应写入配置并立即重排
w.combo_sort.click()
assert cfg.get("sort_mode") == SORT_MODES[1][0]
w.combo_sort.setCurrentIndex(w.combo_sort.findData("custom"))
print("5. 页签去数字 / 全部页 300 行 / 托盘+任务栏实时价格 OK")

# ================= 6. 全历史一屏 + 图表新功能 =================
chart = CandleChart()
chart.resize(1000, 640)
chart.set_data(make_candles())
chart.interval = "1d"
assert chart._extremes is not None, "应记录历史最高/最低及其位置"

# 全历史铺满一屏
chart._view_count = len(chart.candles)
chart._pan = 0.0
start, end = chart._visible_range()
assert start == 0 and end == len(chart.candles), (start, end)
chart.grab()   # 触发 paintEvent，验证绘制不崩
# 根数足够多时（全历史典型场景）自动切换成收盘价面积折线
dense = CandleChart()
dense.resize(1000, 640)
dense.set_data(make_candles(1200))
dense._view_count = len(dense.candles)
dense._pan = 0.0
assert dense._geom()["step"] < 2.6
dense.grab()

# 数字随缩放变化
chart._view_count = 20
big = chart._axis_px(10)
chart._view_count = 1000
small = chart._axis_px(10)
assert big > small >= 7, (big, small)
assert chart._axis_scale() < 1.0

# 智能线：趋势线 + 压力位 + 支撑位
chart._view_count = 120
a = chart._compute_auto(chart._bars())
assert a and "p0" in a and "p1" in a and "res" in a and "sup" in a
assert isinstance(a["res"], list) and isinstance(a["sup"], list)
chart.show_auto = True
chart.show_extremes = True
chart._mouse_pos = QPoint(500, 240)   # 光标倍数浮动标签
chart.grab()

# 滚轮缩到尽头应进入自动回溯一屏模式
chart._view_count = 90
from PySide6.QtGui import QWheelEvent
from PySide6.QtCore import QPointF
signals = []
chart.need_history.connect(lambda: signals.append(1))
for _ in range(20):
    chart.wheelEvent(QWheelEvent(QPointF(400, 300), QPointF(400, 300),
                                 QPoint(0, 0), QPoint(0, -120),
                                 Qt.NoButton, Qt.NoModifier,
                                 Qt.NoScrollPhase, False))
assert chart._view_count >= len(chart.candles), "应至少缩到全部已加载历史"
assert chart._visible_range() == (0, len(chart.candles)), \
    "全部已加载 K 线必须都在屏内"
assert signals, "应发出加载更早历史的信号"

# ChartView 的「全部历史」按钮链路
cv = ChartView(cfg)
cv.chart.set_data(make_candles())
cv._symbol = "BTC"
cv._interval = "1d"
with patch.object(ChartView, "_load_history", lambda self: None):
    cv._show_all_history()
assert cv.chart.fit_all and cv._show_all
assert cv.chart._view_count == len(cv.chart.candles)
print("6. 全历史一屏 / 数字随缩放 / 智能线 / 史高史低 / 光标倍数 OK")

print("\nv5 全部回归测试通过 ✅")
