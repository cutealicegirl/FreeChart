# -*- coding: utf-8 -*-
"""主流品种 K 线历史后台预缓存。

前面的 kline_cache 只做「浏览过才落盘」，第一次点开某品种仍然要等 API。
本模块在程序启动后用一个低优先级后台线程，按节流顺序把主流品种的
历史批量写入本地 SQLite：

- 队列 = 全部自选 + 托盘品种 + 四个市场各自前 N 个主流品种；
- 每个品种落盘「默认周期」和「日线」两个周期（股票两者相同会自动去重）；
- 已有本地数据且未过预缓存 TTL 的直接跳过，零网络请求；
- 请求之间留间隔、启动留延迟，避免和实时行情刷新抢网络；
- 任何单个品种失败都只跳过，不影响其它品种，也不弹错误框；
- 不在 MainWindow.__init__ 里自启，必须由入口 main.py 显式调用
  start_prefetch()，否则离线回归测试会被后台网络线程拖住。

缓存写入走 kline_cache（threading.local 每线程独立连接），因此与
KlineWorker / HistoryWorker 并发安全。
"""
from PySide6.QtCore import QThread, Signal

from data import kline_cache
from data.klines import default_interval, fetch_klines
from data.universe import all_of

MARKETS = ("crypto", "cn", "hk", "us")
CRYPTO_DAY = "1d"
STOCK_DAY = "day"


def intervals_for_prefetch(symbol: str) -> list:
    """该品种需要预缓存的周期：默认周期 + 日线，去重后返回。"""
    day = STOCK_DAY if ":" in symbol else CRYPTO_DAY
    out = []
    for key in (default_interval(symbol), day):
        if key not in out:
            out.append(key)
    return out


def build_queue(config) -> list:
    """构造 [(symbol, interval), ...]，自选优先，其次各市场前 N 主流。"""
    top = max(0, int(config.get("prefetch_top") or 0))
    symbols = []
    seen = set()

    def add(sym):
        if sym and sym not in seen:
            seen.add(sym)
            symbols.append(sym)

    for sym in (config.get("symbols") or []):
        add(sym)
    add(config.get("tray_symbol") or "")
    for market in MARKETS:
        for sym in all_of(market)[:top]:
            add(sym)

    queue = []
    for sym in symbols:
        for interval in intervals_for_prefetch(sym):
            queue.append((sym, interval))
    return queue


class PrefetchWorker(QThread):
    """串行、可中断的后台预缓存线程。"""

    progress = Signal(str)
    finished_all = Signal(int, int)     # 本次实际写入数, 队列总数

    def __init__(self, config, parent=None, ttl=None, gap_ms=None,
                 delay_s=0, queue=None):
        super().__init__(parent)
        self._queue = list(queue) if queue is not None else build_queue(config)
        self._ttl = int(ttl if ttl is not None
                        else (config.get("prefetch_ttl") or 21600))
        self._gap = max(0, int(gap_ms if gap_ms is not None
                               else (config.get("prefetch_gap") or 350)))
        self._delay = max(0, int(delay_s))

    def queue_size(self) -> int:
        return len(self._queue)

    def stop(self) -> bool:
        """请求中断并等待线程收尾（网络请求可能正在超时，给足等待时间）。

        返回 True 表示线程已干净结束；False 表示 wait 超时后仍在运行，
        调用方必须保留引用 / 保活，禁止直接丢弃（否则父对象析构时
        Qt 会销毁一个仍在运行的 QThread 而 fail-fast）。
        """
        self.requestInterruption()
        try:
            self.wait(10000)
            return not self.isRunning()
        except RuntimeError:
            return True

    def run(self):
        # 启动延迟按秒分段睡，退出时能立刻响应中断
        for _ in range(self._delay):
            if self.isInterruptionRequested():
                return
            self.msleep(1000)

        ok = 0
        total = len(self._queue)
        for i, (symbol, interval) in enumerate(self._queue, 1):
            if self.isInterruptionRequested():
                break
            try:
                if kline_cache.is_fresh(symbol, interval, ttl=self._ttl):
                    continue                       # 本地已有，零请求
                candles = fetch_klines(symbol, interval)
                # 网络调用不可中断：返回后检查中断标志，退出期间不再emit/write
                if self.isInterruptionRequested():
                    break
                if candles:
                    # 与浏览时已回溯出的更早历史合并保存，不覆盖
                    kline_cache.save(symbol, interval, candles)
                    ok += 1
                self.progress.emit(
                    f"预缓存 {i}/{total} · {symbol} {interval} · "
                    f"{len(candles)} 根")
            except Exception:
                self.progress.emit(
                    f"预缓存 {i}/{total} · {symbol} {interval} · 跳过")
            # 节流间隔，同样可被中断
            for _ in range(max(1, self._gap // 50)):
                if self.isInterruptionRequested():
                    break
                self.msleep(50)
        self.finished_all.emit(ok, total)
