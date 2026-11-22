# -*- coding: utf-8 -*-
"""品种资料：总市值 / 流通市值 / 市盈率 / 市值排名。

行情接口只给价格、涨跌、高低、成交额，没有股本与市值。这里补这一层：

  - 加密货币：CoinLore 全量市值榜（一次请求拿前 300 名），总市值 / 单价
    反推流通量，市值随实时价重算；
  - A股 / 港股 / 美股：腾讯行情单只快照，字段 45 = 总市值（亿）、
    44 = 流通市值（亿）、39 = 市盈率(TTM)，同样用「亿 / 价」反推股本。

拿到股本后市值 = 股本 × 当前价，所以面板上的市值会跟最新价一起动，
不会出现「价格变了市值还是几小时前那个数」。

网络失败一律返回空字典，界面按「拿不到就显示 —」处理，绝不阻塞 UI：
调用方在后台线程里调本模块（见 ui/info_panel.ProfileWorker）。
"""
import datetime
import json
import os
import time
from typing import Any, Dict, Optional

import requests

from data import about as about_db
from data.universe import all_of, market_of

# 与行情层一致：绕过系统代理，避免代理软件把行情接口拦掉
HTTP = requests.Session()
HTTP.trust_env = False
HTTP.headers["User-Agent"] = "Mozilla/5.0"

# 股本 / 市盈率这类静态字段的缓存时长（30 分钟足够，市值靠价格重算）
TTL = 1800.0
# 落盘缓存作为首选数据源的有效期：首次联网取回后固化在本地，
# 此时间内（1 天）直接读本地，不再每次启动都去调腾讯 / CoinLore 接口。
DISK_TTL = 86400.0

# 进程内缓存：symbol -> {"data": {...}, "ts": float}
_CACHE: Dict[str, Dict[str, Any]] = {}
# 加密市值榜：整个进程只拉一次（30 分钟内复用）
_CRYPTO: Dict[str, Any] = {"rows": None, "ts": 0.0}

_COINLORE = "https://api.coinlore.net/api/tickers/"
_TENCENT = "https://qt.gtimg.cn/q="

# 腾讯行情字段下标（2026-11-14 实测：A股 88 字段 / 港股 78 / 美股 73）
# 只使用已核实含义的位；不同市场同一位置含义不同，见 _stock_profile。
_T_NAME, _T_PRICE, _T_PE = 1, 3, 39
_T_FLOAT_CAP, _T_TOTAL_CAP = 44, 45
_T_TS, _T_VOLUME, _T_AMOUNT, _T_TURNOVER, _T_PB = 30, 36, 37, 38, 46
_T_PREV_CLOSE, _T_OPEN, _T_HIGH, _T_LOW = 4, 5, 33, 34
_T_AMPLITUDE, _T_LIMIT_UP, _T_LIMIT_DOWN = 43, 47, 48
_T_VOL_RATIO, _T_AVG_PRICE = 49, 51
_T_PE_DYNAMIC, _T_PE_STATIC = 52, 53
# 港股 / 美股：48 / 49 是 52 周最高 / 最低；A 股这两位是涨停 / 跌停价
_T_W52_HIGH, _T_W52_LOW = 48, 49

# 界面上「没有数据」的统一文案：绝不填 0 或估算值来充数
MISSING = "— 暂无公开数据"

# profile v2 固定字段表。所有键始终存在，值为 None 表示数据源没有提供，
# 由 UI 显示 MISSING；新增字段只往这里加，调用方不用改判空逻辑。
PROFILE_FIELDS = (
    "cap", "float_cap", "pe", "pb", "rank",
    "shares", "float_shares",
    "supply_circulating", "supply_total", "supply_max",
    "volume_24h", "volume_unit", "amount_24h", "turnover_rate",
    "liquidity", "revenue", "profit",
    "token_allocation", "unlock_schedule", "protocol_revenue",
    # v37：腾讯快照里已核实含义的真实字段（股票）
    "prev_close", "open_price", "day_high", "day_low", "amplitude",
    "limit_up", "limit_down", "volume_ratio", "avg_price",
    "pe_dynamic", "pe_static", "week52_high", "week52_low",
    "quote_currency", "quote_tz", "exchange",
    "source", "source_url", "source_note",
    "updated_ts", "updated_text", "updated_kind",
)

