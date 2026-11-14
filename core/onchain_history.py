# -*- coding: utf-8 -*-
"""链上真实报价采样历史。

链上合约代币没有交易所 OHLC，DeX/GeckoTerminal 等 K 线源在国内网络也
不可直连。这里不伪造蜡烛，而是把每次从 Rugcheck 取到的**真实价格**连同
时间戳落盘，累积成一条可绘制的走势序列：

    { "ONCHAIN:<addr>": [[ts, price], ...] }

界面必须标注「本设备采集的真实报价走势 · 非交易所 K 线 · 无 OHLC / 成交量」。
只存真实观测值：不插值、不外推、不补点。
"""
import json
import os
import time

MAX_POINTS = 720          # 每个品种最多保留的采样点
MIN_GAP = 20.0            # 20 秒内同价重复回调不重复记点


def path() -> str:
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "CryptoTicker", "onchain_history.json")


def _load() -> dict:
    try:
        with open(path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    p = path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass  # 只读环境不影响程序运行，只是不落盘


def series(symbol: str) -> list:
    """返回 [[ts, price], ...]；脏数据会被剔除。"""
    raw = _load().get(symbol) or []
    out = []
    for row in raw if isinstance(raw, list) else []:
        if (isinstance(row, (list, tuple)) and len(row) >= 2):
            try:
                ts, price = float(row[0]), float(row[1])
                if ts > 0 and price > 0 and ts == ts and price == price:
                    out.append([ts, price])
            except (TypeError, ValueError):
                continue
    # 手工编辑 / 旧版本残留的超长文件也只取最近的一段，避免绘制时卡顿
    if len(out) > MAX_POINTS:
        out = out[-MAX_POINTS:]
    return out


def record(symbol: str, price, ts=None) -> bool:
    """记录一个真实价格点；重复/无效数据返回 False。"""
    try:
        price = float(price)
        ts = float(ts if ts is not None else time.time())
    except (TypeError, ValueError):
        return False
    if price <= 0 or ts <= 0 or price != price or ts != ts:
        return False
    data = _load()
    rows = data.get(symbol)
    if not isinstance(rows, list):
        rows = []
    if rows and isinstance(rows[-1], (list, tuple)) and len(rows[-1]) >= 2:
        try:
            last_ts, last_price = float(rows[-1][0]), float(rows[-1][1])
            if abs(ts - last_ts) < MIN_GAP and last_price == price:
                return False
        except (TypeError, ValueError):
            pass
    rows.append([ts, price])
    if len(rows) > MAX_POINTS:
        rows = rows[-MAX_POINTS:]
    data[symbol] = rows
    _save(data)
    return True


def clear(symbol: str = None) -> None:
    """删掉某个品种（或全部）的采样历史。"""
    if symbol is None:
        _save({})
        return
    data = _load()
    data.pop(symbol, None)
    _save(data)
