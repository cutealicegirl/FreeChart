# -*- coding: utf-8 -*-
"""历史价格复权引擎（纯函数，无网络 / 无 Qt 依赖）。

核心语义
--------
- **ratio** = 除权后每 1 份旧份额换到的新份额数（拆股 4、反向拆股 0.1）。
- **前复权（qfq / forward）**：以最新价为基准，把除权日**之前**的历史价
  按 price_factor=1/ratio 放大/缩小，使历史与当前同口径（A股腾讯 qfq 口径）。
- **后复权（hfq / backward）**：以最早价为基准，把除权日**之后**的价格乘
  ratio，保持早期价格不动。
- **成交量**：只有份额数量变化的事件才按 volume_factor=ratio 调整；
  纯现金分红 volume_factor=1。价格与成交量必须使用同一套事件，避免不一致。

幂等
----
复权只应该在"原始未复权数据"上做一次。`apply_adjustment` 要求显式传入
`basis`：
  - basis="raw"          -> 应用复权；
  - basis="forward"/"hfq" -> 原样返回（拒绝二次复权）。
调用方（klines）必须在数据源已返回 qfq 时传 basis="forward"。

不可猜测原则
------------
- 只有 action.usable=True 且 source_rebased=False 的事件参与计算；
- 其余（unknown / reported / unverified / 数据源已重算）只产生 anomaly
  标记，**绝不修改任何一根 K 线**。
- 不插值、不删除 K 线、不单独改某一根价格。

聚合
----
周/月/年 K 必须由复权后的日线再聚合（open=首、high=最大、low=最小、
close=末、volume=求和），本模块提供 `aggregate` 供 klines 复用，确保
多周期口径一致。
"""
from __future__ import annotations

import datetime as _dt
from typing import Iterable, List, Optional, Sequence, Tuple

from data.corporate_actions import CorporateAction

RAW = "raw"
FORWARD = "forward"
BACKWARD = "backward"
QFQ = "qfq"      # 等价 forward（数据源命名）
HFQ = "hfq"      # 等价 backward

_VALID_IN_BASIS = {RAW, FORWARD, BACKWARD, QFQ, HFQ}


def _date_of_ts(ts: float) -> str:
    try:
        return _dt.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d")
    except (ValueError, TypeError, OSError, OverflowError):
        return ""


def _usable(actions: Iterable[CorporateAction]) -> List[CorporateAction]:
    return sorted([a for a in actions if a.usable and not a.source_rebased],
                  key=lambda a: a.ex_date)


def forward_factors_for_date(date_str: str,
                             actions: Sequence[CorporateAction]) -> Tuple[float, float]:
    """返回某根 K 线的 (价格乘数, 成交量乘数)，前复权口径。

    对除权日**之前**（ex_date > bar_date）的每个事件累乘其因子。
    """
    if not date_str:
        return 1.0, 1.0
    pf, vf = 1.0, 1.0
    for a in _usable(actions):
        if a.ex_date > date_str:
            pf *= a.price_factor
            vf *= a.volume_factor
    return pf, vf


def backward_factors_for_date(date_str: str,
                              actions: Sequence[CorporateAction]) -> Tuple[float, float]:
    """后复权：对除权日**及之后**（ex_date <= bar_date）的事件累乘。"""
    if not date_str:
        return 1.0, 1.0
    pf, vf = 1.0, 1.0
    for a in _usable(actions):
        if a.ex_date <= date_str:
            pf *= a.volume_factor   # 后复权价乘 ratio
            vf *= 1.0 / a.volume_factor if a.volume_factor else 1.0
    return pf, vf