# _stock_profile 直接产出的真实字段：profile() 原样透传，不做估算
_EXTRA_KEYS = (
    "prev_close", "open_price", "day_high", "day_low", "amplitude",
    "limit_up", "limit_down", "volume_ratio", "avg_price",
    "pe_dynamic", "pe_static", "week52_high", "week52_low",
    "quote_currency", "quote_tz", "exchange",
)


def _fmt_time(ts: float) -> str:
    """时间戳 -> 本地可读时间；无时间返回破折号，绝不写「刚刚」这类假值。"""
    try:
        ts = float(ts or 0)
    except (TypeError, ValueError):
        return "—"
    if ts <= 0:
        return "—"
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return "—"


def _parse_quote_ts(raw: str) -> float:
    """腾讯 f[30] 的三种真实格式（2026-11-14 实测）：

      A 股  20261113161455
      港股  2026/11/13 16:08:22
      美股  2026-11-13 16:00:01

    旧版只认第一种，港股 / 美股的「行情时间」一直显示 —，v37 修正。
    时间戳按本机时区解析；UI 会标注为「交易所本地时间」，不做时区换算。
    """
    s = str(raw or "").strip()
    for fmt in ("%Y%m%d%H%M%S", "%Y/%m/%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M"):
        try:
            return datetime.datetime.strptime(s, fmt).timestamp()
        except (ValueError, TypeError):
            continue
    return 0.0


def _onchain_about(symbol: str, q: dict | None = None) -> dict:
    """链上合约品种的介绍：只填链上可核实的字段，其余一律 None。

    不写项目背景、业务、前景、代币分配、解锁、协议收入 —— 这些没有
    数据源，编出来就是假资料。
    """
    from data import onchain, timeline as timeline_db
    q = q or {}
    addr = onchain.address_of(symbol)
    chain = onchain.chain_of(addr) or "公链"
    out = {
        "title": q.get("name") or q.get("code") or "链上合约代币",
        "category": f"{chain} 链上合约代币",
        "founder": None, "since": None, "product": None,
        "summary": None, "background": None, "business": None,
        "highlights": None, "purpose": None, "outlook": None,
        "contract": addr, "launchpad": q.get("launchpad") or None,
        "source": "链上元数据（代币报告 / Mint 账户）",
        "source_note": "仅展示链上可核实的名称、代码、发行平台与合约地址；"
                       "项目背景 / 业务 / 前景暂无公开资料",
        "covered": False,
        "timeline": [], "timeline_note": timeline_db.NO_DATA,
        "timeline_sources": [],
        "timeline_verified_at": timeline_db.VERIFIED_AT,
        "archive": timeline_db.archive(symbol),
        "archive_fields": [list(x) for x in timeline_db.ARCHIVE_FIELDS],
    }
    return out


def _onchain_profile(symbol: str, price: float = 0.0) -> dict:
    """链上合约品种的 v2 资料：真实链上价 / 供应量 / 流动性 + 来源时间。"""
    from data import onchain
    base = blank_profile(symbol)
    q = onchain.quote(onchain.address_of(symbol))
    base["about"] = _onchain_about(symbol, q)
    if not q:
        base["source"] = onchain.SOURCE
        base["source_note"] = "链上报价源不可达或未收录，未采到数值"
        base["updated_text"] = "— 无采集时间"
        base["updated_kind"] = "离线"
        return base
    p = q.get("price") or float(price or 0)
    sup = q.get("supply")
    base["cap"] = p * sup if p > 0 and sup else None
    base["supply_circulating"] = sup
    base["supply_total"] = sup
    base["liquidity"] = q.get("liquidity")
    base["source"] = q.get("source")
    base["source_url"] = q.get("source_url")
    base["updated_ts"] = q.get("ts")
    base["updated_text"] = _fmt_time(q.get("ts"))
    base["updated_kind"] = "链上报价"
    base["source_note"] = (
        "USD 报价 / 流动性 / 持有地址数 / 供应量取自链上代币报告；"
        "市值 = 链上价 × 链上总供应量；"
        "24h 成交额 / 涨跌幅 / 代币分配 / 解锁 / 协议收入无数据源，未展示")
    return base


