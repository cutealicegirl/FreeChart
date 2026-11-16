# -*- coding: utf-8 -*-
"""QThread 安全收尾的公共工具。

背景（这是一类崩溃级缺陷）：
    退出/关闭时若某个网络 QThread 仍在 run() 中，而它的 QObject 父对象
    正在被 Qt 对象树递归析构，Qt 会 fail-fast 报
    "QThread: Destroyed while thread is still running" 并直接 abort 进程。

统一范式：
    请求中断 -> 等待（有上限，不无限延长）-> 复查 isRunning()
    -> 仍在运行则脱离对象树(setParent(None)) + 保留强引用保活
    -> 已结束则 deleteLater()。

保活的线程对象随进程一起回收；它们持有的 requests 调用会在各自的
socket timeout 后自然结束，不会再有父对象去销毁一个运行中的 QThread。

参考：本范式最初由 core/updater.py:RefreshScheduler.stop() 正确实现，
此模块将其提炼出来，供 live_feed / chart_view / main_window 复用，
避免各模块收尾逻辑再次漂移。
"""
from PySide6.QtCore import QThread  # noqa: F401  (类型标注用)

# 运行中未能及时结束的线程：保留强引用，禁止 Qt 在退出时销毁它们。
_ORPHAN_THREADS = []


def safe_stop_thread(worker, wait_ms: int = 2000, signals=()) -> bool:
    """安全地停止一个 QThread worker，返回是否已干净结束。

    参数:
        worker:  QThread 实例（可为空）。
        wait_ms: 等待上限（毫秒）。取 socket timeout 量级即可，不要无限等。
        signals: 需要在等待前主动断开的 Signal 列表（可选）。
    返回:
        True  —— 线程已结束并已安排 deleteLater；
        False —— 线程仍在运行，已脱离对象树并保活（不会触发 Qt 崩溃）。
    """
    if worker is None:
        return True
    for sig in signals:
        if sig is None:
            continue
        try:
            sig.disconnect()
        except (RuntimeError, TypeError):
            pass
    try:
        worker.requestInterruption()
    except RuntimeError:
        return True                      # C++ 对象已销毁
    try:
        worker.wait(wait_ms)
    except RuntimeError:
        return True
    try:
        running = worker.isRunning()
    except RuntimeError:
        return True
    if running:
        # 关键：先脱离父对象，否则父对象析构仍会删除这个运行中的线程。
        # getattr 兼容缺少 setParent 的 duck-typed worker（如离线测试替身）。
        setter = getattr(worker, "setParent", None)
        if callable(setter):
            try:
                setter(None)
            except (RuntimeError, TypeError):
                pass
        if worker not in _ORPHAN_THREADS:
            _ORPHAN_THREADS.append(worker)
        return False
    cleanup = getattr(worker, "deleteLater", None)
    if callable(cleanup):
        try:
            cleanup()
        except RuntimeError:
            pass
    return True
