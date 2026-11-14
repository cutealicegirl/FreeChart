# -*- coding: utf-8 -*-
"""v10 离线回归：任务栏价格条避让其它程序小工具 + 手动微调。

用户反馈：价格条和别的程序（内存/网速）小工具显示的内容重叠了。
现在的规则：
1. 扫描贴在任务栏区域的第三方顶层小窗，把自己的小工具摆到它们左侧；
2. 通知区与这些窗口谁更靠左就贴在谁左边；
3. 右键「位置微调」可手动左/右移并持久化；
4. 自己的窗口标题带标记，多实例时互不当成「别人的小工具」。
"""
import inspect
import os
import sys
import tempfile
from unittest.mock import patch

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_v10_")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import QApplication

app = QApplication([])

import core.taskbar as tb
import ui.price_badge as pb_mod
from core.config import Config
from ui.price_badge import PriceBadge

screen = app.primaryScreen()
full = screen.geometry()

# ===== 1. 避让扫描接口存在且可安全调用 =====
assert callable(tb.busy_widget_lefts)
lefts = tb.busy_widget_lefts(screen, exclude=())
assert isinstance(lefts, list) and all(isinstance(v, int) for v in lefts)
assert lefts == sorted(lefts), "返回值应按左边界升序"
src = inspect.getsource(tb.busy_widget_lefts)
assert "EnumWindows" in src and "IsWindowVisible" in src and "_SHELL_CLASSES" in src
assert "BADGE_TITLE" in src, "多实例的同类价格条要排除"
print(f"1. 任务栏小工具扫描 OK（当前检出 {len(lefts)} 个：{lefts[:4]}）")

# ===== 2. 通知区 / 其它小工具，谁更靠左就贴在谁左边 =====
nl = full.right() - 320
with patch.object(tb, "notify_left", return_value=nl), \
        patch.object(tb, "busy_widget_lefts", return_value=[]):
    x0, y0, w0, h0 = tb.dock_geometry(screen, 158, 46)
assert x0 == nl - w0 - tb._GAP, (x0, nl, w0)

with patch.object(tb, "notify_left", return_value=nl), \
        patch.object(tb, "busy_widget_lefts", return_value=[nl - 120, nl - 200]):
    x1, _, w1, _ = tb.dock_geometry(screen, 158, 46)
assert x1 == (nl - 200) - w1 - tb._GAP, (x1, nl)
assert x1 + w1 + tb._GAP <= nl - 200, "必须完全避开最左的那个小工具"
print(f"2. 自动避让 OK（无小工具 x={x0}，有小工具 x={x1}）")

# ===== 3. 手动微调：左移 / 右移 / 复位，并持久化 =====
with patch.object(tb, "notify_left", return_value=nl), \
        patch.object(tb, "busy_widget_lefts", return_value=[]):
    xs, _, ws, _ = tb.dock_geometry(screen, 158, 46, shift=48)
assert xs == x0 - 48, "shift 正数应左移"
cfg = Config()
assert cfg.get("price_badge_shift") == 0, "默认无微调"

badge = PriceBadge(cfg)
assert badge.windowTitle() == tb.BADGE_TITLE, "价格条要带自我标识标题"
captured = {}


def fake_dock(screen_, width, max_height=46, exclude=(), shift=0):
    captured["exclude"] = exclude
    captured["shift"] = shift
    return 40, 40, width, 38


with patch.object(pb_mod, "dock_geometry", side_effect=fake_dock):
    badge.dock()
    assert captured["shift"] == 0
    assert isinstance(captured["exclude"], tuple) and captured["exclude"], \
        "必须传自己的窗口句柄给避让扫描"
    badge._nudge(16)
    assert captured["shift"] == 16 and cfg.get("price_badge_shift") == 16
    badge._nudge(-32)
    assert captured["shift"] == -16 and cfg.get("price_badge_shift") == -16
    badge._reset_shift()
    assert captured["shift"] == 0 and cfg.get("price_badge_shift") == 0
menu_src = inspect.getsource(PriceBadge.contextMenuEvent)
assert "位置微调" in menu_src and "_nudge" in menu_src
badge.hide()
print("3. 手动微调（左移/右移/复位）与配置持久化 OK")

# ===== 4. 源码层面确认价格条不再硬定位到通知区左侧 =====
dock_src = inspect.getsource(PriceBadge.dock)
assert "exclude" in dock_src and "shift" in dock_src
assert "busy_widget_lefts" in inspect.getsource(tb.dock_geometry)
print("4. 定位链路（dock → dock_geometry → busy_widget_lefts）OK")

print("\nv10 全部回归测试通过 ✅")
