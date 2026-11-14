# -*- coding: utf-8 -*-
"""v28 回归：阶段 3「完整排序体系 + 筛选条件保持」。

验收点（全部离线，数值由测试显式注入，程序本身不编造）：
1. 排序维度齐全：市值 / 涨跌幅 / 成交量(额) / 价格 / 流动性 /
   上市时间 / 默认 / 自定义，且每种都有升降序；
2. 排序基于真实数值，无数据的品种一律排末尾而不是填 0；
3. ⇅ 翻转升/降序、☰ 分组菜单覆盖全部模式；
4. 搜索框作为筛选器，排序 / 切子页 / 切市场后筛选条件都保留；
5. 排序元数据层绝不编造：离线时市值/换手率为 None，
   上市年份取自内置资料库，兜底结果不覆盖已有真实数值；
6. 后台取元数据不阻塞 UI 线程。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v28_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CT_OFFLINE"] = "1"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import QApplication

from core.config import Config
from data import rank_meta
from data.api_base import Ticker
from ui.main_window import (META_SORT_MODES, REVERSE_SORT, SORT_GROUPS,
                            SORT_MODES, MainWindow)

app = QApplication([])


def pump(sec=0.08):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def set_mode(w, mode):
    idx = w.combo_sort.findData(mode)
    assert idx >= 0, f"缺少排序模式 {mode}"
    w.combo_sort.setCurrentIndex(idx)
    pump(0.04)
    return list(w._all_order.get(w._current_market()) or [])


# ============ 1. 维度齐全且兼容旧顺序 ============
modes = [m[0] for m in SORT_MODES]
assert modes[:5] == ["custom", "change_desc", "change_asc",
                     "price_desc", "amount_desc"], \
    "前 5 项顺序必须保持，v5 回归依赖 findData 索引"
for base in ("cap", "change", "amount", "price", "liquidity", "listed"):
    assert f"{base}_desc" in modes and f"{base}_asc" in modes, base
assert "default" in modes and "custom" in modes
menu_modes = [m for _g, group in SORT_GROUPS for m in group]
assert set(menu_modes) == set(modes), "排序菜单必须覆盖所有模式"
print(f"1. {len(modes)} 种排序 / 6 个维度均有升降序 / 菜单覆盖完整 OK")

# ============ 2. 基于真实数值排序、无数据排末尾 ============
cfg = Config()
cfg.set("mascot_enabled", False)
w = MainWindow(cfg)
w.scheduler.stop()
w.scheduler.refresh_now = lambda: None
w.resize(560, 900)
w.prepare_show()
key = w._current_market()
w._last_tickers.update({
    "BTC": Ticker("BTC", "Bitcoin", 100.0, 5.0, 110, 90, 1e9),
    "ETH": Ticker("ETH", "Ethereum", 50.0, -2.0, 55, 45, 5e8),
    "SOL": Ticker("SOL", "Solana", 10.0, 1.0, 12, 9, 2e8),
})
w._rank_meta.update({
    "BTC": {"cap": 2e12, "turnover": 3.5, "listed_year": 2009},
    "ETH": {"cap": 5e11, "turnover": 8.0, "listed_year": 2015},
})

cap_desc = set_mode(w, "cap_desc")
cap_asc = set_mode(w, "cap_asc")
assert cap_desc.index("BTC") < cap_desc.index("ETH"), "市值降序 BTC 应在前"
assert cap_asc.index("ETH") < cap_asc.index("BTC"), "市值升序 ETH 应在前"
liq = set_mode(w, "liquidity_desc")
assert liq.index("ETH") < liq.index("BTC"), "换手率降序 ETH 应在前"
chg = set_mode(w, "change_asc")
assert chg[:3] == ["ETH", "SOL", "BTC"], chg[:3]
px = set_mode(w, "price_desc")
assert px[:3] == ["BTC", "ETH", "SOL"], px[:3]
amt = set_mode(w, "amount_asc")
assert amt[:3] == ["SOL", "ETH", "BTC"], amt[:3]
# 没数据的品种必须排在有数据的后面
assert all(s in ("BTC", "ETH") for s in cap_desc[:2])
missing = [s for s in cap_desc[2:4]]
assert all((w._rank_meta.get(s) or {}).get("cap") is None for s in missing), \
    "无市值数据的品种应排在末尾而不是拿 0 参与比较"
print("2. 市值 / 流动性 / 涨跌 / 价格 / 成交额 升降序 + 无数据排末尾 OK")

# ============ 3. ⇅ 翻转 ============
set_mode(w, "cap_desc")
w.btn_sort_dir.click()
pump(0.04)
assert w.combo_sort.currentData() == "cap_asc"
for a, b in REVERSE_SORT.items():
    assert REVERSE_SORT.get(b) == a, "升降序映射必须双向闭合"
print("3. ⇅ 一键翻转升/降序 OK")

# ============ 4. 筛选条件保持 ============
w.edit_search.setText("BTC")
pump(0.3)
assert w._filter_text == "BTC"
assert set(w._all_order[key]) == {"BTC"}, \
    f"筛选后只应剩 BTC，实际 {w._all_order[key]}"
assert f"筛选「BTC」" in w.lbl_section.text()
set_mode(w, "price_desc")
assert w.edit_search.text() == "BTC" and w._filter_text == "BTC", \
    "排序切换不得清空筛选"
w._switch_sub("all")
pump(0.1)
assert w._filter_text == "BTC" and w.edit_search.text() == "BTC", \
    "切子页不得清空筛选"
w._switch_market("cn")
pump(0.1)
assert w._filter_text == "BTC" and w.edit_search.text() == "BTC", \
    "切市场不得清空筛选"
w._switch_market(key)
pump(0.1)
w.edit_search.clear()
pump(0.3)
assert w._filter_text == "", "主动清空才恢复全量"
print("4. 筛选在排序 / 切子页 / 切市场后保持，计数与标题同步 OK")

# ============ 5. 元数据层不编造 / 不覆盖真值 ============
offline = rank_meta.snapshot(["BTC", "US:ZZZZ"], timeout=1)
assert offline["BTC"]["cap"] is None, "离线不得编造市值"
assert offline["BTC"]["turnover"] is None, "离线不得编造换手率"
assert offline["BTC"]["listed_year"] == 2009, "内置资料库年份可用"
assert offline["US:ZZZZ"]["listed_year"] is None, \
    "资料库未收录的品种必须标注无数据"
assert offline["US:ZZZZ"]["cap"] is None
assert rank_meta.metric({"cap": None}, "cap") is None
assert rank_meta.metric({"cap": "123"}, "cap") == 123.0
old_cap = w._rank_meta["BTC"]["cap"]
w._on_rank_meta(offline)
assert w._rank_meta["BTC"]["cap"] == old_cap, \
    "离线兜底不得覆盖已取到的真实市值"
print("5. 元数据不编造 / 无数据留空 / 兜底不覆盖真值 OK")

# ============ 6. 元数据排序走后台、不阻塞 UI ============
w._rank_ready[key] = False
set_mode(w, "cap_desc")
pump(0.2)
assert w._rank_ready[key] is True, "元数据排序应触发后台批量取数"
assert not w.status.btn_retry.isVisible(), "取数期间不该弹重试"
w._close_settings_page()
print("6. 市值 / 流动性 / 上市时间后台取数不阻塞 UI OK")

# ============ 收尾 ============
w._detail_cache.clear()
pump(0.05)
from qt_exit import finish
print("\nv28 全部回归测试通过 ✅")
finish()
