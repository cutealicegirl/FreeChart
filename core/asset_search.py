# -*- coding: utf-8 -*-
"""统一资产身份 / 搜索结果适配 / 搜索历史（桌面与 Android 同口径）。

设计原则（对应任务书 三、四、七）：
- 资产唯一标识一律用 **Chain ID + Contract / Mint Address**（链上），
  股票 / CEX 用 **market + symbol**；禁止仅凭名称或 Symbol 合并资产，
  防止同名代币、仿冒代币、不同链资产混淆。
- 统一搜索结果适配层：不同数据源的结果先归一成统一的 hit 结构，
  再按相关性排序、按 asset_id 去重，避免各资产类型各搞一套。
- 搜索历史是**资产对象**而非纯字符串：保存名称 / Symbol / Logo /
  资产类型 / 市场或区块链；按 asset_id 去重、重复移至最前、上限 50 条；
  兼容旧版纯字符串数组（加载时自动包装）。

该模块是纯函数库，不依赖 Qt / 网络，可离线单元测试。
Android 端在 app.js 中实现同口径的 assetId / normalizeHistory /
recordHistory / relevance / mergeHits，并用一致性测试保证两端对齐。
"""
import re
import time
from typing import Iterable, Optional

# ---- 常量 ----
HISTORY_VERSION = 2          # 数据结构版本；1 = 旧版纯字符串
HISTORY_MAX = 50             # 任务书要求 30~50 条

ASSET_STOCK = "stock"
ASSET_CEX = "cex"
ASSET_ONCHAIN = "onchain"

# 链名 -> 稳定 Chain ID（Solana 用 mint，EVM 用链名缩写，避免同地址跨链混淆）
CHAIN_IDS = {
    "solana": "solana", "sol": "solana",
    "ethereum": "eth", "eth": "eth", "erc20": "eth",
    "base": "base",
    "bnb chain": "bsc", "bnbchain": "bsc", "bsc": "bsc", "bnb": "bsc",
    "arbitrum": "arb", "arbitrum one": "arb",
    "optimism": "op",
    "polygon": "polygon", "matic": "polygon",
    "avalanche": "avax", "avax": "avax",
    "sui": "sui", "ton": "ton", "tron": "tron",
    "evm": "evm",
}

_EVM_ADDR = re.compile(r"^0x[0-9a-fA-F]{40}$")
_WS = re.compile(r"\s+")


def _norm(s) -> str:
    """归一化查询：去首尾空格、折叠多余空格、忽略大小写。"""
    return _WS.sub(" ", str(s if s is not None else "").strip()).lower()


def chain_id(chain) -> str:
    """把数据源返回的链名归一为稳定 Chain ID。"""
    if not chain:
        return ""
    key = str(chain).strip().lower()
    return CHAIN_IDS.get(key, key)


def asset_id(hit) -> str:
    """资产唯一标识。

    - 链上：``<chain_id>:<address>``（EVM 地址小写，Solana mint 保持原样）。
    - 股票 / CEX：``<market>:<symbol>``；无 symbol 时退化为查询键。
    - 纯字符串（旧历史）：``q:<归一化查询>``。
    """
    if not isinstance(hit, dict):
        return "q:" + _norm(hit)
    t = hit.get("asset_type") or ""
    addr = str(hit.get("address") or "").strip()
    if t == ASSET_ONCHAIN and addr:
        cid = chain_id(hit.get("chain") or hit.get("chain_id") or "") or "unknown"
        # 任何 0x 开头的 EVM 地址都统一小写（不依赖精确的 40 位长度，
        # 数据源偶尔带前导/尾随字符也能稳定归一化）；Solana mint 大小写敏感，保持原样。
        a = addr.lower() if addr.lower().startswith("0x") else addr
        return cid + ":" + a
    sym = str(hit.get("symbol") or "").strip()
    if sym:
        market = str(hit.get("market") or "").strip() or "na"
        return market + ":" + sym
    return "q:" + _norm(hit.get("query") or hit.get("label") or "")


def make_hit(symbol, *, label="", name="", asset_type="", market="",
             chain="", address="", logo="", query="", aliases=None,
             **extra) -> dict:
    """构造统一搜索结果 hit（所有数据源输出同一结构）。"""
    h = {
        "symbol": str(symbol or ""),
        "label": str(label or symbol or ""),
        "name": str(name or ""),
        "asset_type": asset_type or "",
        "market": market or "",
        "chain": chain or "",
        "address": address or "",
        "logo": logo or "",
        "query": query or "",
        "aliases": list(aliases or []),
    }
    h.update(extra)
    h["id"] = asset_id(h)
    return h


def relevance(query, hit) -> int:
    """相关性评分（越大越靠前）：合约精确 > 代码精确 > 名称精确 >
    代码前缀 > 名称前缀 > 别名 > 包含。合约地址优先精确匹配。"""
    q = _norm(query)
    if not q:
        return 0
    if not isinstance(hit, dict):
        hit = {"symbol": str(hit)}
    sym = _norm(hit.get("symbol"))
    code = _norm(hit.get("label"))
    addr = _norm(hit.get("address"))
    name = _norm(hit.get("name"))
    if addr and q == addr:
        return 200                       # 合约地址精确匹配最高
    if q == sym or q == code:
        return 100
    if q == name:
        return 95
    if code.startswith(q) or sym.startswith(q):
        return 80
    if name.startswith(q):
        return 70
    for a in hit.get("aliases") or []:
        na = _norm(a)
        if na == q:
            return 65
        if na.startswith(q):
            return 55
    if q in code or q in sym or q in name:
        return 40
    for a in hit.get("aliases") or []:
        if q in _norm(a):
            return 30
    return 0


