# -*- coding: utf-8 -*-
"""v22 预览图：工具条悬停自动展开 / 收纳 + 看板娘遮挡隐藏后重现说话。

运行：QT_QPA_PLATFORM=offscreen python tools/make_preview_v22.py
输出到 preview/（85 / 86 / 87）。
"""
import json
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_prev22_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.makedirs(os.path.join(_TMP, "FreeChart"), exist_ok=True)
# 故意留下旧版「固定展开」脏配置，验证新版启动会纠正
with open(os.path.join(_TMP, "FreeChart", "config.json"),
          "w", encoding="utf-8") as f:
    json.dump({"chart_tools_open": True, "mascot_enabled": True,
               "mascot_speech": True, "mascot_bubble_style": "candy",
               "price_badge": False}, f)

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from core.config import Config
from ui.main_window import MainWindow

OUT = os.path.join(_ROOT, "preview")
app = QApplication([])


def pump(sec=0.4):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def save(widget, name, mascot=None, bubble=None):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    pm = widget.grab()
    pt = QPainter(pm)
    pt.setRenderHint(QPainter.SmoothPixmapTransform, True)
    if mascot is not None and mascot.isVisible():
        pos = widget.mapFromGlobal(mascot.frameGeometry().topLeft())
        scaled = mascot._current_pixmap().scaled(
            mascot.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pt.drawPixmap(pos, scaled)
    if bubble is not None and bubble.isVisible():
        pos = widget.mapFromGlobal(bubble.frameGeometry().topLeft())
        pt.drawPixmap(pos, bubble.grab())
    pt.end()
    pm.save(path)
    print("saved", path)


w = MainWindow(Config())
w.resize(1080, 820)
w.prepare_show()
pump(1.0)
cv = w.chart_view
assert cv._tools_pinned is False, "旧脏配置不该卡住工具条"

sym = next(iter(w.rows))
w._open_chart(sym)
pump(1.2)

m = w.mascot
m._scale = 40
m._apply_geometry()
pump(0.2)
rect = cv.candles_global_rect().toRect()
assert not rect.isEmpty(), "K 线区域应已渲染"
host = w.frameGeometry()


def place_outside():
    geo = m.frameGeometry()
    cands = [(rect.right() + 8, rect.bottom() - geo.height()),
             (rect.left() + 40, rect.top() - geo.height() - 4),
             (rect.left() + 40, rect.bottom() + 6)]
    for x, y in cands:
        x = min(max(x, host.left() + 2), host.right() - geo.width() - 2)
        y = min(max(y, host.top() + 2), host.bottom() - geo.height() - 2)
        cand = geo.translated(x - geo.left(), y - geo.top())
        if not cand.intersects(rect):
            m.move(x, y)
            return True
    return False


assert place_outside(), "预览里应能找到不遮挡的位置"
pump(1.0)

# ---- 1. 收纳状态 ----
QTest.mouseMove(w, QPoint(6, w.height() - 6))
pump(0.6)
assert not cv.tools_panel.isVisible()
save(w, "85_tools_collapsed.png", mascot=m)

# ---- 2. 鼠标扫过自动展开 ----
head = cv.tools_head
QTest.mouseMove(w, head.mapTo(w, QPoint(head.width() // 2,
                                       head.height() // 2)))
pump(0.25)
assert cv.tools_panel.isVisible(), "悬停应展开"
save(w, "86_tools_hover_expanded.png", mascot=m)

# ---- 3. 移开自动收纳 ----
QTest.mouseMove(w, QPoint(6, w.height() - 6))
pump(0.6)
assert not cv.tools_panel.isVisible(), "离开应收纳"

# ---- 4. 挡住 K 线隐藏 → 移开重现并说话 ----
m.move(rect.center().x() - m.width() // 2, rect.top() + 10)
pump(1.2)
assert not m.isVisible(), "压住 K 线应完全消失"
assert place_outside()
pump(1.4)
assert m.isVisible(), "离开重叠区应重现"
print("reappear bubble:", m._bubble._text)
assert m._bubble.isVisible(), "重现后应有对话"
save(w, "87_mascot_return_bubble.png", mascot=m, bubble=m._bubble)

# ---- 收尾 ----
for hw in (cv.tools_head, cv.tools_panel):
    hw.removeEventFilter(cv)
cv._tools_hover_timer.stop()
cv._tools_leave_timer.stop()
w._mascot_timer.stop()
m._reappear_timer.stop()
m._bubble.dismiss()
m._bubble._timer.stop()
if m._fade is not None:
    m._fade.stop()
    m._fade = None
m.hide()
try:
    w.live.shutdown()
except Exception:
    pass
w.scheduler.stop()
w.close()
pump(0.1)
print("\nv22 预览图生成完毕 ✅")
sys.stdout.flush()
os._exit(0)
