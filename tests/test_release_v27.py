# -*- coding: utf-8 -*-
"""v27 回归：阶段 2「全部行情按需加载 / 消除反复加载与连环弹窗」。

验收点（全部离线，不依赖网络）：
1. 打开「全部」页只把首屏 PAGE_SIZE 行挂进布局，而不是 200/500 行；
2. 刷新请求只包含已挂载窗口 + 预取一页 + 自选 + 指定品种；
3. 行情回来只重绘挂载窗口内的行，且合并快照不清空已加载的其它页；
4. 滚动接近底部增量加载下一页，请求窗口跟着扩大，且不整页重建；
5. refresh_now 在 120ms 内的重复调用合并为一次真实请求；
6. 加载失败只给状态栏轻量提示 + 有限次重试，不创建任何模态窗口；
7. 详情抽屉按品种复用，重复打开不新建卡片 / 线程。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v27_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CT_OFFLINE"] = "1"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import QApplication

from core.config import Config
from core.updater import RefreshScheduler
from data.api_base import Ticker
from data.universe import all_of
from ui.main_window import (MAX_RETRY, PAGE_SIZE, PREFETCH_ROWS,
                            MainWindow)

app = QApplication([])


def pump(sec=0.05):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def wait_fill(w, key, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if key not in w._filling_all:
            pump(0.05)
            return
        time.sleep(0.005)
    raise AssertionError("建行超时")


def mounted(w, key):
    lay = w.pages[key]["layout"]
    return [lay.itemAt(i).widget() for i in range(lay.count())
            if lay.itemAt(i).widget() is not None]


cfg = Config()
cfg.set("mascot_enabled", False)
w = MainWindow(cfg)
w.scheduler.stop()
w.scheduler.refresh_now = lambda: None      # 主窗口侧不发真实网络请求
w.resize(560, 900)
w.prepare_show()
key = w._current_market()

# ============ 1. 首屏只挂载一页（行对象也按页建，不一次性全量） ============
w._switch_sub("all")
wait_fill(w, key)
total = len(all_of(key))
first = mounted(w, key)
assert len(w.all_rows[key]) == min(PAGE_SIZE, total), \
    "按页按需：首屏只应创建一页的行对象"
assert len(first) == min(PAGE_SIZE, total), \
    f"首屏只该挂 {PAGE_SIZE} 行，实际 {len(first)}"
assert all(hasattr(x, "symbol") for x in first), \
    "列表布局里不该混入非行情行控件"
print(f"1. 首屏只挂载 {len(first)}/{total} 行 OK")

# ============ 2. 请求窗口化 ============
syms = w._refresh_symbols()
assert len(syms) <= PAGE_SIZE + PREFETCH_ROWS + len(w.rows) + 1, \
    f"请求集合仍接近全量：{len(syms)}"
assert len(syms) < total, "不应把整个市场都塞进一次请求"
# 未挂载的远端品种不该在请求集合里
far = w._all_order[key][min(total - 1, PAGE_SIZE + PREFETCH_ROWS + 5)]
assert far not in syms, "未加载的远端品种不应被请求"
print(f"2. 本轮只请求 {len(syms)}/{total} 个标的 OK")

# ============ 3. 只重绘挂载窗口 / 快照合并 ============
calls = []
orig_paint = {}
for s, row in list(w.all_rows[key].items())[:PAGE_SIZE * 3]:
    orig_paint[s] = row.update_ticker
    row.update_ticker = (lambda _s: (lambda t: calls.append(_s)))(s)
w._last_tickers["__KEEP__"] = Ticker("__KEEP__", "keep", 1.0, 0.0,
                                     1.0, 1.0, 1.0)
w._on_fetched({"BTC": Ticker("BTC", "BTC", 100.0, 1.0,
                             101.0, 99.0, 1e9)}, "test", time.time())
pump(0.05)
hit = set(calls)
assert all(s in w._all_order[key][:PAGE_SIZE] for s in hit), \
    "刷新碰到了未挂载的行"
assert "__KEEP__" in w._last_tickers, "分页请求不得清空已有行情缓存"
for s, fn in orig_paint.items():
    w.all_rows[key][s].update_ticker = fn
print(f"3. 只重绘挂载窗口 {len(hit)} 行 + 快照合并 OK")

# ============ 4. 滚动增量加载 ============
bar = w.pages[key]["scroll"].verticalScrollBar()
w._on_list_scroll(key, bar.maximum())
pump(0.1)
assert w._page_limit[key] > PAGE_SIZE, "滚到底部应加载下一页"
second = mounted(w, key)
assert len(second) > len(first), "下一页应追加到列表"
assert len(second) <= w._page_limit[key], "挂载数不得超过已加载页数"
syms2 = w._refresh_symbols()
assert len(syms2) > len(syms), "请求窗口应随已加载页扩大"
print(f"4. 滚动加载下一页：{len(first)} → {len(second)} 行，"
      f"请求 {len(syms)} → {len(syms2)} OK")

# ============ 5. refresh_now 合并 / 请求去重 ============
class FakeManager:
    source_name = "fake"
    last_success_time = 0.0

    def fetch_tickers(self, symbols):
        return {}


class CountingScheduler(RefreshScheduler):
    def __init__(self):
        super().__init__(FakeManager(), ["BTC"])
        self.starts = 0

    def _tick(self, force=False):
        if force:
            self.starts += 1
        # 不真的启动线程，只统计「立即刷新」被触发了几次
        return None


s = CountingScheduler()
for _ in range(5):
    s.refresh_now()
pump(0.35)
assert s.starts == 1, f"5 次立即刷新应合并成 1 次，实际 {s.starts}"
s.stop()
print("5. 120ms 内 5 次 refresh_now 合并为 1 次 OK")

# ============ 6. 失败轻量提示 + 有限重试 ============
before = len(app.topLevelWidgets())
w._on_failed("模拟网络失败")
pump(0.05)
assert len(app.topLevelWidgets()) == before, "失败不得新建任何窗口"
assert w.status.lbl_note.isVisible()
assert w.status.btn_retry.isVisible()
for i in range(MAX_RETRY + 2):
    w._on_retry()
assert w._retry_left == 0, "重试次数必须受限"
w._on_failed("再次失败")
assert not w.status.btn_retry.isVisible(), "次数用完后不再给重试按钮"
w._on_fetched({"BTC": Ticker("BTC", "BTC", 100.0, 1.0,
                             101.0, 99.0, 1e9)}, "test", time.time())
assert w._retry_left == MAX_RETRY, "成功后应重置重试次数"
print(f"6. 失败不弹窗 / 重试上限 {MAX_RETRY} 次 OK")

# ============ 7. 详情抽屉复用 ============
w.chart_view._symbol = "BTC"
w._open_detail()
d1 = w._detail_cache.get("BTC")
assert d1 is not None
pump(0.1)
w._open_detail()
assert w._detail_cache.get("BTC") is d1, "重复打开同一品种必须复用"
for other in ("ETH", "SOL", "XRP"):
    w.chart_view._symbol = other
    w._open_detail()
    pump(0.03)
assert len(w._detail_cache) <= 3, "详情抽屉缓存需有上限"
for d in list(w._detail_cache.values()):
    d.close()
print("7. 详情抽屉复用且缓存有上限 OK")

# ============ 收尾 ============
w._detail_cache.clear()
pump(0.05)
from qt_exit import finish
print("\nv27 全部回归测试通过 ✅")
finish()
