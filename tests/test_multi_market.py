# -*- coding: utf-8 -*-
"""多市场数据层测试：混合取数 + 搜索。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.market_manager import MarketManager

m = MarketManager()

# ---- 1. 混合市场行情 ----
symbols = ["BTC", "ETH", "SH:600519", "SZ:000001", "HK:00700", "US:AAPL"]
t = m.fetch_tickers(symbols)
print(f"返回 {len(t)}/{len(symbols)} 个标的 | 来源: {m.source_name}")
for s in symbols:
    tk = t.get(s)
    if tk:
        print(f"  {s} [{tk.name}] 价格={tk.last_price} "
              f"涨跌={tk.change_pct:+.2f}% 额={tk.quote_volume_24h:,.0f}")
    else:
        print(f"  {s}: 未返回!")

# ---- 2. 搜索 ----
print()
for q in ("doge", "茅台", "apple", "00700", "tesla"):
    r = m.search(q)
    print(f"搜索[{q}] {len(r)} 条:")
    for item in r[:6]:
        print(f"   {item['symbol']} {item['name']} ({item['kind']})")
print("\n数据层多市场测试通过")
