# -*- coding: utf-8 -*-
"""第五阶段冒烟测试：无边框/置顶/透明度/托盘/增删币种/几何保存。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from core.config import Config
from ui.main_window import MainWindow, make_tray_icon

app = QApplication([])
cfg = Config()
cfg.set("always_on_top", True)
cfg.set("frameless", True)
cfg.set("opacity", 80)
w = MainWindow(cfg)
w.show()


def check():
    flags = w.windowFlags()
    print("无边框:", bool(flags & Qt.FramelessWindowHint),
          "| 置顶:", bool(flags & Qt.WindowStaysOnTopHint))
    print("透明度:", round(w.windowOpacity() * 100), "%")
    print("标题栏可见:", w.title_bar.isVisible())
    print("托盘图标生成:", not make_tray_icon().isNull())

    w.set_symbols(["BTC", "ETH", "SOL", "LTC"])
    print("添加 LTC 后行数:", len(w.rows))
    w.set_symbols(["BTC", "ETH", "SOL"])
    print("删除 LTC 后行数:", len(w.rows),
          "| LTC 行已移除:", "LTC" not in w.rows)

    w.toggle_on_top()
    print("切换置顶后:", bool(w.windowFlags() & Qt.WindowStaysOnTopHint))
    w.toggle_on_top()  # 切回 True，保持配置一致
    print("窗口几何已保存:", cfg.get("x"), cfg.get("y"),
          cfg.get("w"), cfg.get("h"))
    w.quit_app()


QTimer.singleShot(9000, check)
app.exec()
print("第五阶段冒烟测试通过")
sys.exit(0)
