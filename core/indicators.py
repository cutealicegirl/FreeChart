# -*- coding: utf-8 -*-
"""K 线指标纯函数：MA / EMA / BOLL / MACD。

设计要点
--------
1. 只依赖标准库 ``math``，不导入 PySide6 或任何 UI 模块，
   因此桌面端、Android H5 与离线测试可共用同一套公式基准；
2. 序列与输入 closes 等长，预热段为 ``None``，便于绘制时按索引对齐；
3. 与 Android ``app.js`` 的实现逐式对应（见 tests/test_indicator_consistency*.py/.js）：

   - EMA：前 n 根用 SMA 初始化，之后 ``e = close*k + e*(1-k)``，``k = 2/(n+1)``；
   - BOLL：中轨 MA(n)，上下轨 ``中轨 ± k*总体标准差``（ddof=0，通达信/币安惯例）；
   - MACD：DIF = EMA(fast) - EMA(slow)，DEA = EMA(signal) 作用于有效 DIF 序列，
     HIST = 2*(DIF - DEA)（国内惯例）。

``ui.chart_view`` 从本模块再导出这些函数，保持历史导入路径兼容。
"""
import math


def _ema_series(values, n):
    """EMA 序列（与 values 等长，前段为 None 预热）。"""
    out = [None] * len(values)
    if len(values) < n:
        return out
    k = 2.0 / (n + 1)
    e = sum(values[:n]) / n
    out[n - 1] = e
    for i in range(n, len(values)):
        e = values[i] * k + e * (1 - k)
        out[i] = e
    return out


def ma_series(closes, n):
    """简单移动平均 MA(n)，前 n-1 个为 None。"""
    out = [None] * len(closes)
    s = 0.0
    for i, v in enumerate(closes):
        s += v
        if i >= n:
            s -= closes[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def boll_series(closes, n=20, k=2.0):
    """布林线 BOLL(n,k)：返回 (上轨, 中轨, 下轨)，标准差用总体（ddof=0）。"""
    size = len(closes)
    upper = [None] * size
    mid = [None] * size
    lower = [None] * size
    for i in range(n - 1, size):
        window = closes[i - n + 1:i + 1]
        m = sum(window) / n
        std = math.sqrt(sum((v - m) ** 2 for v in window) / n)
        mid[i] = m
        upper[i] = m + k * std
        lower[i] = m - k * std
    return upper, mid, lower


def macd_series(closes, fast=12, slow=26, signal=9):
    """MACD(fast,slow,signal)：返回 (DIF, DEA, HIST)，hist=2*(DIF-DEA)。"""
    ef = _ema_series(closes, fast)
    es = _ema_series(closes, slow)
    dif = [None if (a is None or b is None) else a - b
           for a, b in zip(ef, es)]
    valid = [(i, v) for i, v in enumerate(dif) if v is not None]
    dea = [None] * len(closes)
    if len(valid) >= signal:
        e9 = _ema_series([v for _, v in valid], signal)
        for j, (i, _) in enumerate(valid):
            dea[i] = e9[j]
    hist = [None if (d is None or e is None) else 2 * (d - e)
            for d, e in zip(dif, dea)]
    return dif, dea, hist
