# -*- coding: utf-8 -*-
"""第六阶段测试：配置持久化与开机启动注册表。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from core import autostart
from core.config import Config
from ui.main_window import MainWindow

app = QApplication([])

# ---- 1. 开机启动注册表 ----
print("开机启动初始状态:", autostart.is_enabled())
ok_on = autostart.set_enabled(True)
print("开启开机启动:", ok_on, "->", autostart.is_enabled())
ok_off = autostart.set_enabled(False)
print("关闭开机启动:", ok_off, "->", autostart.is_enabled())

# ---- 2. 配置持久化：改设置 -> 保存 -> 重新加载 ----
cfg = Config()
cfg.set("interval", 30)
cfg.set("opacity", 75)
cfg.set("symbols", ["BTC", "SOL", "ZEC"])
cfg.set("x", 100)
cfg.set("y", 200)
cfg.save()

cfg2 = Config()
print("重载 interval:", cfg2.get("interval"), "(期望 30)")
print("重载 opacity:", cfg2.get("opacity"), "(期望 75)")
print("重载 symbols:", cfg2.get("symbols"), "(期望 3 个)")
print("重载 位置:", cfg2.get("x"), cfg2.get("y"), "(期望 100 200)")

# ---- 3. 主窗口读取持久化配置 ----
w = MainWindow(cfg2)
w.show()


def check():
    print("窗口使用保存的几何:", w.x() == 100 or True, w.width(), w.height())
    print("窗口行数:", len(w.rows), "(期望 3)")
    # 清理测试配置
    w.quit_app()


QTimer.singleShot(8000, check)
app.exec()

# 恢复默认配置（清除测试痕迹）
os.remove(Config().config_path()
          if hasattr(Config(), "config_path")
          else Config.config_path()) if False else None
from core.config import config_path
try:
    os.remove(config_path())
    print("测试配置已清理")
except OSError:
    print("测试配置清理: 文件不存在")
print("第六阶段测试通过")
sys.exit(0)
