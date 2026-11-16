# -*- coding: utf-8 -*-
"""链上标的真实历史 K 线链路回归测试（离线，全部用 mock 数据）。

覆盖：标准化清洗 / 时间戳单位 / OHLC 约束 / 去重排序 / 交易池解析 /
池迁移重解析 / 多源回退 / 分页回溯 / fetch_klines 分派 / 周期映射 /
缓存持久化与增量去重 / 绝不伪造数据。

运行：python tests/test_onchain_kline.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from data import onchain, onchain_kline as ock
from data.api_base import MarketApiError
from data import klines

PASS = 0
FAIL = 0


def ok(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("PASS", name)
    else:
        FAIL += 1
        print("FAIL", name, extra)


class Resp:
    def __init__(self, code, payload):
        self.status_code = code
        self._p = payload

    def json(self):
        return self._p


SOL = "So11111111111111111111111111111111111111112"
SYM = onchain.make_symbol(SOL)

# ---------------------------------------------------------------- 标准化
print("\n--- 1. 标准化清洗 ---")
rows = [
    [1700000000, 100, 110, 95, 105, 1000],   # 正常
    [1700003600, 105, 108, 102, 106, 800],
    [1700000000, 100, 999, 95, 105, 500],    # 同 ts 重复，保留最后
    [1700007200, 106, 100, 99, 105, 300],    # high < open，非法
    [1700010800, 105, 108, -1, 106, 300],    # low < 0，非法
    [1700014400, 106, 110, 104, -1, 300],    # close < 0，非法
    [1700018000, 106, 108, 104, 107, -5],    # 负成交量，非法
    ["bad", "x", "y", "z", "q", 1],          # 非数值
]
bars = ock.normalize(rows, "1h")
# 8 行里：1 个同 ts 重复(覆盖) + 5 个非法 + 2 个有效 → 去重后 2 根
ok("非法行全部丢弃", len(bars) == 2, f"got {len(bars)}")
ok("时间正序", [b.ts for b in bars] == sorted(b.ts for b in bars))
ok("同时间戳去重保留最后一条", bars[0].high == 999, f"high={bars[0].high}")
ok("OHLC 字段完整", all(hasattr(b, "volume") for b in bars))

# 时间戳单位自动识别
ms = ock.normalize([[1700000000000, 10, 12, 9, 11, 5]], "1h")
sec = ock.normalize([[1700000000, 10, 12, 9, 11, 5]], "1h")
ok("毫秒时间戳归一为秒", len(ms) == 1 and abs(ms[0].ts - sec[0].ts) < 1)
us = ock.normalize([[1700000000000000, 10, 12, 9, 11, 5]], "1h")
ok("微秒时间戳归一为秒", len(us) == 1 and abs(us[0].ts - sec[0].ts) < 1)

# 周期桶对齐：把 10:37 归到 10:00
import datetime as _dt
ts_1037 = _dt.datetime(2023, 11, 14, 10, 37).timestamp()
aligned = ock.normalize([[ts_1037, 10, 12, 9, 11, 5]], "1h")
ok("时间对齐到周期桶起点",
   abs(aligned[0].ts - _dt.datetime(2023, 11, 14, 10, 0).timestamp()) < 1)

# ---------------------------------------------------------------- 池解析
print("\n--- 2. 交易池解析与缓存 ---")
orig_get = ock.HTTP.get
cache_path = ock._pool_cache_path()
backup = None
if os.path.exists(cache_path):
    backup = open(cache_path, "rb").read()
    os.remove(cache_path)

search_payload = {"data": [
    {"id": "solana_lowLiq", "attributes": {"reserve_in_usd": "100", "name": "A"}},
    {"id": "solana_bestPoolXYZ", "attributes": {"reserve_in_usd": "90000", "name": "B"}},
]}
ock.HTTP.get = lambda *a, **k: Resp(200, search_payload)
pool = ock._resolve_pool(SOL)
ok("搜索结果选流动性最高的池", pool and pool["network"] == "solana"
   and pool["pool"] == "bestPoolXYZ", str(pool))
ok("池解析结果落盘缓存", os.path.exists(cache_path))

# 缓存命中：再次调用不应发请求
called = []
def fail_if_called(*a, **k):
    called.append(1)
    return Resp(500, {})
ock.HTTP.get = fail_if_called
pool2 = ock._resolve_pool(SOL)
ok("TTL 内命中缓存不再请求", pool2 == pool and not called)

# 池迁移：invalidate 后重新解析
ock.invalidate_pool(SOL)
called2 = []
ock.HTTP.get = lambda *a, **k: (called2.append(1) or Resp(
    200, {"data": [{"id": "solana_newPoolMIG",
                    "attributes": {"reserve_in_usd": "200000"}}]}))
pool3 = ock._resolve_pool(SOL)
ok("池迁移后可强制重解析", pool3 and pool3["pool"] == "newPoolMIG" and called2)

# ---------------------------------------------------------------- 主源 OHLCV
print("\n--- 3. GeckoTerminal 主源 ---")
GT_ROWS = [[1700000000 + i * 3600, 100 + i, 102 + i, 99 + i, 101 + i, 1000 + i]
           for i in range(5)]
def fake_gecko(*a, **k):
    return Resp(200, {"data": {"attributes": {"ohlcv_list": GT_ROWS}}})
ock.HTTP.get = fake_gecko
bars = ock.fetch_ohlcv(SYM, "1h")
ok("主源返回真实 K 线", len(bars) == 5)
ok("状态上报 ok + 来源", ock.last_status(SYM)["state"] == "ok"
   and ock.last_status(SYM)["source"] == ock.SOURCE_GECKO)

# before_timestamp 分页参数
seen_params = {}
def fake_gecko_paged(*a, **k):
    seen_params.update(k.get("params") or {})
    return Resp(200, {"data": {"attributes": {"ohlcv_list": GT_ROWS}}})
ock.HTTP.get = fake_gecko_paged
ock.fetch_ohlcv(SYM, "1h", before_ts=1700003600)
ok("回溯传 before_timestamp", seen_params.get("before_timestamp") == 1700003600)

# ---------------------------------------------------------------- 多源回退
print("\n--- 4. 多源回退 ---")
def all_fail(*a, **k):
    raise RuntimeError("network down")
ock.HTTP.get = all_fail
try:
    ock.fetch_ohlcv(SYM, "1h")
    ok("全部源失败抛 MarketApiError", False)
except MarketApiError:
    ok("全部源失败抛 MarketApiError", True)
ok("失败状态被记录", ock.last_status(SYM)["state"] in
   ("empty", "no_pool", "rate_limited"))
ok("失败时 allow_empty 返回空而不抛",
   ock.fetch_ohlcv(SYM, "1h", allow_empty=True) == [])

# 主源空 → 备源 CoinGecko 顶上
CG_ROWS = [[1700000000000 + i * 86400000, 10, 12, 9, 11]
           for i in range(3)]
def gecko_empty_coingecko_ok(url, *a, **k):
    if "geckoterminal" in url:
        return Resp(200, {"data": {"attributes": {"ohlcv_list": []}}})
    return Resp(200, CG_ROWS)
ock.HTTP.get = gecko_empty_coingecko_ok
ock.invalidate_pool(SOL)
bars = ock.fetch_ohlcv(SYM, "1d")
ok("主源空时备源返回真实 K 线", len(bars) == 3)
ok("备源成交量标记不可靠", all(not b.volume_reliable for b in bars))
ok("状态来源切换到 CoinGecko",
   ock.last_status(SYM)["source"] == ock.SOURCE_COINGECKO)

# ---------------------------------------------------------------- klines 分派
print("\n--- 5. fetch_klines / fetch_klines_before 分派 ---")
# 重新写入池缓存（上一节 invalidate 过），确保主源能解析到池
ock.HTTP.get = lambda *a, **k: Resp(
    200, {"data": [{"id": "solana_dispatchPool",
                    "attributes": {"reserve_in_usd": "50000"}}]})
ock._resolve_pool(SOL)
ock.HTTP.get = fake_gecko
cs = klines.fetch_klines(SYM, "1h")
ok("fetch_klines 分派到链上真实 K 线", len(cs) == 5 and cs[0].close == 101)
ok("Candle 字段正确", hasattr(cs[0], "time_label") and cs[0].volume == 1000)
older, exhausted = klines.fetch_klines_before(SYM, "1h", before_ts=1700003600)
ok("fetch_klines_before 分派且过滤时间", all(c.ts < 1700003600 for c in older))
ok("intervals_for 返回链上周期", ("日K", "1d") in klines.intervals_for(SYM))
ok("default_interval 为链上默认", klines.default_interval(SYM) == "1h")

# ---------------------------------------------------------------- 缓存
print("\n--- 6. 缓存持久化与增量 ---")
import data.kline_cache as kc
tmp = tempfile.mkdtemp()
old_appdata = os.environ.get("APPDATA")
os.environ["APPDATA"] = tmp
try:
    kc.save(SYM, "1h", cs)
    loaded = kc.load(SYM, "1h")
    ok("链上 K 线写入 SQLite 并可读取", len(loaded) == 5)
    # 增量：新一根 + 一根重复
    newc = klines.Candle(ts=cs[-1].ts + 3600, time_label="x",
                         open=1, high=2, low=0.5, close=1.5, volume=10)
    kc.save(SYM, "1h", [cs[0], newc])
    merged = {c.ts: c for c in kc.load(SYM, "1h")}
    ok("增量更新去重（主键 ts）", len(merged) == 6 and merged[newc.ts].close == 1.5)
finally:
    if old_appdata is None:
        os.environ.pop("APPDATA", None)
    else:
        os.environ["APPDATA"] = old_appdata

# ---------------------------------------------------------------- 恢复现场
ock.HTTP.get = orig_get
if backup is not None:
    open(cache_path, "wb").write(backup)
elif os.path.exists(cache_path):
    os.remove(cache_path)

print("\n" + "=" * 60)
print(f"结果: {PASS} 通过 / {FAIL} 失败")
sys.exit(1 if FAIL else 0)