def apply_adjustment(candles: list, actions: Sequence[CorporateAction],
                     basis: str = RAW, mode: str = FORWARD,
                     ts_to_date=None) -> list:
    """在一个 Candle 列表上应用复权，返回**新的**列表（不改原对象）。

    - candles: 具有 ts/open/high/low/close/volume 的对象（klines.Candle）。
    - actions: 该标的的公司行为列表（registry.actions_for(symbol)）。
    - basis:   输入数据的当前口径；非 raw 时拒绝复权（幂等保护）。
    - mode:    目标口径 forward(qfq) 或 backward(hfq)。
    - ts_to_date: 可选 (ts)->'YYYY-MM-DD'，测试可注入。

    返回新 Candle 列表（同一类型，用 dataclasses.replace 保留全部字段）。
    """
    from dataclasses import replace, is_dataclass

    if basis not in _VALID_IN_BASIS:
        raise ValueError(f"未知数据口径: {basis}")
    if mode not in (FORWARD, BACKWARD, QFQ, HFQ):
        raise ValueError(f"未知复权目标: {mode}")

    # 幂等：已是复权口径 -> 原样返回，绝不二次复权
    if basis in (FORWARD, BACKWARD, QFQ, HFQ):
        return list(candles)

    usable = _usable(actions)
    if not usable:
        return list(candles)   # 无可安全使用的事件：保持原始

    to_date = ts_to_date or _date_of_ts
    factor_fn = (forward_factors_for_date if mode in (FORWARD, QFQ)
                 else backward_factors_for_date)

    out = []
    for c in candles:
        pf, vf = factor_fn(to_date(c.ts), usable)
        if is_dataclass(c):
            out.append(replace(c,
                               open=c.open * pf, high=c.high * pf,
                               low=c.low * pf, close=c.close * pf,
                               volume=c.volume * vf))
        else:  # 兜底：鸭子类型对象
            c.open *= pf; c.high *= pf; c.low *= pf
            c.close *= pf; c.volume *= vf
            out.append(c)
    return out


def adjust_volume_only(candles: list, actions: Sequence[CorporateAction],
                       ts_to_date=None) -> list:
    """只调整成交量，不动价格。

    用于数据源已经对价格做了前复权（如腾讯 qfq）但成交量仍是原始份额的场景：
    拆股后 1 份旧份额 = ratio 份新份额，因此除权日之前的成交量需乘 ratio
    才能与复权后的价格同口径。纯现金分红不影响成交量。

    仅对"份额变动"事件生效，且同样要求 verified。
    """
    from dataclasses import replace, is_dataclass
    usable = [a for a in _usable(actions) if a.volume_factor != 1.0]
    if not usable:
        return list(candles)
    to_date = ts_to_date or _date_of_ts
    out = []
    for c in candles:
        d = to_date(c.ts)
        vf = 1.0
        for a in usable:
            if a.ex_date > d:
                vf *= a.volume_factor
        if vf == 1.0:
            out.append(c)
            continue
        if is_dataclass(c):
            out.append(replace(c, volume=c.volume * vf))
        else:
            c.volume *= vf
            out.append(c)
    return out


def detect_unadjusted_events(candles: list, actions: Sequence[CorporateAction],
                             price_tol: float = 0.12,
                             ts_to_date=None) -> List[CorporateAction]:
    """经验门控：只返回"数据确实是未复权"的事件，防止二次复权。

    背景：部分数据源（如新浪美股 getDailyK）是否自带拆股复权无法离线确认。
    若盲目套用登记库因子，遇到已复权数据就会二次复权，制造错误跳空。

    做法：对每个份额变动事件，取除权日前后相邻的收盘价，
      - 未复权数据的价格比 ≈ 1/ratio（拆股价格按比例下降）；
      - 已复权数据的价格比 ≈ 1（无跳空）。
    只有当观测比值接近 1/ratio 时才认定"未复权"并纳入复权；
    否则视为数据源已处理，跳过。这样对"数据源口径未知"也能自适应。

    现金分红用 (prev_close-cash)/prev_close 作为预期比，容差更宽（受市场波动影响）。

    返回需要实际复权的事件子集（保持原对象）。
    """
    to_date = ts_to_date or _date_of_ts
    ordered = sorted(candles, key=lambda c: c.ts)
    if len(ordered) < 2:
        return []

    # 日期 -> (前一根收盘, 后一根收盘)
    neighbors: dict = {}
    for prev, cur in zip(ordered, ordered[1:]):
        d = to_date(cur.ts)
        if d and prev.close > 0 and cur.close > 0:
            neighbors[d] = (prev.close, cur.close,
                            getattr(prev, "volume", 0), getattr(cur, "volume", 0))

    effective: List[CorporateAction] = []
    for a in actions:
        if not a.usable or a.source_rebased:
            continue
        obs = neighbors.get(a.ex_date)
        if not obs:
            # 没有落在采样窗口内的相邻 K 线：保守跳过，不猜测
            continue
        close_before, close_after = obs[0], obs[1]
        if a.kind in ("split", "reverse_split", "bonus", "rights",
                      "token_migration", "token_redenom") or \
                getattr(a.kind, "value", a.kind) in (
                    "split", "reverse_split", "bonus", "rights",
                    "token_migration", "token_redenom"):
            expected = 1.0 / a.ratio if a.ratio else 1.0
        elif getattr(a.kind, "value", a.kind) == "dividend" and a.prev_close:
            expected = (a.prev_close - (a.cash_per_share or 0)) / a.prev_close
        else:
            continue
        observed = close_after / close_before
        is_dividend = getattr(a.kind, "value", a.kind) == "dividend"
        # 分红幅度通常很小：必须"明显更接近预期值而非 1.0"才认定未复权，
        # 否则正常的市场波动会被误判为需要复权的分红事件。
        closer_to_expected = (abs(observed - expected) < abs(observed - 1.0))
        if expected > 0 and abs(observed - expected) / expected <= price_tol \
                and (closer_to_expected or not is_dividend):
            effective.append(a)
        elif abs(observed - 1.0) <= price_tol:
            # 观测无跳空 -> 数据源已复权，跳过以避免二次复权
            continue
        else:
            # 跳空既不像未复权也不像已复权（可能是当日大跌/大涨）：
            # 保守跳过，标记交给 detect_anomalies
            continue
    return effective


