# -*- coding: utf-8 -*-
"""v23 预览图：悬停资料弹窗 / 独立设置页 / 详情抽屉项目介绍 / 缩放锚点。

运行：QT_QPA_PLATFORM=offscreen python tools/make_preview_v23.py
输出到 preview/（88–92）。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_prev23_")
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

# ---- 1. 行情页：右键某行 -> 「查看资料」在行旁浮出资料弹窗（v24 起行为） ----
sym = next(iter(w.rows))
row = w.rows[sym]
w._show_info_popup(sym)
pump(0.25)
assert w.info_panel.isVisible(), "资料弹窗应可见"
save(w, "88_hover_info_popup.png")
save(w.info_panel, "89_about_card.png")

# ---- 2. 设置：主窗口里的独立界面（不是弹窗）----
w.info_panel.hide_popup()
pump(0.2)
assert not w.info_panel.isVisible()
w.open_settings()
pump(0.25)
assert w.stack.currentWidget() is w.settings_page
save(w, "90_settings_page.png")
w._close_settings_page()
pump(0.2)

# ---- 3. 图表页：详情抽屉含项目 / 创始人介绍 ----
w._open_chart(sym)
pump(0.6)
# 直接 show（主窗口的 _open_detail 用 exec() 会阻塞离屏脚本）
from ui.detail_dialog import SymbolDetailDialog
dlg = SymbolDetailDialog(sym, "", None, w)
dlg.move(w.mapToGlobal(QPoint(560, 60)))
dlg.show()
pump(0.3)
assert dlg.isVisible()
save(w, "91_detail_about.png", extras=(dlg,))
dlg.close()
pump(0.1)

# ---- 4. 缩放锚点：缩小后 K 线仍停在原位置，不被拉到最右侧 ----
chart = w.chart_view.chart
chart.set_data([
    __import__("data.klines", fromlist=["Candle"]).Candle(
        ts=1600000000 + i * 86400, time_label=str(i),
        open=100 + (i * 7) % 31, high=105 + (i * 7) % 31,
        low=95 + (i * 5) % 27, close=101 + (i * 7) % 31,
        volume=1000 + i) for i in range(240)])
chart._view_count = 90.0
chart._pan = 18.0
chart.history_exhausted = True
from PySide6.QtGui import QWheelEvent
from PySide6.QtCore import QPointF
for _ in range(4):
    ev = QWheelEvent(QPointF(420, 260), QPointF(420, 260),
                     QPoint(0, 0), QPoint(0, -120), Qt.NoButton,
                     Qt.NoModifier, Qt.ScrollUpdate, False)
    chart.wheelEvent(ev)
pump(0.2)
save(w, "92_zoom_anchor.png")

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
