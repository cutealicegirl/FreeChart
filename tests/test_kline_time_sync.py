# -*- coding: utf-8 -*-
"""K 线时间同步专项回归：周期边界 / 时区 / 缓存 / 预览。

覆盖用户反馈的跨日滞后、突然补齐、周期边界不一致问题：
- 23:45 -> 23:59 -> 00:00 -> 00:01 -> 00:15 -> 01:00 -> 04:00
- 15m / 1h / 4h / 日 / 周 / 月 / 年，含 2h/6h/12h
- UTC（加密/DEX）、Asia/Shanghai（A股/港股）、America/New_York（美股含 DST）
- 无成交推进、缓存 checked_bucket、预览不落盘、历史回溯不刷新 updated

运行：python tests/test_kline_time_sync.py
"""
import os
import sys
import tempfile
import threading
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import kline_time as kt
from data import kline_cache as kc
from data.klines import Candle, refresh_seconds, _aggregate

PASS = FAIL = 0


def ok(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("PASS", name)
    else:
        FAIL += 1
        print("FAIL", name, extra)


def utc(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp()


print("\n--- 1. 周期集合与刷新频率 ---")
expected = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600,
            "12h": 43200, "1d": 86400, "3d": 259200,
            "1w": 604800, "1M": 2592000}
ok("全部用户列举周期都有明确秒数",
   all(kt.interval_seconds(k) == v for k, v in expected.items()))
ok("刷新分档统一（30m=10s / 1h~6h=30s / 12h+=60s）",
   refresh_seconds("30m") == 10 and refresh_seconds("1h") == 30
   and refresh_seconds("6h") == 30 and refresh_seconds("12h") == 60
   and refresh_seconds("day") == 60 and refresh_seconds("m30") == 10,
   f"{[refresh_seconds(k) for k in ('30m','1h','6h','12h','day','m30')]}")
ok("未知周期返回 0 秒（不再静默回落到 15m）",
   kt.interval_seconds("bogus") == 0)

print("\n--- 2. 加密 / DEX（UTC）跨日边界 ---")
# 2026-11-17 23:45/23:59 UTC -> 11-18 00:00/00:01/00:15/01:00/04:00
t_2345 = utc(2026, 11, 17, 23, 45)
t_2359 = utc(2026, 11, 17, 23, 59)
t_0000 = utc(2026, 11, 18, 0, 0)
t_0001 = utc(2026, 11, 18, 0, 1)
t_0015 = utc(2026, 11, 18, 0, 15)
t_0100 = utc(2026, 11, 18, 1, 0)
t_0400 = utc(2026, 11, 18, 4, 0)
SYM = "BTC"
ok("15m: 23:45/23:59 同桶，00:00 新桶",
   kt.bucket_start(t_2345, "15m", SYM) == t_2345
   and kt.bucket_start(t_2359, "15m", SYM) == utc(2026, 11, 17, 23, 45)
   and kt.bucket_start(t_0000, "15m", SYM) == t_0000)
ok("15m: 00:01/00:15 归属正确",
   kt.bucket_start(t_0001, "15m", SYM) == t_0000
   and kt.bucket_start(t_0015, "15m", SYM) == t_0015)
ok("1h: 23:59 仍属 23:00，00:00 切到 00:00",
   kt.bucket_start(t_2359, "1h", SYM) == utc(2026, 11, 17, 23)
   and kt.bucket_start(t_0000, "1h", SYM) == t_0000)
ok("2h: 01:00 回落到 00:00 桶，04:00 是新桶",
   kt.bucket_start(t_0100, "2h", SYM) == t_0000
   and kt.bucket_start(t_0400, "2h", SYM) == t_0400)
ok("4h: 03:59 仍属 00:00，04:00 切桶",
   kt.bucket_start(utc(2026, 11, 18, 3, 59), "4h", SYM) == t_0000
   and kt.bucket_start(t_0400, "4h", SYM) == t_0400)
ok("6h: 04:00 回落到 00:00 桶，06:00 才切",
   kt.bucket_start(t_0400, "6h", SYM) == t_0000
   and kt.bucket_start(utc(2026, 11, 18, 6), "6h", SYM) == utc(2026, 11, 18, 6))
ok("12h: 00:00/01:00 同桶，12:00 切桶",
   kt.bucket_start(t_0100, "12h", SYM) == t_0000
   and kt.bucket_start(utc(2026, 11, 18, 12), "12h", SYM) == utc(2026, 11, 18, 12))
ok("日线: UTC 23:59 -> 次日 00:00 切桶",
   kt.bucket_start(t_2359, "1d", SYM) == utc(2026, 11, 17)
   and kt.bucket_start(t_0000, "1d", SYM) == utc(2026, 11, 18))
ok("周线: 周日仍在本周，周一开新周",
   kt.bucket_start(utc(2026, 11, 22, 23), "1w", SYM) == utc(2026, 11, 16)
   and kt.bucket_start(utc(2026, 11, 23), "1w", SYM) == utc(2026, 11, 23))
ok("月线: 11-30 23:59 -> 12-01 切桶（自然月，不是 30 天块）",
   kt.bucket_start(utc(2026, 11, 30, 23, 59), "1M", SYM) == utc(2026, 11, 1)
   and kt.bucket_start(utc(2026, 12, 1), "1M", SYM) == utc(2026, 12, 1))
ok("跨年: 12-31 23:59 -> 01-01 00:00 切年/月",
   kt.bucket_start(utc(2026, 12, 31, 23, 59), "1y", SYM) == utc(2026, 1, 1)
   and kt.bucket_start(utc(2027, 1, 1), "1y", SYM) == utc(2027, 1, 1))
ok("闰年 2 月 29 日仍在 2 月桶",
   kt.bucket_start(utc(2028, 2, 29, 12), "1M", SYM) == utc(2028, 2, 1))
ok("next_bucket_start 月线跨月/跨年正确",
   kt.next_bucket_start(utc(2026, 12, 15), "1M", SYM) == utc(2027, 1, 1)
   and kt.next_bucket_start(utc(2028, 2, 1), "1M", SYM) == utc(2028, 3, 1))

print("\n--- 3. 市场时区（A股 / 美股 DST） ---")
CN = "SH:600519"
US = "US:AAPL"
ok("A股日线按北京 00:00 切（不是 UTC 00:00）",
   kt.bucket_start(kt.naive_to_timestamp(
       datetime(2026, 11, 17, 23, 59), CN), "day", CN)
   == kt.naive_to_timestamp(datetime(2026, 11, 17), CN)
   and kt.bucket_start(kt.naive_to_timestamp(
       datetime(2026, 11, 18, 0, 0), CN), "day", CN)
   == kt.naive_to_timestamp(datetime(2026, 11, 18), CN))
ok("A股 1h 按北京整点切",
   kt.bucket_start(kt.naive_to_timestamp(
       datetime(2026, 11, 18, 0, 59), CN), "m60", CN)
   == kt.naive_to_timestamp(datetime(2026, 11, 18, 0), CN))
ok("美股夏令时：7 月 offset=-4h",
   kt.tz_for(US).utcoffset(datetime(2026, 7, 1, 12, tzinfo=kt.tz_for(US)))
   .total_seconds() == -4 * 3600)
ok("美股冬令时：1 月 offset=-5h",
   kt.tz_for(US).utcoffset(datetime(2026, 1, 1, 12, tzinfo=kt.tz_for(US)))
   .total_seconds() == -5 * 3600)
ok("美股日线桶按美东当地午夜（夏/冬均正确）",
   kt.bucket_start(kt.naive_to_timestamp(
       datetime(2026, 7, 1, 15, 59), US), "day", US)
   == kt.naive_to_timestamp(datetime(2026, 7, 1), US)
   and kt.bucket_start(kt.naive_to_timestamp(
       datetime(2026, 1, 1, 15, 59), US), "day", US)
   == kt.naive_to_timestamp(datetime(2026, 1, 1), US))
ok("UTC 分桶 vs 北京跨日：加密日线仍属前一日 UTC 桶",
   kt.bucket_start(kt.naive_to_timestamp(
       datetime(2026, 11, 18, 0, 1), CN), "1d", "BTC")
   == utc(2026, 11, 17))

print("\n--- 4. 当前周期预览（不伪造 / 不落盘） ---")
now = utc(2026, 11, 18, 0, 1)
f = kt.preview_fields("BTC", "1h", 42000.5, quote_ts=now, now=now)
ok("跨 00:00 后预览根落到 00:00 桶",
   f["ts"] == t_0000 and f["preview"] is True, str(f))
ok("预览 OHLC 全部来自真实报价、volume=0",
   f["open"] == f["high"] == f["low"] == f["close"] == 42000.5
   and f["volume"] == 0.0)
ok("无有效报价时不生成预览",
   kt.preview_fields("BTC", "1h", 0, now=now) == {})
ok("is_new_bucket 正确识别跨周期",
   kt.is_new_bucket(t_2359, "1h", "BTC", now=t_0001)
   and not kt.is_new_bucket(t_0000, "1h", "BTC", now=t_0001))

print("\n--- 5. 缓存新鲜度 / checked_bucket / 预览隔离 ---")
tmp = tempfile.mkdtemp()
old_appdata = os.environ.get("APPDATA")
old_now = kc._now
old_conn = kc._local
os.environ["APPDATA"] = tmp
kc._local = threading.local()
try:
    t0 = utc(2026, 11, 18, 0, 1)
    kc._now = lambda: t0
    real = Candle(ts=t_0000, time_label="11-18 00:00", open=1, high=2,
                  low=0.5, close=1.5, volume=10)
    prev = Candle(ts=t_0000, time_label="预览", open=9, high=9, low=9,
                  close=9, volume=0, preview=True)
    kc.save("BTC", "1h", [real, prev])
    ok("预览根不写入缓存", len(kc.load("BTC", "1h")) == 1)
    ok("当前桶真实缓存 fresh", kc.is_fresh("BTC", "1h"))
    ok("last_bar_ts 取真实根", kc.last_bar_ts("BTC", "1h") == t_0000)

    t1 = utc(2026, 11, 18, 1, 1)   # 跨到 01:00 桶
    kc._now = lambda: t1
    ok("跨周期立刻 stale（不再等满 15 分钟）",
       not kc.is_fresh("BTC", "1h"))
    kc.mark_checked("BTC", "1h", kt.bucket_start(t1, "1h", "BTC"))
    ok("源确认本桶无新根后 fresh（不重复打源）",
       kc.is_fresh("BTC", "1h"))

    t2 = t1 + 901
    kc._now = lambda: t2
    ok("TTL 到期后重新校验", not kc.is_fresh("BTC", "1h"))

    # 历史回溯 save(touch=False) 不得刷新 updated
    kc._now = lambda: t0
    kc.save("BTC", "1h", [real])
    updated_before = kc._meta("BTC", "1h")[1]
    kc._now = lambda: t0 + 500
    kc.save("BTC", "1h", [], exhausted=True, touch=False)
    ok("历史回溯不刷新 updated（旧根因：泵一直挡住最新请求）",
       kc._meta("BTC", "1h")[1] == updated_before)
finally:
    kc._now = old_now
    kc._local = old_conn
    if old_appdata is None:
        os.environ.pop("APPDATA", None)
    else:
        os.environ["APPDATA"] = old_appdata

print("\n--- 6. 聚合桶边界 ---")
monthly = [
    Candle(ts=utc(2026, 11, 30, 22), time_label="", open=1, high=2,
           low=1, close=2, volume=1),
    Candle(ts=utc(2026, 12, 1, 0, 5), time_label="", open=3, high=4,
           low=3, close=4, volume=2),
    Candle(ts=utc(2027, 1, 1, 0, 5), time_label="", open=5, high=6,
           low=5, close=6, volume=3),
]
years = _aggregate(monthly, "year", "BTC")
ok("年K按 UTC 自然年分桶，ts=桶起点",
   len(years) == 2 and years[0].ts == utc(2026, 1, 1)
   and years[1].ts == utc(2027, 1, 1),
   str([c.ts for c in years]))

print(f"\n=== 结果: {PASS} 通过 / {FAIL} 失败 ===")
sys.exit(1 if FAIL else 0)
