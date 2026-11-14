# -*- coding: utf-8 -*-
"""图表指标参数：MA / EMA 均线的天数与启用状态、BOLL / MACD 参数。

设计要点
--------
1. 参数与 UI 完全解耦，纯 dict + 纯函数，便于离线回归与移动端复用；
2. 支持「作用域」：``*`` 表示对所有 K 线周期生效，``"1h"`` 等周期键
   表示只覆盖该周期，未设置的字段回落到 ``*``。这样「周期」既是
   均线参数的作用范围，也能做到日线用 MA(5,10,20)、1 小时用 MA(20,60)；
3. normalize() 对任何脏配置（字符串、None、越界、超长列表）都返回
   一份结构完整、可直接用于计算的参数，绝不把异常抛到绘图线程。

配置结构（存在 config.json 的 ``indicator_params`` 键）::

    {
      "*":  {"ma": [{"period": 5, "enabled": true}, ...],
             "ema": [...], "boll": {"period": 20, "k": 2.0},
             "macd": {"fast": 12, "slow": 26, "signal": 9}},
      "1h": {"ma": [...]}          # 只覆盖 ma，其它沿用 "*"
    }
"""
from __future__ import annotations

SCOPE_ALL = "*"
MAX_LINES = 4                  # MA / EMA 各最多 4 条
MIN_PERIOD, MAX_PERIOD = 2, 500
MIN_BOLL, MAX_BOLL = 2, 200
MIN_K, MAX_K = 0.5, 5.0

DEFAULT_MA = [
    {"period": 5, "enabled": True},
    {"period": 10, "enabled": True},
    {"period": 20, "enabled": True},
    {"period": 30, "enabled": True},
]
DEFAULT_EMA = [
    {"period": 12, "enabled": True},
    {"period": 26, "enabled": True},
    {"period": 50, "enabled": True},
    {"period": 99, "enabled": False},
]
DEFAULT_BOLL = {"period": 20, "k": 2.0}
DEFAULT_MACD = {"fast": 12, "slow": 26, "signal": 9}


def default_params() -> dict:
    """返回一份全新的内置默认参数（调用方修改不会污染常量）。"""
    return {
        "ma": [dict(x) for x in DEFAULT_MA],
        "ema": [dict(x) for x in DEFAULT_EMA],
        "boll": dict(DEFAULT_BOLL),
        "macd": dict(DEFAULT_MACD),
    }


def _int(value, lo: int, hi: int, fallback: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError, OverflowError):
        return fallback
    if isinstance(value, float) and value != n:
        return fallback
    return min(hi, max(lo, n))


def _float(value, lo: float, hi: float, fallback: float) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        return fallback
    if n != n or n in (float("inf"), float("-inf")):
        return fallback
    return min(hi, max(lo, n))


def _lines(raw, defaults) -> list:
    """清洗一组均线：不足补默认、超出截断、天数越界钳制。"""
    src = raw if isinstance(raw, list) else []
    out = []
    for i in range(MAX_LINES):
        item = src[i] if i < len(src) else None
        if not isinstance(item, dict):
            item = defaults[i] if i < len(defaults) else {"period": 20,
                                                          "enabled": False}
        period = _int(item.get("period"), MIN_PERIOD, MAX_PERIOD,
                      defaults[i]["period"] if i < len(defaults) else 20)
        out.append({"period": period, "enabled": bool(item.get("enabled"))})
    return out


