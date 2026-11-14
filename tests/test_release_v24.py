# -*- coding: utf-8 -*-
"""v24 回归：工具条独立图层 / 资料弹窗不遮挡且可拖动 / 关闭按钮加大。

覆盖：
1. 工具面板与 K 线不同图层：不参与布局，展开 / 收纳图表区大小完全不变，
   面板悬浮在图表正上方；
2. 资料弹窗默认位置不遮挡：窄窗口停靠右下角（不压右键点开的行），
   宽窗口放行侧面整块空位；
3. 按住标题栏可拖动弹窗、钳制在软件内，且本次会话记住拖动后的位置；
4. 关闭按钮热区加大（>=40x32）。

全部离线（临时 APPDATA + offscreen + CT_OFFLINE）。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v24_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CT_OFFLINE"] = "1"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from core.config import Config
from data.universe import market_of
from ui.main_window import MainWindow
from ui.popup import popup_close_button

app = QApplication([])


def pump(sec=0.1):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


cfg = Config()
cfg.set("mascot_enabled", False)
cfg.set("price_badge", False)
w = MainWindow(cfg)
w.resize(900, 760)
w.prepare_show()
w.show()
pump(0.2)

sym = next(iter(w.rows))
row = w.rows[sym]
assert row.isVisible(), "测试行应可见"

# ============ 1. 工具面板与 K 线不同图层 ============
w._open_chart(sym)
pump(0.3)
cv = w.chart_view
lay = cv.layout()
assert lay.indexOf(cv.tools_head) >= 0, "细条仍在布局里（占稳定的一条）"
assert lay.indexOf(cv.tools_panel) == -1, \
    "展开面板必须脱离布局（独立图层，不挤压 K 线）"
assert cv.tools_panel.parentWidget() is cv, "面板应挂在图表页上悬浮"

chart_frame = cv.chart.parentWidget()
geo_before = QRect(chart_frame.geometry())
cv._tools_hovered = True
cv._apply_tools_visible()
pump(0.05)
assert cv.tools_panel.isVisible(), "悬停应展开工具面板"
assert chart_frame.geometry() == geo_before, \
    "展开面板不得改变图表区大小（K 线不能被挤压重排）"
panel_geo = QRect(cv.tools_panel.geometry())
cf_geo = chart_frame.geometry()
assert panel_geo.top() >= cv.tools_head.geometry().bottom(), \
    "面板应从细条下方开始"
assert panel_geo.intersects(cf_geo), "面板应悬浮在图表上方（覆盖式图层）"
assert panel_geo.left() <= 16, "面板左对齐图表区"

cv._tools_hovered = False
cv._apply_tools_visible()
pump(0.05)
assert not cv.tools_panel.isVisible(), "移开应收纳"
assert chart_frame.geometry() == geo_before, "收纳也不得改变图表区大小"

# 窗口尺寸变化后悬浮面板跟着重新摆位
w.resize(700, 700)
pump(0.1)
cv._tools_hovered = True
cv._apply_tools_visible()
pump(0.05)
assert cv.tools_panel.isVisible()
pg = cv.tools_panel.geometry()
assert pg.width() <= cv.width() - 8, "面板不得超出图表页宽度"
assert pg.top() >= cv.tools_head.geometry().bottom()
cv._tools_hovered = False
cv._apply_tools_visible()
print("1. 工具面板独立图层：展开/收纳/改窗口大小都不动 K 线 OK")

# ============ 2. 资料弹窗默认位置不遮挡 ============
w._leave_chart()
pump(0.1)
w.resize(480, 800)                  # 窄窗口：两侧放不下 380 宽的弹窗
pump(0.2)
w._show_info_popup(sym)
pump(0.05)
pop = w.info_panel
assert pop.isVisible(), "右键「查看资料」应弹出"
pop_tl = pop.mapToGlobal(QPoint(0, 0))
pop_rect = QRect(pop_tl, pop.size())
row_rect = QRect(row.mapToGlobal(QPoint(0, 0)), row.size())
frame = w.frameGeometry()
assert frame.contains(pop_rect), "弹窗必须完整落在软件内"
assert not pop_rect.intersects(row_rect), \
    "窄窗口默认位置不得压住右键点开的那一行"
assert pop_rect.bottom() > frame.bottom() - pop.height() - 24, \
    "窄窗口应停靠在窗口底部（不挡上方行 / 页签）"
assert pop_rect.right() > frame.right() - pop.width() - 24, "停靠右下角"
pop.closed.emit()
pump(0.05)
assert not pop.isVisible()

# 宽窗口：行右侧有整块空位 -> 贴着那一行
w.resize(1280, 800)
pump(0.2)
w._show_info_popup(sym)
pump(0.05)
assert pop.isVisible()
pop_tl = pop.mapToGlobal(QPoint(0, 0))
pop_rect = QRect(pop_tl, pop.size())
assert pop_rect.left() >= row_rect.right() - 2, \
    f"宽窗口应放行右侧整块空位: {pop_rect} vs 行 {row_rect}"
assert not pop_rect.intersects(row_rect), "不得压住行本身"
pop.closed.emit()
pump(0.05)
print("2. 资料弹窗默认不遮挡（窄窗右下停靠 / 宽窗行侧空位）OK")

# ============ 3. 按住标题栏拖动弹窗 ============
w._show_info_popup(sym)
pump(0.05)
assert pop.isVisible()
head = pop.head
start_local = QPointF(20, 15)
start_global = QPointF(head.mapToGlobal(QPoint(20, 15)))
target_global = QPointF(frame.left() + 60, frame.top() + 80)


def send_mouse(ev_type, local, glob, buttons):
    ev = QMouseEvent(ev_type, QPointF(local), QPointF(glob),
                     Qt.LeftButton, buttons, Qt.NoModifier)
    QCoreApplication.sendEvent(head, ev)


send_mouse(QEvent.MouseButtonPress, start_local, start_global,
           Qt.LeftButton)
send_mouse(QEvent.MouseMove, start_local, target_global, Qt.LeftButton)
send_mouse(QEvent.MouseButtonRelease, start_local, target_global,
           Qt.NoButton)
pump(0.05)
moved_tl = pop.mapToGlobal(QPoint(0, 0))
moved_rect = QRect(moved_tl, pop.size())
# 期望落点 = 目标点 - 按下时在标题栏内的偏移(20,15)
assert abs(moved_tl.x() - (int(target_global.x()) - 20)) <= 6 and \
    abs(moved_tl.y() - (int(target_global.y()) - 15)) <= 6, \
    f"拖动应基本贴合目标位置: {moved_tl} vs {target_global}"
assert frame.adjusted(2, 2, -2, -2).contains(moved_rect), \
    "拖动后弹窗必须仍完整落在软件内"
assert pop._last_pos is not None, "拖动后应记住落点"
print("3a. 标题栏拖动弹窗 + 钳制在软件内 OK")

# 再次右键查看：沿用记住的位置
pop.closed.emit()
pump(0.05)
assert not pop.isVisible()
w._show_info_popup(sym)
pump(0.05)
again_tl = pop.mapToGlobal(QPoint(0, 0))
assert abs(again_tl.x() - moved_tl.x()) <= 2 and \
    abs(again_tl.y() - moved_tl.y()) <= 2, \
    "同一会话内应沿用用户拖动后的位置"
pop.closed.emit()
pump(0.05)
print("3b. 记住拖动后的位置 OK")

# ============ 4. 关闭按钮加大 ============
assert pop.btn_close.width() >= 40 and pop.btn_close.height() >= 32, \
    f"资料卡关闭按钮热区应 >=40x32，实际 {pop.btn_close.width()}x{pop.btn_close.height()}"
probe = popup_close_button()
assert probe.width() >= 40 and probe.height() >= 32
print("4. 关闭按钮热区加大（>=40x32）OK")

# ============ 收尾 ============
try:
    w.live.shutdown()
except Exception:
    pass
w.scheduler.stop()
w._leave_chart()
w.close()
pump(0.05)
from qt_exit import finish       # 跳过 offscreen 的 Qt 卸载竞态
print("\nv24 全部回归测试通过 ✅")
finish()
