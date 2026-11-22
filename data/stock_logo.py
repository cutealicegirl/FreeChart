# -*- coding: utf-8 -*-
"""股票真实图标：公司标志 / 品牌商标（本地缓存 + 后台串行抓取）。

数据源（按顺序尝试）：
- 美股：Finnhub 公开静态图，按代码直取 1000×1000 品牌 logo；
- A 股：东财 F10 公司概况取官网域名 -> Yandex favicon 120px；
- 港股 / 美股兜底：东财港股/美股 F10 取官网域名 -> Yandex favicon 120px。

缓存：
- 图标 `%APPDATA%/FreeChart/icons/stock/<code>.png`（≥24px 才收，1×1 占位图会被拒）；
- 域名 `%APPDATA%/FreeChart/stock_domains.json`，避免重复查 F10。

约束：
- 抓取在后台串行线程里做，请求间留间隔，不与实时行情抢带宽；
- 任何失败都静默跳过（退回字徽），下次启动再试；
- 仅当入口显式调用 `start()` 后才联网，离线回归测试不受影响。
"""
import json
import os
import queue
import threading

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QImage

from data.api_base import HTTP

_FINNHUB = ("https://static2.finnhub.io/file/publicdatany/finnhubimage/"
            "stock_logo/{code}.png")
_YANDEX = "https://favicon.yandex.net/favicon/v2/{host}?size=120&bookmark=1"
_EM_CN = ("https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/"
          "PageAjax?code={code}")
_EM_DC = ("https://datacenter.eastmoney.com/securities/api/data/v1/get"
          "?reportName={report}&columns=ORG_WEB&filter=(SECURITY_CODE%3D%22"
          "{code}%22)&pageSize=1")
_REPORTS = {"hk": "RPT_HKF10_INFO_ORGPROFILE",
            "us": "RPT_USF10_INFO_ORGPROFILE"}


def _base() -> str:
    return os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"),
                        "FreeChart")


def logo_dir() -> str:
    d = os.path.join(_base(), "icons", "stock")
    os.makedirs(d, exist_ok=True)
    return d


def market(symbol: str) -> str:
    if symbol.startswith(("SH:", "SZ:")):
        return "cn"
    if symbol.startswith("HK:"):
        return "hk"
    if symbol.startswith("US:"):
        return "us"
    return ""


def code_of(symbol: str) -> str:
    return symbol.split(":")[-1]


def local_file(symbol: str) -> str:
    """已缓存的真实图标路径；没有返回空串。"""
    if not market(symbol):
        return ""
    p = os.path.join(logo_dir(), code_of(symbol).lower() + ".png")
    if os.path.isfile(p) and os.path.getsize(p) > 250:
        return p
    return ""


# ---- 官网域名缓存 ----
_domains: dict = {}
_domains_loaded = False
_domain_lock = threading.Lock()


def _domain_path() -> str:
    return os.path.join(_base(), "stock_domains.json")


