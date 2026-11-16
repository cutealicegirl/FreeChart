# -*- coding: utf-8 -*-
"""公司行为 / 复权专项回归测试。

覆盖用户第五章要求：
- 真实拆股 / 反向拆股 / 代币迁移标的（AAPL/TSLA/NVDA/AMZN/GOOGL + 迁移映射）
- 调整前后价格比例、OHLC 一致性、成交量比例
- 技术指标在复权后重新计算（以 close 序列为输入验证）
- 日/周/月 K 聚合一致（用复权后的日线聚合）
- 幂等（不重复复权）、无事件标的不受影响、unverified 只标记不猜测
- 数据源已自带复权时不二次复权（经验门控）
- 缓存：schema  bump 与事件指纹变化导致失效
"""
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data import corporate_actions as ca
from data import price_adjustment as pa
from data.klines import Candle

PASS = 0
FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS", name)
    else:
        FAIL += 1
        print("  FAIL", name, detail)


def mk(d, close, vol=100.0, spread=0.0):
    ts = datetime.datetime.strptime(d, "%Y-%m-%d").timestamp()
    return Candle(ts=ts, time_label=d,
                  open=close * (1 - spread), high=close * (1 + spread),
                  low=close * (1 - spread), close=close, volume=vol)


def act(symbol, date, ratio, kind="split", **kw):
    return ca.CorporateAction(symbol=symbol, ex_date=date,
                              kind=ca.ActionType(kind), ratio=ratio, **kw)


print("=" * 60)
print("公司行为 / 复权专项回归测试")
print("=" * 60)

# ---------- 1. 登记库真实性 ----------
print("\n[1] 已核实事件登记库")
reg = ca.ActionRegistry()
for sym, date, ratio in [
    ("US:AAPL", "2020-08-31", 4), ("US:AAPL", "2014-06-09", 7),
    ("US:TSLA", "2022-08-25", 3), ("US:TSLA", "2020-08-31", 5),
    ("US:NVDA", "2024-06-10", 10), ("US:AMZN", "2022-06-06", 20),
    ("US:GOOGL", "2022-07-18", 20),
]:
    found = [a for a in reg.actions_for(sym)
             if a.ex_date == date and abs(a.ratio - ratio) < 1e-9]
    ok(f"{sym} {date} 1拆{ratio}", len(found) == 1 and found[0].usable)
migs = reg.migrations_for("RENDER")
ok("代币迁移映射 RNDR→RENDER", len(migs) == 1 and migs[0].source_rebased)

# ---------- 2. 拆股：价格比例 + 成交量比例 + OHLC 一致 ----------
print("\n[2] AAPL 2020 1拆4：价格 / 成交量 / OHLC")
pre_close, pre_vol = 500.0, 200.0
candles = [mk("2020-08-26", 498, pre_vol, 0.01),
           mk("2020-08-27", 500, pre_vol, 0.01),
           mk("2020-08-28", 502, pre_vol, 0.01),
           mk("2020-08-31", 125, pre_vol * 4, 0.01),   # 除权日价格已 1/4
           mk("2020-09-01", 126, pre_vol * 4, 0.01)]
aapl = [a for a in reg.actions_for("US:AAPL") if a.ex_date == "2020-08-31"]
eff = pa.detect_unadjusted_events(candles, aapl)
ok("经验门控识别未复权事件", len(eff) == 1)
adj = pa.apply_adjustment(candles, eff, basis="raw", mode="forward")
c = candles[1]; a = adj[1]
ok("除权前 close 缩为 1/4", abs(a.close - pre_close / 4) < 1e-6, f"{a.close}")
ok("除权前 volume 放大 4 倍", abs(a.volume - pre_vol * 4) < 1e-6, f"{a.volume}")
ok("OHLC 同比例（开）", abs(a.open - c.open / 4) < 1e-6)
ok("OHLC 同比例（高）", abs(a.high - c.high / 4) < 1e-6)
ok("OHLC 同比例（低）", abs(a.low - c.low / 4) < 1e-6)
ok("除权日价格不变", abs(adj[3].close - 125) < 1e-6, f"{adj[3].close}")

# ---------- 3. 反向拆股 ----------
print("\n[3] 反向拆股 10合1（ratio=0.1）")
rev = [act("US:TEST", "2023-05-10", 0.1, "reverse_split")]
rc = [mk("2023-05-09", 5.0, 1000), mk("2023-05-10", 50.0, 100),
      mk("2023-05-11", 51.0, 110)]
