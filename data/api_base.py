# -*- coding: utf-8 -*-
"""行情适配器基类。

所有数据源适配器继承 MarketApi，实现 fetch_tickers 接口。
界面层不接触任何 API 地址，只通过本基类与市场数据交互。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Ticker:
    """单个币种/证券的行情快照。"""
    symbol: str                 # 统一代码：加密货币如 BTC；股票如 SH:600519
    name: str = ""              # 显示名称（如 贵州茅台 / Bitcoin）
    last_price: float = 0.0     # 最新价
    change_pct: float = 0.0     # 当日/24h 涨跌幅（百分数，如 -0.96 表示 -0.96%）
    high_24h: float = 0.0       # 当日/24h 最高价
    low_24h: float = 0.0        # 当日/24h 最低价
    quote_volume_24h: float = 0.0  # 当日/24h 成交额（计价货币）


class MarketApiError(Exception):
    """行情请求失败的统一异常（网络错误、限流、返回异常等）。"""


# 全局共享 HTTP 会话：trust_env=False 强制绕过系统代理/代理环境变量，
# 避免本机代理软件拦截行情与搜索接口（实测代理会导致腾讯接口 502）。
import requests  # noqa: E402

HTTP = requests.Session()
HTTP.trust_env = False
HTTP.headers["User-Agent"] = "Mozilla/5.0"


class MarketApi(ABC):
    """行情数据源适配器基类。"""

    # 数据源显示名（界面上标注行情来源用）
    name: str = "未命名"
    # 该数据源支持的统一币种代码列表（None 表示不做限制）
    supported: List[str] | None = None

    def __init__(self, timeout: float = 10.0):
        # trust_env=False：不使用系统代理，避免本机代理软件干扰直连
        self.timeout = timeout

    @abstractmethod
    def fetch_tickers(self, symbols: List[str]) -> Dict[str, Ticker]:
        """批量获取行情。

        返回 {币种代码: Ticker}；不支持的币种直接跳过。
        任何失败抛出 MarketApiError，由上层统一处理。
        """
        raise NotImplementedError

    def filter_supported(self, symbols: List[str]) -> List[str]:
        """返回该数据源实际支持的币种子集。"""
        if self.supported is None:
            return list(symbols)
        return [s for s in symbols if s in self.supported]
