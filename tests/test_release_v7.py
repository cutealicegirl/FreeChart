# -*- coding: utf-8 -*-
"""v7 离线回归：主流品种 K 线历史「主动预缓存」+ 设置/托盘/入口接入。

不启动真实网络：PrefetchWorker 的 fetch_klines 用 mock；MainWindow 的
refresh scheduler 按既有约定停掉，避免 offscreen teardown 的 127 问题。
"""
import inspect
import os
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_v7_")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

app = QApplication([])
for f in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc"):
    if os.path.exists(f):
        QFontDatabase.addApplicationFont(f)

import data.prefetch as prefetch
from core.config import Config
from data import kline_cache
from data.klines import Candle
from data.universe import all_of
from ui.main_window import MainWindow
from ui.settings_dialog import SettingsDialog


def make_candles(n=30, base=60000.0):
    return [Candle(ts=1600000000 + i * 86400,
                   time_label=f"11-{(i % 28) + 1:02d}",
                   open=base + i, high=base + i + 20,
                   low=base + i - 20, close=base + i + 5,
                   volume=1000 + i) for i in range(n)]


# ===== 1. 默认配置 =====
cfg = Config()
assert cfg.get("prefetch_enabled") is True
assert cfg.get("prefetch_top") == 40
assert cfg.get("prefetch_delay") == 20
assert cfg.get("prefetch_gap") == 350
assert cfg.get("prefetch_ttl") == 21600
print("1. 预缓存默认配置 OK")

# ===== 2. 每个品种需要落盘的周期 =====
assert prefetch.intervals_for_prefetch("BTC") == ["15m", "1d"]
assert prefetch.intervals_for_prefetch("SH:600519") == ["day"]
assert prefetch.intervals_for_prefetch("HK:00700") == ["day"]
assert prefetch.intervals_for_prefetch("US:NVDA") == ["day"]
print("2. 加密 15m+日线 / 股票日线（去重）OK")

# ===== 3. 队列：自选优先 + 四市场主流 + 去重 =====
cfg.set("symbols", ["BTC", "ETH"])
cfg.set("tray_symbol", "BTC")
cfg.set("prefetch_top", 5)
queue = prefetch.build_queue(cfg)
assert [s for s, _ in queue[:4]] == ["BTC", "BTC", "ETH", "ETH"], \
    "自选必须排最前，且每个自带 15m + 日线"
for market in ("crypto", "cn", "hk", "us"):
    for sym in all_of(market)[:5]:
        assert any(s == sym for s, _ in queue), f"{market} 主流 {sym} 未入队"
assert len(queue) == len(set(queue)), "队列不得重复"
assert len(queue) > 20
print(f"3. 预缓存队列 OK（{len(queue)} 个品种/周期，自选优先）")

# ===== 4. 真线程跑一遍：写盘 / 跳过失败 / 跳过已新鲜 =====
kline_cache.clear()
calls = []


from core import kline_time as _kt
import time as _time

_REF_NOW = _time.time()


def fake_fetch(symbol, interval):
    calls.append((symbol, interval))
    if symbol == "BAD":
        raise RuntimeError("offline")
    # v4 缓存按周期桶判新鲜；末根对齐当前桶，才能验证写盘后确实 fresh。
    out = make_candles(25)
    shift = int(_kt.bucket_start(_REF_NOW, interval, symbol)) - out[-1].ts
    for c in out:
        c.ts += shift
    return out


small_queue = [("BTC", "15m"), ("BTC", "1d"), ("BAD", "1d"),
               ("ETH", "1d")]
worker = prefetch.PrefetchWorker(cfg, ttl=3600, gap_ms=0,
                                 delay_s=0, queue=small_queue)
progress = []
worker.progress.connect(progress.append)
done = []
worker.finished_all.connect(lambda ok, total: done.append((ok, total)))
loop = QEventLoop()
worker.finished.connect(loop.quit)
guard = QTimer()
guard.setSingleShot(True)
guard.timeout.connect(loop.quit)
guard.start(15000)                         # 兜底超时
with patch.object(prefetch, "fetch_klines", side_effect=fake_fetch):
    worker.start()
    loop.exec()
worker.wait(2000)
guard.stop()
app.processEvents()

