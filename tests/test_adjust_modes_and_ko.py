# -*- coding: utf-8 -*-
"""KO 2012 拆分异常 + 历史完整性审计 + 三种复权口径 固定回归测试。

背景：用户报告 KO 月线 2012-08 从 80 多美元腰斩到 30 多美元。
权威核实（Coca-Cola 投资者关系 Stock Splits 页 / SEC 8-K）：
2012-07-27 登记、2012-08-10 派发、2012-08-13 除权生效的 2:1 拆股，
数据源新浪返回的是 Raw 名义价，腰斩是真实除权；根因是登记库缺失 KO 事件，
导致复权引擎 0 命中、原始价被直接当成复权价展示。

本测试离线运行，使用代表真实新浪形态的合成 OHLCV，不依赖网络。
"""
import datetime as dt
import math
import os
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_ko_")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, ".")

from data.klines import Candle
from data import corporate_actions as ca
from data import price_adjustment as pa
from data import historical_integrity as hi
from core import adjust_mode as am

PASS = 0
FAIL = 0


def ok(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS", name)
    else:
        FAIL += 1
        print("  FAIL", name, extra)


def mk(date, close, volume, spread=0.01):
    ts = dt.datetime.strptime(date, "%Y-%m-%d").replace(
        tzinfo=dt.timezone.utc).timestamp()
    return Candle(ts=ts, time_label=date, open=close * (1 - spread),
                  high=close * (1 + spread), low=close * (1 - spread),
                  close=close, volume=volume)


print("=" * 62)
print("KO 2012 / 复权口径 / 历史完整性审计 回归")
print("=" * 62)

# ---------- 1. 登记库已核实 KO 拆股 ----------
print("\n[1] KO 登记库完整性")
reg = ca.get_registry()
ko = reg.actions_for("US:KO")
ok("KO 有 5 条已核实拆股", len(ko) == 5, f"实际 {len(ko)}")
ok("2012-08-13 2:1 已登记",
   any(a.ex_date == "2012-08-13" and a.ratio == 2.0
       and a.confidence == "verified" for a in ko))
ok("1986-07-01 3:1 已登记",
   any(a.ex_date == "1986-07-01" and a.ratio == 3.0 for a in ko))
ok("WMT 2024 3:1 已登记",
   any(a.ex_date == "2024-02-26" and a.ratio == 3.0
       for a in reg.actions_for("US:WMT")))
ok("META 从不被误登记拆股", len(reg.actions_for("US:META")) == 0)

# ---------- 2. KO 2012 断层：审计器识别 ----------
print("\n[2] 审计器：未复权 KO 应识别为公司行为而非真实暴跌")
raw = [mk("2012-08-09", 79.24, 4552287),
       mk("2012-08-10", 78.79, 10037931),
       mk("2012-08-13", 39.30, 8775008),   # 真实 2:1 除权
       mk("2012-08-14", 39.38, 10548274)]
rep = hi.audit(raw, "US:KO", reg, jump_threshold=0.30)
gaps = [i for i in rep["issues"] if i["date"] == "2012-08-13"]
ok("2012-08-13 有审计结论", len(gaps) == 1)
if gaps:
    ok("判定为正常公司行为（非真实暴跌）",
       gaps[0]["verdict"] == hi.NORMAL_CORP_ACTION, gaps[0]["verdict"])
    ok("审计比例接近 0.5", abs(gaps[0]["ratio"] - 0.5) < 0.02)

# 未登记的模拟标的：应判为确认异常并给出修复建议
rep2 = hi.audit(raw, "US:UNKNOWN", ca.ActionRegistry(
    path=os.path.join(os.path.dirname(ca.__file__), "corporate_actions.json"),
    overlay=os.path.join(os.environ["APPDATA"], "none.json")),
    jump_threshold=0.30)
g2 = [i for i in rep2["issues"] if i["date"] == "2012-08-13"]
ok("未登记时判为确认异常", bool(g2) and g2[0]["verdict"] == hi.CONFIRMED_ANOMALY)
ok("给出可执行修复建议", bool(g2) and "corporate_actions.json" in (g2[0].get("fix") or ""))

# ---------- 3. KO 长期序列：全部拆股门控命中 + 前复权连续 ----------
print("\n[3] KO 多拆股门控与前复权连续性")
# 用合成的长序列验证 5 个拆股点均被识别
syn = []
price = 130.0
events = [("1986-07-01", 3.0), ("1990-05-14", 2.0),
          ("1992-05-12", 2.0), ("1996-05-13", 2.0), ("2012-08-13", 2.0)]
all_dates = sorted(set([d for d, _ in events] +
                       [dt.date(1980 + y, 1, 2).isoformat() for y in range(0, 40)]))
# 构造：每个事件日前一天价格 P，事件日价格 P/ratio，之后缓慢漂移
for i in range(len(all_dates) - 1):
    d = all_dates[i]
    nxt = all_dates[i + 1]
    ratio = dict(events).get(nxt, 1.0)
    syn.append(mk(d, price, 10_000_000))
    price = price / ratio
syn.append(mk(all_dates[-1], price, 10_000_000))
eff = pa.detect_unadjusted_events(syn, ko)
ok("5 个拆股事件全部命中门控", len(eff) == 5, f"命中 {len(eff)}")
adj = pa.apply_adjustment(syn, eff, basis="raw", mode="forward")
amap = {c.time_label: c.close for c in adj}
ok("前复权后价格连续（无腰斩）",
   all(abs(amap[events[i][0]] / amap[all_dates[all_dates.index(events[i][0]) - 1]] - 1) < 0.02
       for i in range(len(events))))

# ---------- 4. 三种复权口径 ----------
print("\n[4] 三种复权口径")
ok("normalize 三口径", am.normalize("raw") == am.RAW
   and am.normalize("split_adjusted") == am.SPLIT_ADJUSTED
   and am.normalize("total_return") == am.TOTAL_RETURN)
ok("未知口径回落 raw", am.normalize("unknown_mode") == am.RAW)
ok("缓存键含口径隔离", am.cache_symbol("US:KO", "raw") != am.cache_symbol("US:KO", "split_adjusted")
   and am.cache_symbol("US:KO", "split_adjusted") != am.cache_symbol("US:KO", "total_return"))
ok("缓存键含数据版本", "v1" in am.cache_symbol("US:KO", "raw"))
ok("total_return 含分红", am.include_dividends("total_return")
   and not am.include_dividends("split_adjusted"))

# 分红事件在两口径下的差异
prev_close = 50.0
div = ca.CorporateAction(symbol="US:TEST", ex_date="2020-01-02",
                         kind=ca.ActionType.DIVIDEND, ratio=1.0,
                         prev_close=prev_close, cash_per_share=1.0,
                         confidence="verified")
bars = [mk("2020-01-01", 50.0, 1000), mk("2020-01-02", 49.0, 1000),
        mk("2020-01-03", 49.5, 1000)]
out_raw = pa.apply_adjustment(bars, [div], basis="raw", mode="raw")
out_split = pa.apply_adjustment(bars, [div], basis="raw", mode="split_adjusted")
out_total = pa.apply_adjustment(bars, [div], basis="raw", mode="total_return")
ok("raw 不改价", abs(out_raw[0].close - 50.0) < 1e-9)
ok("split_adjusted 不含分红调整",
   abs(out_split[0].close - 50.0) < 1e-9)
ok("total_return 纳入分红（后复权价更高）",
   out_total[-1].close > out_split[-1].close,
   f"total {out_total[-1].close} vs split {out_split[-1].close}")

# ---------- 5. 后复权分红因子修复 ----------
print("\n[5] 后复权价格因子（旧 bug：误用 volume_factor 忽略分红）")
pf_split = ca.CorporateAction(symbol="US:T", ex_date="2020-01-02",
                              kind=ca.ActionType.SPLIT, ratio=4.0,
                              confidence="verified")
p1, v1 = pa.backward_factors_for_date("2020-01-03", [pf_split])
ok("拆股后复权价格 ×4", abs(p1 - 4.0) < 1e-9, f"pf={p1}")
ok("拆股后复权成交量 ÷4", abs(v1 - 0.25) < 1e-9, f"vf={v1}")
p2, v2 = pa.backward_factors_for_date("2020-01-03", [div])
ok("分红后复权价格因子 >1（旧 bug 会得 1.0）", p2 > 1.0, f"pf={p2}")
ok("分红后复权不改成交量", abs(v2 - 1.0) < 1e-9, f"vf={v2}")

print("\n" + "=" * 62)
print(f"结果: {PASS} 通过 / {FAIL} 失败")
print("=" * 62)
sys.exit(1 if FAIL else 0)
