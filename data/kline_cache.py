# -*- coding: utf-8 -*-
"""K 线本地缓存（SQLite，零第三方依赖）。

目标：把每个主流品种的 K 线历史持久化到本机，之后每次浏览直接读盘，
省掉重复的 API 请求与等待。设计要点：

- 每个 (symbol, interval) 一张逻辑表，按 ts 主键 upsert，翻页回溯不会重复；
- meta 表记录「是否已回溯到上市首根」与最后更新时间；
- 缓存新鲜期内完全不联网（默认 15 分钟），过期后才发一次增量请求；
- GUI 线程与 KlineWorker / HistoryWorker 各用各自的 sqlite 连接
  （threading.local），避免跨线程复用连接报错；
- 路径在 %APPDATA%/CryptoTicker/klines.sqlite3，测试用临时 APPDATA 隔离。
"""
import os
import sqlite3
import threading
import time

from data.klines import Candle

_DB_NAME = "klines.sqlite3"
_FRESH_SECONDS = 900          # 15 分钟内直接读本地，不发 K 线请求
_local = threading.local()


def db_path() -> str:
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "CryptoTicker", _DB_NAME)


def _conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        return conn
    path = db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.DatabaseError:
        pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS candles (
            symbol TEXT NOT NULL, interval TEXT NOT NULL, ts REAL NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            label TEXT,
            PRIMARY KEY (symbol, interval, ts))""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            symbol TEXT NOT NULL, interval TEXT NOT NULL,
            exhausted INTEGER DEFAULT 0, updated REAL DEFAULT 0,
            PRIMARY KEY (symbol, interval))""")
    conn.commit()
    _local.conn = conn
    return conn


def _meta(symbol: str, interval: str):
    row = _conn().execute(
        "SELECT exhausted, updated FROM meta WHERE symbol=? AND interval=?",
        (symbol, interval)).fetchone()
    return (bool(row[0]), float(row[1])) if row else (False, 0.0)


def is_fresh(symbol: str, interval: str, ttl: int = _FRESH_SECONDS) -> bool:
    """缓存是否存在且仍在新鲜期内。"""
    _ex, updated = _meta(symbol, interval)
    if updated <= 0 or (time.time() - updated) > ttl:
        return False
    return count(symbol, interval) > 0


def is_exhausted(symbol: str, interval: str) -> bool:
    return _meta(symbol, interval)[0]


def count(symbol: str, interval: str) -> int:
    return _conn().execute(
        "SELECT COUNT(*) FROM candles WHERE symbol=? AND interval=?",
        (symbol, interval)).fetchone()[0]


def load(symbol: str, interval: str) -> list:
    """读取该品种/周期的全部已缓存 K 线（按时间升序）。"""
    rows = _conn().execute(
        "SELECT ts, label, open, high, low, close, volume FROM candles "
        "WHERE symbol=? AND interval=? ORDER BY ts",
        (symbol, interval)).fetchall()
    return [Candle(ts=r[0], time_label=r[1] or "", open=r[2], high=r[3],
                   low=r[4], close=r[5], volume=r[6]) for r in rows]


def take_before(symbol: str, interval: str, before_ts: float,
                limit: int = 1000) -> list:
    """从本地取出更早的一页；够用就完全不用请求 API。"""
    rows = _conn().execute(
        "SELECT ts, label, open, high, low, close, volume FROM candles "
        "WHERE symbol=? AND interval=? AND ts<? ORDER BY ts DESC LIMIT ?",
        (symbol, interval, before_ts, limit)).fetchall()
    return [Candle(ts=r[0], time_label=r[1] or "", open=r[2], high=r[3],
                   low=r[4], close=r[5], volume=r[6])
            for r in reversed(rows)]


def save(symbol: str, interval: str, candles: list,
         exhausted: bool | None = None):
    """写入/更新 K 线；exhausted=None 表示不改动到头标记。"""
    conn = _conn()
    if candles:
        conn.executemany(
            "INSERT OR REPLACE INTO candles "
            "(symbol,interval,ts,open,high,low,close,volume,label) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [(symbol, interval, c.ts, c.open, c.high, c.low, c.close,
              c.volume, c.time_label) for c in candles])
    if exhausted is None:
        conn.execute(
            "INSERT INTO meta(symbol,interval,exhausted,updated) "
            "VALUES (?,?,0,?) ON CONFLICT(symbol,interval) "
            "DO UPDATE SET updated=excluded.updated",
            (symbol, interval, time.time()))
    else:
        conn.execute(
            "INSERT INTO meta(symbol,interval,exhausted,updated) "
            "VALUES (?,?,?,?) ON CONFLICT(symbol,interval) DO UPDATE SET "
            "exhausted=excluded.exhausted, updated=excluded.updated",
            (symbol, interval, int(bool(exhausted)), time.time()))
    conn.commit()


def clear(symbol: str | None = None):
    conn = _conn()
    if symbol:
        conn.execute("DELETE FROM candles WHERE symbol=?", (symbol,))
        conn.execute("DELETE FROM meta WHERE symbol=?", (symbol,))
    else:
        conn.execute("DELETE FROM candles")
        conn.execute("DELETE FROM meta")
    conn.commit()
