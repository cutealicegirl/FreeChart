# -*- coding: utf-8 -*-
"""v16 回归：单实例保护、托盘唤醒、窗口位置归位、窗口标志缓存。

背景：开机自启会在托盘留一个实例，用户再双击图标就起第二个，两个全屏
窗口抢焦点、两个常驻价格条叠在同一处、两个托盘图标各自弹气泡，表现是
「疯狂弹窗 + 疯狂抖动」。本测试锁住修复后的行为。

全部离线（offscreen + 临时 APPDATA）。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v16_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

import main as entry
from core.config import Config
from ui.main_window import MainWindow

app = QApplication([])


def pump(times=25, delay=0.01):
    for _ in range(times):
        app.processEvents()
        time.sleep(delay)


# ================= 1. 单实例互斥 =================
# 用独立管道名，避免和机器上正在运行的真实实例抢同一个名字
entry._SERVER_NAME = "FreeChart-Test-%d" % os.getpid()
# 互斥量也要独立：本机可能正跑着正式版，否则会被判成「已有实例」
entry._MUTEX_NAME = "Local\\FreeChart_Test_%d" % os.getpid()
QLocalServer.removeServer(entry._SERVER_NAME)
assert entry._acquire_mutex() is True, "首个进程应拿到单实例互斥量"
assert entry._claim_single_instance(app) is True, "首个进程应是主实例"
server = getattr(app, "_single_server", None)
assert server is not None and server.isListening(), "主实例应在监听唤醒通道"

# 模拟第二个进程：能连上 = 判为从实例
probe = QLocalSocket()
probe.connectToServer(entry._SERVER_NAME)
assert probe.waitForConnected(1000), "第二个进程应能连上主实例"
probe.disconnectFromServer()
print("1. 单实例互斥：互斥量判重 + 唤醒通道监听 OK")

# ================= 2. 互斥量判重（模拟别的进程来抢） =================
import ctypes
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_h = _k32.CreateMutexW(None, False, entry._MUTEX_NAME)
_other = ctypes.get_last_error() == 183          # ERROR_ALREADY_EXISTS
if _h:
    _k32.CloseHandle(_h)
assert _other, "另一个进程应能检测到互斥量已存在（判为从实例）"
assert entry._acquire_mutex() is True, "本进程重复调用应幂等返回主实例"
print("2. 互斥量判重：外部进程可检测、本进程幂等 OK")

# ================= 3. 唤回窗口（托盘隐藏 -> 前台） =================
cfg = Config()
w = MainWindow(cfg)
w.scheduler.stop()
w.scheduler.refresh_now = lambda: None
w.show()
pump(5)
assert w.isVisible()
w.hide()
pump(5)
assert not w.isVisible(), "隐藏后应不可见"

server.newConnection.connect(lambda: entry._wake_existing(w, server))
wake = QLocalSocket()
wake.connectToServer(entry._SERVER_NAME)
assert wake.waitForConnected(1000)
wake.write(b"wake")
wake.flush()
wake.waitForBytesWritten(1000)
pump(30)
assert w.isVisible(), "收到 wake 后主窗口应回到前台"
print("3. 第二实例能唤回已隐藏的主窗口 OK")

# ================= 4. 窗口位置归位（负坐标 / 越界不出屏） =================
avail = QApplication.primaryScreen().availableGeometry()
cfg.set("x", -120)
cfg.set("y", -60)
cfg.set("w", 400)
cfg.set("h", 300)
w.apply_window_settings(save=False)
pump(3)
assert w.y() >= avail.top(), f"顶边不应出屏: y={w.y()} top={avail.top()}"
assert w.x() >= avail.left(), f"左边不应出屏: x={w.x()} left={avail.left()}"
print(f"4. 负坐标归位 OK（y={w.y()} x={w.x()}）")

# ================= 5. 超出屏幕的尺寸收敛 =================
cfg.set("w", 99999)
cfg.set("h", 99999)
cfg.set("x", avail.left() + 10)
cfg.set("y", avail.top() + 10)
w.apply_window_settings(save=False)
pump(3)
assert w.width() <= avail.width(), f"宽度应被收敛: {w.width()} > {avail.width()}"
assert w.height() <= avail.height(), f"高度应被收敛: {w.height()} > {avail.height()}"
print(f"5. 超大尺寸收敛 OK（{w.width()}x{w.height()}）")

# ================= 6. 窗口标志缓存：重复应用不重设 =================
flag_before = getattr(w, "_win_flags", None)
assert flag_before is not None, "应缓存当前窗口标志"
w.apply_window_settings(save=False)
w.apply_window_settings(save=False)
pump(2)
assert w._win_flags == flag_before, "标志未变时不应重复 setWindowFlags"
print("6. 窗口标志缓存（不反复 hide/show）OK")

# ================= 7. reveal 对最小化同样有效 =================
w.showMinimized()
pump(5)
w.reveal()
pump(5)
assert not w.isMinimized(), "reveal 应取消最小化"
assert w.isVisible()
print("7. reveal 处理最小化 OK")

w.scheduler.stop()
w.close()
print("\nv16 全部回归测试通过 ✅")
