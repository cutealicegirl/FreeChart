# -*- coding: utf-8 -*-
"""确认腾讯行情各市场的字段索引（低点/成交额等）。"""
import re

import requests

s = requests.Session()
s.trust_env = False
s.headers["User-Agent"] = "Mozilla/5.0"

r = s.get("https://qt.gtimg.cn/q=sh600519,hk00700,usAAPL", timeout=10)
r.encoding = "gbk"
for line in r.text.split(";"):
    line = line.strip()
    if not line:
        continue
    m = re.match(r"v_(\w+)=\"(.*)\"", line)
    if not m:
        continue
    f = m.group(2).split("~")
    print(f"[{m.group(1)}] {f[1]}")
    # 打印关键候选字段
    for i in (3, 4, 5, 30, 31, 32, 33, 34, 35, 36, 37, 38, 43, 44, 45):
        if i < len(f):
            print(f"  [{i}] = {f[i]}")
