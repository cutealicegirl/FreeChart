# -*- coding: utf-8 -*-
"""K 线数据获取（图表页专用）。

加密货币：Binance /api/v3/klines（data-api.binance.vision，国内直连可用）
股票：腾讯 ifzq.gtimg.cn K 线接口（A股/港股/美股同一入口）

所有请求走 api_base.HTTP 共享会话（绕过系统代理）。
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List

from PySide6.QtCore import QThread, Signal

from data.api_base import HTTP, MarketApiError
from data.tencent_stock_api import is_stock_symbol
from core import kline_time as _kt
from data import corporate_actions as _ca
from data import price_adjustment as _pa
from data import onchain as _onchain
from data import onchain_kline as _ock

# 加密货币周期 -> Binance interval（3d/1w/1M 为 Binance 原生周期）
CRYPTO_INTERVALS = [
    ("1分", "1m"), ("5分", "5m"), ("15分", "15m"), ("30分", "30m"),
    ("1时", "1h"), ("2时", "2h"), ("4时", "4h"),
    ("6时", "6h"), ("12时", "12h"),
    ("日K", "1d"), ("3日", "3d"), ("周K", "1w"), ("月K", "1M"),
    ("年K", "1y"),
]
# 股票周期（周/月/3日/年由日线本地聚合，见 _aggregate）
STOCK_INTERVALS = [
    ("1分", "m1"), ("5分", "m5"), ("15分", "m15"),
    ("30分", "m30"), ("1时", "m60"),
    ("日K", "day"), ("3日", "3day"), ("周K", "week"),
    ("月K", "month"), ("年K", "1year"),
]
US_INTERVALS = list(STOCK_INTERVALS)
# 港股：腾讯 hkfqkline 提供日线，周/月/3日/年由日线本地聚合
HK_INTERVALS = [
    ("日K", "day"), ("3日", "3day"), ("周K", "week"),
    ("月K", "month"), ("年K", "1year"),
]

# 聚合周期 -> (基础周期, 聚合方式)
STOCK_AGG = {
    "3day": "3day", "week": "week", "month": "month", "1year": "year",
}
_US_SINA_TYPE = {"m1": "1", "m5": "5", "m15": "15",
                 "m30": "30", "m60": "60", "day": "240", "1m": "1"}

_BINANCE_KLINE_URL = "https://data-api.binance.vision/api/v3/klines"
_TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
_HK_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/hkfqkline/get"
_SINA_US_URL = ("https://stock.finance.sina.com.cn/usstock/api/"
                "json_v2.php/US_MinKService.getMinK")
_SINA_US_DAY_URL = ("https://stock.finance.sina.com.cn/usstock/api/"
                    "jsonp_v2.php/x/US_MinKService.getDailyK")
_LIMIT = 1000  # Binance 单次上限，初始即加载较多历史
_AGG_BASE_LIMIT = 20000  # 新浪美股日线一次返回全部历史，取末尾根数上限
_TENCENT_PAGE = 640    # 腾讯单次最多返回根数（实测 >640 直接返回空）
_HISTORY_PAGE = 1000   # Binance 往前翻页时每次拉取的根数


def _prior_date_str(before_ts: float, symbol: str = "") -> str:
    """按市场当地日历取 before_ts 的前一天，不再减固定 86400 秒。

    DST 切换日（23/25 小时）与跨年边界用固定秒数会落到错误日期，
    导致腾讯分页漏一根或重复一根。
    """
    tz = _kt.tz_for(symbol)
    d = datetime.fromtimestamp(float(before_ts), tz).date()
    return (d - timedelta(days=1)).strftime("%Y-%m-%d")


@dataclass
class Candle:
    """一根 K 线。time_label 用于横轴显示，ts 用于排序。

    preview=True 表示这是由真实实时报价生成的“当前未完成周期”预览：
    只有 close/high/low 来自实际报价，volume=0，绝不写缓存、绝不冒充
    已完成 K 线，也绝不参与历史极值 / 回溯分页。
    """
    ts: float            # Unix 时间戳（秒）
    time_label: str      # 横轴标签（如 14:25 或 11-07）
    open: float
    high: float
    low: float
    close: float
    volume: float
    preview: bool = False
    quote_ts: float = 0.0
    source: str = ""
    volume_reliable: bool = True   # False = 数据源无真实成交量，不画量柱
    pool: str = ""                 # 链上来源交易池；跨池禁止无缝拼接


def onchain_pools_compatible(old_candles, new_candles) -> bool:
    """判断两批 K 线能否安全拼接（桌面图表回溯页使用）。

    链上池迁移后，新旧两段走势的真实价格可能不连续；把它们接成一条
    「连续」K 线属于伪造历史。只有双方都带明确池且不同才拒绝，旧缓存
    无池信息时不误伤。非链上标的 pool 恒为空，天然不受影响。
    """
    return _ock.pools_compatible(old_candles, new_candles)


# ============ 公司行为复权集成 ============
# 记录最近一次复权/异常探测结果，供界面可选提示；不影响主流程。
_ADJUST_REPORT: Dict[str, dict] = {}


# 当前历史价格口径（core.adjust_mode）；由配置层在启动时设置，
# 切换口径后 K 线重新抓取并写入隔离的缓存命名空间。
_adjust_mode = "split_adjusted"


def set_adjust_mode(mode: str):
    from core import adjust_mode as _am
    global _adjust_mode
    next_mode = _am.normalize(mode)
    changed = next_mode != _adjust_mode
    _adjust_mode = next_mode
    if changed:
        # 复权口径变了：内存里的处理结果不可复用，交给调用方刷新图表
        _ADJUST_REPORT.clear()
    return _adjust_mode


def get_adjust_mode() -> str:
    return _adjust_mode


def adjustment_report(symbol: str) -> dict:
    """返回该标的最近一次的公司行为处理报告（只读）。"""
    return dict(_ADJUST_REPORT.get(symbol, {}))


def _postprocess(symbol: str, candles: List[Candle], basis: str,
                 price_already_adjusted: bool = False) -> List[Candle]:
    """统一后处理：按登记库对公司行为做复权 + 记录异常标记。

    basis: "raw" 数据源未复权 | "source_qfq" 数据源已前复权价格。
    price_already_adjusted=True 时只补成交量（腾讯 qfq 场景）。
    """
    if not candles:
        return candles
    try:
        reg = _ca.get_registry()
        actions = reg.actions_for(symbol)
        if not price_already_adjusted:
            # 登记库之外的拆股品种：从原始价 + 成交量跳空做双确认，
            # 既能兜底处理未登记标的，又不会把 datasource 的 qfq 数据二次复权。
            auto = _pa.detect_split_actions_from_prices(candles, symbol)
            known = {(a.ex_date, getattr(a.kind, "value", a.kind))
                     for a in actions}
            actions = actions + [a for a in auto
                                 if (a.ex_date,
                                     getattr(a.kind, "value", a.kind)) not in known]
        if not actions:
            return candles
        applied: list = []
        from core import adjust_mode as _am
        mode = _am.normalize(_adjust_mode)
        if price_already_adjusted:
            # 价格已由数据源前复权：成交量按已核实份额事件补齐。
            # 该场景无法用价格跳空做门控，直接采用 verified 事件。
            applied = [a for a in actions if a.usable and not a.source_rebased
                       and a.volume_factor != 1.0]
            out = _pa.adjust_volume_only(candles, actions) \
                if mode != _am.RAW else candles
        elif mode == _am.RAW:
            # Raw：完全保留数据源原始名义价，只记录异常，不套任何因子
            out = candles
            applied = []
        else:
            # 原始价：经验门控，只有确认"未复权"的事件才真正应用。
            # split_adjusted = 份额变动前复权；total_return = 含分红后复权。
            effective = _pa.detect_unadjusted_events(candles, actions)
            applied = effective
            out = _pa.apply_adjustment(
                candles, effective, basis="raw", mode=mode) if effective else candles
        anomalies = _pa.detect_anomalies(out, actions)
        _ADJUST_REPORT[symbol] = {
            "symbol": symbol,
            "events": [a.to_dict() for a in actions],
            "applied": [a.to_dict() for a in applied],
            "anomalies": anomalies,
            "fingerprint": _pa.adjustment_fingerprint(actions),
            "basis": basis,
        }
        return out
    except Exception:
        # 复权是增强层：任何意外都不能让 K 线加载失败
        return candles


def intervals_for(symbol: str) -> list:
    """返回该标的可用的周期列表 [(显示名, 周期键)]。"""
    if _onchain.is_onchain(symbol):
        return _ock.intervals()
    if not is_stock_symbol(symbol):
        return CRYPTO_INTERVALS
    if symbol.startswith("US:"):
        return US_INTERVALS
    if symbol.startswith("HK:"):
        return HK_INTERVALS   # 腾讯 hkfqkline 日线 + 本地聚合
    return STOCK_INTERVALS


def default_interval(symbol: str) -> str:
    """默认周期：链上 DEX 1 时，加密货币 15 分，股票日 K。"""
    if _onchain.is_onchain(symbol):
        return _ock.default_interval()
    return "15m" if not is_stock_symbol(symbol) else "day"


def refresh_seconds(interval: str) -> int:
    """图表页自动刷新间隔（秒）：按周期长度分档，不再按周期键硬编码。

    10s：<=30m；30s：1h~6h；60s：12h 及以上。缓存层会再按“周期边界”
    决定是否真的发请求，定时器空转不再造成 15 分钟滞后。
    """
    sec = _kt.interval_seconds(interval)
    if sec <= 0:
        return 10
    if sec <= 1800:
        return 10
    if sec <= 21600:
        return 30
    return 60


def _aggregate(candles: List[Candle], mode: str,
               symbol: str = "") -> List[Candle]:
    """把基础周期 K 线聚合为 3日/周/月/年 K。

    桶起点统一由 core.kline_time 按市场时区计算：
    加密 UTC 日历 / A 股与港股 UTC+8 / 美股美东时区。
    OHLC 取组内首开、最高、最低、末收，成交量求和；不产生新价格。
    """
    if not candles:
        return []
    interval = {"3day": "3day", "week": "week", "month": "month",
                "year": "1year"}.get(mode, mode)
    groups: dict = {}          # 桶起点 ts -> 累积数据
    order: list = []
    for c in candles:
        start = _kt.bucket_start(c.ts, interval, symbol)
        if start not in groups:
            groups[start] = {
                "open": c.open, "high": c.high, "low": c.low,
                "close": c.close, "volume": c.volume}
            order.append(start)
        else:
            g = groups[start]
            g["high"] = max(g["high"], c.high)
            g["low"] = min(g["low"], c.low)
            g["close"] = c.close
            g["volume"] += c.volume
    out: List[Candle] = []
    for start in order:
        g = groups[start]
        out.append(Candle(
            ts=start, time_label=_kt.label_for(start, interval, symbol),
            open=g["open"], high=g["high"], low=g["low"],
            close=g["close"], volume=g["volume"]))
    return out


def fetch_klines(symbol: str, interval: str) -> List[Candle]:
    """拉取 K 线（同步，后台线程调用）。失败抛 MarketApiError。

    公司行为复权在各底层抓取函数内完成（因为只有那里知道数据源口径）：
      - 腾讯 A股/HK 日线 qfq：价格已前复权，只补成交量；
      - 新浪美股 / 腾讯分钟线：原始价，按已核实事件做经验门控前复权；
      - 加密：数据源自行处理迁移，登记库只标记不重复复权。
      - 链上 DEX：真实 OHLCV 由 GeckoTerminal/CoinGecko 提供，不做股票复权。
    """
    if _onchain.is_onchain(symbol):
        return _fetch_onchain(symbol, interval)
    if symbol.startswith("US:"):
        return _fetch_us(symbol, interval)
    if symbol.startswith("HK:"):
        return _fetch_hk(symbol, interval)
    if is_stock_symbol(symbol):
        return _fetch_stock(symbol, interval)
    return _fetch_crypto(symbol, interval)


# ================= 链上标的（真实 DEX OHLCV） =================
def _fetch_onchain_raw_safe(symbol: str, interval: str,
                            allow_empty: bool) -> List[Candle]:
    """兜底：即便误入 _fetch_crypto_raw 也走真实 DEX 源，不拼币安交易对。"""
    try:
        return _fetch_onchain(symbol, interval)
    except MarketApiError:
        if allow_empty:
            return []
        raise


def _fetch_onchain(symbol: str, interval: str) -> List[Candle]:
    """链上合约真实历史 K 线；底层适配多源，失败抛 MarketApiError。"""
    bars = _ock.fetch_ohlcv(symbol, interval, _LIMIT, allow_empty=False)
    return [Candle(ts=b.ts, time_label=b.time_label, open=b.open,
                   high=b.high, low=b.low, close=b.close,
                   volume=b.volume, volume_reliable=b.volume_reliable,
                   pool=b.pool) for b in bars]


# ================= 加密货币（Binance） =================
def _fetch_crypto(symbol: str, interval: str) -> List[Candle]:
    import json as _json

    # 年K：Binance 无原生年线，用月线（1M）聚合
    if interval == "1y":
        monthly = _fetch_crypto_raw(symbol, "1M", _HISTORY_PAGE)
        return _aggregate(monthly, "year", symbol)

    valid = {iv for _, iv in CRYPTO_INTERVALS}
    if interval not in valid:
        interval = "15m"
    recent = _fetch_crypto_raw(symbol, interval, _LIMIT)
    if interval == "1d" and recent:
        # Binance 单次上限 1000 根 ≈ 2.7 年；日线默认再补一页到 ≈5.5 年，
        # 打开日 K 就能直接看到 5 年范围，不必先滚半天等回溯。
        try:
            older = _fetch_crypto_raw(
                symbol, "1d", _LIMIT,
                end_time_ms=int(recent[0].ts * 1000) - 1,
                allow_empty=True)
        except MarketApiError:
            older = []
        if older:
            return sorted(older + recent, key=lambda c: c.ts)
    return recent


def _fetch_crypto_raw(symbol: str, interval: str, limit: int,
                      end_time_ms: int | None = None,
                      allow_empty: bool = False) -> List[Candle]:
    """allow_empty=True 用于回溯到上市首根时优雅收尾（不再抛异常）。"""
    import json as _json

    # 防御：链上标的绝不拼成 ONCHAIN:xxxUSDT 发给 Binance（必然 400）。
    # 正常路径已在 fetch_klines 分派到 _fetch_onchain；这里是最后一道闸。
    if _onchain.is_onchain(symbol):
        return _fetch_onchain_raw_safe(symbol, interval, allow_empty)

    params = {
        "symbol": f"{symbol}USDT",
        "interval": interval,
        "limit": limit,
    }
    # endTime 让接口返回该时刻之前的历史，用于一路缩小到品种上市起点
    if end_time_ms:
        params["endTime"] = int(end_time_ms)
    try:
        resp = HTTP.get(_BINANCE_KLINE_URL, params=params, timeout=10)
        if resp.status_code == 429:
            raise MarketApiError("Binance API 限流 (HTTP 429)")
        resp.raise_for_status()
        rows = resp.json()
    except MarketApiError:
        raise
    except Exception as e:
        raise MarketApiError(f"Binance K线请求失败: {e}") from e

    candles: List[Candle] = []
    for row in rows:
        try:
            ts = row[0] / 1000.0
            # 标签与市场时区、周期桶同源（加密 = UTC），不再用进程本地时区
            label = _kt.label_for(ts, interval, symbol)
            candles.append(Candle(
                ts=ts, time_label=label,
                open=float(row[1]), high=float(row[2]),
                low=float(row[3]), close=float(row[4]),
                volume=float(row[5])))
        except (ValueError, IndexError, TypeError):
            continue  # 格式异常的行跳过
    if not candles:
        if allow_empty:
            return []
        raise MarketApiError("Binance K线返回为空")
    return candles


# ================= 美股（新浪） =================
def _fetch_us(symbol: str, interval: str) -> List[Candle]:
    """新浪美股 K 线。type: 1/5/15/30/60 分钟，240 = 日线。

    周/月/3日/年 K 由日线本地聚合（新浪不提供更长周期）。
    """
    code = symbol[3:].lower()            # US:AAPL -> aapl
    if interval in STOCK_AGG:
        daily = _postprocess(symbol, _fetch_us_daily(code), "raw")
        return _aggregate(daily, STOCK_AGG[interval], symbol)
    if interval == "day":
        return _postprocess(symbol, _fetch_us_daily(code), "raw")
    sina_type = _US_SINA_TYPE.get(interval, "5")
    try:
        resp = HTTP.get(_SINA_US_URL,
                        params={"symbol": code, "type": sina_type},
                        timeout=10)
        resp.raise_for_status()
        import json as _json
        rows = _json.loads(resp.text)
    except MarketApiError:
        raise
    except Exception as e:
        raise MarketApiError(f"新浪美股K线请求失败: {e}") from e

    candles: List[Candle] = []
    for row in rows[-_LIMIT:]:
        try:
            # 字段：d 时间 / o 开 / h 高 / l 低 / c 收 / v 量
            dt = datetime.strptime(row["d"], "%Y-%m-%d %H:%M:%S")
            ts = _kt.naive_to_timestamp(dt, symbol)
            candles.append(Candle(
                ts=ts, time_label=_kt.label_for(ts, interval, symbol),
                open=float(row["o"]), high=float(row["h"]),
                low=float(row["l"]), close=float(row["c"]),
                volume=float(row.get("v") or 0)))
        except (ValueError, KeyError, TypeError):
            continue
    if not candles:
        raise MarketApiError("新浪美股K线返回为空")
    return _postprocess(symbol, candles, "raw")


def _fetch_us_daily(code: str) -> List[Candle]:
    """新浪美股日线（getDailyK，含全部历史，取末尾 _AGG_BASE_LIMIT 根）。"""
    import json as _json

    try:
        resp = HTTP.get(f"{_SINA_US_DAY_URL}?symbol={code}", timeout=10)
        resp.raise_for_status()
        t = resp.text
        rows = _json.loads(t[t.find("(") + 1:t.rfind(")")])
    except MarketApiError:
        raise
    except Exception as e:
        raise MarketApiError(f"新浪美股日线请求失败: {e}") from e

    candles: List[Candle] = []
    for row in rows[-_AGG_BASE_LIMIT:]:
        try:
            dt = datetime.strptime(row["d"], "%Y-%m-%d")
            us_symbol = "US:" + code.upper()
            ts = _kt.naive_to_timestamp(dt, us_symbol)
            candles.append(Candle(
                ts=ts, time_label=_kt.label_for(ts, "day", us_symbol),
                open=float(row["o"]), high=float(row["h"]),
                low=float(row["l"]), close=float(row["c"]),
                volume=float(row.get("v") or 0)))
        except (ValueError, KeyError, TypeError):
            continue
    if not candles:
        raise MarketApiError("新浪美股日线返回为空")
    return candles


# ================= 股票（腾讯） =================
def _fetch_stock(symbol: str, interval: str) -> List[Candle]:
    if symbol.startswith("HK:"):
        raise MarketApiError("港股暂无公开K线数据源")
    # 周/月/3日/年 K：由（已复权的）日线本地聚合，口径与日线一致
    if interval in STOCK_AGG:
        daily = _fetch_stock(symbol, "day")
        return _aggregate(daily, STOCK_AGG[interval], symbol)
    valid = {"m1", "m5", "m15", "m30", "m60", "day"}
    if interval not in valid:
        interval = "day"
    # 请求码：SH:600519 -> sh600519（腾讯 K 线接口大小写不敏感但保持小写）
    code = symbol.replace(":", "").lower()
    if interval == "day":
        param = f"{code},day,,,{_TENCENT_PAGE},qfq"
    else:
        param = f"{code},{interval},,,{_LIMIT}"
    rows = _tencent_rows(param, code, interval)
    candles = _parse_stock_rows(rows, interval, symbol)
    if not candles:
        raise MarketApiError("腾讯K线返回为空")
    # 腾讯日线 qfq 已前复权价格，但成交量仍是原始份额 -> 只补成交量；
    # 分钟线未复权 -> 走经验门控的完整复权。
    if interval == "day":
        return _postprocess(symbol, candles, "source_qfq", price_already_adjusted=True)
    return _postprocess(symbol, candles, "raw")


def _tencent_rows(param: str, code: str, interval: str,
                  url: str | None = None) -> list:
    """请求腾讯 K 线并取出原始行（允许空：用于回溯到头）。"""
    try:
        resp = HTTP.get(url or _TENCENT_KLINE_URL,
                        params={"param": param}, timeout=10)
        resp.raise_for_status()
        body = resp.json()
    except Exception as e:
        raise MarketApiError(f"腾讯K线请求失败: {e}") from e
    data = (body.get("data") or {}).get(code) or {}
    rows = data.get(f"qfq{interval}") or data.get(interval) or []
    if interval == "day" and not rows:
        rows = data.get("day") or []
    return rows


def _parse_stock_rows(rows: list, interval: str,
                      symbol: str = "") -> List[Candle]:
    """腾讯 K 线行 -> Candle。字段：[时间, 开, 收, 高, 低, 量, ...]。

    源时间是交易所当地墙钟（无时区），统一按市场时区解释，不再依赖进程时区。
    """
    candles: List[Candle] = []
    for row in rows:
        try:
            raw_t = str(row[0])
            if interval == "day":
                try:
                    dt = datetime.strptime(raw_t, "%Y-%m-%d")
                except ValueError:
                    dt = datetime.strptime(raw_t, "%Y%m%d")
                ts = _kt.naive_to_timestamp(dt, symbol)
            else:
                dt = datetime.strptime(raw_t, "%Y%m%d%H%M")
                ts = _kt.naive_to_timestamp(dt, symbol)
            label = _kt.label_for(ts, interval, symbol)
            candles.append(Candle(
                ts=ts, time_label=label,
                open=float(row[1]), high=float(row[3]),
                low=float(row[4]), close=float(row[2]),
                volume=float(row[5] or 0)))
        except (ValueError, IndexError, TypeError):
            continue
    return candles


def _hk_daily_rows(code: str, end_date: str = "",
                   symbol: str = "") -> List[Candle]:
    """港股日线：腾讯 hkfqkline（qfqday / day）。"""
    param = (f"{code},day,,{end_date},{_TENCENT_PAGE},qfq" if end_date
             else f"{code},day,,,{_TENCENT_PAGE},qfq")
    rows = _tencent_rows(param, code, "day", _HK_KLINE_URL)
    hk_symbol = symbol or ("HK:" + code[2:] if code.startswith("hk") else "")
    return _parse_stock_rows(rows, "day", hk_symbol)


def _fetch_hk(symbol: str, interval: str) -> List[Candle]:
    """港股 K 线：日线直取，周/月/3日/年 K 由日线本地聚合。"""
    code = symbol.replace(":", "").lower()      # HK:00700 -> hk00700
    daily = _hk_daily_rows(code, symbol=symbol)
    if not daily:
        raise MarketApiError("港股K线返回为空")
    # hkfqkline qfq 已前复权价格，只补成交量
    daily = _postprocess(symbol, daily, "source_qfq", price_already_adjusted=True)
    if interval in STOCK_AGG:
        return _aggregate(daily, STOCK_AGG[interval], symbol)
    return daily


def _fetch_hk_before(symbol: str, interval: str,
                     before_ts: float) -> List[Candle]:
    code = symbol.replace(":", "").lower()
    end_date = _prior_date_str(before_ts, symbol)
    daily = _hk_daily_rows(code, end_date, symbol)
    if not daily:
        return []
    daily = _postprocess(symbol, daily, "source_qfq", price_already_adjusted=True)
    if interval in STOCK_AGG:
        agg = _aggregate(daily, STOCK_AGG[interval], symbol)
        if agg:
            agg = agg[:-1]        # 页尾不完整桶留到下一页凑齐
        return [c for c in agg if c.ts < before_ts]
    return [c for c in daily if c.ts < before_ts]


def _fetch_stock_before(symbol: str, interval: str,
                        before_ts: float) -> List[Candle]:
    """A 股按结束日期往前翻页（腾讯 param 的第 4 段就是 end date）。

    实测 `sh600519,day,,2024-03-17,640,qfq` 会返回该日期之前的 640 根，
    因此可以一直翻到上市首日。聚合周期先在日线上聚合再丢弃页尾的
    不完整桶，避免下一页出现同桶重复。
    """
    if interval in ("m1", "m5", "m15", "m30", "m60") or before_ts <= 0:
        return []
    code = symbol.replace(":", "").lower()
    end_date = _prior_date_str(before_ts, symbol)
    rows = _tencent_rows(f"{code},day,,{end_date},{_TENCENT_PAGE},qfq",
                         code, "day")
    daily = _parse_stock_rows(rows, "day", symbol)
    if not daily:
        return []
    daily = _postprocess(symbol, daily, "source_qfq", price_already_adjusted=True)
    if interval in STOCK_AGG:
        agg = _aggregate(daily, STOCK_AGG[interval], symbol)
        # 页尾那一桶很可能只含半个周期，留到下一页凑齐再生成
        if agg:
            agg = agg[:-1]
        return [c for c in agg if c.ts < before_ts]
    return [c for c in daily if c.ts < before_ts]


# ================= 历史回溯（滚轮可缩到品种整个生命周期） =================
def fetch_klines_before(symbol: str, interval: str, before_ts: float,
                        limit: int = _HISTORY_PAGE):
    """拉取 before_ts 之前的 K 线，返回 (candles, exhausted)。

    只以「是否拿到更早的数据」判断到头，不再用「本页不足 limit」提前收尾：
    网络抖动导致的短页不会再让缩放永久卡住。加密货币用 Binance endTime
    逐页往前翻，A 股用腾讯的结束日期翻页，美股日线一次已返回全部历史。
    """
    if before_ts <= 0:
        return [], True
    if _onchain.is_onchain(symbol):
        bars = _ock.fetch_ohlcv(symbol, interval, limit,
                                before_ts=before_ts, allow_empty=True)
        candles = [Candle(ts=b.ts, time_label=b.time_label, open=b.open,
                          high=b.high, low=b.low, close=b.close,
                          volume=b.volume, volume_reliable=b.volume_reliable,
                          pool=b.pool) for b in bars
                   if b.ts < before_ts]
        return candles, not candles
    if symbol.startswith("US:"):
        return [], True     # 新浪美股日线一次已返回全部历史
    if symbol.startswith("HK:"):
        older = _fetch_hk_before(symbol, interval, before_ts)
        return older, not older
    if is_stock_symbol(symbol):
        older = _fetch_stock_before(symbol, interval, before_ts)
        return older, not older

    end_ms = int(before_ts * 1000) - 1
    if interval == "1y":
        monthly = _fetch_crypto_raw(symbol, "1M", limit,
                                   end_time_ms=end_ms, allow_empty=True)
        candles = [c for c in _aggregate(monthly, "year", symbol)
                   if c.ts < before_ts]
        return candles, not candles
    valid = {iv for _, iv in CRYPTO_INTERVALS if iv != "1y"}
    if interval not in valid:
        return [], True
    raw = _fetch_crypto_raw(symbol, interval, limit,
                            end_time_ms=end_ms, allow_empty=True)
    candles = [c for c in raw if c.ts < before_ts]
    return candles, not candles


class HistoryWorker(QThread):
    """往前翻页加载更早 K 线的后台线程。"""

    loaded = Signal(str, str, list, bool)  # symbol, interval, candles, 到头
    failed = Signal(str, str, str)

    def __init__(self, symbol: str, interval: str, before_ts: float,
                 parent=None):
        super().__init__(parent)
        self._symbol = symbol
        self._interval = interval
        self._before = before_ts

    def run(self):
        try:
            candles, exhausted = fetch_klines_before(
                self._symbol, self._interval, self._before)
            self.loaded.emit(self._symbol, self._interval,
                             candles, exhausted)
        except MarketApiError as e:
            self.failed.emit(self._symbol, self._interval, str(e))
        except Exception as e:
            self.failed.emit(self._symbol, self._interval, f"未知错误: {e}")


class KlineWorker(QThread):
    """K 线加载后台线程：结果通过信号回传 GUI。"""

    loaded = Signal(str, str, list)   # (symbol, interval, candles)
    failed = Signal(str, str, str)    # (symbol, interval, 错误信息)

    def __init__(self, symbol: str, interval: str, parent=None):
        super().__init__(parent)
        self._symbol = symbol
        self._interval = interval

    def run(self):
        try:
            candles = fetch_klines(self._symbol, self._interval)
            self.loaded.emit(self._symbol, self._interval, candles)
        except MarketApiError as e:
            self.failed.emit(self._symbol, self._interval, str(e))
        except Exception as e:  # 兜底：任何意外都不能崩溃
            self.failed.emit(self._symbol, self._interval, f"未知错误: {e}")
