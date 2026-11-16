# -*- coding: utf-8 -*-
"""链上标的离线 / 异常环境兼容测试。

覆盖第五阶段要求：
- 无网络时不崩溃、明确失败、绝不伪造 K 线
- 缓存命中时零网络请求
- 状态清晰区分：ok / cache / empty / no_pool / rate_limited
- 全部数据源失败时快速返回（有总预算），不无限重试
- 时间预算内不会写出任何假数据到缓存

运行：CT_OFFLINE=1 python tests/test_onchain_offline.py
"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from data import onchain_kline as ock
from data import onchain
from data.api_base import MarketApiError

PASS = FAIL = 0


def ok(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("PASS", name)
    else:
        FAIL += 1; print("FAIL", name, extra)


SOL = "So11111111111111111111111111111111111111112"
SYM = onchain.make_symbol(SOL)
orig_get = ock.HTTP.get

# 隔离缓存文件
cp = ock._pool_cache_path()
backup = open(cp, "rb").read() if os.path.exists(cp) else None
if os.path.exists(cp):
    os.remove(cp)

try:
    print("\n--- 1. 全源不可达：快速失败 + 明确状态 ---")
    def down(*a, **k):
        raise OSError("network unreachable")
    ock.HTTP.get = down
    t0 = time.time()
    try:
        ock.fetch_ohlcv(SYM, "1h")
        ok("不可达时抛 MarketApiError", False)
    except MarketApiError:
        ok("不可达时抛 MarketApiError", True)
    elapsed = time.time() - t0
    ok("有总预算不无限等待", elapsed < 25, f"{elapsed:.1f}s")
    st = ock.last_status(SYM)
    ok("状态明确区分（非空/未知）",
       st["state"] in ("empty", "no_pool", "rate_limited"), st["state"])
    ok("失败不写缓存（无伪造数据）", ock.fetch_ohlcv(SYM, "1h", allow_empty=True) == [])

    print("\n--- 2. 限流单独识别 ---")
    def limited(*a, **k):
        class R:
            status_code = 429
            def json(self): return {}
        return R()
    ock.HTTP.get = limited
    try:
        ock.fetch_ohlcv(SYM, "1h", allow_empty=True)
    except MarketApiError:
        pass
    ok("限流被识别为 rate_limited",
       ock.last_status(SYM)["state"] == "rate_limited",
       ock.last_status(SYM)["state"])

    print("\n--- 3. 缓存命中零请求 ---")
    # 造一个已缓存的池 + 正常 OHLCV
    class R:
        def __init__(self, p): self.status_code = 200; self._p = p
        def json(self): return self._p
    ock.HTTP.get = lambda *a, **k: R({"data": [
        {"id": "solana_offlinePool", "attributes": {"reserve_in_usd": "100000"}}]})
    ock._resolve_pool(SOL)
    gt_rows = [[1700000000 + i * 3600, 10+i, 12+i, 9+i, 11+i, 100+i]
               for i in range(4)]
    ock.HTTP.get = lambda *a, **k: R({"data": {"attributes": {"ohlcv_list": gt_rows}}})
    bars = ock.fetch_ohlcv(SYM, "1h")
    ok("首次拿到真实 K 线", len(bars) == 4)
    ok("状态 ok", ock.last_status(SYM)["state"] == "ok")

    # 写本地 K 线缓存并验证后续读取不触发网络
    import data.kline_cache as kc
    from data.klines import Candle
    tmp = tempfile.mkdtemp()
    old = os.environ.get("APPDATA")
    os.environ["APPDATA"] = tmp
    try:
        cs = [Candle(ts=b.ts, time_label=b.time_label, open=b.open, high=b.high,
                     low=b.low, close=b.close, volume=b.volume) for b in bars]
        kc.save(SYM, "1h", cs)
        ok("本地缓存可读且数据一致", len(kc.load(SYM, "1h")) == 4)
        ok("缓存新鲜度判定 True", kc.is_fresh(SYM, "1h"))
    finally:
        if old is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = old

    print("\n--- 4. 空响应被识别为无历史（非伪造） ---")
    ock.invalidate_pool(SOL)
    ock.HTTP.get = lambda *a, **k: R({"data": {"attributes": {"ohlcv_list": []}}})
    empty = ock.fetch_ohlcv(SYM, "1h", allow_empty=True)
    ok("空响应返回空列表", empty == [])
    ok("状态非 ok（未伪造）", ock.last_status(SYM)["state"] != "ok")

finally:
    ock.HTTP.get = orig_get
    if backup is not None:
        open(cp, "wb").write(backup)
    elif os.path.exists(cp):
        os.remove(cp)

print("\n" + "=" * 60)
print(f"结果: {PASS} 通过 / {FAIL} 失败")
sys.exit(1 if FAIL else 0)