def blank_profile(symbol: str) -> dict:
    """生成一份「全部字段都有、但数值全为空」的 v2 资料。

    离线 / 断网 / 数据源失败都返回它，界面据此逐项标注「暂无公开数据」，
    不会出现空白卡，也不会出现编造的数字。
    """
    out: Dict[str, Any] = {k: None for k in PROFILE_FIELDS}
    out["schema"] = 2
    out["about"] = about_db.about(symbol)
    out["rank"] = rank_of(symbol)
    out["source_note"] = "数值字段待联网获取"
    return out


# --------------------------------------------------------------------------
# 磁盘缓存：断网时还能显示上次取到的股本
# --------------------------------------------------------------------------
def cache_path() -> str:
    appdata = os.getenv("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "FreeChart", "fundamentals.json")


def _read_disk() -> Dict[str, Any]:
    try:
        with open(cache_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_disk(symbol: str, entry: dict):
    """单条落盘；失败静默（缓存只是锦上添花）。"""
    try:
        data = _read_disk()
        data[symbol] = entry
        if len(data) > 1200:                 # 别让缓存无限长
            keep = sorted(data.items(), key=lambda kv: kv[1].get("ts", 0),
                          reverse=True)[:1000]
            data = dict(keep)
        os.makedirs(os.path.dirname(cache_path()), exist_ok=True)
        with open(cache_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except (OSError, ValueError, TypeError):
        pass


# --------------------------------------------------------------------------
# 加密：CoinLore 市值榜
# --------------------------------------------------------------------------
def _crypto_rows(timeout: float = 8.0) -> Dict[str, Dict[str, Any]]:
    """{代码: {cap, px, csupply, tsupply, msupply, volume24, rank}}。

    字段来自 CoinLore /api/tickers/ 实测返回：csupply 流通量、tsupply
    总供应量、msupply 最大供应量、volume24 24h 成交额(USD)、rank 市值排名。
    取不到就留 None，绝不用市值反推的量冒充「总供应量 / 最大供应量」。
    """
    now = time.time()
    rows = _CRYPTO.get("rows")
    if rows is not None and now - float(_CRYPTO.get("ts") or 0) < TTL:
        return rows
    out: Dict[str, Dict[str, Any]] = {}

    def fnum(item: dict, key: str):
        try:
            v = float(item.get(key) or 0)
        except (TypeError, ValueError):
            return None
        return v if v > 0 else None

    for start in (0, 100, 200):
        try:
            r = HTTP.get(_COINLORE, params={"start": start, "limit": 100},
                         timeout=timeout)
            items = (r.json() or {}).get("data") or []
        except Exception:
            break
        for d in items:
            if not isinstance(d, dict):
                continue
            sym = str(d.get("symbol") or "").strip().upper()
            cap, px = fnum(d, "market_cap_usd"), fnum(d, "price_usd")
            if not (sym and cap and px):
                continue
            out.setdefault(sym, {
                "cap": cap, "px": px,
                "csupply": fnum(d, "csupply"),
                "tsupply": fnum(d, "tsupply"),
                "msupply": fnum(d, "msupply"),
                "volume24": fnum(d, "volume24"),
                "rank": fnum(d, "rank"),
            })
        if len(items) < 100:
            break
    if out:
        _CRYPTO["rows"] = out
        _CRYPTO["ts"] = now
    return out


def _crypto_profile(symbol: str, timeout: float) -> dict:
    row = _crypto_rows(timeout).get(symbol.upper())
    if not row:
        return {}
    # csupply 是真实流通量；取不到时才有必要用「市值 / 单价」反推，
    # 且只用于 shares / 流通量，不会冒充总供应量或最大供应量。
    circulating = row.get("csupply") or (row["cap"] / row["px"])
    return {
        "shares": circulating, "float_shares": circulating,
        "supply_circulating": circulating,
        "supply_total": row.get("tsupply"),
        "supply_max": row.get("msupply"),
        "volume_24h": row.get("volume24"),
        "volume_unit": "USD（24h 成交额）",
        "pe": None, "pb": None,
        "cap0": row["cap"], "px0": row["px"],
        "source": "CoinLore", "source_url": _COINLORE,
        "quote_ts": 0.0, "quote_kind": "",     # CoinLore 榜单不带行情时间
    }


# --------------------------------------------------------------------------
# 股票：腾讯行情单只快照
# --------------------------------------------------------------------------
def tencent_code(symbol: str) -> str:
    """统一代码 -> 腾讯行情代码：SH:600519 -> sh600519。"""
    mkt = market_of(symbol)
    if mkt == "crypto":
        return ""
    head, _, code = symbol.partition(":")
    if mkt == "us":
        return "us" + code
    return head.lower() + code


def _stock_profile(symbol: str, timeout: float) -> dict:
    code = tencent_code(symbol)
    if not code:
        return {}
    try:
        r = HTTP.get(_TENCENT + code, timeout=timeout)
        r.encoding = "gbk"
        body = r.text.split('"')
        fields = body[1].split("~") if len(body) > 1 else []
    except Exception:
        return {}
    if len(fields) <= max(_T_TOTAL_CAP, _T_PB):
        return {}

    def num(idx: int) -> Optional[float]:
        try:
            v = float(fields[idx])
        except (TypeError, ValueError, IndexError):
            return None
        return v if v > 0 else None

    def txt(idx: int) -> str:
        try:
            return str(fields[idx]).strip()
        except IndexError:
            return ""

    mkt = market_of(symbol)
    is_cn = mkt == "cn"
    price = num(_T_PRICE)
    cap = num(_T_TOTAL_CAP)                  # 亿（本币）
    float_cap = num(_T_FLOAT_CAP)
    if not cap or not price:
        return {}
    unit = 1e8                                # 亿 -> 元（人民币 / 港币 / 美元同理）
    amount = num(_T_AMOUNT)
    # 实测：A 股 f[37] 单位是「万元」，港股 / 美股已经是「元 / 美元」。
    # 旧版一律 ×1e4，港美股成交额被放大一万倍，v37 修正。
    amount_real = (amount * 1e4) if (is_cn and amount) else amount
    exchange = {"cn": "中国内地证券交易所", "hk": "香港交易所",
                "us": "美国证券市场"}.get(mkt, "")
    tz = {"cn": "交易所本地时间（北京时间）",
          "hk": "交易所本地时间（香港时间）",
          "us": "交易所本地时间（美东时间）"}.get(mkt, "")
    curr = {"cn": "人民币 CNY", "hk": "港元 HKD",
            "us": "美元 USD"}.get(mkt, "")
    out = {
        "shares": cap * unit / price,
        "float_shares": (float_cap * unit / price) if float_cap else None,
        "pe": num(_T_PE), "pb": num(_T_PB),
        "cap0": cap * unit, "px0": price,
        # 成交量：A 股以「手」计，港股 / 美股以「股」计
        "volume_24h": num(_T_VOLUME),
        "volume_unit": "手（成交量）" if is_cn else "股（成交量）",
        "amount_24h": amount_real,
        "turnover_rate": num(_T_TURNOVER),
        "prev_close": num(_T_PREV_CLOSE), "open_price": num(_T_OPEN),
        "day_high": num(_T_HIGH), "day_low": num(_T_LOW),
        "amplitude": num(_T_AMPLITUDE),
        "quote_ts": _parse_quote_ts(txt(_T_TS)),
        "quote_kind": "行情源时间",
        "quote_currency": curr, "quote_tz": tz, "exchange": exchange,
        "source": "腾讯行情", "source_url": _TENCENT + code,
    }
    if is_cn:
        # A 股 f[47]/f[48] = 涨停 / 跌停价（按昨收 ±10% 校验过）
        out.update({
            "limit_up": num(_T_LIMIT_UP), "limit_down": num(_T_LIMIT_DOWN),
            "volume_ratio": num(_T_VOL_RATIO), "avg_price": num(_T_AVG_PRICE),
            "pe_dynamic": num(_T_PE_DYNAMIC), "pe_static": num(_T_PE_STATIC),
        })
    else:
        # 港股 / 美股 f[48]/f[49] = 52 周最高 / 最低，含义与 A 股不同
        out.update({
            "week52_high": num(_T_W52_HIGH), "week52_low": num(_T_W52_LOW),
        })
    return out


# --------------------------------------------------------------------------
# 对外接口
# --------------------------------------------------------------------------
def rank_of(symbol: str) -> Optional[int]:
    """该品种在本市场「全部」清单里的位次（清单本身就按市值降序）。"""
    try:
        lst = all_of(market_of(symbol))
        idx = lst.index(symbol)
    except (ValueError, KeyError):
        return None
    return idx + 1


def _offline() -> bool:
    """自动化测试 / 无头环境：跳过网络请求。

    资料卡与详情抽屉都在守护线程里调 profile()。测试结束常用
    os._exit() 硬退出，若此刻线程正卡在 OpenSSL 读 socket，
    Windows 上会触发 access violation（进程退出码 139）。
    """
    return (os.getenv("CT_OFFLINE") == "1"
            or os.getenv("QT_QPA_PLATFORM") == "offscreen")


def profile(symbol: str, price: float = 0.0, timeout: float = 8.0) -> dict:
    """取品种资料 v2；任何字段拿不到都是 None，界面据此明确标注。

    返回 `blank_profile()` 的全字段结构（schema=2），额外保证：
      - source / source_url / source_note：数值到底来自哪里；
      - updated_ts / updated_text / updated_kind：真实采集或行情时间，
        不再用「刚刚」这种没有依据的假时间；
      - supply_* / volume_24h / turnover_rate / pb：只填数据源实测返回的
        真实字段（CoinLore csupply/tsupply/msupply/volume24；腾讯 f[30]、
        f[36~39]、f[44~46]）；
      - liquidity / revenue / profit / token_allocation / unlock_schedule /
        protocol_revenue：当前没有接入对应数据源，一律 None，绝不编造。

    缓存策略（静态数据本地固化，不必每次都调接口）：
      - 首次联网取回后落盘到 %APPDATA%/FreeChart/fundamentals.json；
      - 进程内缓存 30 分钟内零延迟复用；
      - 内存未命中时优先读本地固化缓存，DISK_TTL（1 天）内直接用它，
        不再每次启动都去调腾讯 / CoinLore 接口；
      - 仅当本地缺失 / 过期才联网取一次，取回即刻重新落盘。
    """
    if not symbol:
        return blank_profile("")
    from data import onchain
    is_oc = onchain.is_onchain(symbol)
    if is_oc and not _offline():
        return _onchain_profile(symbol, price)
    base = blank_profile(symbol)
    if is_oc:
        base["about"] = _onchain_about(symbol)
    if _offline():
        base["source"] = "链上报价源" if is_oc else "离线资料库"
        base["source_note"] = ("未联网：链上数值字段未采集" if is_oc
                               else "未联网：数值字段未采集")
        base["updated_text"] = "— 未联网，无采集时间"
        base["updated_kind"] = "离线"
        return base

    mkt = market_of(symbol)
    now = time.time()
    hit = _CACHE.get(symbol)
    if hit is not None and now - float(hit.get("ts") or 0) <= TTL:
        pass                                        # 内存缓存未过期：零网络
    else:
        # 内存未命中 / 已过期：优先读本地固化缓存（首次加载后已落盘），
        # 未过期就直接用它，不再每次启动都去调腾讯 / CoinLore 接口。
        entry = _read_disk().get(symbol)
        if (isinstance(entry, dict)
                and now - float(entry.get("ts") or 0) < DISK_TTL):
            hit = {"data": entry, "ts": float(entry.get("ts") or 0)}
            _CACHE[symbol] = hit
        else:
            # 本地没有或已过期：才联网取一次，取回即重新落盘固化
            try:
                fresh = (_crypto_profile(symbol, timeout) if mkt == "crypto"
                         else _stock_profile(symbol, timeout))
            except Exception:
                fresh = {}
            if fresh:
                fresh["ts"] = now
                _CACHE[symbol] = {"data": fresh, "ts": now}
                _write_disk(symbol, fresh)
                hit = _CACHE[symbol]
            elif entry is not None:                  # 拉取失败但本地有旧值：兜底用旧值
                hit = {"data": entry, "ts": float(entry.get("ts") or 0)}
                _CACHE[symbol] = hit
            else:
                hit = {"data": {}, "ts": now}
                _CACHE[symbol] = hit

    data = dict((hit or {}).get("data") or {})
    if not data:
        base["source"] = "—"
        base["source_note"] = "数据源本次未返回数值"
        base["updated_text"] = "— 暂无数据"
        base["updated_kind"] = "无"
        return base

    # 用当前价折算市值；没有实时价就用抓取时的快照
    cur = float(price or 0.0)
    px0 = float(data.get("px0") or 0.0)
    shares = data.get("shares")
    fshares = data.get("float_shares")
    scale = (cur / px0) if (cur > 0 and px0 > 0) else 1.0
    cap = float(shares) * px0 * scale if shares else data.get("cap0")
    float_cap = (float(fshares) * px0 * scale
                 if fshares and px0 else None)

    quote_ts = float(data.get("quote_ts") or 0)
    kind = data.get("quote_kind") or ""
    if not quote_ts:
        quote_ts = float(data.get("ts") or 0)   # 抓取时刻，真实可追溯
        kind = "本地采集时间"

    src = data.get("source") or ""
    base.update({
        "cap": cap, "float_cap": float_cap,
        "pe": data.get("pe"), "pb": data.get("pb"),
        "shares": shares, "float_shares": fshares,
        "supply_circulating": data.get("supply_circulating"),
        "supply_total": data.get("supply_total"),
        "supply_max": data.get("supply_max"),
        "volume_24h": data.get("volume_24h"),
        "volume_unit": data.get("volume_unit") or "",
        "amount_24h": data.get("amount_24h"),
        "turnover_rate": data.get("turnover_rate"),
        "source": src,
        "source_url": data.get("source_url") or "",
        "source_note": ("CoinLore 全球市值榜（前 300）" if src == "CoinLore"
                        else "腾讯行情单只快照" if src == "腾讯行情" else src),
        "updated_ts": quote_ts,
        "updated_text": _fmt_time(quote_ts),
        "updated_kind": kind,
    })
    # v37：把快照里已核实含义的字段原样透传；接口没给就保持 None
    for k in _EXTRA_KEYS:
        if data.get(k) is not None:
            base[k] = data[k]
    if src == "腾讯行情":
        base["source_note"] = (
            "腾讯行情单只快照（字段按市场区分单位：A 股成交额万元 / "
            "港股美股为本币元，A 股成交量手 / 港美股股；"
            "A 股 47/48 为涨跌停价，港美股 48/49 为 52 周高低）")
    return base


def about(symbol: str, name: str = "") -> dict:
    """品种背景介绍（离线，不联网；弹窗/详情页可直接调用）。"""
    return about_db.about(symbol, name)
