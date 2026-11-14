# -*- coding: utf-8 -*-
"""v32 回归：没有 K 线的链上合约币种也能收藏、也能看真实价格。

背景：pump.fun / Raydium 新币没有币安现货交易对，旧逻辑把「有 K 线」
当成「能加入自选」的前提，这类币既不能收藏也看不到价格。

验收点（离线，不依赖真实网络）：
1. 链上品种标识 / 短地址 / 链判断 / 非 Solana 明确无报价（不编造）；
2. exists=True 且 tradable=False 时仍给出可加入自选的搜索结果；
3. 元数据落盘，重启后自选行仍显示代币代码而不是 44 位地址；
4. 自举行显示真实链上价，涨跌幅 / H / L / V 显示「—」而不是 0.00%；
5. 链上品种不进入交易所请求集合（不发无效请求）；
6. 图表页明确「暂无 K 线」，不启动秒级 live 轮询，仍显示价格与资料；
7. 置顶 / 排序 / 取消置顶对链上品种同样生效；
8. 无报价时明确标注来源与「暂无公开链上报价」，绝不显示假数据；
9. 旧配置缺 onchain_symbols 键时安全迁移为空字典。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v32_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CT_OFFLINE"] = "1"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import QApplication

import ui.main_window as mw
from core.config import Config, DEFAULTS
from data import onchain
from ui.main_window import MainWindow

app = QApplication([])
FAILS = []


def pump(sec=0.08):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


CHECKS = [0]


def ok(name, cond, extra=""):
    CHECKS[0] += 1
    print(("PASS " if cond else "FAIL ") + name + ("  " + str(extra) if extra else ""))
    if not cond:
        FAILS.append(name)


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


ADDR = "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump"
SYM = onchain.make_symbol(ADDR)

# ---- 1. 数据层 ----
ok("1. 链上标识可识别", onchain.is_onchain(SYM) and not onchain.is_onchain("BTC"))
ok("1. 地址可还原", onchain.address_of(SYM) == ADDR)
ok("1. 链判断正确", onchain.chain_of(ADDR) == "Solana"
   and onchain.chain_of("0x" + "a" * 40) == "EVM")
ok("1. 短地址不撑破布局", "…" in onchain.short_address(ADDR)
   and len(onchain.short_address(ADDR)) < 20)
ok("1. 非 Solana 不编造报价", onchain.quote("0x" + "a" * 40) == {})
ok("1. 无涨跌幅标记正确", not onchain.has_change({"change": None})
   and onchain.has_change({"change": 1.2}))
ok("1. meta schema 固定", set(onchain.blank_meta(ADDR, "ANSEM", "The Black Bull") or {})
   >= {"address", "code", "name", "chain", "source"})
ok("1. 旧配置安全迁移", "onchain_symbols" in DEFAULTS
   and DEFAULTS["onchain_symbols"] == {}
   and Config().get("onchain_symbols") == {})

# 避免测试触发真实网络线程；报价通过 _on_onchain_quote 手动注入
MainWindow._refresh_onchain = lambda self: None

cfg = Config()
cfg.set("mascot_enabled", False)
w = MainWindow(cfg)
w.scheduler.stop()
w.scheduler.refresh_now = lambda: None
w.resize(420, 760)
w.prepare_show()
pump()

# ---- 2. 搜索结果：没有 K 线也允许收藏 ----
info = {
    "address": ADDR, "symbol": "ANSEM", "name": "The Black Bull",
    "chain": "Solana", "program": "Token-2022",
    "price": 0.05133747818589247, "change": "",
    "tradable": False,          # 币安无交易对 -> 没有 K 线
    "supply": 997354435.111923, "decimals": 6,
    "liquidity": 1860717.8824534104, "holders": 383918.0,
    "price_source": onchain.SOURCE, "price_ts": time.time(),
    "onchain": True, "exists": True, "launchpad": "Pump.Fun",
}
w.edit_search.setText(ADDR)
w._on_contract_result(info)
pump()
results = list(w.search_panel._results)
ok("2. tradable=False 仍给出收藏项", len(results) == 1,
   "results=%d" % len(results))
if results:
    it = results[0]
    ok("2. 用合约地址做唯一代码", it["symbol"] == SYM)
    ok("2. 结果显示代币代码", it.get("label") == "ANSEM")
note_lbl = w.search_panel._layout.itemAt(0).widget()
ok("2. 说明含来源 / 可收藏 / 无 K 线",
   all(x in note_lbl.text() for x in
       ("可加入自选", onchain.SOURCE, "暂无 K 线")),
   note_lbl.text()[:140])
ok("2. 元数据已落盘", w.config.get("onchain_symbols", {}).get(SYM, {}).get("code") == "ANSEM")

# ---- 3. 加入自选中 ----
w._add_symbol(SYM)
pump()
ok("3. 链上品种进入自选", SYM in w.rows)
row = w.rows[SYM]
ok("3. 行显示代币代码而非地址", row._code == "ANSEM"
   and ADDR not in row._code and len(row._code) <= 12, row._code)
ok("3. 行显示项目名称", row._name == "The Black Bull", row._name)

# ---- 4. 真实链上报价渲染 ----
q = {
    "price": 0.05133747818589247, "change": None,
    "liquidity": 1860717.8824534104, "holders": 383918.0,
    "source": onchain.SOURCE, "ts": time.time(),
}
w._on_onchain_quote({SYM: q})
pump()
ok("4. 显示真实链上价", row.lbl_price.text().startswith("$")
   and "0.051" in row.lbl_price.text(), row.lbl_price.text())
ok("4. 涨跌幅显示 —（不编造 0.00%）", row.lbl_change.text() == "—",
   row.lbl_change.text())
ok("4. H/L/V 明确无数据",
   row.lbl_high.text() == "H —" and row.lbl_low.text() == "L —"
   and row.lbl_vol.text() == "V —")
ok("4. tooltip 标注来源与时间",
   onchain.SOURCE in row.lbl_price.toolTip()
   and "取数时间" in row.lbl_price.toolTip())
ok("4. 报价进入价格条缓存", SYM in w._last_tickers
   and abs(w._last_tickers[SYM].last_price - q["price"]) < 1e-9)

# 无报价：明确标注，不显示假数据
row.update_onchain({"source": onchain.SOURCE, "ts": time.time()})
ok("4. 无报价时不编造", row.lbl_price.text() == "--"
   and "暂无公开链上报价" in row.lbl_price.toolTip())
w._on_onchain_quote({SYM: q})

# ---- 5. 不进入交易所请求集合 ----
req = w._refresh_symbols()
ok("5. 链上品种不发给交易所", SYM not in req, "syms=%d" % len(req))
ok("5. 其它品种仍正常请求", "BTC" in req or len(req) > 0)
w.config.set("tray_symbol", SYM)
ok("5. 指定品种为链上币时也不发交易所请求",
   SYM not in w._refresh_symbols())
w.config.set("tray_symbol", "BTC")

# ---- 6. 图表页：明确无 K 线 ----
w._open_chart(SYM)
pump()
cv = w.chart_view
ok("6. 图表标记无 K 线", getattr(cv, "_no_kline", False) is True)
ok("6. 不启动秒级 live 轮询", not w.live._timer.isActive())
ok("6. 图表标题是代币代码", cv.lbl_symbol.text() == "ANSEM",
   cv.lbl_symbol.text())
ok("6. 图表显示真实价格", cv.lbl_price.text().startswith("$"),
   cv.lbl_price.text())
ok("6. 图表涨跌幅为 —", cv.lbl_change.text() == "—")
ok("6. 图表状态明确说明（v36 起为真实报价走势，非 K 线）",
   "非交易所 K 线" in getattr(cv.chart, "_status", "")
   and getattr(cv.chart, "onchain_view", None) is not None,
   getattr(cv.chart, "_status", ""))
ok("6. 周期按钮为空（无无效按钮）", len(cv._interval_buttons) == 0,
   len(cv._interval_buttons))
ok("6. 没有 K 线请求线程", cv._load() is None)
ok("6. 蜡烛数据为空而不是伪造", len(cv.chart.candles) == 0)

# 链上报价到达图表页时同步刷新
q2 = dict(q); q2["price"] = 0.0625
w._on_onchain_quote({SYM: q2})
pump()
ok("6. 图表价格跟随链上报价", "0.0625" in cv.lbl_price.text(),
   cv.lbl_price.text())

# ---- 7. 置顶 / 排序 / 持久化 ----
w._set_pinned(SYM, True)
pump()
ok("7. 链上品种可置顶", SYM in w.pinned and row._pinned)
ok("7. 置顶状态落盘", SYM in (w.config.get("pinned_symbols") or []))
w._set_pinned(SYM, False)
ok("7. 可取消置顶", SYM not in w.pinned)
ok("7. 自选顺序持久化", SYM in (w.config.get("symbols") or []))

# 普通品种图表仍走原路径（不回归）
w._open_chart("BTC")
pump()
ok("8. 普通品种仍有 K 线周期", len(w.chart_view._interval_buttons) > 0
   and not getattr(w.chart_view, "_no_kline", True))

print("\n=== v32: %d checks, %d failed ===" % (CHECKS[0], len(FAILS)))
if FAILS:
    print("FAILED: " + ", ".join(FAILS))
from tests.qt_exit import finish
finish(1 if FAILS else 0)
