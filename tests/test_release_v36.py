# -*- coding: utf-8 -*-
"""v36 回归：链上币真实图表（桌面端）+ 采样历史持久化。

链上合约代币没有交易所 OHLC，外部 K 线源在本机也不可直连。这里的图表
只画两类真实数据：本设备历次刷新的 Rugcheck 真实报价采样走势，以及报告
里的前十大持有地址占比 / 流动性池类型分布；不插值、不编造蜡烛。

验收点（默认离线，不联网、不启动刷新线程）：
1. 采样历史去重、脏数据过滤、上限、清理与落盘；
2. quote 解析真实结构字段，涨跌/高低仍为 None；
3. CandleChart 链上视图可绘制、能切回普通蜡烛；
4. ChartView 打开链上品种自动切视图、show_onchain 注入真实数据；
5. 主窗口收到真实链上报价时会写入采样历史。
"""
import json
import os
import sys
import tempfile
import time
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix="ct_v36_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtGui import QPixmap          # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

from core import onchain_history as oh      # noqa: E402
from core.config import Config               # noqa: E402
from data import onchain                     # noqa: E402
from ui.chart_view import CandleChart, ChartView  # noqa: E402
from ui.main_window import MainWindow        # noqa: E402

FAILS = []
CHECKS = [0]
SYM = "ONCHAIN:9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump"
MINT = onchain.address_of(SYM)