def merge_hits(*groups: Iterable, query: str = "", limit: int = 60) -> list:
    """合并多源结果：按 asset_id 去重、按相关性排序；同分保持源顺序。

    只保留相关性 > 0 的命中（无关联结果不进列表），返回结果带
    ``id`` 与 ``relevance`` 字段，供 UI 直接渲染。
    """
    best: dict = {}
    order = 0
    for g in groups:
        for h in (g or []):
            if not h:
                continue
            score = relevance(query, h)
            if score <= 0:
                continue
            hid = h.get("id") or asset_id(h)
            cand = (score, order, dict(h, relevance=score, id=hid))
            order += 1
            prev = best.get(hid)
            if prev is None or score > prev[0]:
                best[hid] = cand
    ranked = sorted(best.values(), key=lambda x: (-x[0], x[1]))
    out = [c[2] for c in ranked]
    return out[:limit] if limit and limit > 0 else out


# ---------------- 搜索历史 ----------------
def normalize_history(raw) -> list:
    """把旧版（纯字符串）/ 新版（对象）统一成资产对象数组，按 id 去重保序。

    兼容要点：
    - 旧字符串 -> ``{query, label, id:"q:..."}``；
    - 对象缺字段全部补默认；
    - 丢弃 id 为空或重复的记录，不抛异常（配置损坏不能崩程序）。
    """
    out, seen = [], set()
    items = raw if isinstance(raw, list) else []
    for it in items:
        if isinstance(it, str):
            q = it.strip()
            if not q:
                continue
            h = {"query": q, "label": q, "symbol": "", "name": "",
                 "asset_type": "", "market": "", "chain": "", "logo": "",
                 "ts": 0.0, "id": "q:" + _norm(q)}
        elif isinstance(it, dict):
            h = dict(it)
            h.setdefault("query", h.get("label") or h.get("symbol") or "")
            h.setdefault("label", h.get("query") or "")
            for k in ("symbol", "name", "asset_type", "market", "chain", "logo"):
                h.setdefault(k, "")
            h.setdefault("ts", 0.0)
            hid = h.get("id") or asset_id(h)
            if not hid:
                continue
            h["id"] = hid
        else:
            continue
        h["v"] = HISTORY_VERSION
        if h["id"] in seen:
            continue
        seen.add(h["id"])
        out.append(h)
    return out


def record_history(hist, entry, max_items: int = HISTORY_MAX,
                    now: Optional[float] = None) -> list:
    """记录一次**成功**搜索：按 asset_id 去重、移至最前、截断上限。

    entry 可以是资产 hit 对象，也可以是纯字符串查询（旧入口兼容）。
    无效输入（空、无 query 且无 symbol）不记录。返回**新的**列表。
    """
    items = normalize_history(hist)
    if isinstance(entry, str):
        q = entry.strip()
        if not q:
            return items
        e = {"query": q, "label": q, "symbol": "", "name": "",
             "asset_type": "", "market": "", "chain": "", "logo": "",
             "id": "q:" + _norm(q)}
    elif isinstance(entry, dict):
        e = dict(entry)
        e.setdefault("query", e.get("label") or e.get("symbol") or "")
        e.setdefault("label", e.get("query") or "")
        eid = e.get("id") or asset_id(e)
        if not eid:
            return items
        e["id"] = eid
        if not str(e.get("query") or "").strip() and not str(e.get("symbol") or "").strip():
            return items
    else:
        return items

    e["ts"] = float(now if now is not None else time.time())
    e["v"] = HISTORY_VERSION

    # 同一资产的历史条目（含旧版 q: 查询条目）一并折叠，避免重复。
    # 旧版历史是纯查询字符串（q:<关键词>），资产命中要按 query / label 两种
    # 可能的关键词都折叠，否则「AAPL」与「US:AAPL」会各占一条。
    drop = {e["id"]}
    for key in (e.get("query"), e.get("label"), e.get("symbol")):
        k = str(key or "").strip()
        if k:
            drop.add("q:" + _norm(k))
    # symbol 形如 "US:AAPL"，旧版查询常只写 "AAPL"
    sym = str(e.get("symbol") or "")
    if ":" in sym:
        drop.add("q:" + _norm(sym.split(":", 1)[1]))
    old = next((h for h in items if h["id"] in drop), None)
    if old:
        merged = dict(old)
        merged.update({k: v for k, v in e.items()
                        if v not in ("", None, 0, 0.0)})
        e = merged
    rest = [h for h in items if h["id"] not in drop]
    cap = max_items if max_items and max_items > 0 else HISTORY_MAX
    return [e] + rest[:max(cap - 1, 0)]


def delete_history(hist, key) -> list:
    """删除单条（按 id 或按 query 文本，兼容旧调用）。"""
    items = normalize_history(hist)
    return [h for h in items
            if h["id"] != key and str(h.get("query") or "") != key]


def clear_history() -> list:
    return []


def history_display(h) -> str:
    """历史条目展示文本。"""
    if not isinstance(h, dict):
        return str(h)
    return str(h.get("label") or h.get("query") or h.get("symbol") or "")


def history_query(h) -> str:
    """历史条目回填到搜索框的文本。"""
    if not isinstance(h, dict):
        return str(h)
    return str(h.get("query") or h.get("label") or "")


def history_symbol(h) -> str:
    """历史条目可直接打开的资产 symbol；空串表示只能重新搜索。"""
    if not isinstance(h, dict):
        return ""
    return str(h.get("symbol") or "")
