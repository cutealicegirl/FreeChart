# -*- coding: utf-8 -*-
"""市场数据管理器。

职责：
1. 按市场前缀把请求路由到对应适配器：
   - 加密货币（BTC 等）：Binance -> OKX 优先级链，失败自动切换
   - 股票（SH:/SZ:/HK:/US: 前缀）：腾讯行情
2. fetch_tickers：一次调用合并全部市场结果；某组失败不影响另一组，
   全部失败才抛异常（界面显示网络错误并保留缓存）。
3. search：统一搜索入口 —— 加密货币按 Binance 全量代码本地过滤，
   股票走腾讯 smartbox 联想接口（支持中文/拼音/代码）。
"""
import re
import time
from typing import Dict, List

from . import onchain
from .api_base import HTTP, MarketApiError, Ticker
from .binance_api import BinanceApi
from .okx_api import OkxApi
from .tencent_stock_api import TencentStockApi, is_stock_symbol

# 加密货币数据源优先级链
CRYPTO_CHAIN = [BinanceApi, OkxApi]

# 剔除的杠杆代币/稳定币后缀与基础代码（搜索时过滤）
_EXCLUDE_SUFFIX = ("UP", "DOWN", "BULL", "BEAR")
_EXCLUDE_BASE = {"USDC", "FDUSD", "TUSD", "BUSD", "DAI", "EUR", "TRY",
                 "BRL", "ARS", "AEUR", "USDP", "PAXG"}

# 腾讯搜索接口（GBK 编码，支持中文/拼音/代码联想）
SEARCH_URL = "https://smartbox.gtimg.cn/s3/"
# 统一为内部代码时剥离的美股交易所后缀
_US_EXCHANGE_SUFFIX = {"OQ", "N", "AM", "PR", "UQ", "UT"}


