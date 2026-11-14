# -*- coding: utf-8 -*-
"""v23 回归：资料弹窗改为右键菜单选中才弹出 / 修复设置页点「行情」无法跳回。

覆盖：
1. 悬停不再自动弹出资料卡；右键菜单「ℹ 查看资料」才弹出、带 ✕ 可关闭；
2. 弹窗弹出后：滚动列表、切市场、进图表、进设置都会自动收起；
3. 设置页里点底栏「行情」能跳回（从列表页进入设置 / 从图表页进入设置两条路径）；
4. 设置页里重复点「设置」不重置回退目标。

全部离线（临时 APPDATA + offscreen + CT_OFFLINE）。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v23_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CT_OFFLINE"] = "1"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from core.config import Config
from data.universe import market_of
from ui.main_window import MainWindow

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

# ============ 1. 右键菜单选中才弹出资料卡 ============
sym = next(iter(w.rows))
row = w.rows[sym]
assert row.isVisible(), "测试行应可见"
# 1a. 悬停不自动弹出
row.hovered.emit(sym)
pump(0.25)
assert not w.info_panel.isVisible(), "悬停不得自动弹出资料卡"
# 1b. 右键菜单动作 -> 弹出
w._show_info_popup(sym)
pump(0.05)
assert w.info_panel.isVisible(), "右键「查看资料」后应弹出资料卡"
assert w.info_panel._symbol == sym, (w.info_panel._symbol, sym)
tl = w.info_panel.mapToGlobal(QPoint(0, 0))
frame = w.frameGeometry()
assert frame.left() - 4 <= tl.x() <= frame.right(), \
    f"浮层跑出软件左右: {tl.x()} / {frame}"
assert frame.top() - 4 <= tl.y() <= frame.bottom(), \
    f"浮层跑出软件上下: {tl.y()} / {frame}"
# 1c. 有关闭按钮，点 ✕ 收起
assert not w.info_panel.btn_close.isHidden(), "资料卡应带 ✕ 关闭按钮"
w.info_panel.closed.emit()
assert not w.info_panel.isVisible(), "点 ✕ 后应收起"
print("1. 悬停不弹 / 右键选中才弹 / ✕ 可关闭 OK")

# ============ 2. 弹窗自动收起时机 ============
# 2a. 滚动列表 -> 收起
w._show_info_popup(sym)
pump(0.05)
assert w.info_panel.isVisible()
sb = w.pages[w._current_market()]["scroll"].verticalScrollBar()
sb.valueChanged.emit(3)            # 直接发信号，避免无滚动范围时测不到
assert not w.info_panel.isVisible(), "滚动列表后应自动收起资料卡"
# 2b. 切市场 -> 收起
w._show_info_popup(sym)
pump(0.05)
assert w.info_panel.isVisible()
other = next((k for k in w.pages if k != w._current_market()), None)
if other:
    w._switch_market(other)
    pump(0.05)
    assert not w.info_panel.isVisible(), "切市场后应自动收起资料卡"
    w._switch_market(market_of(sym))
    pump(0.05)
# 2c. 进设置 -> 收起
w._show_info_popup(sym)
pump(0.05)
assert w.info_panel.isVisible()
w.open_settings()
pump(0.05)
assert not w.info_panel.isVisible(), "进设置页应自动收起资料卡"
print("2. 滚动 / 切市场 / 进设置自动收起资料卡 OK")

# ============ 3. 设置页里点「行情」能跳回 ============
# 3a. 当前在设置页（从列表页进入）：点行情 -> 回列表页
assert w.stack.currentWidget() is w.settings_page
w._on_bottom_nav("list")
pump(0.05)
assert w.stack.currentWidget() is not w.settings_page, \
    "设置页里点「行情」必须跳回列表页（v23 修复的 bug）"
assert w.stack.currentWidget() is \
    w.pages[market_of(sym)]["scroll"] or \
    w.stack.currentWidget() is w.pages[w._current_market()]["scroll"], \
    f"应回到行情列表页，实际在 {w.stack.currentWidget()}"
assert w.bottom_nav.buttons["list"].isChecked(), "底栏应高亮「行情」"

# 3b. 从图表页进设置：点行情 -> 回图表页（图表也归「行情」）
w._open_chart(sym)
pump(0.2)
assert w.stack.currentWidget() is w.chart_view
w.open_settings()
pump(0.05)
assert w.stack.currentWidget() is w.settings_page
w._on_bottom_nav("list")
pump(0.05)
assert w.stack.currentWidget() is w.chart_view, \
    "从图表进设置后点「行情」应回到图表页"
assert w.bottom_nav.buttons["chart"].isChecked()

# 3c. 设置页里重复点「设置」不重置回退目标
w.open_settings()
pump(0.05)
assert w.stack.currentWidget() is w.settings_page
w.open_settings()                   # 重复点击应被忽略
assert w._settings_return is w.chart_view, \
    "设置页里重复点「设置」不得把回退目标改成设置页自身"
w._close_settings_page()
pump(0.05)
assert w.stack.currentWidget() is w.chart_view
print("3. 设置页点「行情」可跳回（列表 / 图表两条路径）OK")

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
print("\nv23 全部回归测试通过 ✅")
finish()
