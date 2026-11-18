# -*- coding: utf-8 -*-
"""链上标的历史 K 线数据源（真实 DEX OHLCV，不伪造任何数据）。

背景
----
旧版链上标的 ``ONCHAIN:<合约地址>`` 只有 Rugcheck 实时报价 + 本设备逐次采样的
[ts, price] 折线，**没有任何真实历史 OHLCV 来源**，因此图表首次打开必然空白。

本模块把「链上历史 K 线」作为一等公民接入，采用真实公开 DEX 聚合接口：

  主源 GeckoTerminal API v2（免费 / 无需 key / 返回真实 OHLCV + 成交量）
  备源 CoinGecko onchain OHLC（免费 / 无需 key / 真实 OHLC，但不提供成交量）

数据源适配、周期映射、交易池解析（含迁移重解析）、分页回溯、标准化清洗、
缓存与状态上报都在此收口。上层 ``data.klines`` 只做分派，界面无需感知细节。

数据红线
--------
1. 只返回接口真实返回的 OHLCV；拿不到就返回空并标注原因，绝不插值 / 外推 /
   复制当前价到过去 / 拼接不同交易对。
2. 每根 K 线都做 OHLC 约束、成交量非负、时间戳单位与排序去重校验。
3. 价格单位统一为 USD（接口 currency=usd）；时间戳统一为 Unix 秒。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import List, Optional

from data import onchain
from core import kline_time as _kt
from data.api_base import HTTP, MarketApiError

# ---------------- 数据源配置 ----------------
_GT_BASE = "https://api.geckoterminal.com/api/v2"
_GT_SEARCH = _GT_BASE + "/search/pools"
_GT_POOLS = _GT_BASE + "/networks/{net}/tokens/{addr}/pools"
_GT_OHLCV = _GT_BASE + "/networks/{net}/pools/{pool}/ohlcv/{tf}"
_CG_OHLC = ("https://api.coingecko.com/api/v3/coins/"
            "{platform}/contract/{addr}/ohlc")

SOURCE_GECKO = "GeckoTerminal DEX"
SOURCE_COINGECKO = "CoinGecko onchain"

# 地址 → GeckoTerminal 网络名的候选（EVM 链无法从地址本身判断，逐个探测）
_NETWORK_HINTS = {
    "Solana": ["solana"],
    "Tron": ["tron"],
    "EVM": ["eth", "bsc", "base", "arbitrum", "polygon_pos",
            "avax_c_chain", "optimism", "fantom"],
}

# 统一周期 → (GeckoTerminal timeframe, aggregate)
_GT_TF = {
    "1m": ("minute", 1), "5m": ("minute", 5),
    "15m": ("minute", 15), "30m": ("minute", 30),
    "1h": ("hour", 1), "2h": ("hour", 2), "4h": ("hour", 4),
    "6h": ("hour", 6), "12h": ("hour", 12),
    "1d": ("day", 1), "3d": ("day", 3),
    "1w": ("week", 1), "1M": ("month", 1),
}
# 周期 -> 桶秒数；仅作兼容 / 校验，真正的边界统一由 core.kline_time 计算
_TF_SECONDS = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600,
    "12h": 43200, "1d": 86400, "3d": 259200,
    "1w": 604800, "1M": 2592000,
}
# CoinGecko 平台名候选
_CG_PLATFORM = {"Solana": "solana", "Tron": "tron", "EVM": "ethereum"}

ONCHAIN_INTERVALS = [
    ("1分", "1m"), ("5分", "5m"), ("15分", "15m"), ("30分", "30m"),
    ("1时", "1h"), ("2时", "2h"), ("4时", "4h"),
    ("6时", "6h"), ("12时", "12h"),
    ("日K", "1d"), ("3日", "3d"), ("周K", "1w"), ("月K", "1M"),
]
_LIMIT = 1000
_POOL_TTL = 6 * 3600.0        # 交易池解析缓存有效期
_RESOLVE_TIMEOUT = 4.0        # 单次池解析超时（不可达时快速失败）
_OHLCV_TIMEOUT = 6.0          # 单次 OHLCV 请求超时
_TOTAL_BUDGET = 15.0          # 单次 fetch_ohlcv 全链路总预算（秒），防止卡死

# 单一时钟入口：测试可替换 _now 来模拟跨边界 / 超时，无需引入 freezegun
_now = time.time


class _Deadline:
    """一次取数的全局时间预算；超时后所有后续网络请求直接跳过。"""

    def __init__(self, seconds: float):
        self.end = _now() + seconds

    def left(self) -> float:
        return self.end - _now()

    def ok(self) -> bool:
        return self.left() > 0.4

    def timeout(self) -> float:
        # 单次请求超时不超过剩余预算
        return max(0.5, min(_OHLCV_TIMEOUT, self.left() - 0.2))


@dataclass
class Bar:
    """一根标准化后的真实 K 线（字段与 data.klines.Candle 一致，便于转换）。"""
    ts: float
    time_label: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    volume_reliable: bool = True   # CoinGecko 备源无成交量时为 False
    pool: str = ""                 # 来源交易池 ID：跨池不可无缝拼接


def pool_of(bars) -> str:
    """取一批 K 线的交易池身份；空串表示来源未知（旧缓存）。"""
    for b in bars or []:
        p = getattr(b, "pool", "") or ""
        if p:
            return p
    return ""


def pools_compatible(a, b) -> bool:
    """两批 K 线能否安全拼接。

    只有**双方都有明确池身份且不同**时才判不兼容。旧缓存可能尚未记录池，
    此时不误伤；但新数据一旦给出不同池，必须拒绝衔接，因为把迁移前后的
    两段走势接成一条连续 K 线是数据造假。
    """
    pa, pb = pool_of(a), pool_of(b)
    return not (pa and pb and pa != pb)


# ---------------- 状态上报 ----------------
_STATUS: dict = {}


def last_status(symbol: str) -> dict:
    """返回该链上标的最近一次 K 线获取状态（只读）。

    state: ok(拿到真实 OHLCV) / empty(源可用但无历史) / no_pool(未找到交易池)
           / unavailable(数据源不可达) / rate_limited / invalid(数据全部未通过校验)
    """
    return dict(_STATUS.get(symbol, {"state": "unknown", "source": "",
                                     "ts": 0, "count": 0, "message": ""}))


def _set_status(symbol: str, state: str, source: str, count: int = 0,
                message: str = ""):
    _STATUS[symbol] = {"state": state, "source": source, "count": count,
                       "ts": _now(), "message": message}


# ---------------- 交易池解析（含迁移重解析） ----------------
def _pool_cache_path() -> str:
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "CryptoTicker", "onchain_pools.json")


def _load_pool_cache() -> dict:
    try:
        with open(_pool_cache_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_pool_cache(data: dict):
    p = _pool_cache_path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def invalidate_pool(address_or_symbol: str):
    """池迁移 / 历史为空时调用：强制下一次重新解析交易池。"""
    key = onchain.address_of(address_or_symbol) or address_or_symbol
    cache = _load_pool_cache()
    if key in cache:
        cache.pop(key, None)
        _save_pool_cache(cache)


def _pick_pool_from_payload(payload: dict) -> Optional[dict]:
    """按流动性 / 24h 成交量 / 活跃度 / 数据完整性综合挑选交易池。

    旧实现只看 reserve_in_usd，会把「TVL 高但 24h 零成交」的死池选成主池，
    结果就是搜索能命中、历史却取不到或极稀疏。现在四个维度共同评分；
    各项真实指标一并返回，供状态诊断使用，不伪造缺失值。
    """
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None
    import math
    best = None
    for row in rows:
        try:
            attrs = row.get("attributes") or {}
            liq = float(attrs.get("reserve_in_usd") or 0)
            vol = float((attrs.get("volume_usd") or {}).get("h24") or 0)
            tx = (attrs.get("txns") or {}).get("h24") or {}
            trades = float(tx.get("buys") or 0) + float(tx.get("sells") or 0)
            pid = str(row.get("id") or "")       # 形如 solana_0x...
            if "_" not in pid:
                continue
            net, pool = pid.split("_", 1)
            if not net or not pool:
                continue
            # 对数评分：避免单个巨鲸池碾压；零成交 / 零流动性直接重罚
            score = (math.log1p(max(liq, 0.0))
                     + 0.8 * math.log1p(max(vol, 0.0))
                     + 0.6 * math.log1p(max(trades, 0.0)))
            if liq <= 0:
                score -= 20
            if vol <= 0:
                score -= 6
            if trades <= 0:
                score -= 6
            cand = {"network": net, "pool": pool, "liq": liq,
                    "volume_24h": vol, "trades_24h": trades,
                    "score": score, "name": attrs.get("name") or ""}
            if best is None or score > best["score"]:
                best = cand
        except (TypeError, ValueError, AttributeError):
            continue
    return best


def _resolve_pool(address: str, allow_cached: bool = True,
                  deadline: Optional[_Deadline] = None) -> Optional[dict]:
    """解析合约地址对应的真实 DEX 交易池。结果落盘缓存，迁移后可强制重解析。"""
    cache = _load_pool_cache()
    hit = cache.get(address)
    if (allow_cached and isinstance(hit, dict)
            and _now() - float(hit.get("ts") or 0) < _POOL_TTL
            and hit.get("network") and hit.get("pool")):
        return hit

    dl = deadline or _Deadline(_RESOLVE_TIMEOUT * 3)
    # 1) 全局搜索：一次请求即可覆盖多链，命中率最高
    if dl.ok():
        try:
            resp = HTTP.get(_GT_SEARCH, params={"query": address, "page": 1},
                            timeout=min(_RESOLVE_TIMEOUT, dl.timeout()),
                            headers={"Accept": "application/json; version=20230302"})
            if resp.status_code == 429:
                # 限流必须向上冒泡，不能被误报成「未找到交易池」：
                # 上层据此区分 rate_limited 与 no_pool 两种完全不同的状态。
                raise MarketApiError("DEX 数据源限流 (HTTP 429)")
            if resp.status_code == 200:
                found = _pick_pool_from_payload(resp.json() or {})
                if found:
                    found["ts"] = _now()
                    cache[address] = found
                    _save_pool_cache(cache)
                    return found
        except MarketApiError:
            raise
        except Exception:                        # noqa: BLE001 - 多源容错
            pass

    # 2) 按链候选逐个探测 /networks/{net}/tokens/{addr}/pools
    # 受 deadline 约束：不可达时不会把 8 条 EVM 链逐个等到超时。
    for net in _NETWORK_HINTS.get(onchain.chain_of(address), []):
        if not dl.ok():
            break
        try:
            resp = HTTP.get(_GT_POOLS.format(net=net, addr=address),
                            params={"page": 1},
                            timeout=min(_RESOLVE_TIMEOUT, dl.timeout()),
                            headers={"Accept": "application/json; version=20230302"})
            if resp.status_code == 429:
                raise MarketApiError("DEX 数据源限流 (HTTP 429)")
            if resp.status_code != 200:
                continue
            found = _pick_pool_from_payload(resp.json() or {})
            if found:
                found["ts"] = _now()
                cache[address] = found
                _save_pool_cache(cache)
                return found
        except MarketApiError:
            raise
        except Exception:                        # noqa: BLE001
            pass
    return None


# ---------------- 标准化清洗 ----------------
def _fmt_label(ts: float, interval: str) -> str:
    # DEX 数据源按 UTC 分桶，标签同源，不能用设备本地时区
    return _kt.label_for(ts, interval, "ONCHAIN:UTC")


def normalize(rows: list, interval: str,
              volume_reliable: bool = True,
              market: str = "crypto",
              pool: str = "") -> List[Bar]:
    """把 [ts, o, h, l, c, v] 原始行标准化为真实 K 线列表。

    - ts 自动识别秒/毫秒/微秒并统一为秒
    - 校验 high>=max(o,c)、low<=min(o,c)、价格>0、成交量>=0
    - 按时间正序，同时间戳去重（保留最后一条）
    - 非法行整条丢弃，不修补、不插值
    - pool 记录来源交易池；跨池数据禁止无缝拼接（见 pools_compatible）
    """
    out = []
    for r in rows:
        try:
            if not isinstance(r, (list, tuple)) or len(r) < 5:
                continue
            raw_ts = float(r[0])
            # 时间戳单位识别（GeckoTerminal 秒 / CoinGecko 毫秒）
            if raw_ts > 1e14:
                ts = raw_ts / 1e6
            elif raw_ts > 1e11:
                ts = raw_ts / 1e3
            else:
                ts = raw_ts
            o, h, l, c = (float(r[1]), float(r[2]), float(r[3]), float(r[4]))
            v = float(r[5]) if len(r) > 5 and r[5] is not None else 0.0
        except (TypeError, ValueError, IndexError):
            continue
        if not (ts > 0 and o > 0 and h > 0 and l > 0 and c > 0):
            continue
        if h + 1e-12 < max(o, c) or l - 1e-12 > min(o, c) or h < l:
            continue
        if v < 0 or v != v:
            continue
        if interval in _TF_SECONDS:
            # 统一走 core.kline_time：UTC 自然周 / 自然月，不再用 604800、
            # 2592000 这类固定秒桶（会导致月K从周四起、30天一月）。
            pseudo = "crypto" if market == "crypto" else (
                "US:X" if market == "us" else "SH:X")
            ts = _kt.bucket_start(ts, interval, pseudo)
        out.append({"ts": ts, "o": o, "h": h, "l": l, "c": c, "v": v})
    if not out:
        return []
    out.sort(key=lambda x: x["ts"])
    dedup = {}
    for x in out:                       # 同桶保留最后一条（最新的真实值）
        dedup[x["ts"]] = x
    return [Bar(ts=x["ts"], time_label=_fmt_label(x["ts"], interval),
                open=x["o"], high=x["h"], low=x["l"], close=x["c"],
                volume=x["v"], volume_reliable=volume_reliable, pool=pool)
            for x in (dedup[t] for t in sorted(dedup))]


def _aggregate(bars: List[Bar], interval: str) -> List[Bar]:
    """把分钟/小时/日线聚合成更大周期（仅用真实基础 K 线）。

    桶起点统一由 core.kline_time 计算（DEX=UTC 自然周 / 自然月），
    输出 ts 是桶起点而不是组内首根的真实 ts，避免跨月跨年错位。
    聚合不产生新价格，只用桶内真实 OHLC。
    """
    if not bars:
        return []
    groups: dict = {}
    for b in bars:
        key = _kt.bucket_start(b.ts, interval, "ONCHAIN:UTC")
        g = groups.setdefault(key, {"ts": key, "o": b.open, "h": b.high,
                                    "l": b.low, "c": b.close, "v": 0.0,
                                    "vr": b.volume_reliable})
        g["h"] = max(g["h"], b.high)
        g["l"] = min(g["l"], b.low)
        g["c"] = b.close
        g["v"] += b.volume    # 从 0 起累加；旧实现多算一次首根，量能虚高
        g["vr"] = g["vr"] and b.volume_reliable
    out = []
    for key in sorted(groups):
        g = groups[key]
        out.append(Bar(ts=key, time_label=_fmt_label(key, interval),
                       open=g["o"], high=g["h"], low=g["l"], close=g["c"],
                       volume=g["v"], volume_reliable=g["vr"],
                       pool=pool_of(bars)))
    return out


# ---------------- 主源：GeckoTerminal OHLCV ----------------
def _fetch_gecko(address: str, interval: str, limit: int,
                 before_ts: Optional[float], resolve_attempt: int = 0,
                 deadline: Optional[_Deadline] = None) -> List[Bar]:
    tf, aggregate = _GT_TF.get(interval, ("hour", 1))
    dl = deadline or _Deadline(_TOTAL_BUDGET)
    if not dl.ok():
        raise MarketApiError("取数时间预算耗尽")
    pool = _resolve_pool(address, allow_cached=(resolve_attempt == 0),
                         deadline=dl)
    if not pool:
        raise MarketApiError("未找到该代币的公开 DEX 交易池")
    if not dl.ok():
        raise MarketApiError("取数时间预算耗尽")
    params = {"aggregate": aggregate, "limit": limit,
              "currency": "usd", "page": 1}
    if before_ts and before_ts > 0:
        params["before_timestamp"] = int(before_ts)
    resp = HTTP.get(_GT_OHLCV.format(net=pool["network"],
                                     pool=pool["pool"], tf=tf),
                    params=params, timeout=dl.timeout(),
                    headers={"Accept": "application/json; version=20230302"})
    if resp.status_code == 429:
        raise MarketApiError("DEX 数据源限流 (HTTP 429)")
    if resp.status_code != 200:
        raise MarketApiError(f"DEX 数据源返回 HTTP {resp.status_code}")
    payload = resp.json() or {}
    attrs = ((payload.get("data") or {}).get("attributes")
             if isinstance(payload, dict) else None) or {}
    rows = attrs.get("ohlcv_list") or []
    # 记录来源池身份：回溯分页一旦跨池，上层必须断开而不是无缝拼接。
    pool_id = f"{pool['network']}_{pool['pool']}"
    bars = normalize(rows, interval, volume_reliable=True, pool=pool_id)
    # 池迁移：曾解析到池但完全无历史 → 强制重解析一次再试（仅在预算允许时）
    if not bars and resolve_attempt == 0 and before_ts is None and dl.ok():
        invalidate_pool(address)
        return _fetch_gecko(address, interval, limit, before_ts,
                            resolve_attempt=1, deadline=dl)
    return bars


# ---------------- 备源：CoinGecko onchain OHLC ----------------
def _fetch_coingecko(address: str, interval: str, limit: int,
                     before_ts: Optional[float],
                     deadline: Optional[_Deadline] = None) -> List[Bar]:
    """CoinGecko 备源：仅提供**日线**粒度 OHLC，无成交量。

    重要修复：旧实现把所有周期都按 "1d" 解析后直接返回，却在 UI 上按请求的
    1h/15m 等周期打标签——这是把日线伪装成小时线的数据造假。现在：
      - 只有 1d/3d/1w/1M（日及以上）才使用该备源，并正确聚合；
      - 分钟 / 小时周期直接返回空并说明原因，交由上层给出明确空状态，
        绝不用日线数据冒充低周期 K 线。
    """
    if interval not in ("1d", "3d", "1w", "1M"):
        # 诚实拒绝：CoinGecko 无分钟/小时级 OHLC
        raise MarketApiError(
            f"CoinGecko 仅提供日线粒度，无法提供 {interval}；"
            f"该周期需要 GeckoTerminal 等真实分钟/小时数据源")
    dl = deadline or _Deadline(_TOTAL_BUDGET)
    if not dl.ok():
        raise MarketApiError("取数时间预算耗尽")
    platform = _CG_PLATFORM.get(onchain.chain_of(address), "solana")
    # CoinGecko 只提供 1 日 OHLC 粒度，days 控制长度；按回溯时间换算天数
    if before_ts and before_ts > 0:
        days = max(2, min(365, int((_now() - before_ts) / 86400) + 2))
    else:
        days = 365
    resp = HTTP.get(_CG_OHLC.format(platform=platform, addr=address),
                    params={"vs_currency": "usd", "days": days},
                    timeout=dl.timeout(),
                    headers={"Accept": "application/json"})
    if resp.status_code == 429:
        raise MarketApiError("CoinGecko 限流 (HTTP 429)")
    if resp.status_code != 200:
        raise MarketApiError(f"CoinGecko 返回 HTTP {resp.status_code}")
    rows = resp.json() or []
    if not isinstance(rows, list):
        return []
    # CoinGecko 无成交量：v=0 且 volume_reliable=False，界面据此不显示量柱
    bars = normalize([[r[0], r[1], r[2], r[3], r[4], 0.0] for r in rows
                      if isinstance(r, (list, tuple)) and len(r) >= 5],
                     "1d", volume_reliable=False)
    return _aggregate(bars, interval) if interval in ("3d", "1w", "1M") else bars


# ---------------- 对外统一入口 ----------------
def fetch_ohlcv(symbol: str, interval: str, limit: int = _LIMIT,
                before_ts: Optional[float] = None,
                allow_empty: bool = False) -> List[Bar]:
    """取一个链上标的的真实历史 K 线；失败抛 MarketApiError。

    before_ts: 只返回该时刻之前的 K 线（历史回溯分页），None 表示取最新窗口。
    """
    address = onchain.address_of(symbol) or symbol
    if not address:
        _set_status(symbol, "empty", "", 0, "缺少合约地址")
        return []
    if interval not in _GT_TF and interval not in ("3d", "1w", "1M"):
        interval = "1h"

    errors = []
    dl = _Deadline(_TOTAL_BUDGET)
    for name, fn in ((SOURCE_GECKO, _fetch_gecko),
                     (SOURCE_COINGECKO, _fetch_coingecko)):
        if not dl.ok():
            errors.append(f"{name}: 取数时间预算耗尽")
            continue
        try:
            bars = fn(address, interval, limit, before_ts, deadline=dl)
        except Exception as e:                   # noqa: BLE001 - 逐源容错
            errors.append(f"{name}: {e}")
            continue
        if bars:
            _set_status(symbol, "ok", name, len(bars),
                        f"pool={pool_of(bars)}")
            return bars
        errors.append(f"{name}: 无历史数据")
    # 全部数据源都没给数据：诚实上报，绝不编造
    state = "rate_limited" if any("429" in e for e in errors) else (
        "no_pool" if any("交易池" in e for e in errors) else "empty")
    _set_status(symbol, state, " / ".join(n for n, _ in
                ((SOURCE_GECKO, 0), (SOURCE_COINGECKO, 0))), 0,
                "; ".join(errors)[:300])
    if allow_empty:
        return []
    raise MarketApiError("; ".join(errors)[:300])


def has_history(symbol: str) -> bool:
    """最近一次是否拿到真实历史（供界面决定显示蜡烛 vs 采样折线）。"""
    return last_status(symbol).get("state") == "ok"


def intervals() -> list:
    return list(ONCHAIN_INTERVALS)


def default_interval() -> str:
    return "1h"
