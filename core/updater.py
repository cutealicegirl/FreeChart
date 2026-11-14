# -*- coding: utf-8 -*-
"""行情刷新调度器。

设计要点（对应资源占用要求）：
1. 网络请求在独立 QThread 中执行，GUI 不阻塞。
2. 心跳定时器每秒检查一次是否该发起请求（CPU 占用可忽略），
   而不是频繁重建 QTimer。
3. 失败后逐步延长重试间隔（5s -> 10s -> 20s -> ... 上限 120s）。
4. 窗口最小化时自动降频（间隔 x4，至少 60s）。
5. 同一时刻只允许一个在途请求，避免堆积。
"""
import time

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from data.api_base import MarketApiError
from data.market_manager import MarketManager


class FetchWorker(QThread):
    """单个行情请求的工作线程：每次刷新创建一个，取完即结束。

    相比常驻线程 + 任务队列，这种模式更简单，线程不常驻，
    更省资源。
    """

    # 成功：发送 (行情字典, 数据源名, 最后成功时间戳)
    fetched = Signal(dict, str, float)
    # 失败：发送错误信息
    failed = Signal(str)

    def __init__(self, manager: MarketManager, symbols, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._symbols = list(symbols)

    def run(self):
        try:
            tickers = self._manager.fetch_tickers(self._symbols)
            self.fetched.emit(tickers, self._manager.source_name,
                              self._manager.last_success_time)
        except MarketApiError as e:
            self.failed.emit(str(e))
        except Exception as e:  # 兜底：任何意外都不能让程序崩溃
            self.failed.emit(f"未知错误: {e}")


# 极少数情况下退出时网络线程仍未结束：保留强引用，不让 Qt 销毁一个
# 还在运行的 QThread（否则会 "Destroyed while thread is still running"
# 直接 fail-fast）。对象随进程一起回收，不影响正常使用路径。
_ORPHAN_WORKERS = []


class RefreshScheduler(QObject):
    """刷新调度器。

    界面只需：
      scheduler.set_interval(15)          # 设置正常刷新间隔
      scheduler.set_throttled(True/False) # 最小化降频开关
      scheduler.refresh_now()             # 手动立即刷新
    """

    fetched = Signal(dict, str, float)  # (行情字典, 数据源名, 时间戳)
    failed = Signal(str)                # 刷新失败信息

    def __init__(self, manager: MarketManager, symbols, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._symbols = list(symbols)
        self._interval = 15          # 用户设定间隔（秒）
        self._throttled = False      # 是否处于降频状态（最小化）
        self._fail_count = 0         # 连续失败次数
        self._worker: FetchWorker | None = None
        self._next_at = 0.0          # 下次应发起请求的时间戳
        self._pending_force = False  # force 撞上在途请求，结束后补一次

        # 心跳定时器：每秒检查是否到刷新时间
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # 阶段 2：请求合并。切市场 / 切子页 / 增删自选 / 滚动加载更多
        # 往往在同一帧里连着调好几次 refresh_now()，旧版每次都排队一次
        # 网络请求（还有一批在途），是「反复加载」的主要来源。这里把
        # 120ms 内的多次立即刷新合并成一次，且只在集合真的变了才发。
        self._burst = QTimer(self)
        self._burst.setSingleShot(True)
        self._burst.setInterval(120)
        self._burst.timeout.connect(lambda: self._tick(force=True))
        self._last_request_key = None
        self._last_request_at = 0.0

    # ---- 对外接口 ----
    def set_symbols(self, symbols):
        new = list(symbols)
        if new != self._symbols:
            self._symbols = new
            self._last_request_key = None      # 集合变了，允许立即重取

    def set_interval(self, seconds: int):
        """设置正常刷新间隔（秒），立即按新间隔安排下次刷新。"""
        self._interval = max(5, int(seconds))
        self._next_at = 0.0

    def set_throttled(self, throttled: bool):
        """最小化时置 True；恢复可见时立即刷新一次。"""
        if self._throttled and not throttled:
            self._next_at = 0.0
        self._throttled = throttled

    def refresh_now(self):
        """手动刷新：120ms 内的重复调用合并为一次请求。

        切换市场 / 子页 / 增删自选往往会连着触发 2–3 次，合并后
        同一帧只会有一次网络往返，不会再出现「反复加载」。
        """
        self._burst.start()

    def stop(self):
        """停止心跳并确保在途请求线程安全收尾。

        只停 QTimer 是不够的：如果用户在一次行情请求进行中退出，
        QThread 对象会在仍运行时被销毁，Qt 会直接 fail-fast 崩溃。
        正常路径下 worker 早已结束并由 _on_worker_done 清空引用，
        这里几乎不会真的等待，不影响关窗体验。
        """
        self._timer.stop()
        self._burst.stop()
        self._pending_force = False
        worker = self._worker
        self._worker = None
        if worker is None:
            return
        try:
            worker.fetched.disconnect(self._on_success)
            worker.failed.disconnect(self._on_fail)
            worker.finished.disconnect(self._on_worker_done)
            worker.requestInterruption()
            worker.wait(2000)
            if worker.isRunning():
                _ORPHAN_WORKERS.append(worker)
            else:
                worker.deleteLater()
        except (RuntimeError, TypeError):
            pass

    # ---- 内部逻辑 ----
    def _current_delay(self) -> int:
        """当前实际刷新间隔（秒）：降频 > 失败退避 > 正常。"""
        if self._throttled:
            return max(60, self._interval * 4)
        if self._fail_count:
            delay = 5 * (2 ** (self._fail_count - 1))
            return min(delay, 120)
        return self._interval

    def _tick(self, force=False):
        now = time.time()
        if not force and now < self._next_at:
            return
        # 上一次请求仍在进行则跳过本轮，避免请求堆积
        # 注意：worker 的 C++ 对象在 finished 后被 deleteLater 销毁，
        # 必须捕获 RuntimeError 防止访问已删除对象
        if self._worker is not None:
            try:
                if self._worker.isRunning():
                    # 旧版直接 return，切换指定品种 / 切市场时的立即刷新
                    # 会被静默丢掉，要等满一个周期才生效。记下来，等这轮
                    # 结束后补一次（只补一次，不会形成请求风暴）。
                    if force:
                        self._pending_force = True
                    return
            except RuntimeError:
                self._worker = None  # C++ 对象已被销毁，仅剩 Python 引用
        # 同一批标的 1 秒内的重复请求直接丢弃（请求去重）。切页时
        # set_symbols 若没真的改变集合，也不会白跑一次网络往返。
        key = tuple(self._symbols)
        if key == self._last_request_key and \
                now - self._last_request_at < 1.0:
            self._pending_force = False
            return
        self._last_request_key = key
        self._last_request_at = now
        self._pending_force = False
        self._next_at = now + self._current_delay()
        self._worker = FetchWorker(self._manager, self._symbols)
        self._worker.fetched.connect(self._on_success)
        self._worker.failed.connect(self._on_fail)
        self._worker.finished.connect(self._on_worker_done)
        self._worker.start()

    def _on_worker_done(self):
        """线程结束时清空引用（随后 deleteLater 销毁 C++ 对象）。"""
        if self._worker is not None:
            try:
                self._worker.deleteLater()
            except RuntimeError:
                pass
            self._worker = None
        # 立即刷新曾被在途请求挡下 → 这里补发一次，保证「换品种 /
        # 切页面」当轮就能拿到新标的的数据。
        if self._pending_force and self._timer.isActive():
            self._pending_force = False
            # 补发承载着「切换后必须拿到新标的」的语义，不受去重窗口限制
            self._last_request_key = None
            self._tick(force=True)

    def _on_success(self, tickers, source, ts):
        self._fail_count = 0
        self._next_at = time.time() + self._current_delay()
        self.fetched.emit(tickers, source, ts)

    def _on_fail(self, msg):
        self._fail_count += 1
        self._next_at = time.time() + self._current_delay()
        self.failed.emit(msg)


class SearchWorker(QThread):
    """搜索联想的后台线程：输入变化后异步执行，避免阻塞输入框。"""

    # 成功：发送结果列表 [{symbol, name, kind}]
    results = Signal(list)
    failed = Signal(str)

    def __init__(self, manager, query: str, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._query = query

    def run(self):
        try:
            self.results.emit(self._manager.search(self._query))
        except Exception as e:  # 搜索失败静默降级
            self.failed.emit(str(e))
