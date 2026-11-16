# -*- coding: utf-8 -*-
"""窗口拉伸 / 最大化回归：窄窗口下按钮不得消失，边缘热区可用。"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("CT_OFFLINE", "1")
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_window_")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from core.config import Config
from ui.main_window import MainWindow

PASS = 0
FAIL = 0


def ok(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("PASS", name)
    else:
        FAIL += 1
        print("FAIL", name, extra)


w = MainWindow(Config())
w.show()
app.processEvents()
tb = w.title_bar

w.resize(380, 560)
app.processEvents()
ok("窄窗口仍显示最大化按钮", tb.btn_max.isVisible())
ok("窄窗口仍显示全屏按钮", tb.btn_full.isVisible())
ok("窄窗口压缩标题栏按钮", tb.btn_max.width() <= 34,
   f"width={tb.btn_max.width()}")

w.toggle_maximize()
app.processEvents()
ok("最大化生效", w.isMaximized())
w.toggle_maximize()
app.processEvents()
ok("最大化可还原", not w.isMaximized())

w.toggle_fullscreen()
app.processEvents()
ok("全屏生效", w.isFullScreen())
w.toggle_fullscreen()
app.processEvents()
ok("全屏可退出", not w.isFullScreen())

g = w.frameGeometry()
ok("窗口中央不触发边缘缩放",
   not w._edges_at(g.center()))
ok("左边缘触发缩放",
   bool(w._edges_at(QPoint(g.left() + 2, g.center().y())) & Qt.LeftEdge))
ok("右下角触发双向缩放",
   w._edges_at(QPoint(g.right() - 2, g.bottom() - 2))
   == (Qt.RightEdge | Qt.BottomEdge))

w.close()
print(f"\n=== 结果: {PASS} 通过 / {FAIL} 失败 ===")
sys.exit(0 if FAIL == 0 else 1)
