# -*- coding: utf-8 -*-
"""指标一致性回归（Python 端）：core.indicators 对黄金数据集。

本测试只依赖标准库与 core.indicators（不导入 PySide6），
可在任意 Python 环境运行；与 android/tests/test_app_indicator_consistency.js
共用同一份 tests/fixtures/indicator_golden.json，从而证明双端公式一致。

运行：python tests/test_indicator_consistency.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.indicators import ma_series, _ema_series, boll_series, macd_series

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "fixtures", "indicator_golden.json"), encoding="utf-8") as f:
    G = json.load(f)

CLOSES = G["closes"]
P = G["params"]
EXP = G["expected"]
TOL = 1e-4

passed = failed = 0


def ok(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS " + name)
    else:
        failed += 1
        print("  FAIL " + name + ("  " + extra if extra else ""))


def seq_close(actual, expected, name):
    ok(name + " 长度一致", len(actual) == len(expected),
       "got %d want %d" % (len(actual), len(expected)))
    diffs = []
    for i, (a, e) in enumerate(zip(actual, expected)):
        if (a is None) != (e is None):
            diffs.append("i=%d 空值不一致 %s/%s" % (i, a, e))
        elif a is not None and abs(a - e) > TOL:
            diffs.append("i=%d %.6f!=%.6f" % (i, a, e))
    ok(name + " 全部数值在容差内", not diffs, "; ".join(diffs[:3]))


print("=== 指标一致性回归 · Python (core.indicators) ===\n")
seq_close(ma_series(CLOSES, P["ma"]), EXP["ma5"], "MA(5)")
seq_close(_ema_series(CLOSES, P["ema"]), EXP["ema5"], "EMA(5)")
up, mid, dn = boll_series(CLOSES, P["boll_n"], P["boll_k"])
seq_close(up, EXP["boll_up"], "BOLL 上轨")
seq_close(mid, EXP["boll_mid"], "BOLL 中轨")
seq_close(dn, EXP["boll_dn"], "BOLL 下轨")
dif, dea, hist = macd_series(CLOSES, P["macd_fast"], P["macd_slow"], P["macd_signal"])
seq_close(dif, EXP["macd_dif"], "MACD DIF")
seq_close(dea, EXP["macd_dea"], "MACD DEA")
seq_close(hist, EXP["macd_hist"], "MACD HIST")

print("\n=== 结果: %d 通过 / %d 失败 ===\n" % (passed, failed))
sys.exit(1 if failed else 0)
