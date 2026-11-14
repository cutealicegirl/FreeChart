# -*- coding: utf-8 -*-
"""OKX 公共行情适配器。

数据源：https://www.okx.com/api/v5/market/tickers?instType=SPOT

接口一次返回全部 SPOT 交易对，本地按需要币种过滤，避免逐个请求。
24h 涨跌幅用 (最新价 - 24h开盘价) / 24h开盘价 计算（若接口直接提供
chg24h 字段则优先使用）。

实测（2026-11）：本机网络下 OKX 无法直连（代理隧道 502 / 直连被重置），
本适配器仅作为备选数据源保留，默认不启用。
"""
from typing import Dict, List

from .api_base import HTTP, MarketApi, MarketApiError, Ticker

BASE_URL = "https://www.okx.com/api/v5/market/tickers"


class OkxApi(MarketApi):
    name = "OKX"

    def fetch_tickers(self, symbols: List[str]) -> Dict[str, Ticker]:
        wanted = {f"{s}-USDT" for s in symbols}
        try:
            resp = HTTP.get(BASE_URL,
                            params={"instType": "SPOT"},
                            timeout=self.timeout)
            if resp.status_code == 429:
                raise MarketApiError("OKX API 限流 (HTTP 429)")
            resp.raise_for_status()
            body = resp.json()
        except MarketApiError:
            raise
        except Exception as e:
            raise MarketApiError(f"OKX 请求失败: {e}") from e

        code = body.get("code")
        if code != "0":
            raise MarketApiError(f"OKX 返回异常 code={code}")

        result: Dict[str, Ticker] = {}
        for item in body.get("data", []):
            inst_id = item.get("instId", "")
            if inst_id not in wanted:
                continue
            try:
                last = float(item["last"])
                # 优先使用接口自带的 24h 涨跌幅字段，缺失时用开盘价计算
                chg_raw = item.get("chg24h")
                if chg_raw not in (None, ""):
                    change_pct = float(chg_raw)
                else:
                    open_24h = float(item.get("open24h") or 0)
                    change_pct = ((last - open_24h) / open_24h * 100
                                  if open_24h else 0.0)
                ticker = Ticker(
                    symbol=inst_id.replace("-USDT", ""),
                    name=inst_id.replace("-USDT", ""),
                    last_price=last,
                    change_pct=change_pct,
                    high_24h=float(item.get("high24h") or 0),
                    low_24h=float(item.get("low24h") or 0),
                    quote_volume_24h=float(item.get("volCcy24h") or 0),
                )
            except (KeyError, ValueError, TypeError):
                continue
            result[ticker.symbol] = ticker
        if not result:
            raise MarketApiError("OKX 未返回所需币种")
        return result
