# -*- coding: utf-8 -*-
"""重建 data/top300.json：四个市场「全部」页按**总市值从大到小**排序。

目标数量（精确）：crypto 200 / cn 100 / hk 200 / us 500。

本机实测可达性（2026-11，直连 trust_env=False）：
  东方财富 push2.eastmoney.com  —— TCP/TLS 被网络层重置，curl 同样失败，不可用
  CoinGecko / coinpaprika / coincap / CoinMarketCap —— 超时或 DNS 失败，不可用
  api.coinlore.net             —— 可用，返回 market_cap_usd（加密市值排行）
  data-api.binance.vision      —— 可用，exchangeInfo 提供币安可交易代码白名单
  新浪 finance.sina.com.cn     —— 可用，A股 mktcap 降序 / 美股 mktcap 降序+中文名
  api.nasdaq.com               —— 可用，股票 screener 提供 marketCap（美股主榜）
  qt.gtimg.cn（腾讯行情）      —— 可用，f[44] 为总市值（亿），用于港股全量枚举

因此各市场实际采用：
  crypto  coinlore 市值降序 + 币安 USDT 现货可交易白名单交叉 + 稳定币/包装币过滤
  cn      新浪 Market_Center（node=hs_a, sort=mktcap, asc=0）
  hk      腾讯 qt.gtimg.cn 枚举 00001~09999 全部港股代码，按 f[44] 总市值降序
  us      Nasdaq screener marketCap 降序 + 新浪中文名补全
东方财富仍作为首选尝试（快速失败），失败后自动切到上述可用源。

离线可重跑：网络任一环节失败时，回退到**当前 data/top300.json 已有清单**
（保留其顺序，去重、补齐/截断到目标数量），并写入 fallback 标记；
加密回退时把主流币提到前面并置 crypto_fallback=true。
可用 `python tools/rebuild_universe_marketcap.py --offline` 强制离线演练。

只写 data/top300.json，不修改任何其它文件。
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
from data.api_base import HTTP  # noqa: E402  trust_env=False，绕过本机代理

OUT = os.path.join(_ROOT, "data", "top300.json")
TARGET = {"crypto": 200, "cn": 100, "hk": 200, "us": 500}

_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}
_SINA_UA = dict(_UA, Referer="https://finance.sina.com.cn/")
_NASDAQ_UA = dict(_UA, Referer="https://www.nasdaq.com/")


def get(url, params=None, headers=None, timeout=12, tries=2):
    """带重试的 GET；全部失败抛出最后一个异常。"""
    last = None
    for i in range(tries):
        try:
            r = HTTP.get(url, params=params, headers=headers or _UA, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:  # 网络层/HTTP/解析异常统一重试
            last = e
            if i + 1 < tries:
                time.sleep(0.6)
    raise last


def _half(s):
    """全角转半角，仅用于名称过滤判断（输出名称保留原样）。"""
    return unicodedata.normalize("NFKC", s or "")


def _clean_name(s, fallback=""):
    s = (s or "").strip()
    return s or fallback


# --------------------------------------------------------------------------
# 通用：东方财富（首选，实测不可达，快速失败）
# --------------------------------------------------------------------------
EM_URL = "https://push2.eastmoney.com/api/qt/clist/get"
EM_FS = {
    "cn": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
    "hk": "m:128+t:3,m:128+t:4,m:128+t:1,m:128+t:2",
    "us": "m:105,m:106,m:107",
}
# 名称里的基金/ETF/衍生品关键词（东方财富与港股过滤共用）
_EM_BAD = re.compile(
    r"ETF|ETN|基金|指数|认购|沽空|牛熊|反向|每日|杠杆|权证|债券|票据|信托|单位|SPDR",
    re.I)


def _em_rows(fs):
    """返回 (code, name, cap) 列表；不可达返回 None。"""
    try:
        j = get(EM_URL, dict(pn=1, pz=600, po=1, np=1, fltt=2, invt=2,
                             fid="f20", fs=fs, fields="f12,f13,f14,f20"),
                timeout=5, tries=1).json()
        diff = ((j.get("data") or {}).get("diff")) or []
        items = list(diff.values()) if isinstance(diff, dict) else diff
        out = []
        for d in items:
            if not isinstance(d, dict):
                continue
            try:
                cap = float(d.get("f20") or 0)
            except (TypeError, ValueError):
                cap = 0.0
            if cap > 0:
                out.append((str(d.get("f12") or ""), str(d.get("f14") or ""), cap))
        return out or None
    except Exception:
        return None


# --------------------------------------------------------------------------
# crypto：coinlore 市值 + 币安白名单
# --------------------------------------------------------------------------
# 稳定币、包装币、杠杆/份额代币等一律剔除
_CRYPTO_DENY = set("""
USDT USDC FDUSD TUSD BUSD DAI USDE USD1 USDP USDS USDD PYUSD EURC EURT
FRAX LUSD CRVUSD GHO USDB USDG RLUSD BUIDL USDL USDY USDN FEI HUSD
USDT.E USDC.E BUSD.E XAUT PAXG USDX USDQ SUSD MIM DOLA USDK SBD
WBTC WETH WBNB WSTETH STETH RETH CBBTC LBTC WBETH WTRX WAVAX WFTM
WONE BTCB BSCUSD WSOL JUPSOL BNSOL UP DOWN BULL BEAR HALF
""".split())
_CRYPTO_MAJORS = [
    "BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA", "AVAX", "TRX", "LINK",
    "DOT", "LTC", "BCH", "XLM", "TON", "SHIB", "SUI", "UNI", "NEAR", "APT",
    "ARB", "OP", "AAVE", "PEPE", "TAO", "HBAR", "ICP", "FIL", "ETC", "ATOM",
]
# 市值候选源，按优先级逐个尝试；前四个实测不可达，coinlore 为实际生效源
_CRYPTO_CAP_SOURCES = ("coingecko", "coinpaprika", "coincap", "coinmarketcap", "coinlore")


def _crypto_cap_rows():
    """返回 (symbol, name, market_cap) 列表，按市值降序；全失败抛异常。"""
    errors = []

    # CoinGecko
    try:
        j = get("https://api.coingecko.com/api/v3/coins/markets",
                dict(vs_currency="usd", order="market_cap_desc", per_page=250, page=1),
                timeout=5, tries=1).json()
        rows = [(str(d.get("symbol") or ""), str(d.get("name") or ""),
                 float(d.get("market_cap") or 0)) for d in j]
        if rows:
            return rows, "CoinGecko"
    except Exception as e:
        errors.append("coingecko:%s" % type(e).__name__)

    # coinpaprika
    try:
        j = get("https://api.coinpaprika.com/v1/tickers", dict(quotes="USD"),
                timeout=6, tries=1).json()
        rows = [(str(d.get("symbol") or ""), str(d.get("name") or ""),
                 float(((d.get("quotes") or {}).get("USD") or {}).get("market_cap") or 0))
                for d in j]
        if rows:
            return rows, "coinpaprika"
    except Exception as e:
        errors.append("coinpaprika:%s" % type(e).__name__)

    # coincap
    try:
        j = get("https://api.coincap.io/v2/assets", dict(limit=250),
                timeout=5, tries=1).json()
        rows = [(str(d.get("symbol") or ""), str(d.get("name") or ""),
                 float(d.get("marketCapUsd") or 0)) for d in (j.get("data") or [])]
        if rows:
            return rows, "coincap"
    except Exception as e:
        errors.append("coincap:%s" % type(e).__name__)

    # CoinMarketCap 公开数据接口
    try:
        j = get("https://api.coinmarketcap.com/data-api/v3/cryptocurrency/listing",
                dict(start=1, limit=250, sortBy="market_cap", sortType="desc"),
                timeout=5, tries=1).json()
        rows = [(str(d.get("symbol") or ""), str(d.get("name") or ""),
                 float(((d.get("quotes") or [{}])[0].get("marketCap")) or 0))
                for d in ((j.get("data") or {}).get("cryptoCurrencyList") or [])]
        if rows:
            return rows, "CoinMarketCap"
    except Exception as e:
        errors.append("coinmarketcap:%s" % type(e).__name__)

    # coinlore（实测可用；limit 上限 100，分页取前 600 名）
    rows = []
    for start in range(0, 600, 100):
        j = get("https://api.coinlore.net/api/tickers/",
                dict(start=start, limit=100), timeout=25, tries=3).json()
        for d in (j.get("data") or []):
            try:
                cap = float(d.get("market_cap_usd") or 0)
            except (TypeError, ValueError):
                cap = 0.0
            rows.append((str(d.get("symbol") or ""), str(d.get("name") or ""), cap))
    if rows:
        return rows, "coinlore"

    raise RuntimeError("加密市值源全部不可达: " + ", ".join(errors))


def _binance_bases():
    """币安 USDT 现货可交易基础币代码集合，用作白名单。"""
    j = get("https://data-api.binance.vision/api/v3/exchangeInfo",
            timeout=25, tries=3).json()
    return {str(d["baseAsset"]).upper() for d in (j.get("symbols") or [])
            if d.get("quoteAsset") == "USDT" and d.get("status") == "TRADING"}


def fetch_crypto(old_names):
    rows, cap_source = _crypto_cap_rows()
    rows.sort(key=lambda x: -x[2])
    try:
        bases = _binance_bases()
        white_desc = "币安USDT现货白名单"
    except Exception:
        # 币安也失败时，退回到现有 crypto 清单做白名单交叉
        bases = set(old_names)
        white_desc = "现有清单白名单"

    out, seen = [], set()
    for sym, name, cap in rows:
        s = sym.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{1,15}", s) or cap <= 0 or s in seen:
            continue
        if s in _CRYPTO_DENY or s.startswith("1000") \
                or s.endswith(("UP", "DOWN", "BULL", "BEAR")):
            continue
        if s not in bases:
            continue
        seen.add(s)
        out.append([s, _clean_name(old_names.get(s) or name, s)])
    src = "%s 市值降序 + %s" % (cap_source, white_desc)
    return out, src


# --------------------------------------------------------------------------
# cn：新浪沪深 A 股总市值降序
# --------------------------------------------------------------------------
_SINA_A = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           "Market_Center.getHQNodeData")


def fetch_cn(old_names):
    em = _em_rows(EM_FS["cn"])
    if em:
        out = []
        for code, name, cap in sorted(em, key=lambda x: -x[2]):
            c = code.strip()
            if not re.fullmatch(r"\d{6}", c):
                continue
            if _EM_BAD.search(_half(name)):
                continue
            # 6 开头沪市，0/3 开头深市
            pre = "SH" if c.startswith("6") else "SZ"
            out.append(["%s:%s" % (pre, c), _clean_name(name)])
        if len(out) >= TARGET["cn"]:
            return _dedup(out)[:TARGET["cn"]], "东方财富 clist(f20 总市值降序)"

    rows = []
    for page in range(1, 8):  # num 上限 100，足够取到 100 名
        j = get(_SINA_A, dict(page=page, num=100, sort="mktcap", asc=0, node="hs_a"),
                headers=_SINA_UA, timeout=12, tries=2).json()
        if not j:
            break
        for d in j:
            try:
                cap = float(d.get("mktcap") or 0)
            except (TypeError, ValueError):
                cap = 0.0
            rows.append((str(d.get("symbol") or ""), str(d.get("name") or ""), cap))
        if len(rows) >= TARGET["cn"] * 2:
            break
    rows.sort(key=lambda x: -x[2])
    out = []
    for sym, name, cap in rows:
        m = re.fullmatch(r"(sh|sz)(\d{6})", sym.strip().lower())
        if not m or cap <= 0 or _EM_BAD.search(_half(name)):
            continue
        code = "%s:%s" % (m.group(1).upper(), m.group(2))
        out.append([code, _clean_name(old_names.get(code) or name)])
        if len(out) >= TARGET["cn"]:
            break
    return _dedup(out)[:TARGET["cn"]], "新浪 Market_Center hs_a (mktcap 总市值降序)"


# --------------------------------------------------------------------------
# hk：腾讯 qt.gtimg.cn 全量枚举港股代码，按 f[44] 总市值降序
# --------------------------------------------------------------------------
_TC_QUOTE = "https://qt.gtimg.cn/q="
# 非普通股票的代码段：ETF/基金、代币化(-T)股份、牛熊/杠杆产品、创业板
_HK_SKIP_RANGES = ((2800, 2899), (3000, 3199), (4300, 4399), (7200, 7799))
_HK_BAD_NAME = re.compile(
    r"ETF|ETN|基金|指数|认购|沽空|牛熊|反向|每日|杠杆|权证|债券|票据|"
    r"信托|单位|SPDR|DRS|黄金ETF|做多|做空", re.I)
# 非普通股票的名称后缀（-W/-S/-SW/-B 等是真实港股，保留）
_HK_BAD_SUFFIX = ("-T", "-U", "-R", "-D", "-DRS", "-P", "-SS")


def _hk_ok(code_num, name):
    for lo, hi in _HK_SKIP_RANGES:
        if lo <= code_num <= hi:
            return False
    n = _half(name)
    if not n or re.fullmatch(r"\d{5}", n):   # 名称缺失（等于代码）也剔除
        return False
    if _HK_BAD_NAME.search(n) or n.upper().endswith(_HK_BAD_SUFFIX):
        return False
    return True


def fetch_hk(old_names):
    em = _em_rows(EM_FS["hk"])
    if em:
        out = []
        for code, name, cap in sorted(em, key=lambda x: -x[2]):
            c = code.strip().zfill(5)
            if not re.fullmatch(r"\d{5}", c) or _EM_BAD.search(_half(name)):
                continue
            out.append(["HK:%s" % c, _clean_name(name)])
        if len(out) >= TARGET["hk"]:
            return _dedup(out)[:TARGET["hk"]], "东方财富 clist(f20 总市值降序)"

    rows = []
    for lo in range(1, 10000, 200):
        codes = ["hk%05d" % i for i in range(lo, min(lo + 200, 10000))]
        try:
            r = get(_TC_QUOTE + ",".join(codes), timeout=15, tries=2)
            r.encoding = "gbk"
        except Exception:
            continue  # 单个批次失败不影响整体，候选数量充足
        for line in r.text.split(";"):
            m = re.match(r'v_hk(\d{5})="(.*)"', line.strip())
            if not m:
                continue
            f = m.group(2).split("~")
            if len(f) < 45 or not f[1]:
                continue
            try:
                cap = float(f[44] or 0)   # f[44] = 总市值（亿港元）
            except (TypeError, ValueError):
                continue
            num = int(m.group(1))
            name = _clean_name(f[1])
            if cap > 0 and _hk_ok(num, name):
                rows.append((cap, num, name))
    rows.sort(key=lambda x: -x[0])
    out = []
    for cap, num, name in rows:
        code = "HK:%05d" % num
        out.append([code, _clean_name(old_names.get(code) or name)])
        if len(out) >= TARGET["hk"]:
            break
    return _dedup(out)[:TARGET["hk"]], "腾讯 qt.gtimg.cn 全量港股枚举 (f[44] 总市值降序)"


# --------------------------------------------------------------------------
# us：Nasdaq screener 市值降序，新浪中文名补全
# --------------------------------------------------------------------------
_SINA_US = ("https://stock.finance.sina.com.cn/usstock/api/jsonp_v2.php/"
            "var%20t=/US_CategoryService.getList")
_NASDAQ_SCREENER = "https://api.nasdaq.com/api/screener/stocks"
_US_BAD = re.compile(
    r"\b(ETF|ETN|Warrants?|Rights?|Units?|Preferred|Depositary|Notes?|SPAC|"
    r"Acquisition)\b|基金|指数|权证|优先|存托|票据|做多|做空|杠杆|反向|每日", re.I)
_US_TICKER = re.compile(r"[A-Z]{1,5}")


def _sina_us_names(pages=25):
    """尽力抓取新浪美股中文名映射（num 上限 20，25 页覆盖前 500 名）。"""
    out = {}
    for page in range(1, pages + 1):
        try:
            r = get(_SINA_US, dict(page=page, num=20, sort="mktcap", asc=0,
                                  market="", id=""), headers=_SINA_UA,
                    timeout=12, tries=1)
            txt = r.text
            j = json.loads(txt[txt.find("(") + 1:txt.rfind(")")])
            for d in (j.get("data") or []):
                s = str(d.get("symbol") or "").strip().upper()
                n = _clean_name(d.get("cname") or d.get("name"))
                if s and n and s not in out:
                    out[s] = n
        except Exception:
            break
    return out


def _sina_us_ranked():
    """新浪美股列表兜底：按 mktcap 降序返回 (code, name)。"""
    out = []
    for page in range(1, 40):
        try:
            r = get(_SINA_US, dict(page=page, num=20, sort="mktcap", asc=0,
                                  market="", id=""), headers=_SINA_UA,
                    timeout=12, tries=1)
            txt = r.text
            j = json.loads(txt[txt.find("(") + 1:txt.rfind(")")])
        except Exception:
            break
        data = j.get("data") or []
        if not data:
            break
        for d in data:
            s = str(d.get("symbol") or "").strip().upper()
            try:
                cap = float(d.get("mktcap") or 0)
            except (TypeError, ValueError):
                cap = 0.0
            if cap > 0 and _US_TICKER.fullmatch(s) \
                    and not _US_BAD.search(_half(d.get("cname") or d.get("name") or "")):
                out.append(["US:" + s, _clean_name(d.get("cname") or d.get("name") or s)])
        if len(out) >= TARGET["us"]:
            break
    return _dedup(out)[:TARGET["us"]]


def fetch_us(old_names):
    em = _em_rows(EM_FS["us"])
    if em:
        out = []
        for code, name, cap in sorted(em, key=lambda x: -x[2]):
            s = code.strip().upper().split(".")[0]   # 剥离 .OQ/.N/.AM 等后缀
            if not _US_TICKER.fullmatch(s) or _US_BAD.search(_half(name)):
                continue
            out.append(["US:" + s, _clean_name(name)])
        if len(out) >= TARGET["us"]:
            return _dedup(out)[:TARGET["us"]], "东方财富 clist(f20 总市值降序)"

    try:
        j = get(_NASDAQ_SCREENER, dict(tableonly="true", limit=9000, offset=0),
                headers=_NASDAQ_UA, timeout=25, tries=3).json()
        rows = ((j.get("data") or {}).get("table") or {}).get("rows") or []
        cand = []
        en_names = {}
        for d in rows:
            s = str(d.get("symbol") or "").strip().upper()
            n = str(d.get("name") or "").strip()
            try:
                cap = float(str(d.get("marketCap") or "").replace(",", ""))
            except ValueError:
                cap = 0.0
            if cap <= 0 or not _US_TICKER.fullmatch(s) or _US_BAD.search(_half(n)):
                continue
            cand.append((cap, s))
            en_names[s] = n
        cand.sort(key=lambda x: -x[0])
    except Exception:
        return _sina_us_ranked(), "新浪美股 US_CategoryService (mktcap 降序)"

    cn_names = _sina_us_names()
    out = []
    for cap, s in cand:
        code = "US:" + s
        name = old_names.get(code) or cn_names.get(s) or en_names.get(s) or s
        out.append([code, _clean_name(name, s)])
        if len(out) >= TARGET["us"]:
            break
    return _dedup(out)[:TARGET["us"]], "Nasdaq screener (marketCap 降序) + 新浪中文名"


# --------------------------------------------------------------------------
# 工具：去重 / 离线回退 / 校验
# --------------------------------------------------------------------------
def _dedup(pairs):
    seen, out = set(), []
    for p in pairs:
        if p[0] not in seen:
            seen.add(p[0])
            out.append(p)
    return out


# 各市场补齐用的内置候选（仅在现有清单短于目标数量时使用）
EXTRA_POOL = {
    "crypto": """BTC ETH BNB SOL XRP DOGE ADA AVAX TRX LINK DOT LTC BCH XLM ATOM NEAR
