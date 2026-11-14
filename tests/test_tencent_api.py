# -*- coding: utf-8 -*-
"""测试腾讯股票行情 API 与搜索接口的连通性和数据格式。"""
import re

import requests

s = requests.Session()
s.trust_env = False
s.headers["User-Agent"] = "Mozilla/5.0"

# ---- 1. 行情接口：A股 / 港股 / 美股 ----
print("=== 行情: qt.gtimg.cn ===")
try:
    r = s.get("https://qt.gtimg.cn/q=sh600519,sz000001,hk00700,usAAPL",
              timeout=10)
    r.encoding = "gbk"
    print("HTTP", r.status_code)
    for line in r.text.split(";"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"v_(\w+)=\"(.*)\"", line)
        if m:
            code, fields = m.group(1), m.group(2).split("~")
            print(f"[{code}] 字段数={len(fields)}")
            print("   名称:", fields[1], "| 现价:", fields[3],
                  "| 涨跌%:", fields[32] if len(fields) > 32 else "?",
                  "| 高:", fields[33] if len(fields) > 33 else "?")
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:150])

# ---- 2. 搜索接口 ----
print("\n=== 搜索: smartbox.gtimg.cn (中文/拼音/代码) ===")
for q in ("茅台", "maotai", "AAPL", "apple", "00700"):
    try:
        r = s.get("https://smartbox.gtimg.cn/s3/", params={"v": 2, "q": q,
                                                           "t": "all"},
                  timeout=10)
        r.encoding = "gbk"
        text = r.text[:300]
        print(f"[{q}] HTTP {r.status_code}: {text[:200]}")
    except Exception as e:
        print(f"[{q}] FAIL:", type(e).__name__, str(e)[:100])
