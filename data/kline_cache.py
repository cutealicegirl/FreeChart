# -*- coding: utf-8 -*-
"""K 线本地缓存（SQLite，零第三方依赖）。

目标：把每个主流品种的 K 线历史持久化到本机，之后每次浏览直接读盘，
省掉重复的 API 请求与等待。设计要点：

- 每个 (symbol, interval) 一张逻辑表，按 ts 主键 upsert，翻页回溯不会重复；
- meta 表记录「是否已回溯到上市首根」与最后更新时间；
- 新鲜度同时看**周期边界**和时长：跨到新桶立即失效；源确认“本桶无新根”
  后记 checked_bucket，在 TTL 内不再重复打源，既不滞后也不放大请求；
- GUI 线程与 KlineWorker / HistoryWorker 各用各自的 sqlite 连接
  （threading.local），避免跨线程复用连接报错；
- 路径在 %APPDATA%/CryptoTicker/klines.sqlite3，测试用临时 APPDATA 隔离。
"""
import os
import sqlite3
import threading
import time

from data.klines import Candle
from core import kline_time as _kt

_DB_NAME = "klines.sqlite3"
_FRESH_SECONDS = 900          # 同一周期内最长 15 分钟复核一次（边界优先）
# 单一时钟入口，测试可注入固定时间驱动跨日/跨月边界
_now = time.time
# v5 = 缓存键纳入复权口径（adjust_mode + data_version），彻底隔离 raw /
# split_adjusted / total_return 三种口径，防止切换模式后串味。
_CACHE_SCHEMA = "v5-adjust-mode"
_local = threading.local()
# 当前复权口径；由 set_adjust_mode 设置，所有 API 在入口处编入命名空间
_adjust_mode = "split_adjusted"


def set_adjust_mode(mode: str):
    """设置缓存的复权口径命名空间；切换后不同口径数据物理隔离。"""
    from core import adjust_mode as _am
    global _adjust_mode
    _adjust_mode = _am.normalize(mode)


def get_adjust_mode() -> str:
    return _adjust_mode


def _ns(symbol: str) -> str:
    """把当前口径编入缓存 symbol 键。"""
    from core import adjust_mode as _am
    return _am.cache_symbol(symbol, _adjust_mode)


