# -*- coding: utf-8 -*-
"""链上合约品种：标识、真实报价与元数据。

背景：pump.fun / Raydium 上的新币没有币安现货交易对，也就没有 K 线。
旧逻辑把「有 K 线」当成「能加入自选」的前提，这类币种被直接挡在门外，
连价格都看不到。这里把三件事彻底解耦：

    可收藏    —— 只要链上账户真实存在，就能加入自选 / 置顶 / 看详情
    可看价格  —— 走链上真实报价（Solana: Rugcheck.xyz 代币报告）
    可看 K 线 —— 没有就是没有，图表页明确标注「暂无 K 线数据」

数据原则：只取接口真实返回的字段，缺失一律 None / 空并标注来源与时间，
不估算、不外推、不编造涨跌幅。Rugcheck 不提供 24h 涨跌幅，因此 change
恒为 None，界面显示「—」而不是 0.00%。
"""
import re
import time

from data.api_base import HTTP

PREFIX = "ONCHAIN:"
SOURCE = "Rugcheck.xyz 链上代币报告"
SOURCE_URL = "https://api.rugcheck.xyz/v1/tokens/{mint}/report"

_EVM = re.compile(r"^0x[0-9a-fA-F]{40}$")
_TRON = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")
_B58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def is_onchain(symbol: str) -> bool:
    return isinstance(symbol, str) and symbol.startswith(PREFIX)


def make_symbol(address: str) -> str:
    """用合约地址本身做唯一代码，避免同名代币 / 不同链同名互相覆盖。"""
    return PREFIX + (address or "").strip()


def address_of(symbol: str) -> str:
    return symbol[len(PREFIX):] if is_onchain(symbol) else ""


def is_solana(address: str) -> bool:
    return bool(_B58.match(address or "")) and not _TRON.match(address or "")


def chain_of(address: str) -> str:
    if _EVM.match(address or ""):
        return "EVM"
    if _TRON.match(address or ""):
        return "Tron"
    if is_solana(address):
        return "Solana"
    return ""


def short_address(address: str, head: int = 8, tail: int = 6) -> str:
    if not address:
        return ""
    return address if len(address) <= head + tail + 3 else \
        address[:head] + "…" + address[-tail:]


def blank_meta(address: str, code: str = "", name: str = "", chain: str = "",
               supply: float = 0.0, decimals: int = 0, program: str = "") -> dict:
    """搜索命中后写入配置的最小元数据（离线也能恢复行名称）。"""
    return {
        "address": address, "code": (code or "").upper()[:12],
        "name": name or "", "chain": chain or chain_of(address),
        "supply": supply or 0.0, "decimals": decimals or 0,
        "program": program or "", "source": SOURCE,
    }