def normalize(raw) -> dict:
    """把任意输入清洗为完整参数字典。"""
    src = raw if isinstance(raw, dict) else {}
    base = default_params()
    boll = src.get("boll") if isinstance(src.get("boll"), dict) else {}
    macd = src.get("macd") if isinstance(src.get("macd"), dict) else {}
    fast = _int(macd.get("fast"), 2, 100, DEFAULT_MACD["fast"])
    slow = _int(macd.get("slow"), 3, 200, DEFAULT_MACD["slow"])
    if slow <= fast:
        slow = min(200, fast + 1)
    return {
        "ma": _lines(src.get("ma"), DEFAULT_MA),
        "ema": _lines(src.get("ema"), DEFAULT_EMA),
        "boll": {
            "period": _int(boll.get("period"), MIN_BOLL, MAX_BOLL,
                           DEFAULT_BOLL["period"]),
            "k": round(_float(boll.get("k"), MIN_K, MAX_K,
                              DEFAULT_BOLL["k"]), 2),
        },
        "macd": {
            "fast": fast,
            "slow": slow,
            "signal": _int(macd.get("signal"), 2, 100,
                           DEFAULT_MACD["signal"]),
        },
    }


def enabled_periods(params: dict, kind: str) -> list:
    """返回某类均线已启用且不重复的天数列表（保持用户设定的顺序）。"""
    raw = params.get(kind) if isinstance(params, dict) else None
    out = []
    for line in normalize({kind: raw})[kind]:
        p = line["period"]
        if line["enabled"] and p not in out:
            out.append(p)
    return out


def params_for(config, interval: str = "") -> dict:
    """按当前 K 线周期取出最终生效参数。

    ``config`` 可以是 ``core.config.Config``，也可以是普通 dict。
    周期专属配置里没写的字段，一律回落全局 ``*``，不会把 BOLL / MACD
    误重置成默认值。
    """
    if config is None:
        return normalize(None)
    try:
        store = config.get("indicator_params") or {}
    except (AttributeError, TypeError):
        store = {}
    if not isinstance(store, dict):
        store = {}
    scope = normalize(store.get(SCOPE_ALL))
    key = str(interval or "").strip()
    override = store.get(key) if key and key != SCOPE_ALL else None
    if isinstance(override, dict):
        merged = dict(scope)
        for field in ("ma", "ema", "boll", "macd"):
            if field in override:
                merged[field] = override[field]
        return normalize(merged)
    return scope


def write_params(config, scope: str, params: dict) -> dict:
    """把一份参数写入指定作用域并落盘，返回规范化后的参数。

    写入全局作用域时只改 ``*``；写周期作用域时只覆盖该周期里用户
    真正设置过的四组字段（内容完整，读取时按字段回落）。
    """
    if config is None:
        return normalize(params)
    clean = normalize(params)
    try:
        store = config.get("indicator_params") or {}
    except AttributeError:
        store = {}
    if not isinstance(store, dict):
        store = {}
    else:
        store = dict(store)
    key = SCOPE_ALL if not scope or scope == SCOPE_ALL else str(scope)
    if key == SCOPE_ALL:
        store[key] = clean
    else:
        # 周期作用域只保存「与全局不同的字段」：用户在 1h 里只改了 MA
        # 天数，之后调整全局 BOLL / MACD 时 1h 应当跟着变，而不是被
        # 保存时顺手写死的旧值挡住。
        base = normalize(store.get(SCOPE_ALL))
        partial = {f: clean[f] for f in ("ma", "ema", "boll", "macd")
                   if clean[f] != base[f]}
        if partial:
            store[key] = partial
        else:
            store.pop(key, None)
    try:
        config.set("indicator_params", store)
        config.save()
    except AttributeError:
        if isinstance(config, dict):
            config["indicator_params"] = store
    return clean


def reset_scope(config, scope: str) -> dict:
    """移除某个周期的覆盖参数（全局作用域恢复内置默认）。"""
    if config is None:
        return normalize(None)
    key = SCOPE_ALL if not scope or scope == SCOPE_ALL else str(scope)
    try:
        store = config.get("indicator_params") or {}
    except AttributeError:
        store = {}
    store = dict(store) if isinstance(store, dict) else {}
    if key == SCOPE_ALL:
        store[SCOPE_ALL] = default_params()
    else:
        store.pop(key, None)
    try:
        config.set("indicator_params", store)
        config.save()
    except AttributeError:
        if isinstance(config, dict):
            config["indicator_params"] = store
    return params_for(config, "")
