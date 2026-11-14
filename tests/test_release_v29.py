# -*- coding: utf-8 -*-
"""v29 回归：阶段 4「右键移到顶部 / 置顶状态」。

验收点（离线）：
1. 右键「移到顶部」立即把品种排到首位并更新界面；
2. 市值 / 涨跌幅 / 默认等一切排序规则下，置顶品种始终优先，不冲突；
3. 切子页 / 切市场 / 行情刷新后仍保留置顶状态；
4. 支持取消置顶，取消后回到当前规则的正常顺序；
5. 多个置顶按用户置顶先后保持相对顺序，行上有「置顶」徽章；
6. 状态独立持久化到 config.json，重启后仍在；旧配置缺键安全迁移。
"""
import json
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v29_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CT_OFFLINE"] = "1"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

import ui.main_window as mw
from core.config import Config, config_path
from data.api_base import Ticker
from ui.main_window import MainWindow, market_of

app = QApplication([])


class FakeAction:
    def __init__(self, text):
        self._text = text
        self.enabled = True

    def text(self):
        return self._text

    def setEnabled(self, flag):
        self.enabled = bool(flag)

    def setData(self, value):
        self.data = value


class FakeMenu:
    """offscreen 下原生 QMenu.exec 会进事件循环卡住，用假菜单走完整分支。"""

    next_text = ""

    def __init__(self, parent=None):
        self._actions = []

    def setStyleSheet(self, _qss):
        pass

    def addAction(self, text):
        act = FakeAction(text)
        self._actions.append(act)
        return act

    def addSeparator(self):
        return None

    def actions(self):
        return list(self._actions)

    def exec(self, _pos):
        for act in self._actions:
            if FakeMenu.next_text in act.text():
                return act
        return None


def pump(sec=0.08):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def click_menu(w, symbol, keyword):
    """替换菜单类，真正走一遍右键菜单分支（含 chosen 分支判断）。"""
    FakeMenu.next_text = keyword
    orig = mw.QMenu
    mw.QMenu = FakeMenu
    try:
        w._on_row_context(symbol, QPoint(10, 10))
    finally:
        mw.QMenu = orig
    pump(0.06)


cfg = Config()
cfg.set("mascot_enabled", False)
w = MainWindow(cfg)
w.scheduler.stop()
w.scheduler.refresh_now = lambda: None
w.resize(560, 900)
w.prepare_show()
key = w._current_market()
watch = [s for s in w.rows if market_of(s) == key]
target = watch[-1]
assert len(watch) >= 3

# ============ 1. 右键置顶立即生效 ============
assert w._all_order[key][0] != target
click_menu(w, target, "移到顶部")
assert target in w.pinned
assert w._all_order[key][0] == target, \
    f"置顶后应排首位，实际 {w._all_order[key][:3]}"
assert w.rows[target]._pinned and w.rows[target].lbl_pin.isVisible(), \
    "置顶品种应有可见徽章"
print("1. 右键「移到顶部」立即重排 + 置顶徽章 OK")

# ============ 2. 不与数值排序冲突 ============
w._last_tickers.update({
    s: Ticker(s, s, 100.0 + i, 10.0 - i, 110, 90, 1e9)
    for i, s in enumerate(watch)
})
for mode in ("change_desc", "price_asc", "amount_desc", "cap_asc", "default"):
    w.combo_sort.setCurrentIndex(w.combo_sort.findData(mode))
    pump(0.05)
    assert w._all_order[key][0] == target, \
        f"{mode} 下置顶品种仍应排首位，实际 {w._all_order[key][:3]}"
print("2. 市值 / 涨跌 / 价格 / 成交额 / 默认排序下置顶均优先 OK")

# ============ 3. 切页 / 刷新后保留 ============
w._switch_sub("all")
pump(0.1)
assert w._all_order[key][0] == target
w._switch_sub("watch")
w._switch_market("cn")
pump(0.1)
w._switch_market(key)
pump(0.1)
assert w._all_order[key][0] == target, "切市场回来置顶应保留"
w._on_fetched({s: Ticker(s, s, 100.0, 1.0, 110, 90, 1e9)
               for s in watch}, "test", time.time())
pump(0.1)
assert w._all_order[key][0] == target, "行情刷新触发重排后置顶应保留"
print("3. 切子页 / 切市场 / 行情刷新后仍置顶 OK")

# ============ 4. 取消置顶 ============
click_menu(w, target, "取消置顶")
assert target not in w.pinned
assert not w.rows[target].lbl_pin.isVisible()
mode = w.combo_sort.currentData()
if mode != "custom" and mode != "default":
    vals = [w._rank_value(s, mode) for s in w._all_order[key]]
    vals = [v for v in vals if v is not None]
    if mode.endswith("_desc"):
        assert all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1)), \
            "取消置顶后应恢复纯规则排序"
    else:
        assert all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1)), \
            "取消置顶后应恢复纯规则排序"
print("4. 取消置顶恢复规则排序 OK")

# ============ 5. 多个置顶保持先后 ============
w.combo_sort.setCurrentIndex(w.combo_sort.findData("change_desc"))
pump(0.04)
a, b = watch[0], watch[1]
click_menu(w, a, "移到顶部")
click_menu(w, b, "移到顶部")
assert w.pinned == [a, b], w.pinned
assert w._all_order[key][:2] == [a, b], w._all_order[key][:3]
print("5. 多个置顶保持用户置顶先后 OK")

# ============ 6. 持久化与旧配置迁移 ============
with open(config_path(), "r", encoding="utf-8") as f:
    saved = json.load(f)
assert saved["pinned_symbols"] == [a, b]
cfg2 = Config()
assert cfg2.get("pinned_symbols") == [a, b]
w2 = MainWindow(cfg2)
w2.scheduler.stop()
w2.scheduler.refresh_now = lambda: None
w2.prepare_show()
pump(0.1)
assert w2._all_order[w2._current_market()][:2] == [a, b], \
    "重启后置顶状态应恢复"
print("6. config.json 持久化 + 重启恢复 OK")

# 模拟一份没有新键的旧配置：必须安全回退为空，且原 symbols 不变
legacy = dict(saved)
legacy.pop("pinned_symbols", None)
with open(config_path(), "w", encoding="utf-8") as f:
    json.dump(legacy, f, ensure_ascii=False)
cfg3 = Config()
assert cfg3.get("pinned_symbols") == [], "旧配置迁移应为空"
assert cfg3.get("symbols") == saved["symbols"], "不得改动原有自选顺序"
print("7. 旧配置缺键安全迁移、原自选顺序不变 OK")

# ============ 收尾 ============
w2._detail_cache.clear()
pump(0.05)
from qt_exit import finish
print("\nv29 全部回归测试通过 ✅")
finish()