def quote(address: str, timeout: float = 8.0) -> dict:
    """取一个链上代币的真实报价。

    返回 dict（键固定，缺失值为 None）：
      price / change / liquidity / holders / supply / decimals /
      code / name / launchpad / source / source_url / ts /
      top_holders / pool_types / market_count（链上真实结构数据，供图表用）

    没有可用数据源或请求失败时返回 {}，由上层保留上次缓存并标注，
    绝不返回编造的数值。
    """
    if not is_solana(address):
        # 目前只有 Solana 有国内可直连的公开链上报价源；EVM / Tron
        # 明确标注无数据，不用交易所价格冒充链上价格。
        return {}
    url = SOURCE_URL.format(mint=address)
    try:
        resp = HTTP.get(url, timeout=timeout,
                        headers={"User-Agent": "Mozilla/5.0",
                                 "Accept": "application/json"})
        if resp.status_code != 200:
            return {}
        data = resp.json() or {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}

    token = data.get("token") or {}
    meta = data.get("tokenMeta") or {}
    verify = data.get("verification") or {}
    launch = data.get("launchpad") or {}
    decimals = token.get("decimals")
    raw_supply = token.get("supply")
    supply = None
    if isinstance(raw_supply, (int, float)) and isinstance(decimals, int):
        try:
            supply = float(raw_supply) / (10 ** decimals)
        except (OverflowError, ValueError):
            supply = None

    def num(v):
        try:
            f = float(v)
            return f if f == f and f not in (float("inf"), float("-inf")) else None
        except (TypeError, ValueError):
            return None

    # 真实链上结构数据：前十大持有地址占比、流动性池类型分布。
    # 没有交易所 K 线时，图表页用这些真实字段画结构图，而不是假蜡烛。
    tops = []
    raw_tops = data.get("topHolders")
    for h in (raw_tops[:10] if isinstance(raw_tops, list) else []):
        if not isinstance(h, dict):
            continue
        pct = num(h.get("pct"))
        if pct is None or pct <= 0:
            continue
        tops.append({"pct": round(pct, 2),
                     "label": short_address(str(h.get("address") or ""))})
    raw_markets = data.get("markets")
    markets = raw_markets if isinstance(raw_markets, list) else []
    pool_counts = {}
    for m in markets:
        if not isinstance(m, dict):
            continue
        key = str(m.get("marketType") or "other")
        pool_counts[key] = pool_counts.get(key, 0) + 1
    pools = sorted(({"label": k, "count": v}
                    for k, v in pool_counts.items()),
                   key=lambda x: -x["count"])[:6]

    price = num(data.get("price"))
    return {
        "price": price if price and price > 0 else None,
        "top_holders": tops,
        "pool_types": pools,
        "market_count": len(markets) if raw_markets is not None else None,
        # Rugcheck 不提供 24h 涨跌幅：保持 None，界面显示「—」
        "change": None,
        "liquidity": num(data.get("totalMarketLiquidity")),
        "holders": num(data.get("totalHolders")),
        "supply": supply,
        "decimals": decimals if isinstance(decimals, int) else None,
        "code": ((meta.get("symbol") or verify.get("symbol") or "")[:12]).upper(),
        "name": meta.get("name") or verify.get("name") or "",
        "launchpad": launch.get("name") or "",
        "source": SOURCE,
        "source_url": url,
        "ts": time.time(),
    }


def as_ticker(symbol: str, q: dict):
    """把链上报价转成 Ticker，供行情行 / 价格条复用现有渲染逻辑。

    change_pct 用 0.0 占位仅为满足数据类字段；调用方需用
    has_change(symbol) 判断是否显示涨跌幅，避免把 0 当成真实跌幅。
    """
    from data.api_base import Ticker
    if not q or q.get("price") is None:
        return None
    return Ticker(symbol=symbol, name=q.get("name") or "",
                  last_price=float(q["price"]), change_pct=0.0,
                  high_24h=0.0, low_24h=0.0, quote_volume_24h=0.0)


def has_change(q: dict) -> bool:
    """链上报价目前没有可信的 24h 涨跌幅，界面应显示「—」。"""
    return bool(q) and q.get("change") is not None


def ensure_meta(config) -> dict:
    """确保每个已收藏的链上品种都有元数据，并写回配置。

    老版本可能只把 ``ONCHAIN:<addr>`` 写进 symbols 却没写 onchain_symbols，
    界面就会显示空白名称；更重要的是这类品种不能被当成交易所代码去拼
    USDT 交易对。这里补最小记录（短地址 + 真实链名），不编造价格、名称
    或供应量，随后由真实链上报价刷新。
    """
    saved = config.get("onchain_symbols") or {}
    meta = dict(saved) if isinstance(saved, dict) else {}
    added = False
    for sym in (config.get("symbols") or []):
        if not is_onchain(sym) or sym in meta:
            continue
        addr = address_of(sym)
        meta[sym] = blank_meta(addr, code=short_address(addr, 6, 4),
                               chain=chain_of(addr))
        added = True
    if added:
        try:
            config.set("onchain_symbols", meta)
            config.save()
        except Exception:
            pass  # 只读环境下仍可正常工作，只是不落盘
    return meta
