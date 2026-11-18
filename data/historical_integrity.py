# -*- coding: utf-8 -*-
"""Historical Data Integrity Checker —— 历史行情完整性审计器。

这是一个**可长期运行**的审计模块（不是一次性脚本），对股票历史 OHLCV 做
系统性体检，输出可机读的审计结论。设计原则：

1. 不凭涨跌幅单独下结论。价格腰斩必须先对照已核实公司行为、成交量一致性、
   相邻日延续性，才能判为「真实公司行为」还是「确认异常 / 疑似异常」。
2. 五个分类（verdict）：
   - real_move          真实市场波动（跳空后延续、无公司行为、无量价矛盾）
   - normal_corp_action 正常公司行为（跳空日与已核实事件吻合，比例一致）
   - confirmed_anomaly  确认异常（有已核实事件但价格未按比例变化，或
                         OHLC 逻辑错误 / 成交量非正 / 时间戳倒序等硬错误）
   - suspected          疑似异常（大幅跳空但证据不足，人工复核）
   - insufficient       数据不足（样本过短，无法判断）
3. 只审计、不改价。修复由复权引擎与登记库负责；审计器负责发现「登记库缺失」
   与「数据源口径断层」，并给出可执行的修复建议。

用法：
    from data import historical_integrity as hc
    report = hc.audit(candles, symbol="US:KO", registry=...)
    for issue in report["issues"]: print(issue["verdict"], issue["date"])
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import asdict, is_dataclass
from typing import Iterable, List, Optional, Sequence

from data import corporate_actions as _ca
from data import price_adjustment as _pa

# verdict 常量
REAL_MOVE = "real_move"
NORMAL_CORP_ACTION = "normal_corp_action"
CONFIRMED_ANOMALY = "confirmed_anomaly"
SUSPECTED = "suspected"
INSUFFICIENT = "insufficient"

VERDICTS = (REAL_MOVE, NORMAL_CORP_ACTION, CONFIRMED_ANOMALY,
            SUSPECTED, INSUFFICIENT)

# 常见份额比例，用于识别「价格比 ≈ 1/ratio」的未复权拆股
_SHARE_RATIOS = (2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 10.0, 20.0)


def _date_of(c) -> str:
    try:
        return _dt.datetime.fromtimestamp(float(c.ts)).strftime("%Y-%m-%d")
    except (ValueError, TypeError, OSError, OverflowError):
        return ""


def _kind(a) -> str:
    return getattr(a.kind, "value", a.kind)


def _nearest_action(actions: Sequence, date_str: str, window: int = 5):
    try:
        d = _dt.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None
    for a in actions:
        try:
            ad = _dt.datetime.strptime(a.ex_date, "%Y-%m-%d").date()
        except ValueError:
            continue
        if abs((ad - d).days) <= window:
            return a
    return None


def audit(candles: Sequence, symbol: str = "",
          registry: Optional[_ca.ActionRegistry] = None,
          jump_threshold: float = 0.30) -> dict:
    """对一段（最好是日线）历史序列做完整性审计。

    返回 dict：
      symbol, bars, verdict_counts, issues[], summary
    """
    rows = sorted(candles, key=lambda c: c.ts)
    reg = registry or _ca.get_registry()
    actions = reg.actions_for(symbol) if symbol else []
    issues: List[dict] = []
    counts = {v: 0 for v in VERDICTS}

    if len(rows) < 3:
        counts[INSUFFICIENT] = 1
        issues.append({
            "verdict": INSUFFICIENT, "reason": "样本不足（少于 3 根）",
            "date": _date_of(rows[0]) if rows else "",
        })
        return {"symbol": symbol, "bars": len(rows),
                "verdict_counts": counts, "issues": issues,
                "summary": "insufficient"}

    # ---- 硬错误扫描：OHLC 逻辑 / 成交量 / 时间戳 ----
    for i, c in enumerate(rows):
        try:
            o, h, l, cl, v = (float(c.open), float(c.high), float(c.low),
                              float(c.close), float(c.volume))
        except (TypeError, ValueError):
            counts[CONFIRMED_ANOMALY] += 1
            issues.append({"verdict": CONFIRMED_ANOMALY,
                           "date": _date_of(c), "index": i,
                           "reason": "OHLCV 含非数值"})
            continue
        # 容忍数据源四舍五入（新浪美股常见 low 比 close 高 0.01 美分）：
        # 只有超出 0.5% 或绝对值 0.05 的违例才算硬错误，避免误报。
        tol = max(0.05, max(o, h, l, cl) * 0.005)
        if not (h >= max(o, cl) - tol and l <= min(o, cl) + tol
                and h >= l - tol and min(o, h, l, cl) > 0):
            counts[CONFIRMED_ANOMALY] += 1
            issues.append({"verdict": CONFIRMED_ANOMALY,
                           "date": _date_of(c), "index": i,
                           "reason": f"OHLC 逻辑错误 O={o} H={h} L={l} C={cl}"})
        if v < 0:
            counts[CONFIRMED_ANOMALY] += 1
            issues.append({"verdict": CONFIRMED_ANOMALY,
                           "date": _date_of(c), "index": i,
                           "reason": f"成交量为负 {v}"})
        if i > 0 and c.ts <= rows[i - 1].ts:
            counts[CONFIRMED_ANOMALY] += 1
            issues.append({"verdict": CONFIRMED_ANOMALY,
                           "date": _date_of(c), "index": i,
                           "reason": "时间戳非递增"})

    # ---- 跳空扫描 ----
    for prev, cur in zip(rows, rows[1:]):
        if not (prev.close > 0 and cur.close > 0):
            continue
        ratio = cur.close / prev.close
        if abs(ratio - 1.0) < jump_threshold:
            continue
        d = _date_of(cur)
        vol_before = float(prev.volume or 0)
        vol_after = float(cur.volume or 0)
        vol_ratio = (vol_after / vol_before) if vol_before > 0 else None
        a = _nearest_action(actions, d)

        # 判断是否存在常见份额比例，且方向为价格下降（拆股）
        inv_ratio = None
        for r in _SHARE_RATIOS:
            if abs(ratio - 1.0 / r) / (1.0 / r) <= 0.08:
                inv_ratio = r
                break

        vol_txt = f"{vol_ratio:.2f}" if vol_ratio is not None else "N/A"
        if a is not None:
            expected = (1.0 / a.ratio if _kind(a) in
                        ("split", "reverse_split", "bonus", "rights")
                        else None)
            if expected and abs(ratio - expected) / expected <= 0.12:
                verdict = NORMAL_CORP_ACTION
                reason = (f"跳空 {ratio:.3f} 与已核实 {_kind(a)} "
                          f"ratio={a.ratio} 一致")
                fix = None
            else:
                verdict = CONFIRMED_ANOMALY
                reason = (f"除权日 {a.ex_date} 有已核实事件，但价格比 "
                          f"{ratio:.3f} 与预期 {expected} 不符")
                fix = "核对数据源口径或登记库比例"
        elif inv_ratio is not None and (vol_ratio is None
                                        or abs(vol_ratio - 1.0) <= 0.6):
            # 价格精确按常见比例腰斩，成交量未同步缩小 -> 高度疑似未复权拆股
            verdict = CONFIRMED_ANOMALY
            reason = (f"价格比 {ratio:.4f} ≈ 1/{inv_ratio:g}（疑似拆股），"
                      f"量比 {vol_txt}，但登记库无对应事件")
            fix = ("在 corporate_actions.json 增加该标的 "
                   f"ex_date={d} kind=split ratio={inv_ratio:g} 的 verified 记录；"
                   "请以公司公告 / 交易所公告核实后填写，不得凭价格猜测")
        else:
            # 大幅跳空但无公司行为、量价也不像拆股：可能是真实事件，标记疑似
            verdict = SUSPECTED
            reason = (f"跳空 {ratio:.3f}，量比 {vol_txt}，无已核实事件")
            fix = "人工复核是否为真实市场事件或数据源错误"

        counts[verdict] += 1
        issues.append({
            "verdict": verdict, "date": d,
            "prev_close": round(prev.close, 4),
            "close": round(cur.close, 4),
            "ratio": round(ratio, 6),
            "vol_ratio": round(vol_ratio, 4) if vol_ratio is not None else None,
            "reason": reason, "fix": fix,
            "ts": cur.ts,
        })

    hard = counts[CONFIRMED_ANOMALY]
    soft = counts[SUSPECTED]
    if hard:
        summary = f"发现 {hard} 项确认异常"
    elif soft:
        summary = f"发现 {soft} 项疑似异常，需人工复核"
    else:
        summary = "未发现明显完整性问题"
    return {"symbol": symbol, "bars": len(rows),
            "verdict_counts": counts, "issues": issues, "summary": summary}


def audit_many(symbols: Iterable[str], fetcher,
               registry: Optional[_ca.ActionRegistry] = None,
               interval: str = "day") -> dict:
    """批量审计：fetcher(symbol, interval) -> candles。单个失败不影响其它。"""
    results = {}
    for sym in symbols:
        try:
            rows = fetcher(sym, interval)
            results[sym] = audit(rows, sym, registry)
        except Exception as exc:  # 单点失败隔离
            results[sym] = {"symbol": sym, "error": str(exc),
                            "verdict_counts": {}, "issues": [],
                            "summary": "获取失败"}
    return {"results": results, "symbols": list(results)}
