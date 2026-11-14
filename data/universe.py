# -*- coding: utf-8 -*-
"""各市场「全部」页的品类清单，按总市值从大到小排列。

数据由 tools/rebuild_universe_marketcap.py 生成（真实市值降序）：
  crypto  前 200（CoinLore 市值 + 币安 USDT 现货白名单）
  cn      沪深 A 股前 100（新浪市值榜）
  hk      港股前 200（腾讯行情全量枚举，按总市值）
  us      美股前 500（Nasdaq screener，按市值）

清单随程序打包，完全离线可用；价格仍由行情接口实时补全。
"""
import json
import os
import sys
from typing import Dict, List, Tuple

# 各市场「全部」页展示数量（用户指定：加密 200 / 美股 500 / A股 100 / 港股 200）
COUNTS = {"crypto": 200, "cn": 100, "hk": 200, "us": 500}
TOP_N = 500      # 兼容旧调用：允许的最大条数

# JSON 缺失时的最小回退（保证界面永远能显示列表）
_FALLBACK: Dict[str, List[Tuple[str, str]]] = {
    "crypto": [("BTC", "Bitcoin"), ("ETH", "Ethereum"),
               ("SOL", "Solana"), ("BNB", "BNB"), ("XRP", "XRP"),
               ("DOGE", "Dogecoin"), ("ZEC", "Zcash"),
               ("NEAR", "NEAR Protocol"), ("ARB", "Arbitrum")],
    "cn": [("SH:600519", "贵州茅台"), ("SZ:300750", "宁德时代"),
           ("SZ:000001", "平安银行"), ("SH:601318", "中国平安")],
    "hk": [("HK:00700", "腾讯控股"), ("HK:09988", "阿里巴巴-W"),
           ("HK:01810", "小米集团-W"), ("HK:03690", "美团-W")],
    "us": [("US:AAPL", "苹果"), ("US:NVDA", "英伟达"),
           ("US:MSFT", "微软"), ("US:TSLA", "特斯拉")],
}


def _json_path() -> str:
    """兼容源码运行与 PyInstaller 单文件打包。"""
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        p = os.path.join(bundle, "data", "top300.json")
        if os.path.exists(p):
            return p
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "top300.json")


def _load() -> Dict[str, List[Tuple[str, str]]]:
    """只解析四个市场键；JSON 里的 exchanges / crypto_sources 等元数据
    是字符串列表，不能当 (代码, 名称) 解包，否则会整份回退到最小清单。"""
    keys = ("crypto", "cn", "hk", "us")
    try:
        with open(_json_path(), "r", encoding="utf-8") as f:
            raw = json.load(f)
        out = {}
        for key in keys:
            pairs = []
            for e in raw.get(key) or []:
                if isinstance(e, (list, tuple)) and len(e) >= 2 \
                        and isinstance(e[0], str) and e[0]:
                    pairs.append((str(e[0]), str(e[1])))
            out[key] = pairs
        if all(len(out[k]) >= 10 for k in keys):
            return {k: v[:TOP_N] for k, v in out.items()}
    except (OSError, ValueError, TypeError):
        pass
    return {k: list(v) for k, v in _FALLBACK.items()}


UNIVERSE: Dict[str, List[Tuple[str, str]]] = _load()

CRYPTO = UNIVERSE.get("crypto", [])
CN = UNIVERSE.get("cn", [])
HK = UNIVERSE.get("hk", [])
US = UNIVERSE.get("us", [])


def all_of(market: str) -> List[str]:
    """该市场「全部」页的品种代码（按市值降序）。"""
    n = COUNTS.get(market, TOP_N)
    return [s for s, _ in UNIVERSE.get(market, [])][:n]


def count_of(market: str) -> int:
    return len(all_of(market))


def names(market: str) -> Dict[str, str]:
    n = COUNTS.get(market, TOP_N)
    return {s: n2 for s, n2 in UNIVERSE.get(market, [])[:n]}


def name_of(symbol: str) -> str:
    for entries in UNIVERSE.values():
        for s, n in entries:
            if s == symbol:
                return n
    return ""


def market_of(symbol: str) -> str:
    if symbol.startswith(("SH:", "SZ:")):
        return "cn"
    if symbol.startswith("HK:"):
        return "hk"
    if symbol.startswith("US:"):
        return "us"
    return "crypto"
