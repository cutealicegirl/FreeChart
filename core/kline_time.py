# -*- coding: utf-8 -*-
"""K 线时间基准与周期边界（纯函数，无 Qt / 网络依赖）。

设计目标
--------
把「时间戳单位、市场时区、周期桶边界、当前未完成周期」收口到同一处，
桌面 Python、缓存层和测试都调用这里，避免各数据源各自用本地时间算边界。

统一约定
--------
* 内部时间戳一律为 **Unix 秒**（绝对时刻），不做时区标记；
* 周期桶按**数据源所属市场时区**划分：
  - 加密货币 / DEX：UTC（Binance、GeckoTerminal 的原生口径）；
  - A 股 / 港股：Asia/Shanghai（UTC+8，无现代夏令时）；
  - 美股：America/New_York（含 3 月 / 11 月夏令时切换）；
* 图表横轴标签用同一市场时区生成，避免「UTC 分桶 + 本地标签」错位；
* “当前周期预览”只使用真实收到的报价价格，成交量为 0 且明确标记为预览，
  绝不写入缓存、绝不冒充已完成 K 线、绝不用于填充历史缺口。
"""
from __future__ import annotations

import calendar
import math
import time
from datetime import date, datetime, timedelta, timezone, tzinfo

_CNY = timezone(timedelta(hours=8), "Asia/Shanghai")


def _nth_sunday(year: int, month: int, nth: int) -> int:
    """指定月份第 nth 个星期日的日号（nth=1/2）。"""
    weeks = [d for d in range(1, 15)
             if calendar.weekday(year, month, d) == calendar.SUNDAY]
    return weeks[nth - 1]


class _USEastern(tzinfo):
    """无第三方依赖的美东时区（1970 年后的美国夏令时规则）。

    DST：3 月第二个星期日 02:00 本地标准时开始，11 月第一个星期日
    02:00 本地夏令时结束。歧义时刻按 fold=0（夏令时）处理。
    """

    @staticmethod
    def _wall_is_dst(naive: datetime) -> bool:
        y = naive.year
        start = datetime(y, 3, _nth_sunday(y, 3, 2), 2, 0)
        end = datetime(y, 11, _nth_sunday(y, 11, 1), 2, 0)
        return start <= naive.replace(tzinfo=None) < end

    def utcoffset(self, dt):
        if dt is None:
            return timedelta(hours=-5)
        return timedelta(hours=-4 if self._wall_is_dst(dt) else -5)

    def dst(self, dt):
        if dt is None:
            return timedelta(0)
        return timedelta(hours=1 if self._wall_is_dst(dt) else 0)

    def tzname(self, dt):
        return "EDT" if (dt is not None and self._wall_is_dst(dt)) else "EST"

    def fromutc(self, dt):
        """UTC aware -> 本地 aware；默认 tzinfo.fromutc 会把 UTC 墙钟当本地。"""
        utc_naive = dt.replace(tzinfo=None)
        approx = utc_naive + timedelta(hours=-5)
        off = self.utcoffset(approx.replace(tzinfo=self))
        local = utc_naive + off
        off2 = self.utcoffset(local.replace(tzinfo=self))
        if off2 != off:
            local = utc_naive + off2
        return local.replace(tzinfo=self)


_US_EASTERN = _USEastern()

# 分钟 / 小时 / 日历周期 -> 秒数。股票分钟键保留双端历史命名。
_SECONDS = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600,
    "12h": 43200, "1d": 86400, "3d": 259200,
    "1w": 604800, "1M": 2592000, "1y": 31536000,
    "m1": 60, "m5": 300, "m15": 900, "m30": 1800,
    "m60": 3600, "m120": 7200, "m360": 21600, "m720": 43200,
    "day": 86400, "3day": 259200, "week": 604800,
    "month": 2592000, "1year": 31536000,
}

_CALENDAR = {"1d", "3d", "1w", "1M", "1y",
             "day", "3day", "week", "month", "1year"}


def market_of(symbol: str) -> str:
    """返回 'crypto' / 'cn' / 'us'，决定该标的的 K 线时区。"""
    s = str(symbol or "")
    if s.startswith("US:"):
        return "us"
    if s.startswith(("SH:", "SZ:", "HK:")):
        return "cn"
    return "crypto"


def tz_for(symbol: str) -> tzinfo:
    m = market_of(symbol)
    if m == "cn":
        return _CNY
    if m == "us":
        return _US_EASTERN
    return timezone.utc


def interval_seconds(interval: str) -> int:
    """周期秒数；未知周期返回 0（调用方应拒绝，不再静默回落到 15m）。"""
    return int(_SECONDS.get(str(interval or ""), 0))


