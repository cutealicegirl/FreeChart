# -*- coding: utf-8 -*-
"""桌面端统一资产搜索适配层（对应任务书 三、七）。

把不同数据源的搜索结果先归一成 core.asset_search 的统一 hit 结构，
再按 asset_id 去重、按相关性排序，避免「股票/CEX/链上各搞一套」。

数据源：
- 加密货币（CEX）：MarketManager 走 Binance 全量代码本地过滤；
- 股票：MarketManager 走腾讯 smartbox 联想；
- 链上代币：contract_search.search_by_name（本地索引，名称/别名/Symbol）；
- 完整合约地址：由 main_window 的 ContractWorker 单独解析（精确优先）。

统一 hit 在兼容旧字段（symbol/name/kind/label）之外，新增：
asset_type / market / chain / address / id / relevance，
供 UI 清楚标识资产类型、市场、所属区块链。
"""
from core import asset_search as A

MARKET_LABEL = {
    "crypto": "加密货币", "cn": "A股", "hk": "港股", "us": "美股",
    "sh": "沪市A股", "sz": "深市A股",
}


def _kind_of(hit: dict) -> str:
    """按统一模型生成展示标签（含市场/链），不伪造数据。"""
    t = hit.get("asset_type")
    if t == A.ASSET_ONCHAIN:
        chain = hit.get("chain") or "链上"
        return f"链上代币 · {chain}"
    if t == A.ASSET_STOCK:
        return MARKET_LABEL.get(hit.get("market"), "股票")
    if t == A.ASSET_CEX:
        return "加密货币"
    return hit.get("kind") or "资产"


def _stock_market(symbol: str) -> str:
    """从内部 symbol（US:NVDA / SH:600519 / HK:00700）推断市场。"""
    p = symbol.split(":", 1)[0].lower() if ":" in symbol else ""
    if p in ("sh", "sz"):
        return "cn"
    return p or "crypto"


def adapt_market_results(results: list) -> list:
    """把 MarketManager.search 的 [{symbol,name,kind}] 归一为统一 hit。"""
    out = []
    for it in results or []:
        if not isinstance(it, dict):
            continue
        sym = str(it.get("symbol") or "")
        if not sym:
            continue
        kind = str(it.get("kind") or "")
        stock = ("A股" in kind or "美股" in kind or "港股" in kind
                 or ":" in sym and not sym.startswith("ONCHAIN:"))
        if sym.startswith("ONCHAIN:") or "链上" in kind:
            atype, market = A.ASSET_ONCHAIN, "onchain"
        elif stock:
            atype, market = A.ASSET_STOCK, _stock_market(sym)
        else:
            atype, market = A.ASSET_CEX, "crypto"
        label = sym.split(":", 1)[1] if (":" in sym and atype != A.ASSET_ONCHAIN) else sym
        h = A.make_hit(sym, label=label, name=str(it.get("name") or ""),
                       asset_type=atype, market=market)
        h["kind"] = kind or _kind_of(h)
        out.append(h)
    return out


def adapt_onchain_name_hits(hits: list) -> list:
    """把 contract_search.search_by_name 的链上结果归一为统一 hit。"""
    out = []
    for it in hits or []:
        if not isinstance(it, dict):
            continue
        addr = str(it.get("address") or "")
        sym = str(it.get("symbol") or "")
        if not addr:
            continue
        # 内部 symbol 用 ONCHAIN:<address>，与图表链路一致
        from data import onchain
        internal = onchain.make_symbol(addr)
        h = A.make_hit(internal,
                       label=sym or str(it.get("name") or ""),
                       name=str(it.get("name") or ""),
                       asset_type=A.ASSET_ONCHAIN, market="onchain",
                       chain=str(it.get("chain") or ""), address=addr,
                       aliases=[sym, str(it.get("name") or "")])
        h["kind"] = _kind_of(h)
        out.append(h)
    return out


def unified_search(query: str, manager, *, include_onchain: bool = True) -> list:
    """统一搜索：本地索引优先 + 远程联想补充 + 相关性排序 + 去重。

    manager.search() 内部对单个源失败是「静默降级」（不抛异常），
    这里再做一层：全部源都无结果时返回空列表（由 UI 显示「无结果」），
    网络整体失败由 SearchWorker.failed 信号单独上报。
    """
    q = (query or "").strip()
    if not q:
        return []
    market_hits: list = []
    state = {"network_failed": False}
    try:
        market_hits = adapt_market_results(manager.search(q))
    except Exception:                     # noqa: BLE001 - 搜索整体失败不阻塞链上结果
        state["network_failed"] = True
    onchain_hits: list = []
    if include_onchain:
        try:
            from data import contract_search
            onchain_hits = adapt_onchain_name_hits(
                contract_search.search_by_name(q))
        except Exception:                # noqa: BLE001
            pass
    merged = A.merge_hits(market_hits, onchain_hits, query=q, limit=60)
    # 补齐 kind 展示标签（去重/排序后可能来自不同源）
    for h in merged:
        h.setdefault("kind", _kind_of(h))
    return merged


def history_view(entries: list) -> list:
    """把配置里的历史（可能含旧字符串）归一为可渲染对象。"""
    return A.normalize_history(entries)
