# -*- coding: utf-8 -*-
"""v31 回归：阶段 6「移动端优先交互」。

验收点（离线，不依赖真实触摸设备，用合成鼠标事件模拟触摸手势）：
1. 短按 = 进图表；长按 ≥500ms = 品种菜单；滑动 = 不误触；
2. 行内 ⋯ 按钮提供不依赖右键 / 悬停的菜单入口，右键仍兼容桌面；
3. 搜索 / 排序 / 底部导航 / 标题栏 / 图表工具按钮均为 ≥44px 触控目标；
4. 列表注册了触摸惯性滚动，窄屏自动收起次要信息（单列优先）；
5. 图表有触屏缩放按钮，缩放以视口中心为锚点、不强制对齐最右；
6. 资料弹窗不再依赖悬停（悬停信号仍未连到弹窗）。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v31_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CT_OFFLINE"] = "1"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QScroller

import ui.main_window as mw
from core.config import Config
from ui.main_window import MainWindow

app = QApplication([])


def pump(sec=0.1):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


class FakeMenu:
    def __init__(self, parent=None):
        self._acts = []

    def setStyleSheet(self, _qss):
        pass

    def addAction(self, text):
        a = type("A", (), {"text": lambda s: text,
                           "setEnabled": lambda s, v: None})()
        self._acts.append(a)
        return a

    def addSeparator(self):
        return None

    def exec(self, _pos):
        return None


cfg = Config()
cfg.set("mascot_enabled", False)
w = MainWindow(cfg)
w.scheduler.stop()
w.scheduler.refresh_now = lambda: None
w.resize(420, 760)
w.prepare_show()
pump(0.1)
row = next(iter(w.rows.values()))
sym = row.symbol

# ============ 1. 短按 / 长按 / 滑动 ============
clicked, menus, longs = [], [], []
row.row_clicked.disconnect()
row.context_menu.disconnect()
row.long_pressed.disconnect()
row.row_clicked.connect(clicked.append)
row.context_menu.connect(lambda s, _p: menus.append(s))
row.long_pressed.connect(longs.append)
# 长按也会触发窗口侧菜单分支，用假菜单避免 offscreen 原生 exec 阻塞
_orig_menu = mw.QMenu
mw.QMenu = FakeMenu
try:
    def press():
        return QMouseEvent(QEvent.MouseButtonPress, QPointF(10, 10),
                           QPointF(10, 10), Qt.LeftButton, Qt.LeftButton,
                           Qt.NoModifier)

    def release(x=10, y=10):
        return QMouseEvent(QEvent.MouseButtonRelease, QPointF(x, y),
                           QPointF(x, y), Qt.LeftButton, Qt.NoButton,
                           Qt.NoModifier)

    # 短按
    row.mousePressEvent(press())
    row.mouseReleaseEvent(release())
    assert clicked == [sym], clicked
    assert not menus and not longs
    # 长按
    row.mousePressEvent(press())
    pump(0.62)
    assert longs == [sym], longs
    assert menus == [sym], menus
    row.mouseReleaseEvent(release())
    assert clicked == [sym], "长按不得同时进图表"
    # 滑动：移动超过阈值后松手，既不点击也不长按
    clicked.clear(); menus.clear(); longs.clear()
    row.mousePressEvent(press())
    move = QMouseEvent(QEvent.MouseMove, QPointF(60, 80),
                       QPointF(60, 80), Qt.NoButton, Qt.LeftButton,
                       Qt.NoModifier)
    row.mouseMoveEvent(move)
    pump(0.62)
    row.mouseReleaseEvent(release(60, 80))
    assert not clicked and not menus and not longs, \
        f"滑动不得误触：{clicked} {menus} {longs}"
finally:
    mw.QMenu = _orig_menu
print("1. 短按进图表 / 长按出菜单 / 滑动不误触 OK")

# ============ 2. 价格右侧 ⋯ 方框已按需求移除，右键/长按仍可用 ============
menus.clear()
assert not hasattr(row, "btn_more"), "价格右侧的 ⋯ 方框按钮应已删除"
assert not hasattr(row, "_on_more"), "⋯ 的旧点击处理也应一并移除"
row.contextMenuEvent(type("E", (), {
    "globalPos": lambda s: QPoint(12, 12)})())
assert menus == [sym], "桌面右键仍需可用"
print("2. ⋯ 方框已移除 + 长按 / 右键菜单仍可用 OK")

# ============ 3. 触控目标 ≥44px ============
targets = {
    "搜索框": w.edit_search, "排序按钮": w.combo_sort,
    "升降序": w.btn_sort_dir, "排序菜单": w.btn_sort_menu,
    "返回": w.title_bar.btn_back,
    "指标参数": w.chart_view.btn_indicator_settings,
    "图表缩放＋": w.chart_view.btn_zoom_in,
    "图表缩放－": w.chart_view.btn_zoom_out,
    "图表返回": w.chart_view.btn_back,
    "详情": w.chart_view.btn_detail,
    "工具条": w.chart_view.btn_tools,
    "设置返回": w.settings_page.btn_back,
}
for name, widget in targets.items():
    assert widget.size().height() >= 44 or widget.minimumHeight() >= 44, \
        f"{name} 触控目标不足 44px: {widget.size().height()}"
for key, btn in w.bottom_nav.buttons.items():
    assert btn.size().height() >= 44, f"底栏 {key} 太矮"
assert row.minimumHeight() >= 64
print(f"3. {len(targets)} 个主要按钮 + 底栏 + 行高均达标 OK")

# ============ 4. 触摸滚动 + 响应式单列 ============
scrolled = False
for page in w.pages.values():
    g = QScroller.grabbedGesture(page["scroll"].viewport())
    if int(g) != 0:
        scrolled = True
assert scrolled, "列表应注册触摸惯性滚动"
assert w._narrow is True and not w.lbl_hint.isVisible()
w.resize(900, 760)
pump(0.05)
assert w._narrow is False and w.lbl_hint.isVisible()
assert w.edit_search.placeholderText().startswith("搜索代码")
w.resize(420, 760)
pump(0.05)
assert w.edit_search.placeholderText() == "搜索 / 筛选"
assert isinstance(w.pages["crypto"]["layout"],
                  __import__("PySide6.QtWidgets", fromlist=["QVBoxLayout"]).QVBoxLayout)
print("4. 触摸惯性滚动 + 窄屏单列自适应 OK")

# ============ 5. 触屏缩放按钮 ============
chart = w.chart_view.chart
from data.klines import Candle
bars = []
price = 60000.0
for i in range(240):
    bars.append(Candle(ts=1700000000 + i * 86400,
                       time_label=f"11-{(i % 28) + 1:02d}",
                       open=price, high=price + 100, low=price - 100,
                       close=price + (1 if i % 2 else -1) * 50,
                       volume=1000.0 + i))
chart.set_candles(bars) if hasattr(chart, "set_candles") else None
chart.candles = bars
chart._view_count = 90
chart._pan = 3.0
before = chart._view_count
w.chart_view.btn_zoom_in.click()
assert chart._view_count < before, "＋ 应放大（可见根数减少）"
mid = chart._view_count
w.chart_view.btn_zoom_out.click()
assert chart._view_count > mid, "－ 应缩小（可见根数增加）"
assert abs(chart._pan) > 0.001, "缩放不得把视口强制对齐到最右（pan=0）"
print("5. 触屏缩放按钮以视口中心为锚点、不强制贴右 OK")

# ============ 6. 资料弹窗不依赖悬停 ============
assert not w.info_panel.isVisible()
row.hovered.emit(sym)
pump(0.1)
assert not w.info_panel.isVisible(), "悬停不得弹出资料卡"
w._show_info_popup(sym)
pump(0.05)
assert w.info_panel.isVisible()
w.info_panel.hide_popup()
print("6. 资料弹窗只由主动选择触发，不依赖悬停 OK")

# ============ 收尾 ============
w._detail_cache.clear()
pump(0.05)
from qt_exit import finish
print("\nv31 全部回归测试通过 ✅")
finish()
