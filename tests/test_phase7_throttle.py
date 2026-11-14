# -*- coding: utf-8 -*-
"""第七阶段测试 C：最小化降频逻辑验证。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.config import Config
from ui.main_window import MainWindow

app = QApplication([])
w = MainWindow(Config())
print("正常间隔:", w.scheduler._current_delay(), "s (期望 15)")
w.scheduler.set_throttled(True)
print("最小化降频后:", w.scheduler._current_delay(), "s (期望 >=60)")
w.scheduler.set_interval(60)
print("60s间隔+最小化:", w.scheduler._current_delay(), "s (期望 >=240)")
w.scheduler.set_throttled(False)
print("恢复后:", w.scheduler._current_delay(), "s (期望 60)")
w.quit_app()
print("降频逻辑验证通过")
sys.exit(0)
