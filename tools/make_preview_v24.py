# -*- coding: utf-8 -*-
"""v24 预览图：右键菜单弹出的资料卡 / 设置页点「行情」跳回。

运行：QT_QPA_PLATFORM=offscreen python tools/make_preview_v24.py
输出到 preview/（93–95）。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_prev24_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CT_OFFLINE"] = "1"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tests"))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFontDatabase, QPainter
from PySide6.QtWidgets import QApplication

from core.config import Config
from ui import theme
from ui.main_window import MainWindow

OUT = os.path.join(_ROOT, "preview")
app = QApplication([])
# offscreen 下注册系统中文字体，避免预览里中文变成方块
for _p in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc",
           "C:/Windows/Fonts/simsun.ttc"):
    if os.path.isfile(_p):
        QFontDatabase.addApplicationFont(_p)
theme.install_fonts()


def pump(sec=0.4):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def save(widget, name, extras=()):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    pm = widget.grab()
    pt = QPainter(pm)
    pt.setRenderHint(QPainter.SmoothPixmapTransform, True)
    for other in extras:
        if other is not None and other.isVisible():
            pos = widget.mapFromGlobal(other.frameGeometry().topLeft())
            pt.drawPixmap(pos, other.grab())
    pt.end()
    pm.save(path)
    print("saved", path)


cfg = Config()
cfg.set("mascot_enabled", False)
cfg.set("price_badge", False)
w = MainWindow(cfg)
w.resize(1080, 820)
w.prepare_show()
w.show()
pump(0.8)

# ---- 1. 行情页：右键某行 -> 「查看资料」弹出的资料卡 ----
sym = next(iter(w.rows))
row = w.rows[sym]
row.hovered.emit(sym)              # 悬停不再自动弹出
pump(0.25)
assert not w.info_panel.isVisible(), "悬停不得自动弹出"
w._show_info_popup(sym)            # 等价于右键菜单选「ℹ 查看资料」
pump(0.25)
assert w.info_panel.isVisible(), "右键选中后资料卡应弹出"
save(w, "93_context_info_popup.png")
save(w.info_panel, "94_info_popup_card.png")
assert not w.info_panel.btn_close.isHidden()

# ---- 2. 设置页点底栏「行情」跳回列表页 ----
w.info_panel.hide_popup()
w.open_settings()
pump(0.25)
assert w.stack.currentWidget() is w.settings_page
save(w, "95_settings_before_nav.png")
w._on_bottom_nav("list")           # 模拟点底栏「行情」
pump(0.25)
assert w.stack.currentWidget() is not w.settings_page, \
    "设置页里点「行情」必须跳回（v24 修复的 bug）"
assert w.bottom_nav.buttons["list"].isChecked()
save(w, "96_nav_back_to_list.png")

print("preview done")
try:
    w.live.shutdown()
except Exception:
    pass
w.scheduler.stop()
w.close()
pump(0.1)
from qt_exit import finish
finish()