def ok(name, cond, extra=""):
    CHECKS[0] += 1
    print(("PASS " if cond else "FAIL ") + name +
          (("  " + str(extra)) if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


print("=== v36 · 桌面端链上真实图表回归 ===\n")

# ---------- 1. 采样历史 ----------
oh.clear()
ok("1. 首次真实报价写入采样", oh.record(SYM, 0.045, 1700000000) is True
   and len(oh.series(SYM)) == 1)
ok("2. 20 秒内同价不重复记点",
   oh.record(SYM, 0.045, 1700000010) is False
   and len(oh.series(SYM)) == 1)
ok("3. 价格变化写入新点",
   oh.record(SYM, 0.047, 1700000060) is True
   and len(oh.series(SYM)) == 2)
ok("4. 无效价格 / 时间不写入",
   oh.record(SYM, 0, 1700000120) is False
   and oh.record(SYM, 0.05, None) is True)   # None 用当前时间，合法
data = {SYM: [[1700000000, 0.045], "bad", [1700000060, "x"],
              [1700000120, 0.049]]}
with open(oh.path(), "w", encoding="utf-8") as f:
    json.dump(data, f)
ok("5. 脏数据被过滤", oh.series(SYM) == [[1700000000.0, 0.045],
                                     [1700000120.0, 0.049]], oh.series(SYM))
rows = [[1700000000.0 + i * 60, 0.05 + i * 1e-6]
        for i in range(oh.MAX_POINTS + 30)]
with open(oh.path(), "w", encoding="utf-8") as f:
    json.dump({SYM: rows}, f)
ok("6. 采样上限生效", len(oh.series(SYM)) == oh.MAX_POINTS,
   len(oh.series(SYM)))
ok("7. 采样文件确实落盘", os.path.exists(oh.path()))
oh.clear(SYM)
ok("8. 可按品种清理", oh.series(SYM) == [])

# ---------- 2. quote 真实结构字段 ----------
REPORT = {
    "price": 0.04747105238543817,
    "totalMarketLiquidity": 1704443.78,
    "totalHolders": 384611,
    "token": {"supply": 997354258520195, "decimals": 6},
    "tokenMeta": {"symbol": "ANSEM", "name": "The Black Bull"},
    "launchpad": {"name": "Pump.Fun"},
    "topHolders": [
        {"address": "GdrKtm8einYWAfjWhAtmoi6Em5cqEitsF4u1GxZkL3f", "pct": 49.23},
        {"address": "Abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGH", "pct": 3.11},
        {"address": "bad", "pct": -1},
    ],
    "markets": [{"marketType": "pump_fun_amm"},
                {"marketType": "pump_fun_amm"},
                {"marketType": "raydium"}],
}


class FakeResp:
    status_code = 200

    def json(self):
        return REPORT


orig_get = onchain.HTTP.get
onchain.HTTP.get = lambda *a, **k: FakeResp()
try:
    q = onchain.quote(MINT)
finally:
    onchain.HTTP.get = orig_get
ok("9. 取到真实价格", abs(q.get("price") - REPORT["price"]) < 1e-12)
ok("10. 不编造涨跌 / 高低", q.get("change") is None)
ok("11. 前十大持有人占比为真实字段",
   len(q.get("top_holders") or []) == 2
   and q["top_holders"][0]["pct"] == 49.23, q.get("top_holders"))
ok("12. 池类型按数量降序聚合",
   q["pool_types"][0]["label"] == "pump_fun_amm"
   and q["pool_types"][0]["count"] == 2, q.get("pool_types"))
ok("13. 记录真实池总数", q.get("market_count") == 3)

# ---------- 3. CandleChart 绘制 ----------
c = CandleChart()
c.resize(640, 420)
view = {
    "series": [[1700000000, 0.045], [1700000060, 0.047],
               [1700000120, 0.046]],
    "holders": [{"label": "9cRC…pump", "pct": 49.23},
                {"label": "Abc…xyz", "pct": 3.11}],
    "pools": [], "market_count": 518,
    "source": onchain.SOURCE,
}
c.set_onchain_view(view)
ok("14. 链上视图已挂载", c.onchain_view is view)
try:
    c.render(QPixmap(640, 420))
    ok("15. 链上折线 + 结构条绘制不抛异常", True)
except Exception as e:
    ok("15. 链上折线 + 结构条绘制不抛异常", False, repr(e))
c.set_onchain_view({"series": [], "holders": [], "pools": []})
try:
    c.render(QPixmap(640, 420))
    ok("16. 无采样点也能安全绘制", True)
except Exception as e:
    ok("16. 无采样点也能安全绘制", False, repr(e))
c.set_onchain_view(None)
ok("17. 可切回普通蜡烛模式", c.onchain_view is None)

# ---------- 4. ChartView 集成 ----------
cv = ChartView(Config())
cv.open(SYM, "ANSEM", None)
ok("18. 打开链上品种自动切到真实数据视图",
   cv._no_kline is True and cv.chart.onchain_view is not None)
payload = dict(q)
payload["series"] = view["series"]
cv.show_onchain(SYM, {"code": "ANSEM", "name": "The Black Bull",
                      "chain": "Solana"}, payload)
ok("19. show_onchain 注入真实采样与结构数据",
   len(cv.chart.onchain_view["series"]) == 3
   and len(cv.chart.onchain_view["holders"]) == 2)
ok("20. 头部显示真实链上价", "$" in cv.lbl_price.text(),
   cv.lbl_price.text())
try:
    cv.chart.render(QPixmap(640, 420))
    ok("21. 图表页链上视图绘制不抛异常", True)
except Exception as e:
    ok("21. 图表页链上视图绘制不抛异常", False, repr(e))
cv.open("BTC", "Bitcoin", None)
ok("22. 切回普通品种恢复蜡烛模式",
   cv._no_kline is False and cv.chart.onchain_view is None)

# ---------- 5. 主窗口收到报价时记录采样 ----------
oh.clear(SYM)
fake = SimpleNamespace(
    _onchain_quotes={}, _last_tickers={}, _current_batch=set(),
    _tray_ticker_cache={}, rows={}, all_rows={},
    chart_view=None, _detail_cache={},
    _update_tray_price=lambda: None, _sync_badge=lambda: None,
)
MainWindow._on_onchain_quote(fake, {
    SYM: {"price": 0.051, "ts": time.time(), "source": onchain.SOURCE}
})
ok("23. 主窗口收到真实报价会写入采样历史", len(oh.series(SYM)) == 1,
   oh.series(SYM))
ok("24. 同时把采样序列放进报价字典",
   len(fake._onchain_quotes[SYM].get("series") or []) == 1)
oh.clear()

print(f"\n=== {CHECKS[0] - len(FAILS)}/{CHECKS[0]} 通过 ===")
if FAILS:
    print("失败项：" + "; ".join(FAILS))
# offscreen 下 Qt 对象清理竞态会让「断言全过」的进程返回 127，
# 统一走项目的退出助手，让退出码真实反映测试结果。
sys.path.insert(0, os.path.join(_ROOT, "tests"))
from qt_exit import finish  # noqa: E402
finish(1 if FAILS else 0)
