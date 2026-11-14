# -*- coding: utf-8 -*-
"""重建 data/top300.json 的「加密货币」清单。

目标：全部页只出现一线主流交易所实际挂牌的主流品种，而不是任意冷门币。
本机可直连的数据源：
  - Binance  data-api.binance.vision  exchangeInfo + ticker/24hr（成交额排名）
  - Gate.io  api.gateio.ws           spot/currency_pairs（第二家交易所交叉校验）
OKX / Coinbase / Huobi(HTX) 的公开接口在当前网络不可达，因此内置一份
「三大所共同挂牌的蓝筹白名单」（ static，随程序打包），与上面两家实测
挂牌集合取交集后一起构成候选，并把来源交易所记录到 exchanges 字段。

其它三个市场（A股/港股/美股）清单保持原样不变。
"""
import json
import os
import sys
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
from data.api_base import HTTP

BINANCE_INFO = "https://data-api.binance.vision/api/v3/exchangeInfo"
BINANCE_24H = "https://data-api.binance.vision/api/v3/ticker/24hr"
GATE_PAIRS = "https://api.gateio.ws/api/v4/spot/currency_pairs"
OUT = os.path.join(_ROOT, "data", "top300.json")

# OKX / Coinbase / Huobi(HTX) 等一线所长期共同挂牌的蓝筹与主流币
BLUE_CHIP = """
BTC ETH BNB SOL XRP DOGE ADA AVAX LINK DOT LTC TRX BCH XLM ATOM NEAR APT
ARB OP SUI SEI TIA INJ UNI AAVE MKR COMP CRV SNX LDO RPL PENDLE ONDO
ALGO HBAR VET ICP FIL AR GRT IMX SAND MANA AXS GALA ENJ CHZ BAT ZEC DASH
ETC EOS XMR XTZ THETA FTM RUNE KAVA ONE ZIL WAVES IOTA NEO QTUM ICX ONT
ETC EGLD FLOW KSM DYDX GMX SUSHI 1INCH BAL YFI UMA REN ZRX LRC OMG ANT
STORJ SKL CELR CTSI OCEAN BAND NMR RLC TRB STMX DENT HOT WIN JASMY
PEPE SHIB BONK WIF FLOKI MEME BOME MOG BRETT TURBO DOGS NOT
TON TRX TAO RENDER FET AGIX OCEAN RNDR WLD JUP PYTH JTO STRK
ENA HYPE ZEC PUMP ONDO ETHFI EIGEN BABY KERNEL LAYER
USDC USDT FDUSD TUSD DAI
""".split()

# 稳定币 / 杠杆代币 / 明显非主流交易品，直接从候选里剔除
DENY = set("""
USDT USDC FDUSD TUSD BUSD DAI USDP USD1 PYUSD EUR PAX USDE USDX
BTCDOWN BTCUP UPUSDT DOWNUSDT BULL BEAR HALF 1000SATS 1000BONK
""".split())

# 排除 Binance 上的美股代币（形如 AAPLB / NVDAB），用美股清单反查
US_STOCKS = set()


def get_json(url, params=None, timeout=20):
    r = HTTP.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def main():
    with open(OUT, "r", encoding="utf-8") as f:
        data = json.load(f)
    for s, _name in data.get("us", []):
        US_STOCKS.add(s.split(":")[-1].upper())

    info = get_json(BINANCE_INFO)
    binance = {}
    for d in info.get("symbols", []):
        if (d.get("quoteAsset") == "USDT" and d.get("status") == "TRADING"
                and d.get("isSpotTradingAllowed", True)):
            binance[d["baseAsset"].upper()] = d.get("baseAsset")
    tickers = get_json(BINANCE_24H)
    volume = {}
    for d in tickers:
        sym = d.get("symbol", "")
        if sym.endswith("USDT") and sym[:-4] in binance:
            try:
                volume[sym[:-4]] = float(d.get("quoteVolume") or 0)
            except (TypeError, ValueError):
                pass

    gate, gate_names = set(), {}
    try:
        for d in get_json(GATE_PAIRS):
            if d.get("quote") in ("USDT", "USDC"):
                base = str(d.get("base", "")).upper()
                if base:
                    gate.add(base)
                    gate_names[base] = d.get("base_name") or base
    except Exception as e:
        print("gate unavailable:", repr(e), flush=True)

    old_names = {s: n for s, n in data.get("crypto", [])}
    exchanges = {}

    def allowed(sym):
        if sym in DENY or not sym or len(sym) > 15:
            return False
        if sym.startswith("1000") or sym.endswith(("UP", "DOWN", "BULL", "BEAR")):
            return False
        # 美股代币：AAPLB / NVDAB ...（去掉尾部 B 是真实美股代码）
        if len(sym) >= 4 and sym.endswith("B") and sym[:-1] in US_STOCKS:
            return False
        return sym in binance

    blue = [s for s in dict.fromkeys(BLUE_CHIP) if allowed(s)]
    cross = [s for s in binance if s in gate and allowed(s)]
    candidates = list(dict.fromkeys(blue + cross))

    # 先按「挂牌交易所数量」再按 24h 成交额，主流程度一目了然
    def score(s):
        n = 2 + (1 if s in gate else 0) + (2 if s in BLUE_CHIP else 0)
        return (-n, -volume.get(s, 0.0), s)

    ranked = sorted(candidates, key=score)[:300]
    for s in ranked:
        ex = ["Binance"]
        if s in gate:
            ex.append("Gate.io")
        if s in BLUE_CHIP:
            ex += ["OKX", "Coinbase", "Huobi"]
        exchanges[s] = ex

    crypto = [[s, old_names.get(s) or gate_names.get(s) or s]
              for s in ranked]
    data["crypto"] = crypto
    data["generated"] = datetime.now().strftime("%Y-%m-%d")
    data["top_n"] = 300
    data["crypto_sources"] = ["Binance", "Gate.io", "OKX", "Coinbase", "Huobi"]
    data["exchanges"] = exchanges
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    print(f"binance={len(binance)} gate={len(gate)} "
          f"blue={len(blue)} cross={len(cross)} -> crypto={len(crypto)}",
          flush=True)
    print("first 20:", [s for s, _ in crypto[:20]], flush=True)
    print("with 3+ exchanges:",
          sum(1 for s in ranked if len(exchanges[s]) >= 3), flush=True)
    print("markets:", {k: len(v) for k, v in data.items()
                       if isinstance(v, list)}, flush=True)


if __name__ == "__main__":
    main()
