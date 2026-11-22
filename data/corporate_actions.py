# -*- coding: utf-8 -*-
"""公司行为数据模型与已核实事件登记库。

本模块只描述"发生了什么"，不负责如何改价（改价在 price_adjustment.py）。
设计原则（对应用户需求三「复权机制与数据架构」）：

1. 明确区分事件类型：拆股 / 反向拆股 / 现金分红 / 送股 / 配股 /
   代币迁移 / 代币面额调整 / 无法确认的异常事件。
2. 每个事件都带 source（出处）与 confidence（verified / reported /
   unverified）。**只有 verified 且比例可确定的事件才会被复权引擎采用**；
   unverified 一律保留原始数据并标记异常，绝不猜测比例。
3. 比例语义统一为 ratio = 除权后每 1 份旧份额换到的新份额数：
     - 1 拆 4        -> ratio = 4
     - 10 合 1(反向) -> ratio = 0.1
     - 1:1 代币迁移  -> ratio = 1
   价格前复权因子 = 1 / ratio；份额成交量因子 = ratio。

登记库 corporate_actions.json 是随项目发布的、可人工审计的静态数据；
远端抓取（如东财分红送配）只会写入"本地覆盖层"，且必须带出处。
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


def _registry_path() -> str:
    """兼容源码运行与 PyInstaller 冻结运行（与 data/universe.py 同惯例）。"""
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        p = os.path.join(bundle, "data", "corporate_actions.json")
        if os.path.exists(p):
            return p
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "corporate_actions.json")


_REGISTRY_FILE = _registry_path()


class ActionType(str, Enum):
    SPLIT = "split"                    # 拆股（1 拆 N，ratio>1）
    REVERSE_SPLIT = "reverse_split"    # 反向拆股（N 合 1，ratio<1）
    DIVIDEND = "dividend"              # 现金分红
    BONUS = "bonus"                    # 送股
    RIGHTS = "rights"                  # 配股
    TOKEN_MIGRATION = "token_migration"  # 代币迁移 / 合约置换（1:1 或多换少）
    TOKEN_REDENOM = "token_redenom"    # 代币面额调整（redenomination）
    UNKNOWN = "unknown"                # 异常事件：比例未知 -> 只标记不复权


# 会改变份额数量（因此需要调整成交量）的事件
SHARE_CHANGE_TYPES = {
    ActionType.SPLIT, ActionType.REVERSE_SPLIT,
    ActionType.BONUS, ActionType.RIGHTS,
    ActionType.TOKEN_MIGRATION, ActionType.TOKEN_REDENOM,
}


@dataclass(frozen=True)
class CorporateAction:
    """一条公司行为记录。字段全部可 JSON 序列化，便于审计与远端合并。"""
    symbol: str
    ex_date: str                 # YYYY-MM-DD，除权/迁移生效日
    kind: ActionType
    ratio: float = 1.0           # 新份额/旧份额
    prev_close: Optional[float] = None    # 除权前一交易日收盘（分红因子用）
    cash_per_share: Optional[float] = None  # 每股现金分红（税前）
    source: str = ""             # 出处（公司公告 / 权威媒体 / 交易所）
    confidence: str = "verified"  # verified | reported | unverified
    source_rebased: bool = False  # 数据源是否已自行重算历史（加密迁移常见）
    note: str = ""

    # ---- 派生因子 ----
    @property
    def usable(self) -> bool:
        """是否可以安全地用于复权。"""
        if self.confidence != "verified" or self.kind == ActionType.UNKNOWN:
            return False
        if self.kind in SHARE_CHANGE_TYPES:
            return self.ratio > 0
        if self.kind == ActionType.DIVIDEND:
            return bool(self.prev_close and 0 < self.cash_per_share < self.prev_close)
        return False

    @property
    def price_factor(self) -> float:
        """前复权价格乘数（作用于 ex_date 之前的 K 线）。"""
        if self.kind in SHARE_CHANGE_TYPES:
            return 1.0 / self.ratio
        if self.kind == ActionType.DIVIDEND and self.usable:
            return (self.prev_close - self.cash_per_share) / self.prev_close
        return 1.0

    @property
    def volume_factor(self) -> float:
        """成交量乘数：只有份额数量变化才调整；纯现金分红不影响成交量。"""
        if self.kind in SHARE_CHANGE_TYPES:
            return self.ratio
        return 1.0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "ex_date": self.ex_date,
            "kind": self.kind.value, "ratio": self.ratio,
            "prev_close": self.prev_close, "cash_per_share": self.cash_per_share,
            "source": self.source, "confidence": self.confidence,
            "source_rebased": self.source_rebased, "note": self.note,
        }

    @staticmethod
    def from_dict(d: dict) -> "CorporateAction":
        return CorporateAction(
            symbol=d["symbol"], ex_date=d["ex_date"],
            kind=ActionType(d.get("kind", "unknown")),
            ratio=float(d.get("ratio", 1.0)),
            prev_close=d.get("prev_close"), cash_per_share=d.get("cash_per_share"),
            source=d.get("source", ""), confidence=d.get("confidence", "verified"),
            source_rebased=bool(d.get("source_rebased", False)),
            note=d.get("note", ""),
        )


# ---------------- 代码/代币迁移映射 ----------------
@dataclass(frozen=True)
class SymbolMigration:
    """旧代码 -> 新代码，用于把迁移前的历史接续到当前代码。"""
    old_symbol: str
    new_symbol: str
    effective_date: str       # 新代码启用日
    ratio: float = 1.0        # 旧份额换新份额
    source_rebased: bool = True   # 数据源是否已用新代码重算历史
    source: str = ""
    confidence: str = "verified"


# ---------------- 登记库 ----------------
class ActionRegistry:
    """合并静态登记库与本地覆盖层；按标的索引，按日期排序。"""

    def __init__(self, path: str = _REGISTRY_FILE,
                 overlay: Optional[str] = None):
        self.path = path
        self.overlay = overlay or self._default_overlay()
        self._actions: Dict[str, List[CorporateAction]] = {}
        self._migrations: List[SymbolMigration] = []
        self._load()

    @staticmethod
    def _default_overlay() -> str:
        base = os.getenv("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "FreeChart", "corporate_actions_overlay.json")

    def _load(self):
        self._actions, self._migrations = {}, []
        for p in (self.path, self.overlay):
            if not p or not os.path.exists(p):
                continue
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            for d in data.get("actions", []):
                try:
                    a = CorporateAction.from_dict(d)
                except (KeyError, ValueError):
                    continue
                self._actions.setdefault(a.symbol, []).append(a)
            for d in data.get("migrations", []):
                try:
                    self._migrations.append(SymbolMigration(
                        old_symbol=d["old_symbol"], new_symbol=d["new_symbol"],
                        effective_date=d["effective_date"],
                        ratio=float(d.get("ratio", 1.0)),
                        source_rebased=bool(d.get("source_rebased", True)),
                        source=d.get("source", ""),
                        confidence=d.get("confidence", "verified")))
                except (KeyError, ValueError):
                    continue
        for lst in self._actions.values():
            lst.sort(key=lambda a: a.ex_date)
        # 覆盖层同 (symbol, ex_date, kind) 去重，后写覆盖先写
        dedup: Dict[str, List[CorporateAction]] = {}
        for sym, lst in self._actions.items():
            seen = {}
            for a in lst:
                seen[(a.ex_date, a.kind.value)] = a
            dedup[sym] = sorted(seen.values(), key=lambda x: x.ex_date)
        self._actions = dedup

    # ---- 查询 ----
    def actions_for(self, symbol: str) -> List[CorporateAction]:
        return list(self._actions.get(symbol, []))

    def usable_actions_for(self, symbol: str) -> List[CorporateAction]:
        """只返回可安全复权的事件；source_rebased 的不参与改价。"""
        return [a for a in self.actions_for(symbol)
                if a.usable and not a.source_rebased]

    def migrations_for(self, symbol: str) -> List[SymbolMigration]:
        return [m for m in self._migrations
                if m.new_symbol == symbol and m.confidence == "verified"]

    def all_symbols(self) -> List[str]:
        return sorted(self._actions)

    def unknown_events_for(self, symbol: str) -> List[CorporateAction]:
        """无法确认比例的事件：调用方应保留原始数据并标记异常。"""
        return [a for a in self.actions_for(symbol) if not a.usable]

    def fingerprint(self, symbol: str) -> str:
        """事件指纹：事件或比例变化时用于让缓存失效。"""
        items = self.actions_for(symbol)
        if not items:
            return "none"
        import hashlib
        raw = "|".join(f"{a.ex_date}:{a.kind.value}:{a.ratio}:"
                       f"{a.prev_close}:{a.cash_per_share}:{a.confidence}"
                       for a in items)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _date_of_ts(ts: float) -> str:
        try:
            return _dt.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d")
        except (ValueError, TypeError, OSError, OverflowError):
            return ""

    def verified_event_near(self, symbol: str, ts: float,
                            window_days: int = 5) -> Optional[CorporateAction]:
        """查找某根 K 线附近是否有已核实事件（用于区分真实跳空与异常）。"""
        d = self._date_of_ts(ts)
        if not d:
            return None
        try:
            dt = _dt.datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            return None
        for a in self.actions_for(symbol):
            try:
                ad = _dt.datetime.strptime(a.ex_date, "%Y-%m-%d").date()
            except ValueError:
                continue
            if abs((ad - dt).days) <= window_days:
                return a
        return None


# 全局单例（惰性创建，便于测试注入临时 registry）
_REGISTRY: Optional[ActionRegistry] = None


def get_registry() -> ActionRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ActionRegistry()
    return _REGISTRY


def set_registry(reg: Optional[ActionRegistry]):
    """测试注入用；传 None 恢复默认单例。"""
    global _REGISTRY
    _REGISTRY = reg
