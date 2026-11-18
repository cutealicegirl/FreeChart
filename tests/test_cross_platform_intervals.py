# -*- coding: utf-8 -*-
"""双端 K 线周期集合一致性回归测试。

Windows 侧读取 data/klines.py 的周期表，Android 侧读取 app.js 的周期数组
（用正则提取，不依赖 Node 运行环境），断言两端对各市场暴露的周期键完全一致。
同时校验桌面美股分钟线 type 映射与周期键匹配（历史 bug：m1 曾写成 1m 导致
选 1 分实际取 5 分数据）。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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


from data import klines  # noqa: E402

with open(os.path.join(ROOT, "android", "assets", "www", "app.js"),
          encoding="utf-8") as f:
    js = f.read()


def js_intervals(varname):
    """从 app.js 提取 var XXX = [[label, key], ...] 里的 key 列表。"""
    m = re.search(r"var\s+" + varname + r"\s*=\s*\[(.*?)\];", js, re.S)
    assert m, "未找到 " + varname
    return [k for k in re.findall(r"\['[^']+'\s*,\s*'([^']+)'\]", m.group(1))]


def py_keys(varname):
    return [k for _, k in getattr(klines, varname)]


# 1) 加密货币周期集合一致
py_crypto = py_keys("CRYPTO_INTERVALS")
js_crypto = js_intervals("CRYPTO_INTERVALS")
ok("crypto 周期集合双端一致", py_crypto == js_crypto,
   f"\n  Windows={py_crypto}\n  Android={js_crypto}")
# 防止“两端一致地缺失”通过：用户明确要求覆盖 1m~12h 全周期。
EXPECTED_CRYPTO = ["1m", "5m", "15m", "30m", "1h", "2h", "4h",
                   "6h", "12h", "1d", "3d", "1w", "1M", "1y"]
ok("加密端覆盖全部要求周期（含 2h/6h/12h）",
   py_crypto == EXPECTED_CRYPTO,
   f"\n  Windows={py_crypto}\n  期望={EXPECTED_CRYPTO}")

# 2) 股票（A股）周期集合：桌面 STOCK_INTERVALS == Android CN_MINUTES + STOCK_INTERVALS
py_stock = py_keys("STOCK_INTERVALS")
js_cn = js_intervals("CN_MINUTES") + js_intervals("STOCK_INTERVALS")
ok("A股周期集合双端一致", set(py_stock) == set(js_cn),
   f"\n  Windows={py_stock}\n  Android={js_cn}")

# 3) 美股周期集合：桌面 US_INTERVALS == Android US_MINUTES + STOCK_INTERVALS
py_us = py_keys("US_INTERVALS")
js_us = js_intervals("US_MINUTES") + js_intervals("STOCK_INTERVALS")
ok("美股周期集合双端一致", set(py_us) == set(js_us),
   f"\n  Windows={py_us}\n  Android={js_us}")

# 4) 港股周期集合：桌面 HK_INTERVALS == Android STOCK_INTERVALS
py_hk = py_keys("HK_INTERVALS")
js_hk = js_intervals("STOCK_INTERVALS")
ok("港股周期集合双端一致", py_hk == js_hk,
   f"\n  Windows={py_hk}\n  Android={js_hk}")

# 5) 桌面美股分钟线 type 映射必须覆盖所有暴露的分钟周期键
minute_keys = [k for k in py_us if re.fullmatch(r"m\d+", k)]
missing = [k for k in minute_keys if k not in klines._US_SINA_TYPE]
ok("桌面美股分钟周期均有 type 映射（m1 历史 bug 回归）",
   not missing, f"缺失映射={missing}")

# 6) Android 美股 typeMap 必须覆盖相同分钟周期
m = re.search(r"var\s+typeMap\s*=\s*\{([^}]+)\}", js)
assert m, "未找到美股 typeMap"
js_type_keys = set(re.findall(r"\b(m\d+)\s*:", m.group(1)))
ok("Android 美股分钟 typeMap 覆盖全部分钟周期",
   set(minute_keys) == js_type_keys,
   f"Windows={set(minute_keys)} Android={js_type_keys}")

# 7) Android 年K 走月线聚合而非透传非法 interval
ok("Android 年K 用 1M 聚合（不透传 1y）",
   "interval === '1y'" in js and "'&interval=1M&limit=1000'" in js)

# 8) 链上 DEX K 线周期集合：桌面 onchain_kline.ONCHAIN_INTERVALS ==
#    Android OC_INTERVALS（v1.4 新增真实历史 K 线，双端必须一致）
from data import onchain_kline as _ock  # noqa: E402
py_oc = [k for _, k in _ock.ONCHAIN_INTERVALS]
js_oc = js_intervals("OC_INTERVALS")
ok("链上 DEX 周期集合双端一致", py_oc == js_oc,
   f"\n  Windows={py_oc}\n  Android={js_oc}")
ok("链上 DEX 同样覆盖 2h/6h/12h",
   py_oc == ["1m", "5m", "15m", "30m", "1h", "2h", "4h",
             "6h", "12h", "1d", "3d", "1w", "1M"],
   f"\n  Windows={py_oc}")

# 9) 链上周期 → DEX timeframe 映射双端一致（GeckoTerminal aggregate）
py_tf = _ock._GT_TF
js_tf_block = re.search(r"var\s+OC_TF\s*=\s*\{(.*?)\};", js, re.S)
assert js_tf_block, "未找到 Android OC_TF"
js_tf_keys = re.findall(r"'([^']+)'\s*:\s*\['(\w+)',\s*(\d+)\]", js_tf_block.group(1))
js_tf = {k: (tf, int(agg)) for k, tf, agg in js_tf_keys}
ok("链上 DEX timeframe 映射双端一致",
   all(js_tf.get(k) == tuple(v) for k, v in py_tf.items()),
   f"\n  Windows={py_tf}\n  Android={js_tf}")

print(f"\n=== 结果: {PASS} 通过 / {FAIL} 失败 ===")
sys.exit(1 if FAIL else 0)
