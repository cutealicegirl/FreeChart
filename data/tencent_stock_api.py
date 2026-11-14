# -*- coding: utf-8 -*-
"""腾讯股票行情适配器（A股 / 港股 / 美股）。

数据源：https://qt.gtimg.cn/q=sh600519,sz000001,hk00700,usAAPL
腾讯公开行情接口，无需 Key，国内网络直连实测可用。

统一代码体系（内部存储，冒号区分市场）：
  SH:600519  沪市A股      -> 请求码 sh600519
  SZ:000001  深市A股      -> 请求码 sz000001
  HK:00700   港股        -> 请求码 hk00700
  US:AAPL    美股        -> 请求码 usAAPL

返回字段（各市场一致）：[1]名称 [3]现价 [32]涨跌% [33]最高
[34]最低 [37]成交额（A股单位为万元，港股/美股为元）。
"""
import re
from typing import Dict, List


from .api_base import HTTP, MarketApiError, Ticker

QUOTE_URL = "https://qt.gtimg.cn/q="
# 美股请求码后缀小写化；常见交易所后缀在统一代码中剥离
_US_EXCHANGE_SUFFIX = {"OQ", "N", "AM", "PR", "UQ", "UT"}

_PREFIX_RE = re.compile(r"^(SH|SZ|HK|US):(.+)$")


def is_stock_symbol(symbol: str) -> bool:
    """判断统一代码是否为股票（带冒号市场前缀）。"""
    return _PREFIX_RE.match(symbol) is not None


def to_tencent_code(symbol: str) -> str:
    """统一代码 -> 腾讯请求码。

    实测：美股代码大小写敏感，必须为 us + 大写股票代码（如 usAAPL）；
    A股/港股为纯数字，大小写均可。
    """
    m = _PREFIX_RE.match(symbol)
    if not m:
        raise MarketApiError(f"非法股票代码: {symbol}")
    market, code = m.group(1).lower(), m.group(2)
    if market == "us":
        return f"us{code.upper()}"
    return f"{market}{code.lower()}"


class TencentStockApi:
    """A股 / 港股 / 美股行情适配器（接口与加密货币适配器同构）。"""

    name = "腾讯股票"

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def fetch_tickers(self, symbols: List[str]) -> Dict[str, Ticker]:
        """批量获取股票行情。返回 {统一代码: Ticker}。"""
        codes = [to_tencent_code(s) for s in symbols]
        try:
            resp = HTTP.get(QUOTE_URL + ",".join(codes),
                                timeout=self.timeout,
                                headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            resp.encoding = "gbk"
        except Exception as e:
            raise MarketApiError(f"腾讯行情请求失败: {e}") from e

        result: Dict[str, Ticker] = {}
        for line in resp.text.split(";"):
            line = line.strip()
            m = re.match(r"v_(\w+)=\"(.*)\"", line)
            if not m:
                continue
            qt_code, f = m.group(1), m.group(2).split("~")
            if len(f) < 38:
                continue  # 数据格式异常，跳过
            try:
                # 反推统一代码：前缀 + 腾讯代码
                market = qt_code[:2].upper()
                raw = qt_code[2:]
                if market == "US":
                    # aapl.oq -> AAPL（剥离交易所后缀）
                    parts = raw.split(".")
                    if len(parts) == 2 \
                            and parts[1].upper() in _US_EXCHANGE_SUFFIX:
                        raw = parts[0]
                symbol = f"{market}:{raw.upper()}"
                amount = float(f[37] or 0)
                if market in ("SH", "SZ"):
                    amount *= 1e4  # A股成交额单位是万元 -> 元
                result[symbol] = Ticker(
                    symbol=symbol,
                    name=f[1],
                    last_price=float(f[3] or 0),
                    change_pct=float(f[32] or 0),
                    high_24h=float(f[33] or 0),
                    low_24h=float(f[34] or 0),
                    quote_volume_24h=amount,
                )
            except (ValueError, IndexError):
                continue  # 单条解析失败不影响其余
        if not result:
            raise MarketApiError("腾讯行情返回数据为空或格式变化")
        return result
