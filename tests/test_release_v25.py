# -*- coding: utf-8 -*-
"""v25 回归：任务栏「指定品种实时价格」小工具失灵修复。

复现的真实配置：price_badge=True / tray_show_price=False / tray_symbol=BTC。
旧版把两个独立开关 AND 在一起，关掉托盘价格后价格条被隐藏、指定品种
也不再进入请求集合，看起来就是「小工具失灵」。

覆盖：
1. 显隐解耦：tray_show_price=False 时价格条依然可见；
2. 请求解耦：指定品种仍进入刷新集合（含非当前市场的股票代码）；
3. 指定品种行情能正确画到价格条上；
4. 单轮数据源缺项时不闪回 "-- WAIT"，沿用上次报价并标注来源；
5. 小工具右键「隐藏」同步托盘菜单勾选状态；
6. 可指定品种清单注入（自选 + 当前市场全部页 + 当前品种）；
7. 立即刷新撞上在途请求时不丢弃，结束后补发一次。

全部离线（临时 APPDATA + offscreen + CT_OFFLINE）。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v25_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CT_OFFLINE"] = "1"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from core.config import Config
from core.updater import RefreshScheduler
from data.api_base import Ticker
from ui.main_window import MainWindow

app = QApplication([])


def pump(sec=0.1):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


cfg = Config()
cfg.set("mascot_enabled", False)
cfg.set("price_badge", True)
cfg.set("tray_show_price", False)      # ← 触发旧版 bug 的关键开关
cfg.set("tray_symbol", "SH:600519")    # 非自选、非当前市场的股票
w = MainWindow(cfg)
w.scheduler.stop()
w.scheduler.refresh_now = lambda: None
w.prepare_show()
w.show()
pump(0.15)

# ============ 1. 显隐解耦 ============
assert w.price_badge.isVisible(), \
    "关掉托盘图标价格不应连带隐藏任务栏常驻价格条"
print("1. 任务栏价格条不再受 tray_show_price 牵连 OK")

# ============ 2. 请求解耦 ============
syms = w._refresh_symbols()
assert "SH:600519" in syms, \
    "price_badge 开启时，指定品种必须进入行情请求集合"
print(f"2. 指定品种纳入刷新集合 OK（本轮 {len(syms)} 个标的）")

# ============ 3. 指定品种行情正确上屏 ============
moutai = Ticker("SH:600519", "贵州茅台", 1700.0, 1.25,
                1720.0, 1680.0, 1.2e9)
w._on_fetched({"SH:600519": moutai, "BTC": Ticker(
    "BTC", "BTC", 67891.23, 2.35, 70000.0, 66000.0, 1.7e9)},
    "test", time.time())
pump(0.05)
badge = w.price_badge
assert badge._symbol == "SH:600519", badge._symbol
assert "1,700" in badge._price_text, badge._price_text
assert badge._has_data is True
assert "本轮实时行情" in badge.toolTip()
print(f"3. 指定品种价格上屏 OK（{badge._price_text}）")

# ============ 4. 单轮缺项不闪回 WAIT ============
btc_only = Ticker("BTC", "BTC", 67900.0, 2.4, 70000.0, 66000.0, 1.7e9)
w._on_fetched({"BTC": btc_only}, "test", time.time())
pump(0.05)
assert "1,700" in badge._price_text, \
    f"股票源单轮缺项不应把价格条清成占位符：{badge._price_text}"
assert "缓存" in badge.toolTip(), badge.toolTip()
t, stale = w._ticker_for("SH:600519")
assert t is not None and stale is True
print("4. 数据源临时缺项保留上次报价并标注来源 OK")

# 缓存过期后应老实回到等待态
sym, (ts, old_t) = next(iter(w._tray_ticker_cache.items()))
w._tray_ticker_cache[sym] = (ts - w._TRAY_CACHE_TTL - 1, old_t)
t2, stale2 = w._ticker_for("SH:600519")
assert t2 is None and stale2 is False
w._tray_ticker_cache[sym] = (ts, old_t)     # 还原，供后续断言
print("4b. 缓存超时后不再冒充实时价 OK")

# ============ 5. 右键隐藏同步托盘菜单 ============
assert w.act_badge.isChecked(), "初始应为开启"
badge._hide_from_menu()
pump(0.05)
assert not badge.isVisible()
assert not w.act_badge.isChecked(), \
    "小工具里隐藏后，托盘菜单勾选必须同步（否则再点一次反而关掉）"
assert w.config.get("price_badge") is False
w._toggle_price_badge(True)
pump(0.05)
assert badge.isVisible() and w.act_badge.isChecked()
print("5. 小工具隐藏 / 托盘菜单勾选同步 OK")

# ============ 6. 候选品种注入 ============
cands = badge._candidates
assert cands and "BTC" in cands and "SH:600519" in cands, cands[:8]
print(f"6. 可指定品种清单注入 OK（{len(cands)} 项）")

# ============ 7. 在途请求不吞掉立即刷新 ============
class FakeManager:
    source_name = "fake"
    last_success_time = 0.0
    last_errors = []

    def fetch_tickers(self, symbols):
        return {}


class BusyWorker(QObject):
    def isRunning(self):
        return True


s = RefreshScheduler(FakeManager(), ["BTC"])
s._next_at = time.time() + 3600        # 心跳不会自己插队
got = []
s.fetched.connect(lambda *a: got.append(a))
s._worker = BusyWorker()
s._tick(force=True)
assert s._pending_force is True, "force 撞上在途请求必须记下来"
s._worker = None
s._on_worker_done()
assert s._pending_force is False
assert s._worker is not None, "在途结束后应立即补发一次"
pump(0.15)
assert got, "补发的请求应真的拿到结果并广播"
s.stop()
print("7. 立即刷新不再被在途请求吞掉 OK")

# ============ 收尾 ============
try:
    w.live.shutdown()
except Exception:
    pass
w.scheduler.stop()
w.close()
pump(0.05)
from qt_exit import finish           # 跳过 offscreen 的 Qt 卸载竞态
print("\nv25 全部回归测试通过 ✅")
finish()
