# -*- coding: utf-8 -*-
"""秒级实时行情源（只服务「当前打开的图表品种」）。

为什么单独做一个：
  * 列表页每 5–15 秒批量刷新几十/几百个品种，不适合做 K 线动画；
  * 图表只需要「一个品种」的最新价，单品种接口极轻量，可以 1 秒一次，
    这样最新那根 K 线才能随着成交价连续伸缩，有实时的紧迫感。

实现要点：
  * QTimer 触发 -> 派生一个短命 QThread 请求 -> 结果回到主线程；
  * 同一时刻只有一个在途请求（_busy），网络慢时自动降频，不会堆积线程；
  * 任何异常都静默吞掉（实时增强失败不能影响主行情刷新）。
"""
import time

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from core.thread_cleanup import safe_stop_thread


class _QuoteWorker(QThread):
    done = Signal(str, float, float)     # symbol, price, change_pct

    def __init__(self, manager, symbol: str, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._symbol = symbol

    def run(self):
        # 退出期间若已请求中断，直接收尾，不再发起新的网络调用。
        if self.isInterruptionRequested():
            return
        try:
            price, change = self._manager.fetch_quote(self._symbol)
        except Exception:
            return
        # 网络调用不可中断（requests 阻塞），返回后再检查一次：中断期间
        # 拿到的结果不再发信号，避免退出过程触碰上层 UI。
        if self.isInterruptionRequested():
            return
        if price and price > 0:
            self.done.emit(self._symbol, float(price), float(change or 0.0))


class LiveFeed(QObject):
    """单品种秒级轮询；tick(symbol, price, change_pct)。"""

    tick = Signal(str, float, float)

    def __init__(self, manager, interval_ms: int = 900, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._symbol = ""
        self._enabled = True
        self._busy = False
        self._worker = None
        self._last_ts = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(max(400, int(interval_ms)))
        self._timer.timeout.connect(self._fire)

    # ---- 配置 ----
    def set_enabled(self, enabled: bool):
        self._enabled = bool(enabled)
        if not enabled:
            self.stop()
        elif self._symbol:
            self.start()

    def set_interval(self, ms: int):
        self._timer.setInterval(max(400, min(5000, int(ms))))

    def set_symbol(self, symbol: str):
        if symbol == self._symbol:
            return
        self._symbol = symbol or ""
        self._last_ts = 0.0
        if not self._symbol:
            self.stop()
        elif self._enabled:
            self.start()

    # ---- 生命周期 ----
    def start(self):
        if not self._symbol or not self._enabled:
            return
        if not self._timer.isActive():
            self._timer.start()
            self._fire()

    def stop(self):
        self._timer.stop()

    def shutdown(self):
        """停止定时器并安全收尾在途请求线程。

        旧实现先清空 _worker 再 wait，且丢弃 wait 结果：若网络请求超时
        未结束（fetch_quote 单次最长约 16s，而只等 1.2s），线程引用被
        提前丢弃，退出时 QThread 仍在运行，Qt 会 fail-fast 崩溃。
        现改为「中断 -> 等待 -> 复查 -> 保活」的统一范式。
        """
        self.stop()
        worker = self._worker
        self._worker = None
        self._busy = False
        if worker is None:
            return
        safe_stop_thread(worker, wait_ms=1500,
                         signals=(worker.done, worker.finished))

    # ---- 内部 ----
    def _fire(self):
        if self._busy or not self._symbol or not self._enabled:
            return
        self._busy = True
        worker = _QuoteWorker(self._manager, self._symbol, self)
        worker.done.connect(self._on_done)
        worker.finished.connect(self._on_finished)
        self._worker = worker
        worker.start()

    def _on_done(self, symbol, price, change):
        if symbol != self._symbol:
            return
        self._last_ts = time.time()
        self.tick.emit(symbol, price, change)

    def _on_finished(self):
        self._busy = False
        worker = self._worker
        self._worker = None
        if worker is not None:
            try:
                worker.deleteLater()
            except RuntimeError:
                pass
