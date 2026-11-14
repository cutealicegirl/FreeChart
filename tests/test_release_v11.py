# -*- coding: utf-8 -*-
"""v11 离线回归：缩放可逆 / 全历史紧凑铺满 + 图标原图无白底高分辨率。"""
import inspect
import os
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_v11_")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QPoint, QPointF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

app = QApplication([])

import ui.chart_view as cv_mod
import ui.icons as icons_mod
from data.klines import Candle
from ui.chart_view import CandleChart, ChartView
from ui.icons import project_badge, symbol_icon


class Wheel:
    """最小滚轮事件替身：只需要 angleDelta / position / accept。"""

    def __init__(self, dy, x=990):
        self._dy, self._x = dy, x
        self.accepted = False

    def angleDelta(self):
        return QPoint(0, self._dy)

    def position(self):
        return QPointF(self._x, 300)

    def accept(self):
        self.accepted = True


def bars(n):
    return [Candle(ts=1600000000 + i * 86400, time_label=str(i),
                   open=100 + i % 7, high=105 + i % 9, low=95 + i % 5,
                   close=101 + i % 6, volume=1000 + i) for i in range(n)]


# ===== 1. 放大后可缩小，缩到尽头正好铺满全部历史（无右侧空白）=====
for n in (300, 20000):
    c = CandleChart()
    c.resize(1000, 600)
    c.set_data(bars(n))
    for _ in range(10):
        c.wheelEvent(Wheel(120))
    assert c._view_count < 60, "应先能放大"
    assert c.fit_all is False, "放大必须解除「全部历史」自动贴合"
    for _ in range(80):
        c.wheelEvent(Wheel(-120))
    # v22 起：缩小极限仍是 2×总根数、全部历史仍在屏内，但位置由
    # 「缩放锚点」决定，不再被强制 pan=0（贴右）或居中。
    assert int(c._view_count) == 2 * n, (c._view_count, n)
    assert c._pan != 0.0, "缩放不得强制把最新一根对齐到最右侧"
    assert abs(c._pan + n / 2.0) > 1e-6, "缩放不得强制整块居中"
    assert c._visible_range() == (0, n), "全部历史必须都在屏内"
    # 反复放大缩小仍然可逆
    for _ in range(6):
        c.wheelEvent(Wheel(120))
    for _ in range(60):
        c.wheelEvent(Wheel(-120))
    assert int(c._view_count) == 2 * n and c._visible_range() == (0, n)
print("1. 放大/缩小可逆，缩到尽头铺满全历史 OK (300 / 20000 根)")

# ===== 2. 缩放以光标下那根 K 线为锚点，位置不被强制重排 =====
def anchor_index(chart, x):
    """屏幕 x 处对应的是第几根 K 线（浮点索引）。"""
    w = max(60.0, chart.width() - chart._margin_l - chart._margin_r)
    right_px = chart._margin_l + w
    step = w / chart._view_count
    return chart._right_edge() - (right_px - x) / step


c = CandleChart()
c.resize(1000, 600)
c.set_data(bars(800))
c.wheelEvent(Wheel(120))          # 先放大到中间
ax = 400
for _ in range(30):
    before = anchor_index(c, ax)
    c.wheelEvent(Wheel(-120, x=ax))
    after = anchor_index(c, ax)
    # 视野还没宽过全部历史时，锚点那根 K 线的屏幕位置必须原地不动
    if c._view_count < len(c.candles):
        assert abs(before - after) < 1e-6, \
            f"缩放锚点漂移 {before} -> {after}"
    assert c._visible_range()[1] == len(c.candles), \
        "缩放不得把最新一根推出屏外"
print("2. 缩放锚点保持不变、不强制对齐 OK")

# ===== 3. 用户主动放大 / 拖动会退出全历史模式 =====
events = []
c2 = CandleChart()
c2.user_view_change.connect(lambda: events.append(1))
c2.resize(900, 500)
c2.set_data(bars(200))
c2.fit_all = True
c2._view_count = 200
c2.wheelEvent(Wheel(120))
assert events and c2.fit_all is False, "放大必须通知页面退出全历史"
src = inspect.getsource(CandleChart.mousePressEvent)
assert "user_view_change" in src and "fit_all = False" in src, "拖动也要退出全历史"
view_src = inspect.getsource(ChartView._on_user_view_change)
assert "_show_all = False" in view_src and "_stop_history_pump" in view_src
fit_src = inspect.getsource(ChartView._fit_all_view)
assert "_pan = 0.0" in fit_src and "fit_all = True" in fit_src
print("3. 放大/拖动退出自动贴合，_fit_all_view 左对齐铺满 OK")

# ===== 4. 币种图标：256px、透明背景、不再有白底圆盘 =====
coin = os.path.join(_ROOT, "assets", "coins", "btc.png")
im = QImage(coin)
assert im.width() >= 256 and im.height() >= 256, (im.width(), im.height())
assert im.hasAlphaChannel()
corner = im.pixelColor(1, 1)
assert corner.alpha() < 16, f"图标不能有底色圆盘 (alpha={corner.alpha()})"
count = len([f for f in os.listdir(os.path.join(_ROOT, "assets", "coins"))
             if f.endswith(".png")])
assert count >= 260, f"官方图标数量偏少: {count}"
print(f"4. 币种图标 256px + 透明无白底 OK（{count} 个）")

# ===== 5. 图标按设备像素比绘制，显示时不再被拉伸 =====
dpr = icons_mod._dpr()
pm = symbol_icon("BTC", 30)
assert abs(pm.devicePixelRatio() - dpr) < 1e-6
assert pm.width() == round(30 * dpr), (pm.width(), dpr)
assert abs(pm.devicePixelRatio() and pm.width() / pm.devicePixelRatio() - 30) < 1.0
pm20 = symbol_icon("BTC", 20)
assert pm20.width() == round(20 * dpr)
print(f"5. 图标按 DPR={dpr:g} 渲染 OK（30px -> {pm.width()} 物理像素）")

# ===== 6. 股票类徽章：项目图标直出，无白色圆底 =====
from PySide6.QtGui import QPixmap, QColor

badge = project_badge("SZ:300750", 30)
assert badge.hasAlphaChannel()
img = badge.toImage()
# 四角必须基本透明（说明没有白色圆盘铺满）
for x, y in ((0, 0), (img.width() - 1, 0),
             (0, img.height() - 1), (img.width() - 1, img.height() - 1)):
    assert img.pixelColor(x, y).alpha() < 40, (x, y,
                                               img.pixelColor(x, y).alpha())
# 中心区域必须有内容
mid = img.pixelColor(img.width() // 2, img.height() // 2)
assert mid.alpha() > 60
badge_src = inspect.getsource(project_badge)
assert "#eef3fb" not in badge_src and "#f4f7fd" not in badge_src, \
    "不能再出现白色圆底"
sym_src = inspect.getsource(symbol_icon)
assert "#f4f7fd" not in sym_src and "drawEllipse" not in sym_src, \
    "官方图标不得再套白底圆"
print("6. 股票徽章 / 官方图标均无白色圆底 OK")

print("\nv11 全部回归测试通过 ✅")
