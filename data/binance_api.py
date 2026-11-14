# -*- coding: utf-8 -*-
"""Binance 公共行情适配器。

数据源：https://data-api.binance.vision（Binance 官方公开行情镜像，
专为只读行情设计，无需 API Key，国内网络实测可直连）。

接口：GET /api/v3/ticker/24hr?symbols=["BTCUSDT",...]
一次请求返回全部币种，天然满足"批量获取、低资源占用"的要求。

重要：该接口的 symbols 是「全有或全无」——数组里只要有一个不存在的
交易对（下架币、链上合约地址、股票代码被误拼进来），整批 100 个品种
都会返回 HTTP 400，界面表现就是「加密货币整页没数据」。因此这里：
1. 先按合法基础代码过滤，链上/股票等带冒号的代码绝不进请求；
2. 仍遇到 400 Invalid symbol 时，对该批二分拆开重试，只丢弃真正
   非法的那一个，其余品种照常取回；
3. 记住已确认无交易对的代码，后续刷新不再重复拆分。
"""
import json as _json
import re
from typing import Dict, List, Set

from .api_base import HTTP, MarketApi, MarketApiError, Ticker

BASE_URL = "https://data-api.binance.vision/api/v3/ticker/24hr"
# 「全部」页一次刷新 300 个品种；symbols URL 过长会被拒绝，按批拆分。
_BATCH = 100
# 币安现货基础代码：纯大写字母/数字，不含冒号、空格、合约地址等。
_LEGAL_BASE = re.compile(r"^[A-Z0-9]{1,20}$")


class BinanceApi(MarketApi):
    name = "Binance"

    def __init__(self, timeout: float = 10.0):
        super().__init__(timeout)
        # 已确认「无 USDT 交易对」的代码（值形如 XYZUSDT）。
        # MarketManager 长期复用同一个适配器实例，缓存跨刷新有效。
        self._invalid: Set[str] = set()

    @staticmethod
    def legal_pairs(symbols: List[str]) -> List[str]:
        """把内部统一代码转成合法的 USDT 交易对，剔除无法查询的代码。"""
        pairs = []
        for s in symbols:
            code = str(s or "").strip().upper()
            if _LEGAL_BASE.match(code):
                pairs.append(code + "USDT")
        return pairs

    def _request_batch(self, pairs: List[str]):
        """返回数据列表；遇到「整批含非法交易对」返回 None 让上层拆分。

        其它错误（限流、超时、5xx）抛 MarketApiError，交给上层切换数据源，
        不在这里拆分子批，避免网络故障时放大请求量。
        """
        url = BASE_URL + "?symbols=" + _json.dumps(
            pairs, separators=(",", ":"))
        try:
            resp = HTTP.get(url, timeout=self.timeout)
            if resp.status_code == 429:
                raise MarketApiError("Binance API 限流 (HTTP 429)")
            if resp.status_code == 400:
                try:
                    msg = str((resp.json() or {}).get("msg", ""))
                except Exception:
                    msg = ""
                # 只有「数组里含无效交易对」才值得拆分；其它 400 是请求
                # 本身有问题（如参数格式），拆分只会重复报错。
                if "invalid symbol" in msg.lower() or "not valid" in msg.lower():
                    return None
                raise MarketApiError(f"Binance 请求被拒绝 (HTTP 400: {msg or '无详情'})")
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except MarketApiError:
            raise
        except Exception as e:
            raise MarketApiError(f"Binance 请求失败: {e}")

    def _collect(self, pairs: List[str], errors: List[str]) -> list:
        """取整批数据；400 时二分定位并剔除非法交易对。"""
        if not pairs:
            return []
        try:
            data = self._request_batch(pairs)
        except MarketApiError as e:
            errors.append(str(e))
            return []
        if data is not None:
            return data
        if len(pairs) == 1:
            self._invalid.add(pairs[0])
            return []
        mid = len(pairs) // 2
        return (self._collect(pairs[:mid], errors)
                + self._collect(pairs[mid:], errors))

    def fetch_tickers(self, symbols: List[str]) -> Dict[str, Ticker]:
        result: Dict[str, Ticker] = {}
        errors: List[str] = []
        pairs = [p for p in self.legal_pairs(symbols)
                 if p not in self._invalid]
        for i in range(0, len(pairs), _BATCH):
            data = self._collect(pairs[i:i + _BATCH], errors)
            for item in data:
                if not isinstance(item, dict):
                    continue
                symbol = item.get("symbol", "")
                if not isinstance(symbol, str) or not symbol.endswith("USDT"):
                    continue
                try:
                    ticker = Ticker(
                        symbol=symbol[:-4],  # BTCUSDT -> BTC
                        name=symbol[:-4],
                        last_price=float(item["lastPrice"]),
                        change_pct=float(item["priceChangePercent"]),
                        high_24h=float(item["highPrice"]),
                        low_24h=float(item["lowPrice"]),
                        quote_volume_24h=float(item["quoteVolume"]),
                    )
                except (KeyError, TypeError, ValueError):
                    # 数据格式异常时跳过该币种，不影响其余币种
                    continue
                result[ticker.symbol] = ticker
        if not result:
            raise MarketApiError(
                "Binance 返回数据为空或格式变化"
                + (f"（{'; '.join(errors)}）" if errors else ""))
        return result
