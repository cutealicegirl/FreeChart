# -*- coding: utf-8 -*-
"""1000 品种行情列表性能测量（实测，不编造）。

patch 数据层注入 1000 个虚拟品种，构造真实 MainWindow，测量：
  - 首屏（全部页）加载耗时与创建的行对象数
  - 逐页加载到末页后的行对象数 / 布局挂载数
  - 连续刷新 100 次后对象数是否稳定（不累积）
  - 排序响应时间
  - QThread 残留数量

运行：QT_QPA_PLATFORM=offscreen python tests/test_perf_1000.py
"""
import os
import sys
import tempfile
import time
from unittest.mock import patch

_TMP = tempfile.mkdtemp(prefix="ct_perf_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CT_OFFLINE"] = "1"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import QApplication
import ui.main_window as mw_mod
from ui.main_window import MainWindow, PAGE_SIZE
from core.config import Config
from data.api_base import Ticker
from data.universe import all_of as real_all_of

app = QApplication([])
cfg = Config()

N = 1000
SYMS = [f"PERF{i:04d}" for i in range(N)]
NAMES = {s: f"Perf {i}" for i, s in enumerate(SYMS)}
TICK = {s: Ticker(symbol=s, name=NAMES[s], last_price=100.0 + i,
                  change_pct=1.0, high_24h=200.0 + i, low_24h=50.0)
        for i, s in enumerate(SYMS)}


def pump(ms=30):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.003)


def layout_count(w, key):
    lay = w.pages[key]["layout"]
    return sum(1 for i in range(lay.count()) if lay.itemAt(i).widget() is not None)


print(f"模拟品种数: {N}  PAGE_SIZE: {PAGE_SIZE}")
print("=" * 60)

# 用 patch 注入虚拟 universe：crypto 市场 1000 品种，其余保持空以免干扰
def fake_all_of(market):
    return list(SYMS) if market == "crypto" else []


def fake_names(market):
    return dict(NAMES) if market == "crypto" else {}


with patch.object(mw_mod, "all_of", fake_all_of), \
     patch.object(mw_mod, "names", fake_names), \
     patch.object(mw_mod.MarketManager, "fetch_tickers",
                  lambda self, syms: {s: TICK.get(s) for s in syms}):
    w = MainWindow(cfg)
    pump(100)

    # --- 首屏：切到 crypto 的「全部」页 ---
    w._sub_tabs["crypto"] = "all"
    t0 = time.perf_counter()
    w._current_tab = "crypto"
    w._ensure_all_rows("crypto")
    pump(500)
    first_screen_s = time.perf_counter() - t0
    first_rows = len(w.all_rows["crypto"])
    first_mounted = layout_count(w, "crypto")
    print(f"首屏加载耗时:        {first_screen_s*1000:.1f} ms")
    print(f"首屏创建行对象数:    {first_rows}")
    print(f"首屏布局挂载行数:    {first_mounted}")

    # --- 逐页滚动到末页 ---
    t0 = time.perf_counter()
    guard = 0
    while len(w.all_rows["crypto"]) < N and guard < 40:
        w._page_limit["crypto"] = min(N, w._page_limit["crypto"] + PAGE_SIZE)
        w._relayout_page("crypto")
        pump(30)
        guard += 1
    full_scroll_s = time.perf_counter() - t0
    total_rows = len(w.all_rows["crypto"])
    total_mounted = layout_count(w, "crypto")
    print(f"滚到末页耗时:        {full_scroll_s*1000:.1f} ms (翻 {guard} 页)")
    print(f"末页累计行对象数:    {total_rows}")
    print(f"末页布局挂载行数:    {total_mounted}  ← 实测：全部页翻到底会挂载所有已加载行（按页累积架构）")

    # --- 连续刷新 100 次：对象数是否累积 ---
    rows_before = len(w.all_rows["crypto"])
    mounted_before = layout_count(w, "crypto")
    t0 = time.perf_counter()
    for _ in range(100):
        w._relayout_page("crypto")
    pump(100)
    refresh100_s = time.perf_counter() - t0
    rows_after = len(w.all_rows["crypto"])
    mounted_after = layout_count(w, "crypto")
    print(f"100 次重排耗时:      {refresh100_s*1000:.1f} ms (平均 {refresh100_s*1000/100:.2f} ms/次)")
    print(f"刷新后行对象数:      {rows_before} -> {rows_after}  {'✓ 无累积' if rows_after==rows_before else '✗ 累积!'}")
    print(f"刷新后挂载行数:      {mounted_before} -> {mounted_after}")

    # --- 排序响应时间 ---
    t0 = time.perf_counter()
    w._all_order["crypto"] = list(reversed(SYMS))
    w._relayout_page("crypto")
    pump(100)
    sort_s = time.perf_counter() - t0
    print(f"全量倒序重排耗时:    {sort_s*1000:.1f} ms")

    # --- 线程残留 ---
    live = [t for t in w.__dict__.values() if hasattr(t, "isRunning") and
            callable(t.isRunning) and t.isRunning()]
    print(f"运行中 QThread 残留: {len(live)}")

    w.close()

print("=" * 60)
print("说明：以上均为本环境（offscreen，无真实网络/图标 IO）实测值。")
print("CPU 占用 / 滚动帧率 / 真实内存增量需真机或带 GUI 环境测量，此处 NOT RUN。")