def _adjust_tag(symbol: str) -> str:
    """该标的的公司行为指纹；登记库变化时缓存自动失效。

    放在缓存层内部计算，调用方无需改动。异常时返回空串（退化为不校验指纹
    但 schema 仍生效），保证复权增强层永不让缓存不可用。
    """
    try:
        from data import corporate_actions as _ca
        return _ca.get_registry().fingerprint(symbol)
    except Exception:
        return ""


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
            checked_bucket REAL DEFAULT 0,
            PRIMARY KEY (symbol, interval))""")
    # 兼容旧库：新增列但保留原有行；schema 为空会被判定为过期并重新抓取。
    for col, decl in (("schema", "TEXT DEFAULT ''"),
                      ("adj_tag", "TEXT DEFAULT ''"),
                      ("checked_bucket", "REAL DEFAULT 0")):
        try:
            conn.execute(f"ALTER TABLE meta ADD COLUMN {col} {decl}")
        except sqlite3.OperationalError:
            pass  # 列已存在
    conn.commit()
    _local.conn = conn
    return conn


def _meta(symbol: str, interval: str):
    row = _conn().execute(
        "SELECT exhausted, updated, schema, adj_tag, checked_bucket "
        "FROM meta WHERE symbol=? AND interval=?", (_ns(symbol), interval)).fetchone()
    if not row:
        return (False, 0.0, "", "", 0.0)
    return (bool(row[0]), float(row[1]),
            row[2] if row[2] is not None else "",
            row[3] if row[3] is not None else "",
            float(row[4] or 0))


def expected_bucket(symbol: str, interval: str,
                    now: float | None = None) -> float:
    """当前时刻应形成的 K 线桶起点（按市场时区）。"""
    return _kt.bucket_start(_now() if now is None else now,
                            interval, symbol)


def last_bar_ts(symbol: str, interval: str) -> float:
    """该序列最后一根真实 K 线的 ts；空序列返回 0。"""
    row = _conn().execute(
        "SELECT MAX(ts) FROM candles WHERE symbol=? AND interval=?",
        (_ns(symbol), interval)).fetchone()
    return float(row[0] or 0) if row else 0.0


def is_fresh(symbol: str, interval: str, ttl: int = _FRESH_SECONDS) -> bool:
    """缓存是否足够新：先看周期边界，再看时长与复权口径。

    关键修复：旧实现只看 `now - updated > 900`，导致 00:00 跨到新周期后
    仍用昨天的缓存最多 15 分钟，TTL 一过又一次性补齐（跳变）。
    现在只要“缓存最后一根不在当前桶”且“尚未确认本桶无新根”，立即判旧；
    数据源确认本桶没有新根后写 checked_bucket，TTL 内不再重复打源。
    """
    _ex, updated, schema, adj_tag, checked = _meta(symbol, interval)
    if schema != _CACHE_SCHEMA:       # 旧版缓存（未复权）：强制失效
        return False
    if adj_tag != _adjust_tag(symbol):  # 公司行为登记库已变化：强制失效
        return False
    last = last_bar_ts(symbol, interval)
    if last <= 0:
        return False
    now = _now()
    bucket = expected_bucket(symbol, interval, now)
    # 已拿到当前桶的真实 K 线：TTL 内无需再请求
    if last >= bucket and (now - updated) <= ttl:
        return True
    # 源已确认本桶没有新根（例如休市 / 尚未成交）：TTL 内也不再请求
    if checked >= bucket and (now - updated) <= ttl:
        return True
    return False


def mark_checked(symbol: str, interval: str,
                 bucket: float | None = None,
                 now: float | None = None):
    """记录“该周期桶已经向数据源确认过，没有更新”，避免刷新风暴。

    只改 meta，不动任何真实 K 线；下一个桶到来时 is_fresh 会立刻失效。
    """
    now = _now() if now is None else float(now)
    bucket = (expected_bucket(symbol, interval, now)
              if bucket is None else float(bucket))
    conn = _conn()
    ex, _upd, schema, tag, checked = _meta(symbol, interval)
    conn.execute(
        "INSERT INTO meta(symbol,interval,exhausted,updated,schema,adj_tag,"
        "checked_bucket) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(symbol,interval) DO UPDATE SET "
        "updated=excluded.updated, checked_bucket=excluded.checked_bucket, "
        "schema=excluded.schema, adj_tag=excluded.adj_tag",
        (_ns(symbol), interval, int(ex), now, _CACHE_SCHEMA,
         tag or _adjust_tag(symbol), max(float(checked or 0), bucket)))
    conn.commit()


def is_exhausted(symbol: str, interval: str) -> bool:
    return _meta(symbol, interval)[0]


def count(symbol: str, interval: str) -> int:
    return _conn().execute(
        "SELECT COUNT(*) FROM candles WHERE symbol=? AND interval=?",
        (_ns(symbol), interval)).fetchone()[0]


def load(symbol: str, interval: str) -> list:
    """读取该品种/周期的全部已缓存 K 线（按时间升序）。"""
    rows = _conn().execute(
        "SELECT ts, label, open, high, low, close, volume FROM candles "
        "WHERE symbol=? AND interval=? ORDER BY ts",
        (_ns(symbol), interval)).fetchall()
    return [Candle(ts=r[0], time_label=r[1] or "", open=r[2], high=r[3],
                   low=r[4], close=r[5], volume=r[6]) for r in rows]


def take_before(symbol: str, interval: str, before_ts: float,
                limit: int = 1000) -> list:
    """从本地取出更早的一页；够用就完全不用请求 API。"""
    rows = _conn().execute(
        "SELECT ts, label, open, high, low, close, volume FROM candles "
        "WHERE symbol=? AND interval=? AND ts<? ORDER BY ts DESC LIMIT ?",
        (_ns(symbol), interval, before_ts, limit)).fetchall()
    return [Candle(ts=r[0], time_label=r[1] or "", open=r[2], high=r[3],
                   low=r[4], close=r[5], volume=r[6])
            for r in reversed(rows)]


def save(symbol: str, interval: str, candles: list,
         exhausted: bool | None = None,
         touch: bool = True,
         checked_bucket: float | None = None):
    """写入/更新真实 K 线。

    - exhausted=None 表示不改动到头标记；
    - touch=False 供历史回溯使用：只写 candles/exhausted，不刷新 `updated`，
      否则长时间分页会一直把缓存伪装成“刚更新”，挡住最新行情请求；
    - 预览 K 线（preview=True）一律不落盘，绝不污染真实历史。
    """
    conn = _conn()
    key = _ns(symbol)
    tag = _adjust_tag(symbol)
    real = [c for c in (candles or []) if not getattr(c, "preview", False)]
    if real:
        conn.executemany(
            "INSERT OR REPLACE INTO candles "
            "(symbol,interval,ts,open,high,low,close,volume,label) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [(key, interval, c.ts, c.open, c.high, c.low, c.close,
              c.volume, c.time_label) for c in real])

    ex, updated, schema, old_tag, checked = _meta(symbol, interval)
    if exhausted is not None:
        ex = int(bool(exhausted))
    now = _now()
    new_updated = now if touch else float(updated or 0)
    if checked_bucket is not None:
        checked = max(float(checked or 0), float(checked_bucket))
    elif real:
        data_bucket = max(_kt.bucket_start(c.ts, interval, symbol)
                          for c in real)
        checked = max(float(checked or 0), float(data_bucket))
    conn.execute(
        "INSERT INTO meta(symbol,interval,exhausted,updated,schema,adj_tag,"
        "checked_bucket) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(symbol,interval) DO UPDATE SET "
        "exhausted=excluded.exhausted, updated=excluded.updated, "
        "schema=excluded.schema, adj_tag=excluded.adj_tag, "
        "checked_bucket=excluded.checked_bucket",
        (key, interval, int(ex), new_updated,
         _CACHE_SCHEMA, tag or old_tag, checked))
    conn.commit()


def clear(symbol: str | None = None):
    conn = _conn()
    if symbol:
        conn.execute("DELETE FROM candles WHERE symbol=?", (_ns(symbol),))
        conn.execute("DELETE FROM meta WHERE symbol=?", (_ns(symbol),))
    else:
        conn.execute("DELETE FROM candles")
        conn.execute("DELETE FROM meta")
    conn.commit()


# ---------------- 存储容量管理 ----------------
# 每个（品种, 周期）保留的最大根数。分钟线按 10000 根 ≈ 7 个月的 1m 数据，
# 足够缩放回溯，又不让数据库无限增长。首次配置时在后台 prune 一次即可。
_MAX_BARS_PER_SERIES = 10000


def prune(max_bars: int = _MAX_BARS_PER_SERIES) -> int:
    """裁剪每个（品种, 周期）过旧的 K 线，只保留最近 max_bars 根。

    返回删除的行数。按 ts 倒序保留最新，避免删掉用户正在看的最近历史。
    exhausted 标记一并清除（历史被裁剪后不再是「到上市首根」）。
    """
    conn = _conn()
    removed = 0
    keys = conn.execute("SELECT DISTINCT symbol, interval FROM candles").fetchall()
    for symbol, interval in keys:
        # symbol 来自数据库，已是带命名空间的值，不能再套 _ns()
        total = conn.execute(
            "SELECT COUNT(*) FROM candles WHERE symbol=? AND interval=?",
            (symbol, interval)).fetchone()[0]
        if total <= max_bars:
            continue
        cutoff = conn.execute(
            "SELECT ts FROM candles WHERE symbol=? AND interval=? "
            "ORDER BY ts DESC LIMIT 1 OFFSET ?",
            (symbol, interval, max_bars - 1)).fetchone()
        if not cutoff:
            continue
        cur = conn.execute(
            "DELETE FROM candles WHERE symbol=? AND interval=? AND ts<?",
            (symbol, interval, cutoff[0]))
        removed += cur.rowcount
        conn.execute(
            "UPDATE meta SET exhausted=0 WHERE symbol=? AND interval=?",
            (symbol, interval))
    if removed:
        conn.commit()
    return removed


def stats() -> dict:
    """缓存统计：品种数、序列数、K 线总根数、数据库文件字节数。"""
    conn = _conn()
    series = conn.execute("SELECT COUNT(*) FROM meta").fetchone()[0]
    symbols = conn.execute(
        "SELECT COUNT(DISTINCT symbol) FROM candles").fetchone()[0]
    bars = conn.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
    try:
        size = os.path.getsize(db_path())
    except OSError:
        size = 0
    return {"symbols": symbols, "series": series, "bars": bars, "bytes": size}
