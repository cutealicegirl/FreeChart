# -*- coding: utf-8 -*-
"""第七阶段测试 B：资源占用采样。

程序运行 3 分钟（默认 15s 间隔 + 17 币种），每 30s 采样一次
工作集内存与 CPU 时间，验证长期运行下无内存泄漏、CPU 占用极低。
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from core.config import Config
from ui.main_window import MainWindow


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


def sample():
    """返回 (工作集 MB, CPU 时间秒)。"""
    k32 = ctypes.WinDLL("kernel32")
    psapi = ctypes.WinDLL("psapi")
    k32.GetCurrentProcess.restype = wt.HANDLE
    handle = k32.GetCurrentProcess()
    pmc = PROCESS_MEMORY_COUNTERS()
    pmc.cb = ctypes.sizeof(pmc)
    psapi.GetProcessMemoryInfo.argtypes = [
        wt.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wt.DWORD]
    psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc),
                               ctypes.sizeof(pmc))
    ft_create, ft_exit, ft_kernel, ft_user = \
        wt.FILETIME(), wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
    k32.GetProcessTimes.argtypes = [
        wt.HANDLE, ctypes.POINTER(wt.FILETIME), ctypes.POINTER(wt.FILETIME),
        ctypes.POINTER(wt.FILETIME), ctypes.POINTER(wt.FILETIME)]
    k32.GetProcessTimes(
        handle, ctypes.byref(ft_create), ctypes.byref(ft_exit),
        ctypes.byref(ft_kernel), ctypes.byref(ft_user))
    def ft2s(ft):
        return (ft.dwHighDateTime << 32 | ft.dwLowDateTime) / 1e7
    cpu = ft2s(ft_kernel) + ft2s(ft_user)
    return pmc.WorkingSetSize / 1024 / 1024, cpu


app = QApplication([])
w = MainWindow(Config())
w.show()

samples = []
t0 = time.time()


def take(n):
    mem, cpu = sample()
    elapsed = time.time() - t0
    samples.append((elapsed, mem, cpu))
    print(f"[{elapsed:6.1f}s] 内存 {mem:6.1f} MB | CPU 累计 {cpu:6.2f} s "
          f"| 失败计数 {w.scheduler._fail_count}")
    if n < 6:
        QTimer.singleShot(30000, lambda: take(n + 1))
    else:
        # 分析结果
        first_mem, last_mem = samples[0][1], samples[-1][1]
        growth = last_mem - first_mem
        total_cpu = samples[-1][2] - samples[0][2]
        span = samples[-1][0] - samples[0][0]
        print("-" * 46)
        print(f"150 秒内内存增长: {growth:+.1f} MB"
              f"（< 10MB 视为无泄漏）")
        print(f"平均 CPU 占用: {total_cpu / span * 100:.2f} %")
        ok = growth < 10 and total_cpu / span < 0.05
        print("第七阶段资源测试:", "通过" if ok else "需关注")
        w.quit_app()
        sys.exit(0)


QTimer.singleShot(30000, lambda: take(1))  # 30s 后开始采样
app.exec()