def bucket_start(ts: float, interval: str, symbol: str = "") -> float:
    """返回 ts 所属周期桶的起始 Unix 秒。

    分钟 / 小时：按市场时区对齐到自然刻线（UTC 加密为 epoch 取模）。
    日 / 3 日 / 周 / 月 / 年：按市场当地日历边界对齐。
    """
    sec = interval_seconds(interval)
    if sec <= 0:
        return float(ts)
    market = market_of(symbol)
    tz = tz_for(symbol)

    if sec < 86400:
        if market == "crypto":
            return float(int(math.floor(float(ts) / sec) * sec))
        local = datetime.fromtimestamp(float(ts), tz)
        if sec < 3600:
            mins = int(sec // 60)
            local = local.replace(minute=(local.minute // mins) * mins,
                                  second=0, microsecond=0)
        else:
            hours = int(sec // 3600)
            local = local.replace(hour=(local.hour // hours) * hours,
                                  minute=0, second=0, microsecond=0)
        return float(int(local.timestamp()))

    # 3 日：加密沿用数据源的 epoch 天取模；股票用当地日历日序号取模。
    if interval in ("3d", "3day"):
        if market == "crypto":
            day = int(math.floor(float(ts) / 86400))
            return float((day // 3) * 3 * 86400)
        d = datetime.fromtimestamp(float(ts), tz).date()
        start = d - timedelta(days=d.toordinal() % 3)
        return float(int(datetime(start.year, start.month, start.day,
                                  tzinfo=tz).timestamp()))

    if market == "crypto":
        d = datetime.fromtimestamp(float(ts), timezone.utc).date()
    else:
        d = datetime.fromtimestamp(float(ts), tz).date()

    if interval in ("1d", "day"):
        start = d
    elif interval in ("1w", "week"):
        start = d - timedelta(days=d.weekday())
    elif interval in ("1M", "month"):
        start = d.replace(day=1)
    else:                                                # 1y / 1year
        start = d.replace(month=1, day=1)

    if market == "crypto":
        return float(int(datetime(start.year, start.month, start.day,
                                  tzinfo=timezone.utc).timestamp()))
    return float(int(datetime(start.year, start.month, start.day,
                              tzinfo=tz).timestamp()))


def next_bucket_start(ts: float, interval: str, symbol: str = "") -> float:
    """返回紧随 ts 所属桶之后的桶起点（跨月 / 跨年按当地日历推进）。"""
    sec = interval_seconds(interval)
    if sec <= 0:
        return float(ts)
    base = bucket_start(ts, interval, symbol)
    if interval not in ("1M", "month", "1y", "1year"):
        return float(base + sec)
    tz = tz_for(symbol)
    if market_of(symbol) == "crypto":
        d = datetime.fromtimestamp(base, timezone.utc).date()
        out = (d.replace(year=d.year + 1, month=1, day=1)
               if interval in ("1y", "1year")
               else (d.replace(day=28) + timedelta(days=4)).replace(day=1))
        return float(int(datetime(out.year, out.month, out.day,
                                  tzinfo=timezone.utc).timestamp()))
    d = datetime.fromtimestamp(base, tz).date()
    out = (d.replace(year=d.year + 1, month=1, day=1)
           if interval in ("1y", "1year")
           else (d.replace(day=28) + timedelta(days=4)).replace(day=1))
    return float(int(datetime(out.year, out.month, out.day,
                              tzinfo=tz).timestamp()))


def label_for(ts: float, interval: str, symbol: str = "") -> str:
    """按市场时区生成横轴标签；与 bucket_start 同源，不再用进程本地时区。"""
    tz = tz_for(symbol)
    d = datetime.fromtimestamp(float(ts), tz)
    if interval in ("1M", "month"):
        return d.strftime("%Y-%m")
    if interval in ("1y", "1year"):
        return d.strftime("%Y")
    if interval in ("1d", "3d", "1w", "day", "3day", "week"):
        return d.strftime("%m-%d")
    return d.strftime("%m-%d %H:%M")


def naive_to_timestamp(naive: datetime, symbol: str = "") -> float:
    """把数据源返回的“不带时区”的本地时间串，按市场时区转成 Unix 秒。

    修复原来用 `datetime.timestamp()` / `time.mktime()` 解释为进程本地时区，
    导致美股日线在非 UTC+8 设备上错一天的问题。
    """
    tz = tz_for(symbol)
    return float(naive.replace(tzinfo=tz).timestamp())


def preview_fields(symbol: str, interval: str, price: float,
                   quote_ts: float = 0.0, now: float | None = None) -> dict:
    """生成“当前未完成周期预览”所需字段。

    价格必须是真实收到的报价；price<=0 时返回空字典，调用方不得创建预览。
    成交量为 0 且 preview=True：明确表示这不是已完成 K 线，不写入缓存。
    """
    try:
        p = float(price)
    except (TypeError, ValueError):
        return {}
    if not math.isfinite(p) or p <= 0:
        return {}
    now = float(now if now is not None else time.time())
    quote_ts = float(quote_ts or now)
    bucket = bucket_start(now, interval, symbol)
    return {
        "ts": bucket,
        "label": label_for(bucket, interval, symbol),
        "open": p, "high": p, "low": p, "close": p,
        "volume": 0.0, "preview": True,
        "quote_ts": quote_ts, "source": "实时报价预览（非已完成 K 线）",
    }


def is_new_bucket(last_ts: float, interval: str, symbol: str = "",
                  now: float | None = None) -> bool:
    """当前系统时间是否已经越过最后一根真实 K 线所在的周期。"""
    if not last_ts:
        return False
    now = float(now if now is not None else time.time())
    return bucket_start(now, interval, symbol) > float(last_ts)
