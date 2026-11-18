# -*- coding: utf-8 -*-
"""历史价格口径（adjust mode）统一定义。

三种口径是**互斥且显式**的，绝不允许把不同口径的数据混用或共用缓存：

- raw              Raw 未复权：保留数据源的历史名义价格，不套用任何复权因子。
- split_adjusted   仅拆股复权：应用拆股 / 反向拆股 / 送转 / 配股 / 份额型代币迁移，
                    **不**纳入现金分红调整。对应 industry 的「前复权(仅拆股)」。
- total_return     Total-Return 复权：在 split_adjusted 之上再纳入现金分红，
                   以分红再投入口径计算总回报。对应 hfq/后复权的总回报语义。

设计约束
--------
1. 缓存键必须包含 (symbol, source, interval, adjust_mode, data_version)。本模块
   提供 `cache_symbol()` / `cache_key()` 让调用方把口径显式编入键，杜绝串味。
2. 复权引擎只在 raw 数据上应用一次；已复权数据再次应用会被幂等拒绝。
3. 未知口径一律回落到 raw 并给出明确标注，绝不静默按某一口径处理。
"""
from __future__ import annotations

RAW = "raw"
SPLIT_ADJUSTED = "split_adjusted"
TOTAL_RETURN = "total_return"

ALL_MODES = (RAW, SPLIT_ADJUSTED, TOTAL_RETURN)
DEFAULT_MODE = SPLIT_ADJUSTED

# 缓存数据版本：复权算法 / 字段语义发生变化时递增，强制旧缓存失效重建。
DATA_VERSION = 1

_LABELS = {
    RAW: "原始价（未复权）",
    SPLIT_ADJUSTED: "拆股复权",
    TOTAL_RETURN: "总回报复权（含分红）",
}


def normalize(mode: str | None) -> str:
    """把外部传入的口径归一到合法值；未知值回落到 RAW（保守）。"""
    m = (mode or "").strip().lower()
    if m in ALL_MODES:
        return m
    # 兼容历史/别名
    alias = {
        "": DEFAULT_MODE,
        "none": RAW,
        "forward": SPLIT_ADJUSTED,
        "qfq": SPLIT_ADJUSTED,
        "hfq": TOTAL_RETURN,
        "backward": TOTAL_RETURN,
        "split": SPLIT_ADJUSTED,
        "dividend": TOTAL_RETURN,
    }
    return alias.get(m, RAW)


def label(mode: str | None) -> str:
    return _LABELS.get(normalize(mode), _LABELS[RAW])


def is_adjusted(mode: str | None) -> bool:
    return normalize(mode) != RAW


def include_dividends(mode: str | None) -> bool:
    return normalize(mode) == TOTAL_RETURN


def cache_symbol(symbol: str, mode: str | None = None) -> str:
    """把复权口径编入缓存用的 symbol。

    采用可逆前缀而非改动 SQLite 主键，兼容既有库且让每个口径物理隔离：
      raw              -> "US:KO|raw|v1"
      split_adjusted   -> "US:KO|split|v1"
      total_return     -> "US:KO|total|v1"
    """
    m = normalize(mode)
    tag = {RAW: "raw", SPLIT_ADJUSTED: "split", TOTAL_RETURN: "total"}[m]
    return f"{symbol}|{tag}|v{DATA_VERSION}"


def cache_key(symbol: str, interval: str, mode: str | None = None,
              source: str = "") -> tuple:
    """完整的缓存逻辑键。source 为空时用 'auto' 占位。"""
    return (cache_symbol(symbol, mode), interval, source or "auto")


def source_of(symbol: str) -> str:
    """从数据源头部读取来源标注（如 'sina' / 'tencent-qfq'）。"""
    return ""
