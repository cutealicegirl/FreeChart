# -*- coding: utf-8 -*-
"""排序元数据：市值 / 流动性 / 创立上市时间。

阶段 3 的排序要求「必须基于真实数据」。行情快照 Ticker 只有价格、
涨跌幅、成交额，缺市值、流动性、上市时间，因此这里单独提供批量元数据：

* 加密货币：CoinLore /api/tickers/ 的 market_cap_usd、volume24、rank
  （复用 fundamentals 的 30 分钟内存缓存，不额外发请求）；
* 股票：腾讯行情批量接口 f[45] 总市值 / f[44] 流通市值 / f[38] 换手率
  / f[37] 成交额，60 只一批，一次请求覆盖一页；
* 创立 / 上市年份：内置资料库 about.py 的 since（仅收录品种有值）。

流动性统一采用「换手率 %」口径：股票直接取行情源 f[38]；加密用
24h 成交额 ÷ 流通市值 × 100（两者同为 USD，是可计算的真实比率）。
任何字段拿不到都是 None，绝不填 0、绝不估算、绝不用价格倒推市值。

结果落盘缓存 7 天，断网时仍可按上次的真实快照排序。
"""
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from . import fundamentals
from .about import about as about_of
from .api_base import HTTP
from .tencent_stock_api import is_stock_symbol, to_tencent_code

_TENCENT = "https://qt.gtimg.cn/q="
_BATCH = 60
_TOTAL_CAP, _FLOAT_CAP, _TURNOVER, _AMOUNT = 45, 44, 38, 37
_DISK_TTL = 86400 * 7

_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_LOADED = False
_QUOTE_RE = re.compile(r'v_(\w+)="(.*)"')


def _cache_file() -> str:
    return os.path.join(os.path.dirname(fundamentals.cache_path()),
                        "rank_meta.json")


def load_cached() -> Dict[str, Dict[str, Any]]:
    """读磁盘缓存（启动时立即有上一次的真实排序依据）。"""
    global _CACHE, _CACHE_LOADED
    if _CACHE_LOADED:
        return dict(_CACHE)
    _CACHE_LOADED = True
    try:
        with open(_cache_file(), "r", encoding="utf-8") as f:
            raw = json.load(f)
        now = time.time()
        for sym, row in raw.items():
            if isinstance(row, dict) and now - float(row.get("asof") or 0) \
                    < _DISK_TTL:
                _CACHE[sym] = row
    except Exception:
        pass
    return dict(_CACHE)


def _save_cache():
    try:
        with open(_cache_file(), "w", encoding="utf-8") as f:
            json.dump(_CACHE, f, ensure_ascii=False)
    except Exception:
        pass


def listed_year(symbol: str) -> Optional[int]:
    """内置资料库里的创立 / 上市年份；未收录返回 None。"""
    raw = str((about_of(symbol) or {}).get("since") or "")
    m = re.search(r"(1[89]\d{2}|20\d{2})", raw)
    return int(m.group(1)) if m else None


def _num(fields, idx) -> Optional[float]:
    try:
        v = float(fields[idx])
    except (TypeError, ValueError, IndexError):
        return None
    return v if v > 0 else None


def _stock_batch(symbols: List[str], timeout: float) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for i in range(0, len(symbols), _BATCH):
        group = symbols[i:i + _BATCH]
        codes = []
        for s in group:
            try:
                codes.append(to_tencent_code(s))
            except Exception:
                continue
        if not codes:
            continue
        try:
            r = HTTP.get(_TENCENT + ",".join(codes), timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0"})
            r.encoding = "gbk"
            text = r.text
        except Exception:
            continue
        for line in text.split(";"):
            m = _QUOTE_RE.match(line.strip())
            if not m:
                continue
            qt_code, fields = m.group(1), m.group(2).split("~")
            if len(fields) <= _TOTAL_CAP:
                continue
            market = qt_code[:2].upper()
            raw = qt_code[2:].split(".")[0]
            symbol = f"{market}:{raw.upper()}"
            cap = _num(fields, _TOTAL_CAP)         # 亿元（本市场计价货币）
            fcap = _num(fields, _FLOAT_CAP)
            turnover = _num(fields, _TURNOVER)     # 行情源换手率 %
            amount = _num(fields, _AMOUNT)
            if cap is None and fcap is None and turnover is None:
                continue
            out[symbol] = {
                "cap": cap, "float_cap": fcap,
                "turnover": turnover,
                "amount": amount,
                "cap_unit": "亿元（本市场计价货币）",
                "source": "腾讯行情", "asof": time.time(),
            }
    return out


def snapshot(symbols: List[str], timeout: float = 8.0) -> Dict[str, dict]:
    """批量取排序元数据。离线 / 断网时只返回内置创立年份，不编造数值。

    返回 {代码: {cap, float_cap, turnover, listed_year, source, asof}}。
    """
    global _CACHE
    load_cached()
    if fundamentals._offline():
        # 离线环境（含回归测试）：只用内置资料库的年份，绝不发网络请求
        return {s: {"cap": None, "float_cap": None, "turnover": None,
                    "listed_year": listed_year(s),
                    "source": "内置资料库" if listed_year(s) else "",
                    "asof": 0.0}
                for s in symbols}

    out: Dict[str, dict] = {}
    stocks = [s for s in symbols if is_stock_symbol(s)]
    cryptos = [s for s in symbols if not is_stock_symbol(s)]

    if cryptos:
        try:
            rows = fundamentals._crypto_rows(timeout)
        except Exception:
            rows = {}
        for s in cryptos:
            row = rows.get(s.upper())
            if not row:
                continue
            cap = row.get("cap")
            vol = row.get("volume24")
            turnover = (vol / cap * 100.0) if (cap and vol) else None
            out[s] = {
                "cap": cap, "float_cap": cap,
                "turnover": turnover, "amount": vol,
                "cap_unit": "USD（CoinLore 流通市值）",
                "source": "CoinLore", "asof": time.time(),
            }

    out.update(_stock_batch(stocks, timeout))
    # 磁盘缓存里上一轮成功的值作为断网兜底（带 7 天 TTL）
    for s in symbols:
        old = _CACHE.get(s)
        if s not in out and old:
            out[s] = dict(old)
        elif s in out and old:
            for k in ("cap", "float_cap", "turnover"):
                if out[s].get(k) is None and old.get(k) is not None:
                    out[s][k] = old[k]
        out.setdefault(s, {})
        out[s]["listed_year"] = listed_year(s)
        out[s].setdefault("source", "")
        out[s].setdefault("asof", 0.0)

    for s, row in out.items():
        if row.get("cap") is not None or row.get("turnover") is not None:
            _CACHE[s] = row
    _save_cache()
    return out


def metric(row: dict, key: str) -> Optional[float]:
    """取排序用的数值；None 表示该品种没有这个公开数据。"""
    if not row:
        return None
    v = row.get(key)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None