APT ARB OP SUI SEI TIA INJ UNI AAVE MKR COMP CRV LDO PENDLE ONDO ALGO HBAR
VET ICP FIL AR GRT IMX SAND MANA AXS GALA ENJ CHZ ZEC DASH ETC XMR XTZ
THETA RUNE KAVA ZIL WAVES IOTA NEO QTUM FLOW KSM DYDX GMX SUSHI 1INCH
PEPE SHIB BONK WIF FLOKI JASMY TON TAO RENDER FET WLD JUP PYTH JTO STRK""".split(),
    "cn": """SH:600519 SH:601398 SH:601939 SH:601288 SH:601988 SH:600941 SH:601857
SH:600938 SH:600036 SH:601088 SH:601628 SH:601318 SH:688981 SH:601138
SH:601899 SH:601328 SH:600900 SH:600028 SH:601012 SH:600030 SH:601166
SZ:300750 SZ:000001 SZ:002594 SZ:300308 SZ:000858 SZ:002415 SZ:300502
SZ:000333 SZ:002475 SZ:300059 SZ:002230 SZ:000725 SZ:300124 SZ:300760""".split(),
    "hk": """HK:00700 HK:09988 HK:00005 HK:00939 HK:00941 HK:01299 HK:01398
HK:01810 HK:03690 HK:00883 HK:09999 HK:00945 HK:02388 HK:03988 HK:02888
HK:00388 HK:02318 HK:00267 HK:06160 HK:00016 HK:03328 HK:00981 HK:00001
HK:09618 HK:01211 HK:00669 HK:03968 HK:02378 HK:00992 HK:09633 HK:01109""".split(),
    "us": """US:AAPL US:NVDA US:MSFT US:GOOGL US:GOOG US:AMZN US:TSM US:META
