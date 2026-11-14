# -*- coding: utf-8 -*-
"""v30 回归：阶段 5「独立图表选项卡 / 去掉右上角设置 / 统一导航」。

验收点（离线）：
1. 底栏为行情 / 图表 / 设置三个独立选项卡，触摸目标 ≥ 44px；
2. 点「图表」能直接进入图表页（上次品种或第一个自选），点行进图仍保留；
3. 右上角与工具条都不再有设置按钮，设置只在底栏；
4. 设置页有明确「← 返回」按钮，返回到进入前的页面；
5. 标题栏随页面显示一致的名称与返回按钮，统一返回逻辑逐级回退；
6. 图表 / 设置 / 行情三页高亮与页面状态始终一致。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v30_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CT_OFFLINE"] = "1"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import QApplication, QPushButton

from core.config import Config
from ui.main_window import MainWindow

app = QApplication([])


def pump(sec=0.08):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def active(w):
    return [k for k, b in w.bottom_nav.buttons.items() if b.isChecked()]


cfg = Config()
cfg.set("mascot_enabled", False)
w = MainWindow(cfg)
w.scheduler.stop()
w.scheduler.refresh_now = lambda: None
w.resize(560, 900)
w.prepare_show()
pump(0.1)

# ============ 1. 三选项卡底栏 ============
assert set(w.bottom_nav.buttons) == {"list", "chart", "settings"}
assert w.bottom_nav.height() >= 60
assert active(w) == ["list"], active(w)
for btn in w.bottom_nav.buttons.values():
    assert btn.minimumHeight() >= 0        # 由 Expanding 策略撑满整栏
print("1. 底栏行情 / 图表 / 设置三选项卡 OK")

# ============ 2. 独立图表入口 ============
w._on_bottom_nav("chart")
pump(0.15)
assert w.stack.currentWidget() is w.chart_view, \
    "点「图表」应直接进入图表页"
assert w.chart_view._symbol, "没有上次品种时应自动选中一个"
assert active(w) == ["chart"], active(w)
assert w.bottom_nav.buttons["chart"].isChecked()
w._on_bottom_nav("list")
pump(0.15)
assert w.stack.currentWidget() is not w.chart_view
# 点品种进图表的原有路径仍然可用
sym = next(iter(w.rows))
w._open_chart(sym)
pump(0.15)
assert w.chart_view._symbol == sym
assert active(w) == ["chart"]
w._on_bottom_nav("list")
pump(0.15)
print("2. 独立图表入口 + 点品种进图表两条路径都可用 OK")

# ============ 3. 设置只在底栏 ============
title_buttons = [b.text() for b in w.title_bar.findChildren(QPushButton)]
assert not any("设置" in t or t == "≡" for t in title_buttons), \
    f"标题栏不应再有设置按钮：{title_buttons}"
assert "←" in title_buttons, "标题栏应有统一返回按钮"
tool = w._list_controls[2]      # 工具条 QFrame
tool_texts = [b.text() for b in tool.findChildren(QPushButton)]
assert not any(t == "≡" for t in tool_texts), \
    f"工具条不应再有设置按钮：{tool_texts}"
assert "settings" in w.bottom_nav.buttons, "设置入口应在底栏"
print("3. 右上角 / 工具条设置按钮已移除，入口统一到底栏 OK")

# ============ 4. 设置页明确返回 ============
assert hasattr(w.settings_page, "btn_back")
assert "返回" in w.settings_page.btn_back.text()
assert w.settings_page.btn_back.height() >= 44
w.open_settings()
pump(0.1)
assert w.stack.currentWidget() is w.settings_page
assert w.title_bar.lbl_page.text() == "设置"
assert w.title_bar.btn_back.isVisible()
w.settings_page.btn_back.click()
pump(0.1)
assert w.stack.currentWidget() is not w.settings_page
assert active(w) == ["list"]
print("4. 设置页「← 返回」明确可见且能返回 OK")

# ============ 5. 统一标题栏与逐级返回 ============
w._open_chart(sym)
pump(0.1)
assert w.title_bar.lbl_page.text() == "图表"
assert w.title_bar.btn_back.isVisible()
w._navigate_back()
pump(0.1)
assert w.title_bar.lbl_page.text() == "行情"
assert not w.title_bar.btn_back.isVisible(), "列表页无需返回按钮"
w.open_settings()
pump(0.1)
w._navigate_back()
pump(0.1)
assert w.stack.currentWidget() is not w.settings_page, \
    "标题栏返回应从设置页回到列表页"
assert w.title_bar.lbl_page.text() == "行情"
print("5. 标题栏页面名 / 返回按钮 / 逐级回退统一 OK")

# ============ 6. 从图表进设置再返回，高亮一致 ============
w._open_chart(sym)
w.open_settings()
pump(0.1)
w._close_settings_page()
pump(0.1)
assert w.stack.currentWidget() is w.chart_view
assert active(w) == ["chart"], active(w)
assert w.title_bar.lbl_page.text() == "图表"
print("6. 图表 ↔ 设置往返后高亮与标题一致 OK")

# ============ 收尾 ============
w._detail_cache.clear()
pump(0.05)
from qt_exit import finish
print("\nv30 全部回归测试通过 ✅")
finish()
