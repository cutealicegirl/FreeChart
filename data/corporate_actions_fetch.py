# -*- coding: utf-8 -*-
"""公司行为远端抓取（可选增强，失败不影响主流程）。

设计原则（对应用户需求三）：
- 优先使用可靠数据源提供的公司行为记录与复权因子；
- 抓取结果写入本地覆盖层（APPDATA/corporate_actions_overlay.json），
  带 source 出处与 confidence，可人工审计；
- **现金分红若缺少可信的除权前收盘价，不写入 verified**，而是写入
  reported 事件 -> 复权引擎只标记异常、不猜测比例；
- 任何网络/解析失败都静默跳过，主 K 线流程不依赖本模块。

当前可用源：
- 东方财富 RPT_SHAREBONUS_DET（A股分红送配，含送股/转增/派息/除权日）。
  实测 https://datacenter-web.eastmoney.com/api/data/v1/get 可访问。
- 美股拆股/港股拆股等源在部分网络环境不可达（Yahoo 403 / 腾讯 501），
  因此美股拆股以随项目发布的已核实静态登记库为准。
"""
from __future__ import annotations

import json
import os
from typing import List, Optional

from data import corporate_actions as _ca

_EM_URL = ("https://datacenter-web.eastmoney.com/api/data/v1/get"
           "?reportName=RPT_SHAREBONUS_DET&columns=ALL"
           "&filter=(SECURITY_CODE%3D%22{code}%22)&pageSize=40"
           "&sortColumns=EX_DIVIDEND_DATE&sortTypes=-1")


def _overlay_path() -> str:
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "FreeChart", "corporate_actions_overlay.json")


def _read_overlay() -> dict:
    p = _overlay_path()
    if not os.path.exists(p):
        return {"actions": [], "migrations": []}
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("actions", []); d.setdefault("migrations", [])
        return d
    except (OSError, ValueError):
        return {"actions": [], "migrations": []}


def _write_overlay(d: dict) -> bool:
    p = _overlay_path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def _http_json(url: str, timeout: float = 8.0) -> Optional[dict]:
    try:
        from data.api_base import HTTP
        resp = HTTP.get(url, timeout=timeout)
        return resp.json()
    except Exception:
        return None


def parse_eastmoney_dividend(symbol: str, payload: dict) -> List[dict]:
    """解析东财分红送配 JSON -> action dict 列表。

    只对「已实施分配且有除权除息日」的记录生成事件：
      - 送股/转增（BONUS_RATIO / BONUS_IT_RATIO，每 10 股 X 股）
        -> 份额变化可精确计算 -> verified split/bonus；
      - 纯现金派息（PRETAX_BONUS_RMB，每 10 股 X 元）
        -> 缺 prev_close，生成 reported/unknown -> 只标记不复权。
    """
    out: List[dict] = []
    data = ((payload or {}).get("result") or {}).get("data") or []
    for row in data:
        ex = row.get("EX_DIVIDEND_DATE") or ""
        ex = str(ex)[:10]
        if not ex or row.get("ASSIGN_PROGRESS") not in ("实施分配", "实施", None):
            continue
        bonus = float(row.get("BONUS_RATIO") or 0)      # 送股 每10股
        cap = float(row.get("BONUS_IT_RATIO") or 0)     # 转增 每10股
        cash = float(row.get("PRETAX_BONUS_RMB") or 0)  # 派息 每10股
        shares_per10 = bonus + cap
        impp = str(row.get("IMPL_PLAN_PROFILE") or "")
        if shares_per10 > 0:
            # 每10股送/转 X 股 -> ratio = (10+X)/10
            out.append({
                "symbol": symbol, "ex_date": ex, "kind": "bonus",
                "ratio": (10.0 + shares_per10) / 10.0,
                "source": f"东方财富分红送配：{impp}（{row.get('REPORT_DATE','')}）",
                "confidence": "verified", "source_rebased": False,
                "note": impp,
            })
        elif cash > 0:
            out.append({
                "symbol": symbol, "ex_date": ex, "kind": "unknown", "ratio": 1.0,
                "source": f"东方财富分红送配：{impp}（{row.get('REPORT_DATE','')}）",
                "confidence": "reported", "source_rebased": False,
                "note": impp + "；缺少可信除权前收盘价，按规则只标记异常、不猜测复权比例",
            })
    return out


def refresh_a_share(symbol: str, timeout: float = 8.0) -> int:
    """抓取单个 A 股的分红送配并合并进覆盖层，返回新增/更新条数。"""
    if not (symbol.startswith("SH:") or symbol.startswith("SZ:")):
        return 0
    code = symbol.split(":", 1)[1]
    payload = _http_json(_EM_URL.format(code=code), timeout=timeout)
    if not payload:
        return 0
    incoming = parse_eastmoney_dividend(symbol, payload)
    if not incoming:
        return 0
    overlay = _read_overlay()
    # 同 (symbol, ex_date, kind) 去重后覆盖
    idx = {(a.get("symbol"), a.get("ex_date"), a.get("kind")): i
           for i, a in enumerate(overlay["actions"])}
    changed = 0
    for a in incoming:
        key = (a["symbol"], a["ex_date"], a["kind"])
        if key in idx:
            overlay["actions"][idx[key]] = a
        else:
            overlay["actions"].append(a); idx[key] = len(overlay["actions"]) - 1
        changed += 1
    if changed:
        _write_overlay(overlay)
        # 让缓存因指纹变化自动失效
        try:
            _ca.set_registry(None)
        except Exception:
            pass
    return changed


def refresh_many(symbols: List[str], timeout: float = 8.0) -> dict:
    """批量刷新，返回 {symbol: 更新条数}。仅供后台/手动调用。"""
    result = {}
    for s in symbols:
        try:
            n = refresh_a_share(s, timeout=timeout)
            if n:
                result[s] = n
        except Exception:
            continue
    return result
