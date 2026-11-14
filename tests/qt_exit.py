# -*- coding: utf-8 -*-
"""离线回归测试的退出助手。

offscreen 平台下，PySide6 在进程退出阶段若仍有 QTimer / QVariantAnimation /
顶层窗口存活，会出现退出码 127 / 139 的清理竞态（断言其实早已全部通过）。
根因是 Windows 的 ExitProcess 在 DLL 卸载阶段回调已被销毁的 Qt 窗口过程。

断言全部通过后调用 `finish()`：先用 TerminateProcess 以 0 结束进程（跳过
DLL_PROCESS_DETACH），避开这个纯测试环境的竞态。必须显式声明 HANDLE 的
argtypes/restype，否则 64 位伪句柄会被截断成 32 位导致调用失败，随后
os._exit() 又落回有问题的 ExitProcess 路径。

真实程序走 QApplication.quit() 正常关闭，不受影响。
"""
import ctypes
import os
import sys


def finish(code: int = 0):
    """断言全部通过后干净地结束测试进程，退出码真实反映测试结果。"""
    sys.stdout.flush()
    sys.stderr.flush()
    if os.name == "nt":
        try:
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.GetCurrentProcess.restype = ctypes.c_void_p
            k32.TerminateProcess.argtypes = [ctypes.c_void_p,
                                             ctypes.c_uint]
            k32.TerminateProcess.restype = ctypes.c_int
            k32.TerminateProcess(k32.GetCurrentProcess(), int(code))
        except Exception:
            pass
    os._exit(int(code))