def _load_domains():
    global _domains_loaded
    if _domains_loaded:
        return
    _domains_loaded = True
    try:
        with open(_domain_path(), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _domains.update(data)
    except Exception:
        pass


def _save_domains():
    try:
        with open(_domain_path(), "w", encoding="utf-8") as f:
            json.dump(_domains, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def _norm_host(host: str) -> str:
    host = (host or "").strip().lower()
    for pre in ("https://", "http://"):
        if host.startswith(pre):
            host = host[len(pre):]
    host = host.split("/")[0].split("?")[0]
    return host if "." in host else ""


def _hosts(field: str) -> list:
    """东财官网字段可能是 `a.com,b.com`，拆成候选域名列表。"""
    out = []
    for part in str(field or "").replace(";", ",").replace(" ", ",").split(","):
        h = _norm_host(part)
        if h and h not in out:
            out.append(h)
    return out


def domain_of(symbol: str) -> str:
    """公司官网域名（东财 F10）；查不到返回空串（不缓存失败）。"""
    mkt = market(symbol)
    if not mkt:
        return ""
    key = symbol.upper()
    with _domain_lock:
        _load_domains()
        if key in _domains:
            return _domains[key]
    code = code_of(symbol)
    host = ""
    try:
        if mkt == "cn":
            pre = "SH" if symbol.startswith("SH:") else "SZ"
            r = HTTP.get(_EM_CN.format(code=pre + code), timeout=8)
            jb = (r.json().get("jbzl") or [{}])[0]
            host = jb.get("ORG_WEB") or ""
        else:
            r = HTTP.get(_EM_DC.format(report=_REPORTS[mkt], code=code),
                         timeout=8)
            rows = ((r.json().get("result") or {}).get("data") or [{}])
            host = (rows[0] or {}).get("ORG_WEB") or ""
    except Exception:
        return ""
    host = _norm_host(host)
    if host:
        with _domain_lock:
            _domains[key] = host
            _save_domains()
    return host


def _get(url: str, timeout: int = 10) -> bytes:
    try:
        r = HTTP.get(url, timeout=timeout)
        if r.status_code != 200 or len(r.content) < 200:
            return b""
        return r.content
    except Exception:
        return b""


def _decode(data: bytes):
    """校验图片：≥24px、有可见内容、且不是纯色块（白块/黑块 favicon 直接拒）。"""
    if not data:
        return None
    img = QImage.fromData(data)
    if img.isNull() or img.width() < 24 or img.height() < 24:
        return None
    small = img.scaled(16, 16, Qt.IgnoreAspectRatio,
                       Qt.SmoothTransformation)
    vals = []
    for y in range(small.height()):
        for x in range(small.width()):
            c = small.pixelColor(x, y)
            if c.alpha() > 40:
                vals.append(c.lightness())
    total = small.width() * small.height()
    if len(vals) < total * 0.04:         # 几乎全透明，没有可见图案
        return None
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    if len(vals) > total * 0.9 and var < 40:
        return None                      # 满幅纯色块（白块/黑块 favicon）
    return img


def fetch_logo(symbol: str) -> str:
    """抓取并落盘一张真实 logo；成功返回路径，失败返回空串。"""
    mkt = market(symbol)
    if not mkt:
        return ""
    cached = local_file(symbol)
    if cached:
        return cached
    code = code_of(symbol)
    img = None
    if mkt == "us":
        img = _decode(_get(_FINNHUB.format(code=code.upper())))
    if img is None:
        for host in _hosts(domain_of(symbol)):
            img = _decode(_get(_YANDEX.format(host=host)))
            if img is not None:
                break
    if img is None:
        return ""
    path = os.path.join(logo_dir(), code.lower() + ".png")
    if img.save(path, "PNG"):
        return path
    return ""


class _Signals(QObject):
    logo_ready = Signal(str, str)     # symbol, 本地 png 路径


signals = _Signals()

_pending = set()
_pending_lock = threading.Lock()


class StockLogoWorker(QThread):
    """串行抓取线程：请求间隔 120ms，失败静默跳过。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._q = queue.Queue()
        self._stop = False

    def put(self, symbol: str):
        with _pending_lock:
            if symbol in _pending:
                return
            _pending.add(symbol)
        self._q.put(symbol)

    def wake(self):
        self._q.put(None)

    def stop(self):
        self._stop = True
        self._q.put(None)

    def run(self):
        while not self._stop:
            try:
                sym = self._q.get(timeout=0.4)
            except queue.Empty:
                continue
            if sym is None:
                continue
            try:
                path = fetch_logo(sym)
            except Exception:
                path = ""
            with _pending_lock:
                _pending.discard(sym)
            if path:
                signals.logo_ready.emit(sym, path)
            self.msleep(40)


_workers: list = []
_worker = None          # 首个线程（兼容旧调用 / 测试判断是否已启动）
_backlog: list = []     # start() 之前收到的请求，启动时补投


def start():
    """启动 5 个抓取线程（共用同一队列），300 行约 1 分钟铺满。"""
    global _workers, _worker
    if not _workers:
        for _ in range(5):
            w = StockLogoWorker()
            w.start()
            _workers.append(w)
        _worker = _workers[0]
        # 界面可能先于本线程创建（行控件构造即请求），补投当时被丢弃的请求
        pending = list(_backlog)
        _backlog.clear()
        for sym in pending:
            request(sym)
    return _worker


def stop():
    global _workers, _worker
    for w in _workers:
        w.stop()
    for w in _workers:
        w.wait(2000)
    _workers = []
    _worker = None


def request(symbol: str):
    """入队请求；未启动时先记入 backlog，start() 后自动补投。

    这样界面行先于抓取线程创建（常见于记住上次标签的启动路径）也不会漏。
    """
    if not market(symbol) or local_file(symbol):
        return
    if not _workers:
        if symbol not in _backlog and len(_backlog) < 1200:
            _backlog.append(symbol)
        return
    with _pending_lock:
        if symbol in _pending:
            return
    # 放进当前最短的队列，避免某一根线程排队过长
    min(_workers, key=lambda w: w._q.qsize()).put(symbol)