reff = pa.detect_unadjusted_events(rc, rev)
ok("识别反向拆股未复权", len(reff) == 1)
radj = pa.apply_adjustment(rc, reff, basis="raw", mode="forward")
# 10合1：10 旧股=1 新股，前复权把旧价 5 折算到新股口径 = 5/0.1 = 50，
# 与除权日价格 50 衔接；成交量 1000×0.1=100，成交额守恒 1000×5 = 100×50。
ok("反向拆股前价 5/0.1 -> 50", abs(radj[0].close - 50.0) < 1e-6, f"{radj[0].close}")
ok("反向拆股前量 ×0.1 -> 100", abs(radj[0].volume - 100) < 1e-6, f"{radj[0].volume}")
ok("反向拆股成交额守恒",
   abs(radj[0].close * radj[0].volume - rc[1].close * rc[1].volume) < 1e-6)

# ---------- 4. 多次拆股累积（AAPL 全历史） ----------
print("\n[4] 多次拆股累积因子")
# 2014 前一根 / 2014 拆股 / ... / 2020 拆股
multi = [mk("2014-06-06", 645, 100), mk("2014-06-09", 92, 700),
         mk("2020-08-28", 500, 400), mk("2020-08-31", 125, 1600)]
events = [a for a in reg.actions_for("US:AAPL")
          if a.ex_date in ("2014-06-09", "2020-08-31")]
meff = pa.detect_unadjusted_events(multi, events)
ok("识别两次拆股", len(meff) == 2, f"{[x.ex_date for x in meff]}")
madj = pa.apply_adjustment(multi, meff, basis="raw", mode="forward")
# 2014-06-06 之前应同时被 1/7 和 1/4 => /28
ok("两次拆股累积 /28", abs(madj[0].close - 645 / 28) < 1e-4, f"{madj[0].close}")
ok("两次拆股累积量 ×28", abs(madj[0].volume - 2800) < 1e-4, f"{madj[0].volume}")
# 2014之后、2020之前：只被 1/4
ok("中间段仅 /4", abs(madj[2].close - 500 / 4) < 1e-6, f"{madj[2].close}")

# ---------- 5. 幂等 / 无事件 / 不猜测 ----------
print("\n[5] 幂等与保守原则")
again = pa.apply_adjustment(adj, eff, basis="forward", mode="forward")
ok("已复权数据不再二次复权", all(abs(x.close - y.close) < 1e-9
                            for x, y in zip(again, adj)))
none = pa.apply_adjustment(candles, [], basis="raw", mode="forward")
ok("无事件标的数据原样", all(abs(x.close - y.close) < 1e-9
                        for x, y in zip(none, candles)))
unknown = [ca.CorporateAction(symbol="US:X", ex_date="2021-01-01",
                              kind=ca.ActionType.UNKNOWN, ratio=1.0,
                              confidence="unverified")]
uan = pa.detect_anomalies(candles, unknown)
ok("unverified 事件只标记异常", any(x["kind"] == "unconfirmed_event" for x in uan))
uadj = pa.apply_adjustment(candles, unknown, basis="raw", mode="forward")
ok("unverified 不改价格", all(abs(x.close - y.close) < 1e-9
                         for x, y in zip(uadj, candles)))

# ---------- 6. 数据源已复权不二次复权 ----------
print("\n[6] 数据源已复权时经验门控跳过")
already = [mk("2020-08-28", 125, 400), mk("2020-08-31", 125, 100),
           mk("2020-09-01", 126, 110)]
aeff = pa.detect_unadjusted_events(already, aapl)
ok("已复权数据门控返回空", len(aeff) == 0)

# ---------- 7. 指标基于复权后 close 重算 ----------
print("\n[7] 技术指标随复权重算")
from core.indicators import ma_series, macd_series
raw_close = [c.close for c in candles]
adj_close = [c.close for c in adj]
ma_raw = ma_series(raw_close, 3)
ma_adj = ma_series(adj_close, 3)
ok("MA 随复权变化", any(x is not None and y is not None and abs(x - y) > 1e-6
                    for x, y in zip(ma_raw, ma_adj)))
# MACD(12,26,9) 需要至少 26 根预热：构造 30 根平缓序列 + 除权跳空
long_candles = ([mk(f"2021-01-{d+1:02d}", 100.0, 100) for d in range(28)] +
                [mk("2021-02-01", 50.0, 400), mk("2021-02-02", 51.0, 410)])
long_eff = pa.detect_unadjusted_events(
    long_candles, [act("US:LONG", "2021-02-01", 2.0)])
long_adj = pa.apply_adjustment(long_candles, long_eff, basis="raw", mode="forward")
dif_raw, _, _ = macd_series([c.close for c in long_candles])
dif_adj, _, _ = macd_series([c.close for c in long_adj])
ok("MACD 长序列识别拆股", len(long_eff) == 1)
ok("MACD DIF 随复权变化", any(x is not None and y is not None and abs(x - y) > 1e-6
                          for x, y in zip(dif_raw, dif_adj)))

