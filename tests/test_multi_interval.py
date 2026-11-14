# -*- coding: utf-8 -*-
"""多周期 K 线数据层测试：周/月/年/3日 + 聚合正确性。"""
import sys
sys.path.insert(0, ".")

from data.klines import fetch_klines

cases = [
    ("BTC", "3d", 50), ("BTC", "1w", 30), ("BTC", "1M", 24), ("BTC", "1y", 5),
    ("SH:600519", "week", 30), ("SH:600519", "month", 12),
    ("SH:600519", "3day", 20), ("SH:600519", "1year", 3),
    ("US:AAPL", "week", 30), ("US:AAPL", "month", 6), ("US:AAPL", "1year", 3),
]

fails = 0
for sym, iv, min_n in cases:
    try:
        cs = fetch_klines(sym, iv)
        ok = len(cs) >= min_n
        # 聚合正确性抽查：高低点必须 >= 开收
        bad = [c for c in cs if c.high < max(c.open, c.close) - 1e-9
               or c.low > min(c.open, c.close) + 1e-9]
        status = "OK" if ok and not bad else "FAIL"
        if status == "FAIL":
            fails += 1
        print(f"{sym} {iv}: {len(cs)} 根, 首条 {cs[0].time_label} "
              f"OHLC={cs[0].open}/{cs[0].high}/{cs[0].low}/{cs[0].close} "
              f"末条 {cs[-1].time_label} [{status}]"
              + (f" 异常{len(bad)}根" if bad else ""))
    except Exception as e:
        fails += 1
        print(f"{sym} {iv}: FAIL {type(e).__name__} {str(e)[:60]}")

print("\n结果:", "全部通过" if fails == 0 else f"{fails} 项失败")
sys.exit(1 if fails else 0)
