# -*- coding: utf-8 -*-
"""链上交易池身份 / 迁移连续性 / 成交量可靠性回归。

覆盖任务书「不同交易池错误拼接」「池迁移不得制造虚假连续走势」
「volume_reliable 必须在 UI 生效」三项硬要求。
"""
import os
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="fc_pool_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data import klines, onchain_kline as ock  # noqa: E402
from data import kline_cache as kc  # noqa: E402

passed = failed = 0


def ok(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("PASS " + name)
    else:
        failed += 1
        print("FAIL " + name + ("  " + str(extra) if extra else ""))


def bar(pool, ts=1700000000):
    return ock.Bar(ts=ts, time_label="x", open=10, high=11, low=9,
                   close=10.5, volume=1, pool=pool)


print("--- 1. 交易池身份与连续性判定 ---")
ok("同池可拼接", ock.pools_compatible([bar("solana_A")], [bar("solana_A")]))
ok("跨池禁止拼接", not ock.pools_compatible([bar("solana_A")],
                                            [bar("solana_B")]))
ok("旧缓存无池身份不误伤",
   ock.pools_compatible([bar("")], [bar("solana_A")]))
ok("pool_of 取到来源池", ock.pool_of([bar(""), bar("solana_A")]) == "solana_A")

print("\n--- 2. 标准化 / 聚合透传池身份 ---")
rows = [[1700000000, 100, 110, 90, 105, 12],
        [1700003600, 105, 112, 103, 108, 9]]
bars = ock.normalize(rows, "1h", pool="solana_A")
ok("normalize 记录 pool", all(b.pool == "solana_A" for b in bars))
agg = ock._aggregate(bars, "1d")
ok("聚合保留 pool", bool(agg) and all(b.pool == "solana_A" for b in agg))
ok("聚合不伪造成交量", agg and agg[0].volume == 21,
   [(b.ts, b.volume) for b in agg])

print("\n--- 3. 交易池综合评分（死池不得胜出） ---")
payload = {"data": [
    {"id": "solana_DEAD", "attributes": {
        "reserve_in_usd": 5000000, "volume_usd": {"h24": 0},
        "txns": {"h24": {"buys": 0, "sells": 0}}}},
    {"id": "solana_LIVE", "attributes": {
        "reserve_in_usd": 100000, "volume_usd": {"h24": 800000},
        "txns": {"h24": {"buys": 400, "sells": 350}}}},
]}
p = ock._pick_pool_from_payload(payload)
ok("活跃池优先于高 TVL 零成交死池", p and p["pool"] == "LIVE", p)

print("\n--- 4. 成交量可靠性 / 池身份的缓存往返 ---")
sym, itv = "ONCHAIN:TESTPOOL", "1h"
c = klines.Candle(ts=1699999200.0, time_label="x", open=1, high=2,
                  low=0.5, close=1.5, volume=0.0,
                  volume_reliable=False, pool="solana_A")
kc.save(sym, itv, [c])
loaded = kc.load(sym, itv)
ok("缓存保留 pool", bool(loaded) and loaded[0].pool == "solana_A")
ok("缓存保留 volume_reliable=False",
   bool(loaded) and loaded[0].volume_reliable is False)
ok("Candle 默认成交量可靠",
   klines.Candle(0, "x", 1, 1, 1, 1, 0).volume_reliable is True)

print("\n--- 5. 桌面图表合并保护 ---")
old = [klines.Candle(1, "x", 1, 1, 1, 1, 1, pool="solana_A")]
new = [klines.Candle(2, "x", 1, 1, 1, 1, 1, pool="solana_B")]
ok("跨池 Candle 被判不兼容",
   not klines.onchain_pools_compatible(old, new))

print("\n" + "=" * 60)
print("结果: %d 通过 / %d 失败" % (passed, failed))
print("=" * 60)
sys.exit(1 if failed else 0)