# ---------- 8. 日/周/月聚合一致 ----------
print("\n[8] 多周期聚合口径一致")
daily = [mk("2024-01-01", 10, 100), mk("2024-01-02", 12, 110),
         mk("2024-01-03", 11, 105), mk("2024-01-08", 13, 120),
         mk("2024-01-09", 14, 130)]
weekly = pa.aggregate(daily, "week", Candle)
monthly = pa.aggregate(daily, "month", Candle)
# 2024-01-01 是周一：01-01/02/03 属第 1 周，01-08/09 属第 2 周
ok("周K open=组内首", abs(weekly[0].open - 10) < 1e-9)
ok("周K high=组内最高", abs(weekly[0].high - 12) < 1e-9, f"{weekly[0].high}")
ok("周K close=组内末(首周11)", abs(weekly[0].close - 11) < 1e-9, f"{weekly[0].close}")
ok("周K volume=求和(首周315)", abs(weekly[0].volume - 315) < 1e-9, f"{weekly[0].volume}")
ok("第二周 close=14", len(weekly) == 2 and abs(weekly[1].close - 14) < 1e-9)
ok("月K 合并所有日", abs(monthly[0].volume - 565) < 1e-9)

# ---------- 9. 缓存失效 ----------
print("\n[9] 缓存 schema / 指纹失效")
import data.kline_cache as kc
tmp = tempfile.mkdtemp()
old_appdata = os.environ.get("APPDATA")
os.environ["APPDATA"] = tmp
kc._local.__dict__.clear()
kc.save("US:AAPL", "day", candles)
ok("新缓存 fresh", kc.is_fresh("US:AAPL", "day"))
conn = kc._conn(); conn.execute("UPDATE meta SET schema='v1-old'"); conn.commit()
ok("旧 schema 失效", not kc.is_fresh("US:AAPL", "day"))
conn.execute("UPDATE meta SET schema=?, adj_tag='stale'", (kc._CACHE_SCHEMA,)); conn.commit()
ok("事件指纹变化失效", not kc.is_fresh("US:AAPL", "day"))
os.environ["APPDATA"] = old_appdata or ""
kc._local.__dict__.clear()

# ---------- 10. 后复权 ----------
print("\n[10] 后复权（hfq）")
b = pa.apply_adjustment(candles, eff, basis="raw", mode="backward")
# 后复权：除权日之后 ×4
ok("后复权除权日后价 ×4", abs(b[3].close - 500) < 1e-6, f"{b[3].close}")
ok("后复权除权日前价不变", abs(b[1].close - 500) < 1e-6, f"{b[1].close}")

# ---------- 11. 未登记拆股品种的自动检测 ----------
print("\n[11] 未登记拆股：价格 / 成交量双确认后复权")
from data import klines as _kl
auto_raw = [mk("2024-03-01", 100.0, 100), mk("2024-03-04", 101.0, 105),
            mk("2024-03-05", 50.0, 220, 0.01), mk("2024-03-06", 51.0, 215, 0.01)]
auto_events = pa.detect_split_actions_from_prices(auto_raw, "US:UNLISTED")
ok("自动识别 1 拆 2", len(auto_events) == 1
   and abs(auto_events[0].ratio - 2.0) < 1e-9
   and auto_events[0].ex_date == "2024-03-05")
auto_out = _kl._postprocess("US:UNLISTED", auto_raw, "raw")
ok("未登记品种历史价已按拆股后处理",
   abs(auto_out[1].close - 50.5) < 1e-6, f"{auto_out[1].close}")
ok("未登记品种历史成交量同步放大",
   abs(auto_out[1].volume - 210.0) < 1e-6, f"{auto_out[1].volume}")
ok("除权日及之后价格不再重复调整",
   abs(auto_out[2].close - 50.0) < 1e-6 and abs(auto_out[3].close - 51.0) < 1e-6)
already_qfq = [mk("2024-03-01", 50.0, 200), mk("2024-03-04", 50.5, 210),
               mk("2024-03-05", 50.0, 220), mk("2024-03-06", 51.0, 215)]
ok("已前复权序列不产生自动事件",
   not pa.detect_split_actions_from_prices(already_qfq, "US:ALREADY"))
crash = [mk("2024-03-01", 100.0, 100), mk("2024-03-04", 101.0, 105),
         mk("2024-03-05", 50.0, 105), mk("2024-03-06", 51.0, 110)]
ok("价格腰斩但量未放大不误判拆股",
   not pa.detect_split_actions_from_prices(crash, "US:CRASH"))

print("\n" + "=" * 60)
print(f"结果: {PASS} 通过 / {FAIL} 失败")
print("=" * 60)
sys.exit(0 if FAIL == 0 else 1)