def detect_anomalies(candles: list, actions: Sequence[CorporateAction],
                     jump_threshold: float = 0.35,
                     ts_to_date=None) -> List[dict]:
    """探测"疑似未复权跳空"，返回异常标记（不修改价格）。

    逻辑：相邻两根收盘价比值偏离 1 超过阈值（默认 ±35%），且附近没有
    已核实事件覆盖 -> 标记为 anomaly，调用方可在 UI 提示「数据可能未复权」。
    有 verified 事件覆盖的跳空属于正常除权，不标记。

    返回 [{"ts", "date", "ratio", "kind": "unverified_gap"|"unconfirmed_event"}]
    """
    to_date = ts_to_date or _date_of_ts
    usable_dates = {a.ex_date for a in _usable(actions)}
    unconfirmed = [a for a in actions if not a.usable]
    result: List[dict] = []
    ordered = sorted(candles, key=lambda c: c.ts)
    for prev, cur in zip(ordered, ordered[1:]):
        try:
            if prev.close <= 0 or cur.close <= 0:
                continue
            ratio = cur.close / prev.close
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if abs(ratio - 1.0) < jump_threshold:
            continue
        d = to_date(cur.ts)
        if d in usable_dates:
            continue   # 已核实除权日，正常跳空
        result.append({"ts": cur.ts, "date": d,
                       "ratio": round(ratio, 6),
                       "kind": "unverified_gap"})
    for a in unconfirmed:
        result.append({"ts": 0.0, "date": a.ex_date,
                       "ratio": a.ratio, "kind": "unconfirmed_event",
                       "source": a.source, "note": a.note})
    return result


def aggregate(candles: list, mode: str, candle_cls) -> list:
    """把日线聚合为 3日/周/月/年 K（统一口径的关键）。

    mode: 3day | week | month | year
    OHLC = 组内首开/最高/最低/末收，volume = 求和。
    """
    from datetime import timedelta
    if not candles:
        return []
    groups: dict = {}
    order: list = []
    for c in candles:
        d = _dt.datetime.fromtimestamp(c.ts).date()
        if mode == "3day":
            start = d - timedelta(days=d.toordinal() % 3)
        elif mode == "week":
            start = d - timedelta(days=d.weekday())
        elif mode == "month":
            start = d.replace(day=1)
        else:
            start = d.replace(month=1, day=1)
        if start not in groups:
            groups[start] = {"open": c.open, "high": c.high, "low": c.low,
                             "close": c.close, "volume": c.volume}
            order.append(start)
        else:
            g = groups[start]
            g["high"] = max(g["high"], c.high)
            g["low"] = min(g["low"], c.low)
            g["close"] = c.close
            g["volume"] += c.volume
    fmt = {"3day": "%m-%d", "week": "%m-%d",
           "month": "%Y-%m", "year": "%Y"}[mode]
    out = []
    for start in order:
        g = groups[start]
        out.append(candle_cls(
            ts=_dt.datetime(start.year, start.month, start.day).timestamp(),
            time_label=start.strftime(fmt),
            open=g["open"], high=g["high"], low=g["low"],
            close=g["close"], volume=g["volume"]))
    return out


def adjustment_fingerprint(actions: Sequence[CorporateAction]) -> str:
    """事件集指纹，缓存据此判断是否需要失效重建。"""
    usable = _usable(actions)
    if not usable:
        return "none"
    import hashlib
    raw = "|".join(f"{a.ex_date}:{a.kind.value}:{a.ratio}:{a.cash_per_share}"
                   for a in usable)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