US:AVGO US:TSLA US:LLY US:WMT US:JPM US:AMD US:MU US:V US:JNJ US:XOM
US:ASML US:MA US:COST US:HD US:PG US:ABBV US:KO US:PEP US:BAC US:NFLX
US:CRM US:ORCL US:CSCO US:DIS US:WFC US:CVX US:MRK US:INTC US:QCOM""".split(),
}


def _fallback(key, old_list, old_names):
    """网络失败时回退到现有清单，保证数量精确、格式合法、无重复。"""
    lst = []
    for e in old_list or []:
        if isinstance(e, (list, tuple)) and len(e) >= 2 and isinstance(e[0], str):
            code, name = e[0].strip(), _clean_name(str(e[1]))
            if code and name:
                lst.append([code, name])
    lst = _dedup(lst)

    if key == "crypto":
        # 按现有顺序（近似市值序）截取，并把主流币提到前面
        index = {p[0]: p for p in lst}
        majors = [index[s] for s in _CRYPTO_MAJORS if s in index]
        rest = [p for p in lst if p[0] not in set(_CRYPTO_MAJORS)]
        lst = _dedup(majors + rest)

    # 不足则以内置候选池补齐
    seen = {p[0] for p in lst}
    for c in EXTRA_POOL.get(key, []):
        if len(lst) >= TARGET[key]:
            break
        if c in seen:
            continue
        seen.add(c)
        lst.append([c, _clean_name(old_names.get(c), c)])
    if len(lst) < TARGET[key]:
        raise RuntimeError("离线回退：%s 清单不足 %d 条（现有 %d 条）"
                           % (key, TARGET[key], len(lst)))
    return lst[:TARGET[key]]


_CODE_RE = {
    "crypto": re.compile(r"[A-Z0-9]{1,15}"),
    "cn": re.compile(r"(SH|SZ):\d{6}"),
    "hk": re.compile(r"HK:\d{5}"),
    "us": re.compile(r"US:[A-Z0-9]{1,6}"),
}


def validate(data):
    """生成结果断言：数量、格式、无重复、名称非空。"""
    for key, n in TARGET.items():
        assert key in data, "缺少键 %s" % key
        lst = data[key]
        assert isinstance(lst, list), "%s 不是列表" % key
        assert len(lst) == n, "%s 数量 %d != %d" % (key, len(lst), n)
        codes = []
        for e in lst:
            assert isinstance(e, list) and len(e) == 2, "%s 元素格式错误: %r" % (key, e)
            code, name = e
            assert isinstance(code, str) and isinstance(name, str), "%s 元素非字符串" % key
            assert name.strip(), "%s 存在空名称: %r" % (key, e)
            assert _CODE_RE[key].fullmatch(code), "%s 代码格式错误: %r" % (key, code)
            codes.append(code)
        assert len(set(codes)) == n, "%s 存在重复代码" % key
        if key == "us":
            assert all(c.startswith("US:") and c[3:] == c[3:].upper()
                       and "." not in c and c[3:].isupper() or c[3:].isdigit()
                       for c in []), ""  # 占位，下面单独严格校验
            for c in codes:
                raw = c[3:]
                assert raw and not any(ch.islower() for ch in raw), "美股含小写: %s" % c
                assert "." not in raw and "-" not in raw, "美股含点号/连字符: %s" % c
    return True


def main():
    ap = argparse.ArgumentParser(description="按市值重建 data/top300.json")
    ap.add_argument("--offline", action="store_true", help="强制离线，用现有清单回退")
    args = ap.parse_args()

    with open(OUT, "r", encoding="utf-8") as f:
        data = json.load(f)
    old = {k: data.get(k, []) for k in TARGET}
    old_names = {k: {e[0]: e[1] for e in old[k]
                     if isinstance(e, (list, tuple)) and len(e) >= 2}
                 for k in TARGET}

    fetchers = {"crypto": fetch_crypto, "cn": fetch_cn, "hk": fetch_hk, "us": fetch_us}
    result, sources, fallback = {}, {}, []
    for key in TARGET:
        if args.offline:
            result[key] = _fallback(key, old[key], old_names[key])
            sources[key] = "离线回退（现有清单）"
            fallback.append(key)
            continue
        try:
            lst, src = fetchers[key](old_names[key])
            lst = _dedup(lst)
            if len(lst) < TARGET[key]:
                raise RuntimeError("网络结果仅 %d 条，不足 %d" % (len(lst), TARGET[key]))
            result[key] = lst[:TARGET[key]]
            sources[key] = src
        except Exception as e:
            print("[%s] 网络获取失败(%s: %s)，回退现有清单"
                  % (key, type(e).__name__, str(e)[:120]), flush=True)
            result[key] = _fallback(key, old[key], old_names[key])
            sources[key] = "离线回退（现有清单）"
            fallback.append(key)

    # 元数据：保留原有说明性字段，写入新排序/数量信息
    data.update({
        "generated": datetime.now().strftime("%Y-%m-%d"),
        "top_n": max(TARGET.values()),           # 全部页上限，现为 500
        "order_by": "market_cap_desc",
        "counts": dict(TARGET),
        "data_sources": sources,
    })
    for key in TARGET:
        data[key] = result[key]
    data.setdefault("crypto_sources", ["Binance", "Gate.io", "OKX", "Coinbase", "Huobi"])
    data.setdefault("exchanges", {})
    if "crypto" in fallback:
        data["crypto_fallback"] = True
    else:
        data.pop("crypto_fallback", None)
    if fallback:
        data["fallback"] = fallback
    else:
        data.pop("fallback", None)

    validate(data)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    print("\n生成完成:", OUT, flush=True)
    print("counts:", {k: len(data[k]) for k in TARGET}, flush=True)
    print("data_sources:", json.dumps(sources, ensure_ascii=False), flush=True)
    if fallback:
        print("fallback markets:", fallback, flush=True)
    for key in TARGET:
        print("\n%s 前 10 名（市值降序）:" % key, flush=True)
        for i, (c, n) in enumerate(data[key][:10], 1):
            print("  %2d. %-14s %s" % (i, c, n), flush=True)


if __name__ == "__main__":
    main()
