# -*- coding: utf-8 -*-
"""v35 回归：一个非法交易对不再让整个加密货币行情空白。

复现的真实故障：用户自选里收藏了链上合约品种 ONCHAIN:<addr>，旧版把它
拼成 "<addr>USDT" 送进币安批量接口；该接口对含无效交易对的 symbols 数组
返回 HTTP 400，于是同一批 100 个币种全部取不到价，界面表现为「加密货币
打开直接没数据」。

验收点（默认离线）：
1. 合法代码过滤：链上合约、股票、含空格/符号的代码绝不进请求；
2. 批请求 400 Invalid symbol 时二分拆分，只丢弃真正无效的那一个；
3. 无效交易对被缓存，后续刷新不再重复拆分、不再带它发请求；
4. 非 400 的错误不拆分（避免网络故障时放大请求量）；
5. MarketManager 分组路由把链上品种排除在交易所源之外；
6. fetch_quote 对链上品种不发必然 400 的请求；
7. ensure_meta 为老配置补链上元数据并落盘，且不编造价格/名称。
"""
import json
import os
import sys
import tempfile
from urllib.parse import unquote

_TMP = tempfile.mkdtemp(prefix="ct_v35_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from core.config import Config
from data import binance_api as ba, onchain
from data import market_manager as mm
from data.api_base import Ticker

FAILS = []
CHECKS = [0]
ONCHAIN = "ONCHAIN:9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump"


def ok(name, cond, extra=""):
    CHECKS[0] += 1
    print(("PASS " if cond else "FAIL ") + name +
          (("  " + str(extra)) if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


class FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


CALLS = []
BAD = "BADCOINUSDT"


def fake_get(url, timeout=None, **kw):
    pairs = json.loads(unquote(url.split("?symbols=", 1)[1]))
    CALLS.append(list(pairs))
    if BAD in pairs:
        return FakeResp(400, {"code": -1121, "msg": "Invalid symbol."})
    return FakeResp(200, [{
        "symbol": p, "lastPrice": "100.5", "priceChangePercent": "-1.25",
        "highPrice": "110.0", "lowPrice": "90.0", "quoteVolume": "123456.0",
    } for p in pairs])


print("=== v35 · 批量行情容错回归 ===\n")

# ---------- 1. 合法代码过滤 ----------
pairs = ba.BinanceApi.legal_pairs(
    ["BTC", "eth", "ONCHAIN:" + "a" * 44, "SH:600519", "US:AAPL",
     "BAD COIN", "", None, "SOL"])
ok("1. 只保留合法基础代码", pairs == ["BTCUSDT", "ETHUSDT", "SOLUSDT"], pairs)

# ---------- 2~3. 400 拆分 + 无效缓存 ----------
orig_get = ba.HTTP.get
ba.HTTP.get = fake_get
try:
    api = ba.BinanceApi()
    syms = ["BTC", "ETH", "SOL", "BNB", "XRP", "BADCOIN",
            ONCHAIN, "SH:600519", "DOGE", "AR"]
    r1 = api.fetch_tickers(syms)
    ok("2. 坏品种不影响同批其它币种",
       set(r1) == {"BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "AR"},
       sorted(r1))
    ok("3. 价格字段解析正确", abs(r1["BTC"].last_price - 100.5) < 1e-9
       and abs(r1["BTC"].change_pct + 1.25) < 1e-9)
    ok("4. 发生了拆分重试", len(CALLS) > 1, len(CALLS))
    ok("5. 无效交易对被记住", BAD in api._invalid, api._invalid)
    ok("6. 链上/股票从未进入任何请求",
       all(not any(":" in p or "ONCHAIN" in p for p in c) for c in CALLS))

    CALLS.clear()
    r2 = api.fetch_tickers(syms)
    ok("7. 第二次刷新不再请求坏品种",
       all(BAD not in c for c in CALLS), CALLS)
    ok("8. 第二次刷新结果一致", set(r2) == set(r1))

    # ---------- 4. 非 400 错误不拆分 ----------
    def fail_get(url, timeout=None, **kw):
        raise OSError("network down")
    ba.HTTP.get = fail_get
    CALLS.clear()
    api2 = ba.BinanceApi()
    try:
        api2.fetch_tickers(["BTC", "ETH"])
        ok("9. 网络故障应向上抛错", False, "未抛 MarketApiError")
    except mm.MarketApiError:
        ok("9. 网络故障应向上抛错（交上层切源）", True)
    ok("10. 网络故障不放大请求数", len(api2._invalid) == 0)

    # ---------- 5~6. MarketManager 分组与单品种报价 ----------
    m = mm.MarketManager("")
    seen = {}

    def crypto_stub(s):
        seen["crypto"] = list(s)
        return {"BTC": Ticker("BTC", last_price=1.0)}

    def stock_stub(s):
        seen["stock"] = list(s)
        return {"SH:600519": Ticker("SH:600519", last_price=2.0)}

    m.crypto_chain[0].fetch_tickers = crypto_stub
    m.stock_api.fetch_tickers = stock_stub
    merged = m.fetch_tickers(["BTC", "ETH", ONCHAIN, "SH:600519"])
    ok("11. 链上品种不进交易所批量请求",
       seen.get("crypto") == ["BTC", "ETH"] and ONCHAIN not in seen.get("crypto", []),
       seen.get("crypto"))
    ok("12. 股票仍走腾讯源", seen.get("stock") == ["SH:600519"], seen.get("stock"))
    ok("13. 两组结果正常合并", set(merged) == {"BTC", "SH:600519"}, set(merged))

    called = []
    ba.HTTP.get = lambda *a, **k: called.append(a) or FakeResp(200, {})
    ok("14. 链上品种 fetch_quote 不发交易所请求",
       m.fetch_quote(ONCHAIN) == (0.0, 0.0) and not called, called)
finally:
    ba.HTTP.get = orig_get

# ---------- 7. 老配置元数据补齐 ----------
cfgdir = os.path.join(_TMP, "CryptoTicker")
os.makedirs(cfgdir, exist_ok=True)
cfgpath = os.path.join(cfgdir, "config.json")
with open(cfgpath, "w", encoding="utf-8") as f:
    json.dump({"symbols": ["BTC", ONCHAIN]}, f)
cfg = Config()
ok("15. 老配置读取时 onchain_symbols 为空", not cfg.get("onchain_symbols"))
meta = onchain.ensure_meta(cfg)
ok("16. 为链上品种补了元数据", ONCHAIN in meta, list(meta))
ok("17. 元数据含真实地址与链名",
   meta[ONCHAIN]["address"] == onchain.address_of(ONCHAIN)
   and meta[ONCHAIN]["chain"] == "Solana", meta.get(ONCHAIN))
ok("18. 不编造价格 / 名称 / 供应量",
   meta[ONCHAIN].get("name", "") == "" and meta[ONCHAIN].get("price") is None
   and meta[ONCHAIN].get("supply") == 0.0)
with open(cfgpath, encoding="utf-8") as f:
    saved = json.load(f)
ok("19. 元数据已落盘", ONCHAIN in (saved.get("onchain_symbols") or {}), list(saved))
cfg2 = Config()
ok("20. 重启后不会重复补写",
   onchain.ensure_meta(cfg2) == meta
   and len(cfg2.get("onchain_symbols")) == 1)

print(f"\n=== {CHECKS[0] - len(FAILS)}/{CHECKS[0]} 通过 ===")
if FAILS:
    print("失败项：" + "; ".join(FAILS))
    sys.exit(1)
