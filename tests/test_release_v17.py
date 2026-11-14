# -*- coding: utf-8 -*-
"""v17 回归：手机化布局 + 排序不再整窗重排 + 托盘图标跟随程序图标。

背景：
1. 点一次排序按钮原来会重排四个市场的页面（美股「全部」500 行），再立刻触发
   一次网络刷新，回来的数据又排一遍 —— 整窗冻结、列表闪两轮、提示框疯弹。
2. 托盘图标原来是自绘的价格方块，和桌面/任务栏图标不是一套。
3. 启动瞬间会闪出一个 170x63 的空壳小窗（打包版时序差异）。

全部离线（临时 APPDATA）。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v17_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QFrame

from core.config import Config
from data.api_base import Ticker
from ui.icons import tray_app_icon
from ui.main_window import MainWindow
from ui.settings_dialog import SettingsDialog

app = QApplication([])


def pump(rounds=20, delay=0.005):
    for _ in range(rounds):
        app.processEvents()
        time.sleep(delay)


# ================= 1. 启动窗口不上屏，prepare_show 后才显示 =================
cfg = Config()
w = MainWindow(cfg)
w.scheduler.stop()
w.scheduler.refresh_now = lambda: None
assert w.testAttribute(Qt.WA_DontShowOnScreen), \
    "构造期应压住窗口，避免启动闪空壳小窗"
w.resize(460, 880)
w.show()
pump()
assert not w.isVisible() or w.testAttribute(Qt.WA_DontShowOnScreen)
w.prepare_show()
pump(5)
assert not w.testAttribute(Qt.WA_DontShowOnScreen), "prepare_show 应解除压制"
assert w.isVisible(), "prepare_show 后窗口应可见"
print("1. 启动不闪空壳（WA_DontShowOnScreen）+ prepare_show 上屏 OK")

# ================= 2. 底部导航 =================
assert hasattr(w, "bottom_nav"), "应有底部导航栏"
assert set(w.bottom_nav.buttons) == {"list", "chart", "settings"}, \
    "阶段 5：底栏为行情 / 图表 / 设置三个独立选项卡"
assert w.bottom_nav.height() >= 56, f"底栏高度应触摸友好: {w.bottom_nav.height()}"
assert w.bottom_nav.buttons["list"].isChecked(), "默认应停在「行情」"
# 点一行行情直接进图表，而不是靠底栏按钮
sym = next(iter(w.rows))
w._open_chart(sym)
pump(5)
assert w.stack.currentIndex() == len(w.pages), "点品种应进入图表页"
assert w.bottom_nav.buttons["chart"].isChecked(), \
    "图表页应高亮独立的「图表」选项卡"
assert w.chart_view.btn_detail.text().endswith("详情"), "图表页应有详情按钮"
w._on_bottom_nav("list")
pump(5)
assert w.stack.currentIndex() < len(w.pages), "「行情」应回到列表页"
print("2. 底部导航（行情 / 图表 / 设置）+ 点品种进图表 OK")

# ================= 3. 排序只重排当前页，不动其它市场 =================
calls = []
orig = w._relayout_page
w._relayout_page = lambda key: (calls.append(key), orig(key))[1]

tick = {}
for i, s in enumerate(list(w.rows)):
    tick[s] = Ticker(s, s, 100.0 + i, float(i % 17) - 8.0, 110, 90, 1e8)
w._on_fetched(tick, "test", time.time())
pump(3)

calls.clear()
w.combo_sort.click()
pump(3)
assert len(calls) == 1, f"点排序只该重排当前页一次，实际 {calls}"
assert calls[0] == w._current_market(), f"重排的应只是当前市场: {calls}"
print(f"3. 排序只重排当前页 1 次（{calls[0]}），不再整窗重排 OK")

# ================= 4. 排序结果正确 =================
def order():
    lay = w.pages[w._current_market()]["layout"]
    out = []
    for i in range(lay.count()):
        it = lay.itemAt(i)
        wd = it.widget() if it else None
        if wd is not None and hasattr(wd, "symbol"):
            out.append(wd.symbol)
    return out

mode = w.combo_sort.currentData()
syms = order()
vals = [tick[s].change_pct for s in syms if s in tick]
if mode == "change_desc":
    assert all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1)), (mode, vals)
elif mode == "change_asc":
    assert all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1)), (mode, vals)
print(f"4. 排序结果正确（{mode}，{len(syms)} 行）OK")

# ================= 5. 托盘图标跟随程序图标 =================
assert (cfg.get("tray_icon_style") or "app") == "app", "默认应跟随程序图标"
up, down = tray_app_icon(2.5), tray_app_icon(-2.5)
assert isinstance(up, QIcon) and not up.isNull()
assert isinstance(down, QIcon) and not down.isNull()
assert up.pixmap(64, 64).toImage() != down.pixmap(64, 64).toImage(), \
    "涨跌应画出不同角标"
print("5. 托盘图标跟随程序图标（涨跌角标）OK")

# ================= 6. 设置页改为卡片式 sheet =================
dlg = SettingsDialog(w, w)
pump(3)
cards = dlg.findChildren(QFrame, "settingsCard")
# v30 起按需求删除了设置页「自选列表」整块，现在是 2 张卡
# （常规设置 + 图表指标）。断言对齐当前产品行为，不是放宽检查。
assert len(cards) >= 2, f"设置页应分卡片，实际 {len(cards)} 张"
assert dlg.findChild(QFrame, "settingsFooter") is not None, "应有底部固定按钮栏"
assert dlg.width() <= w.width() + 8 and dlg.width() >= 360, \
    f"设置页宽度应贴合主窗口: {dlg.width()} vs {w.width()}"
assert "tray_icon_style" in dlg.get_settings(), "设置应回传托盘图标样式"
dlg.close()
dlg.deleteLater()
pump(5)
print(f"6. 设置页卡片化（{len(cards)} 张卡片 + 底栏）OK")

# 图表页会启动秒级实时价线程，测试结束前收掉，否则进程退出码会变 127
try:
    w.live.shutdown()
except Exception:
    pass
w.scheduler.stop()
w.close()
pump(5)
from qt_exit import finish           # 跳过 offscreen 的 Qt 卸载竞态
print("\nv17 全部回归测试通过 ✅")
finish()
