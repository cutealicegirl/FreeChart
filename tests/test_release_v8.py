# -*- coding: utf-8 -*-
"""v8 离线回归：局部高低点 LH/LL + 任务栏贴合式常驻价格（非悬浮框）。"""
import inspect
import math
import os
import sys
import tempfile
import time

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_v8_")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QRect
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

app = QApplication([])
for f in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc"):
    if os.path.exists(f):
        QFontDatabase.addApplicationFont(f)

from core.config import Config
from core.taskbar import dock_geometry, system_is_light, taskbar_rect
from data.api_base import Ticker
from data.klines import Candle
from ui.chart_view import CandleChart, ChartView
from ui.main_window import MainWindow
from ui.price_badge import PriceBadge


def wave_candles(n=200):
    """多波峰波谷，保证能识别出多个局部高低点。"""
    out = []
    for i in range(n):
        base = 100 + 18 * math.sin(i / 11.0) + 5 * math.sin(i / 3.0)
        hi = base + 6 + 2 * math.sin(i / 4.0)
        lo = base - 6 - 2 * math.cos(i / 4.0)
        out.append(Candle(ts=1600000000 + i * 86400,
                          time_label=f"d{i:03d}", open=base,
                          high=hi, low=lo, close=base + 1,
                          volume=1000 + i))
    return out


# ===== 1. 局部高低点：一屏各只取一个（可见区间极值）=====
chart = CandleChart()
bars = wave_candles()
pv = chart._compute_pivots(bars)
assert len(pv["h"]) == 1 and len(pv["l"]) == 1, "一屏各只标一个 LH / LL"
hi_i, hi_p = pv["h"][0]
lo_i, lo_p = pv["l"][0]
assert 0 <= hi_i < len(bars) and abs(hi_p - bars[hi_i].high) < 1e-9
assert 0 <= lo_i < len(bars) and abs(lo_p - bars[lo_i].low) < 1e-9
assert hi_p == max(c.high for c in bars) and lo_p == min(c.low for c in bars), \
    "LH/LL 必须是可见区间的最高 / 最低"
assert hi_p > lo_p, "可见区间最高价应高于最低价"
assert chart._compute_pivots(bars[:2]) == {"h": [], "l": []}
print(f"1. 局部高低点识别 OK（LH 1 个 / LL 1 个：{hi_p:.1f} / {lo_p:.1f}）")

# ===== 2. 沿用旧方式：只打点标英文缩写价格，不画水平线；ATH/ATL 让位 =====
src = inspect.getsource(CandleChart._draw_pivots)
assert '"LH", pv["h"]' in src and '"LL", pv["l"]' in src
assert "drawLine" not in src, "不得画贯穿水平线"
assert "drawEllipse" in src and "format_price(price)" in src
assert "self._extreme_rects" in src, "标签要避开 ATH/ATL"
assert "skip_h" in src and "skip_l" in src, "史高/史低可见时 LH/LL 要让位"
paint_src = inspect.getsource(CandleChart.paintEvent)
assert "if self.show_pivots:" in paint_src
ext_src = inspect.getsource(CandleChart._draw_extremes)
assert "self._extreme_rects" in ext_src
print("2. LH/LL 各一个 + 英文缩写 + 不画水平线 + ATH/ATL 让位 OK")

# ===== 3. 第五个独立按钮与配置持久化 =====
cfg = Config()
assert cfg.get("show_pivots") is True, "局部高低点默认显示"
cv = ChartView(cfg)
assert cv.chart.show_pivots is True
assert cv._smart_buttons["show_pivots"].isChecked()
cv._toggle_smart("show_pivots", False)
assert cv.chart.show_pivots is False and cfg.get("show_pivots") is False
cv._toggle_smart("show_trend", True)
assert cv.chart.show_trend is True and cv.chart.show_pivots is False, \
    "开关互不连带"
cfg.set("show_pivots", True)
cv.sync_smart_buttons()
assert cv.chart.show_pivots is True and \
    cv._smart_buttons["show_pivots"].isChecked()
print("3. 「局部高低」独立按钮 + 默认开 + 配置持久化 OK")

# ===== 4. 任务栏矩形：四个贴边方向 =====
full = QRect(0, 0, 1920, 1080)
assert taskbar_rect(full, QRect(0, 0, 1920, 1032)) == QRect(0, 1032, 1920, 48)
assert taskbar_rect(full, QRect(0, 48, 1920, 1032)) == QRect(0, 0, 1920, 48)
assert taskbar_rect(full, QRect(60, 0, 1860, 1080)) == QRect(0, 0, 60, 1080)
assert taskbar_rect(full, QRect(0, 0, 1860, 1080)) == QRect(1860, 0, 60, 1080)
assert isinstance(system_is_light(), bool)
screen = QApplication.primaryScreen()
f = screen.geometry()
tb = taskbar_rect(f, screen.availableGeometry())
x, y, w, h = dock_geometry(screen, 158, 46)
assert tb.left() <= x and x + w <= f.right()
assert tb.top() <= y and y + h <= tb.bottom()
assert w == 158 and 26 <= h <= 46
assert x > f.left() + f.width() // 2, "必须固定在任务栏右侧"
print(f"4. 任务栏定位 OK（贴合点 {x},{y} 尺寸 {w}x{h}）")

# ===== 5. 价格小工具：透明贴合、无卡片、不可拖动 =====
badge = PriceBadge(cfg)
t = Ticker("BTC", "BTC", 67891.23, 2.35, 70000.0, 66000.0, 1.7e9)
badge.update_ticker(t, "BTC")
assert badge._price_text == "$67,891.23", badge._price_text
assert badge._change_raw == "+2.35%"
assert badge._symbol == "BTC"
assert "67,891" in badge.toolTip()
badge.apply_config()
gx, gy, gw, gh = dock_geometry(screen, badge.width(), badge.HEIGHT)
assert (badge.x(), badge.y(), badge.width(), badge.height()) == (gx, gy, gw, gh)
assert badge._dock_timer.isActive(), "要定时重新贴靠任务栏"
badge._save_pos()                       # 固定位置，不再写拖动坐标
bsrc = inspect.getsource(PriceBadge)
assert "drawRoundedRect" not in bsrc, "不能再是圆角卡片"
assert "QPen" not in bsrc and "WA_TranslucentBackground" in bsrc
assert "mouseMoveEvent" not in bsrc and "OpenHandCursor" not in bsrc
assert "dock_geometry" in bsrc and "_force_topmost" in bsrc
assert "拖动" not in inspect.getsource(PriceBadge.update_ticker)
print("5. 任务栏贴合小工具 OK（透明底 / 固定位置 / 定时重贴）")

# ===== 6. 主窗口联动 =====
w = MainWindow(cfg)
w.scheduler.stop()
w.scheduler.refresh_now = lambda: None
assert w.price_badge._dock_timer.isActive()
w._on_fetched({"BTC": t}, "test", time.time())
assert w.price_badge._price_text == "$67,891.23"
assert "67,891" in w.windowTitle()
w.quit_app()
print("6. 主窗口刷新联动 OK")
print("\nv8 全部回归测试通过 ✅")
