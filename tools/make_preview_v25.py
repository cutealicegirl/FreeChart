# -*- coding: utf-8 -*-
"""v25 预览图：工具面板独立图层 / 资料弹窗不遮挡且可拖动 / 关闭按钮加大。

运行：QT_QPA_PLATFORM=offscreen python tools/make_preview_v25.py
输出到 preview/（97–100）。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_prev25_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CT_OFFLINE"] = "1"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tests"))

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QFontDatabase, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication

from core.config import Config
from data.klines import Candle
from ui import theme
from ui.main_window import MainWindow

OUT = os.path.join(_ROOT, "preview")
app = QApplication([])
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


def fake_candles(n=400):
    return [Candle(ts=1600000000 + i * 86400, time_label=str(i),
                   open=100 + i % 9, high=108 + i % 9, low=95 + i % 7,
                   close=102 + i % 8, volume=1200 + i)
            for i in range(n)]


cfg = Config()
cfg.set("mascot_enabled", False)
cfg.set("price_badge", False)
w = MainWindow(cfg)
w.resize(1080, 820)
w.prepare_show()
w.show()
pump(0.8)

# ---- 1. 图表页：工具面板悬浮在 K 线上方（独立图层） ----
sym = next(iter(w.rows))
w._open_chart(sym)
pump(0.4)
cv = w.chart_view
cv._load = lambda *a, **k: cv.chart.set_data(fake_candles())
cv._load()
pump(0.2)
chart_frame = cv.chart.parentWidget()
geo_collapsed = QRect(chart_frame.geometry())
cv._tools_hovered = True
cv._apply_tools_visible()
pump(0.15)
assert cv.tools_panel.isVisible(), "悬停应展开工具面板"
assert chart_frame.geometry() == geo_collapsed, "展开不得挤压 K 线"
save(w, "97_tools_overlay_expanded.png")
cv._tools_hovered = False
cv._apply_tools_visible()
pump(0.1)
assert not cv.tools_panel.isVisible()
save(w, "98_tools_overlay_collapsed.png")

# ---- 2. 窄窗口：资料弹窗默认停靠右下角，不压右键点开的行 ----
w._leave_chart()
pump(0.2)
w.resize(480, 800)
pump(0.4)
row = w.rows[sym]
w._show_info_popup(sym)
pump(0.25)
pop = w.info_panel
assert pop.isVisible()
pop_rect = QRect(pop.mapToGlobal(QPoint(0, 0)), pop.size())
row_rect = QRect(row.mapToGlobal(QPoint(0, 0)), row.size())
assert not pop_rect.intersects(row_rect), "默认位置不得压住点开的行"
save(w, "99_info_popup_docked.png", extras=(pop,))

# ---- 3. 拖到别处：按住标题栏移动 ----
head = pop.head
frame = w.frameGeometry()
press_g = QPointF(head.mapToGlobal(QPoint(24, 16)))
target_g = QPointF(frame.left() + 40, frame.top() + 150)


def send_mouse(t, local, glob, buttons):
    QCoreApplication.sendEvent(
        head, QMouseEvent(t, QPointF(local), QPointF(glob),
                          Qt.LeftButton, buttons, Qt.NoModifier))


send_mouse(QEvent.MouseButtonPress, QPointF(24, 16), press_g, Qt.LeftButton)
send_mouse(QEvent.MouseMove, QPointF(24, 16), target_g, Qt.LeftButton)
send_mouse(QEvent.MouseButtonRelease, QPointF(24, 16), target_g, Qt.NoButton)
pump(0.1)
moved = QRect(pop.mapToGlobal(QPoint(0, 0)), pop.size())
assert frame.contains(moved), "拖动后必须仍在软件内"
assert abs(moved.left() - (int(target_g.x()) - 24)) <= 8
save(w, "100_info_popup_dragged.png", extras=(pop,))

print("preview done")
try:
    w.live.shutdown()
except Exception:
    pass
w.scheduler.stop()
w._leave_chart()
w.close()
pump(0.1)
from qt_exit import finish
finish()
