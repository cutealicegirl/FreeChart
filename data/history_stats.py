# -*- coding: utf-8 -*-
"""行情里程碑：用**真实历史数据**算出的品种走势节点（v37）。

与发展历程的区别（两者都展示，互不混淆）：

  - data/timeline.py  人工整理的公开事件（上市、升级、监管裁决 …）
  - 本模块           程序从 K 线 / 本机报价采样里算出的数值节点
                     （区间首末、区间最高/最低及日期、区间涨跌、最大回撤）

准确性约定：数据源一次只返回有限根数（加密月 K 通常覆盖上市至今，
A 股 / 港股日线一次约 640 根，美股日线覆盖更长）。因此所有统计一律
叫「区间」并明确写出统计起点与样本根数，绝不冒充「上市以来历史最高」。
拿不到数据就返回 ok=False，由界面留白，不编造。
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional


def _ts_text(ts: float, month_only: bool = True) -> str:
    try:
        d = datetime.datetime.fromtimestamp(float(ts))
    except (ValueError, TypeError, OSError, OverflowError):
        return "—"
    return d.strftime("%Y-%m" if month_only else "%Y-%m-%d")


def compute(rows: List[tuple], source: str, interval: str,
           note: str = "") -> Dict[str, Any]:
    """rows: [(ts, high, low, close), ...] 按时间正序。

    统一返回固定键；任何一步算不出来都是 ok=False，界面据此留白。
    """
    clean = []
    for r in rows:
        try:
            ts, hi, lo, close = float(r[0]), float(r[1]), float(r[2]), float(r[3])
        except (TypeError, ValueError, IndexError):
            continue
        if ts <= 0 or hi <= 0 or lo <= 0 or close <= 0:
            continue
        clean.append((ts, max(hi, lo, close), min(hi, lo, close), close))
    if len(clean) < 2:
        return {"ok": False, "reason": "历史样本不足", "source": source}

    clean.sort(key=lambda x: x[0])
    hi_row = max(clean, key=lambda x: x[1])
    lo_row = min(clean, key=lambda x: x[2])
    first_close, last_close = clean[0][3], clean[-1][3]
    peak, mdd = clean[0][3], 0.0
    for _, _, _, close in clean:
        peak = max(peak, close)
        if peak > 0:
            mdd = min(mdd, close / peak - 1.0)
    return {
        "ok": True,
        "bars": len(clean),
        "start": _ts_text(clean[0][0]),
        "end": _ts_text(clean[-1][0]),
        "first_close": first_close,
        "last_close": last_close,
        "high": hi_row[1], "high_date": _ts_text(hi_row[0]),
        "low": lo_row[2], "low_date": _ts_text(lo_row[0]),
        "change_pct": (last_close / first_close - 1.0) * 100.0,
        "max_drawdown": mdd * 100.0,
        "source": source, "interval": interval, "note": note,
    }


def from_candles(candles, source: str, interval: str,
                 note: str = "") -> Dict[str, Any]:
    """把 klines.Candle 列表喂给 compute（本模块不 import Qt）。"""
    rows = [(getattr(c, "ts", 0), getattr(c, "high", 0),
             getattr(c, "low", 0), getattr(c, "close", 0)) for c in (candles or [])]
    return compute(rows, source, interval, note)


def from_price_series(series, source: str = "本机报价采样",
                      note: str = "") -> Dict[str, Any]:
    """链上合约：用 core.onchain_history 的真实 (ts, price) 采样算区间。"""
    rows = []
    for p in (series or []):
        try:
            ts, price = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            continue
        rows.append((ts, price, price, price))
    return compute(rows, source, "本机真实报价采样",
                   note or "链上合约没有交易所 K 线，区间统计基于本设备采集的真实报价点")


def for_symbol(symbol: str) -> Dict[str, Any]:
    """同步抓取并计算；调用方应放在后台线程里。失败返回 ok=False。"""
    import os
    from data import onchain

    # offscreen 回归 / CT_OFFLINE：不发起网络请求，避免硬退出时 socket 竞争
    if (os.getenv("CT_OFFLINE") == "1"
            or os.getenv("QT_QPA_PLATFORM") == "offscreen"):
        return {"ok": False, "reason": "离线环境未请求历史数据",
                "source": "—"}

    if onchain.is_onchain(symbol):
        try:
            from core import onchain_history
            return from_price_series(onchain_history.series(symbol))
        except Exception as e:
            return {"ok": False, "reason": str(e),
                    "source": "本机报价采样"}
    try:
        from data import klines
        if symbol.startswith("ONCHAIN:") or symbol.startswith("OC:"):
            return {"ok": False, "reason": "链上品种无交易所 K 线",
                    "source": "—"}
        is_stock = ":" in symbol and not symbol.startswith("ONCHAIN:")
        interval = "month" if is_stock else "1M"
        candles = klines.fetch_klines(symbol, interval)
        src = ("Binance 月 K" if not is_stock
               else "腾讯 / 新浪日 K 聚合月线")
        note = ("统计区间以数据源本次返回的历史为准；"
                "A 股 / 港股单次约 640 根日线，不等同于上市以来全历史")
        return from_candles(candles, src, "月 K", note)
    except Exception as e:
        return {"ok": False, "reason": str(e),
                "source": "历史 K 线接口"}