assert ("BTC", "15m") in calls and ("BTC", "1d") in calls
assert kline_cache.is_fresh("BTC", "15m") and kline_cache.is_fresh("BTC", "1d")
assert len(kline_cache.load("BTC", "1d")) == 25
assert not kline_cache.count("BAD", "1d"), "单品种失败不得污染缓存"
assert any("BAD" in p and "跳过" in p for p in progress), "失败要被记录并跳过"
assert done and done[0][0] == 3 and done[0][1] == 4, done
print("4. 后台线程批量落盘 / 单点失败隔离 OK")

# 已有本地数据且未过 TTL -> 零请求
calls.clear()
worker2 = prefetch.PrefetchWorker(cfg, ttl=3600, gap_ms=0,
                                  delay_s=0, queue=[("BTC", "1d")])
loop2 = QEventLoop()
worker2.finished.connect(loop2.quit)
guard2 = QTimer()
guard2.setSingleShot(True)
guard2.timeout.connect(loop2.quit)
guard2.start(10000)
with patch.object(prefetch, "fetch_klines", side_effect=fake_fetch) as mocked:
    worker2.start()
    loop2.exec()
worker2.wait(2000)
guard2.stop()
assert mocked.call_count == 0, "本地已新鲜的品种不应再发 API 请求"
print("5. 已有本地历史零网络请求 OK")

# ===== 6. 设置对话框暴露开关与范围 =====
w = MainWindow(cfg)
w.scheduler.stop()
w.scheduler.refresh_now = lambda: None
assert w._prefetch is None, "MainWindow 不得自动启动预缓存线程"
dlg = SettingsDialog(w, w)
st = dlg.get_settings()
assert st["prefetch_enabled"] is True and st["prefetch_top"] == 5
dlg.chk_prefetch.setChecked(False)
dlg.spin_prefetch_top.setValue(80)
st2 = dlg.get_settings()
assert st2["prefetch_enabled"] is False and st2["prefetch_top"] == 80
print("6. 设置项（开关 / 每市场数量）OK")


# ===== 7. 主窗口启动 / 停止 / 状态栏进度（不启真实线程）=====
class _Sig:
    def connect(self, *a):
        pass

    def disconnect(self, *a):
        pass


class FakeWorker:
    last = None

    def __init__(self, config, parent=None, **kw):
        self.kw = kw
        self.started = False
        self.progress = _Sig()
        self.finished_all = _Sig()
        self.finished = _Sig()
        FakeWorker.last = self

    def queue_size(self):
        return 12

    def start(self):
        self.started = True

    def stop(self):
        pass

    def deleteLater(self):
        pass

    def isRunning(self):
        return False


with patch("ui.main_window.PrefetchWorker", FakeWorker):
    w.start_prefetch()
    assert FakeWorker.last.started and FakeWorker.last.kw["delay_s"] == 20
    assert "12" in w.status.lbl_note.text(), "状态栏要显示预缓存进度"
    w._on_prefetch_progress("预缓存 3/12 · BTC 1d · 1000 根")
    assert w.status.lbl_note.text() == "缓存 3/12"
    assert "BTC" in w.status.lbl_note.toolTip()
    w._on_prefetch_done(10, 12)
    assert "缓存完成 10/12" in w.status.lbl_note.text()
    w.stop_prefetch()
    assert w._prefetch is None
    # 关闭开关后不应再启动
    cfg.set("prefetch_enabled", False)
    FakeWorker.last = None
    w.start_prefetch()
    assert FakeWorker.last is None
    cfg.set("prefetch_enabled", True)
    w.start_prefetch(force=True)          # 托盘手动触发忽略开关
    assert FakeWorker.last.kw["delay_s"] == 0
    w.stop_prefetch()
print("7. 主窗口启动/停止/进度显示/开关与手动触发 OK")

# ===== 8. 入口显式启动 =====
main_src = open(os.path.join(_ROOT, "main.py"), encoding="utf-8").read()
assert "window.start_prefetch()" in main_src
assert "start_prefetch" in inspect.getsource(MainWindow)
w.stop_prefetch()
worker.deleteLater()
worker2.deleteLater()
guard.deleteLater()
guard2.deleteLater()
loop.deleteLater()
loop2.deleteLater()
app.processEvents()
dlg.close()
dlg.deleteLater()
w.close()
app.processEvents()
print("\nv7 全部回归测试通过 ✅")
