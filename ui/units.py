# -*- coding: utf-8 -*-
"""价格货币单位。

列表行、图表价格轴、当前价气泡、任务栏价格条统一走这里，避免
"数字有了但看不出是美元还是人民币"的问题：

  crypto -> $      （币安 / OKX 全部按 USDT 计价，与美元 1:1 锚定）
  us     -> $
  cn     -> ¥
  hk     -> HK$

单位只加前缀、不加空格，紧凑且不会把价格挤出布局。
"""

MARKET_UNIT = {
    "crypto": "$",
    "us": "$",
    "cn": "¥",
    "hk": "HK$",
}

# 全局开关（设置里可关）；各行/图表读取同一个值，切换后即时生效
ENABLED = True


def set_enabled(flag: bool):
    global ENABLED
    ENABLED = bool(flag)


def market_of(symbol: str) -> str:
    if symbol.startswith(("SH:", "SZ:")):
        return "cn"
    if symbol.startswith("HK:"):
        return "hk"
    if symbol.startswith("US:"):
        return "us"
    return "crypto"


def unit_of(symbol: str) -> str:
    """该品种计价货币符号。"""
    return MARKET_UNIT.get(market_of(symbol or ""), "$")


def with_unit(text: str, symbol: str, enabled=None) -> str:
    """给已经格式化好的价格文本加货币前缀。

    enabled 传 None 表示跟随全局开关（ENABLED），传 True/False 可单独覆盖。
    """
    if enabled is None:
        enabled = ENABLED
    if not enabled or not text:
        return text
    prefix = unit_of(symbol)
    if text.startswith(prefix):
        return text
    return prefix + text