class MarketManager:
    """行情管理器：封装数据源选择、自动切换与统一搜索。"""

    def __init__(self, preferred: str = ""):
        self.crypto_chain = [cls() for cls in CRYPTO_CHAIN]
        self.stock_api = TencentStockApi()
        self._crypto_index = 0
        self.set_source(preferred)
        self.source_name: str = self.crypto_chain[self._crypto_index].name
        self.last_success_time: float = 0.0

    # ================= 数据源管理 =================
    def list_sources(self) -> List[str]:
        """返回可手动切换的加密货币数据源（股票源固定为腾讯）。"""
        return [a.name for a in self.crypto_chain]

    def set_source(self, name: str) -> None:
        """手动指定加密货币数据源（设置界面调用），找不到则忽略。"""
        for i, a in enumerate(self.crypto_chain):
            if a.name == name:
                self._crypto_index = i
                return

    # ================= 行情获取 =================
    def fetch_tickers(self, symbols: List[str]) -> Dict[str, Ticker]:
        """获取行情：分组路由，合并结果。"""
        # 链上合约品种没有交易所交易对：绝不能混进加密货币批量请求，
        # 否则币安对整个 symbols 数组返回 400，会让全部加密行情一起空白。
        # 它们由界面层的 OnchainWorker 单独走 Rugcheck 真实报价。
        crypto_syms = [s for s in symbols
                       if not is_stock_symbol(s) and not onchain.is_onchain(s)]
        stock_syms = [s for s in symbols if is_stock_symbol(s)]

        result: Dict[str, Ticker] = {}
        ok_sources: List[str] = []
        errors: List[str] = []

        # ---- 加密货币组：优先级链，失败自动切换 ----
        if crypto_syms:
            tried = 0
            while tried < len(self.crypto_chain):
                adapter = self.crypto_chain[self._crypto_index]
                try:
                    result.update(adapter.fetch_tickers(crypto_syms))
                    ok_sources.append(adapter.name)
                    break
                except MarketApiError as e:
                    errors.append(f"{adapter.name}: {e}")
                    self._crypto_index = \
                        (self._crypto_index + 1) % len(self.crypto_chain)
                    tried += 1

        # ---- 股票组：腾讯 ----
        if stock_syms:
            try:
                result.update(self.stock_api.fetch_tickers(stock_syms))
                ok_sources.append(self.stock_api.name)
            except MarketApiError as e:
                errors.append(f"{self.stock_api.name}: {e}")

        if not result:
            raise MarketApiError(f"全部数据源均不可用（{'; '.join(errors)}）")
        # 记录部分失败的错误（供界面状态栏提示，不中断其它市场）
        self.last_errors = errors
        self.last_success_time = time.time()
        # 状态栏显示本次实际成功的数据源组合
        if ok_sources:
            self.source_name = " + ".join(ok_sources)
        return result

    # ================= 单品种实时报价（图表秒级动画用）=================
    def fetch_quote(self, symbol: str):
        """只取一个品种的最新价与 24h 涨跌幅，返回 (price, change_pct)。

        图表要把「最新一根 K 线」随成交价连续伸缩，需要 1 秒级的轻量请求：
        * 加密货币走 Binance 单交易对接口（一次只回一条），失败再退回批量；
        * 股票走腾讯单条行情（qt.gtimg.cn 本身就是一条一条取的）。
        任何失败返回 (0.0, 0.0)，由调用方沿用上一次价格，不抛异常。
        """
        if not symbol:
            return 0.0, 0.0
        if onchain.is_onchain(symbol):
            # 链上品种走独立报价源（见 ui.main_window._refresh_onchain），
            # 这里不拼 ONCHAIN:xxxUSDT 这种必然 400 的请求。
            return 0.0, 0.0
        if is_stock_symbol(symbol):
            try:
                t = self.stock_api.fetch_tickers([symbol]).get(symbol)
                if t is not None:
                    return float(t.last_price), float(t.change_pct)
            except Exception:
                return 0.0, 0.0
            return 0.0, 0.0
        pair = f"{symbol.upper()}USDT"
        try:
            resp = HTTP.get(
                "https://data-api.binance.vision/api/v3/ticker/24hr",
                params={"symbol": pair}, timeout=6,
                headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                item = resp.json()
                if isinstance(item, dict) and "lastPrice" in item:
                    return (float(item["lastPrice"]),
                            float(item.get("priceChangePercent") or 0.0))
        except Exception:
            pass
        # 单条接口不可用（限流/网络抖动）：退回本市场的批量适配器
        try:
            adapter = self.crypto_chain[self._crypto_index]
            t = adapter.fetch_tickers([symbol]).get(symbol)
            if t is not None:
                return float(t.last_price), float(t.change_pct)
        except Exception:
            pass
        return 0.0, 0.0

    # ================= 统一搜索 =================
    def search(self, query: str) -> List[dict]:
        """搜索可添加的标的。

        返回 [{symbol, name, kind}]，kind: 加密货币/沪市A股/深市A股/
        港股/美股。
        """
        q = query.strip()
        if not q:
            return []
        results: List[dict] = []

        # ---- 加密货币：Binance 全量代码本地过滤 ----
        try:
            for sym, name in self._search_crypto(q):
                results.append({"symbol": sym, "name": name,
                                "kind": "加密货币"})
        except MarketApiError:
            pass  # 搜索失败不阻塞股票结果

        # ---- 股票：腾讯联想 ----
        try:
            results.extend(self._search_stocks(q))
        except MarketApiError:
            pass
        return results

    def _search_crypto(self, q: str) -> List[tuple]:
        """按基础资产名过滤 Binance USDT 交易对（10 分钟缓存）。"""
        now = time.time()
        if not hasattr(self, "_crypto_cache") \
                or now - getattr(self, "_crypto_cache_time", 0) > 600:
            resp = HTTP.get(
                "https://data-api.binance.vision/api/v3/ticker/price",
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            bases = set()
            for item in resp.json():
                s = item.get("symbol", "")
                if not s.endswith("USDT"):
                    continue
                base = s[:-4]
                if base.endswith(_EXCLUDE_SUFFIX) or base in _EXCLUDE_BASE:
                    continue
                bases.add(base)
            self._crypto_cache = sorted(bases)
            self._crypto_cache_time = now
        q_upper = q.upper()
        # 前缀匹配优先，包含匹配其次
        prefix = [b for b in self._crypto_cache if b.startswith(q_upper)]
        contains = [b for b in self._crypto_cache
                    if q_upper in b and not b.startswith(q_upper)]
        return [(b, b) for b in (prefix + contains)[:8]]

    def _search_stocks(self, q: str) -> List[dict]:
        """腾讯 smartbox 联想搜索（中文/拼音/代码）。"""
        resp = HTTP.get(
            SEARCH_URL,
            params={"v": 2, "q": q, "t": "all"},
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        resp.encoding = "gbk"
        m = re.search(r'v_hint="(.*)"', resp.text)
        if not m:
            return []
        # 接口返回 \uXXXX 转义的中文，需解码
        body = m.group(1).encode("utf-8", "ignore").decode(
            "unicode_escape", "ignore")
        kind_map = {"sh": "沪市A股", "sz": "深市A股",
                    "hk": "港股", "us": "美股"}
        results: List[dict] = []
        for entry in body.split("^"):
            fields = entry.split("~")
            if len(fields) < 5:
                continue
            market, code, name, _pinyin, typ = fields[:5]
            if market not in kind_map or "GP" not in typ:
                continue  # 只要股票，跳过基金/债券等
            if market == "us":
                parts = code.split(".")
                if len(parts) == 2 \
                        and parts[1].upper() in _US_EXCHANGE_SUFFIX:
                    code = parts[0]
            symbol = f"{market.upper()}:{code.upper()}"
            results.append({"symbol": symbol, "name": name,
                            "kind": kind_map[market]})
            if len(results) >= 12:
                break
        return results
