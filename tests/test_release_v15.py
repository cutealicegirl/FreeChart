# -*- coding: utf-8 -*-
"""v15 离线回归：市值排序清单 / 多主题热切换 / 多套应用图标 / 货币单位 /
图表字号与价格轴 / 支撑压力分级配色 / 秒级实时行情 / 看板娘 / 合约地址。"""
import os
import random
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_v15_")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

app = QApplication([])

from core.config import Config, DEFAULTS
from core.live_feed import LiveFeed
from data import universe
from data.contract_search import is_contract
from data.klines import Candle
from ui import units
from ui.chart_view import CandleChart
from ui.icons import (app_icon_ico_path, app_icon_keys, app_icon_pixmap,
                      set_app_icon_key)
from ui.mascot import MascotWindow, default_mascot_path
from ui.settings_dialog import SettingsDialog
from ui.theme import (THEMES, current_theme, set_theme, tooltip_qss)

# ===== 1. 各市场「全部」页数量与市值降序 =====
assert universe.count_of("crypto") == 200, universe.count_of("crypto")
assert universe.count_of("cn") == 100, universe.count_of("cn")
assert universe.count_of("hk") == 200, universe.count_of("hk")
assert universe.count_of("us") == 500, universe.count_of("us")
crypto = universe.all_of("crypto")
assert {"BTC", "ETH", "BNB", "SOL", "XRP"} <= set(crypto[:12]), crypto[:12]
assert crypto[0] == "BTC", crypto[:3]
cn = universe.all_of("cn")
assert any(s in cn[:25] for s in ("SH:601398", "SH:601939")), "A股应有大行"
hk = universe.all_of("hk")
assert "HK:00700" in hk[:12], hk[:12]
us = universe.all_of("us")
assert {"US:AAPL", "US:NVDA", "US:MSFT"} <= set(us[:12]), us[:12]
assert len(cn) == len(set(cn)) and len(us) == len(set(us))
print("1. 市值排序清单 200/100/200/500 OK")

# ===== 2. 配置默认值包含外观 / 实时 / 看板娘 =====
for key in ("theme", "app_icon", "chart_font_scale", "show_currency",
            "live_feed", "live_interval_ms", "mascot_enabled",
            "mascot_image", "mascot_scale", "mascot_opacity",
            "mascot_click_through", "mascot_on_top"):
    assert key in DEFAULTS, key
cfg = Config()
assert cfg.get("theme") == "binance"
assert cfg.get("chart_font_scale") == 120
assert cfg.get("show_currency") is True
print("2. 配置默认值 OK")

# ===== 3. 主题热切换：常量广播 + 高对比 tooltip =====
import ui.chart_view as chart_mod

assert set(THEMES) == {"binance", "midnight", "oled", "light", "cyber", "sepia"}
name, old, new = set_theme("oled")
assert name == "oled" and current_theme() == "oled"
assert chart_mod.C_UP == THEMES["oled"]["up"], chart_mod.C_UP
# from ui.theme import C_UP 的模块（ui.icons）里那份副本也必须同步
import ui.icons as icons_mod
assert icons_mod.C_UP == THEMES["oled"]["up"], icons_mod.C_UP
tip = tooltip_qss()
assert "QToolTip" in tip and "#07080a" in tip and "#ffffff" in tip, tip
assert "2px solid" in tip
name, old, new = set_theme("light")
assert "#ffffff" in tooltip_qss()
assert chart_mod.C_UP == THEMES["light"]["up"]
set_theme("binance")
assert current_theme() == "binance"
print("3. 6 套主题热切换 / Tooltip 高对比 OK")

# ===== 4. 多套应用图标 =====
keys = app_icon_keys()
assert len(keys) >= 6, keys
for key, label in keys:
    assert label, key
    assert os.path.isfile(app_icon_ico_path(key)), key
    pm = app_icon_pixmap(32, key)
    assert not pm.isNull() and pm.width() == 32, key
assert set_app_icon_key("neon") == "neon"
assert set_app_icon_key("not-exist") == "classic"
print("4. 6 套应用图标 OK")

# ===== 5. 货币单位 =====
assert units.unit_of("BTC") == "$"
assert units.unit_of("US:AAPL") == "$"
assert units.unit_of("SH:600519") == "¥"
assert units.unit_of("SZ:000001") == "¥"
assert units.unit_of("HK:00700") == "HK$"
assert units.with_unit("73,000.00", "BTC") == "$73,000.00"
assert units.with_unit("1,439.00", "HK:00700") == "HK$1,439.00"
units.set_enabled(False)
assert units.with_unit("1,439.00", "SH:600519") == "1,439.00"
units.set_enabled(True)
print("5. 货币单位 $ / ¥ / HK$ OK")


# ===== 6. 图表字号 / 价格轴宽度 / 时间轴不重叠 =====
def make(n, seed=5, step=14400):
    r = random.Random(seed)
    out = []
    price = 100.0
    for i in range(n):
        price *= 1 + (r.random() - 0.48) * 0.02
        out.append(Candle(ts=1600000000 + i * step, time_label=str(i),
                          open=price, high=price * 1.01,
                          low=price * 0.99, close=price, volume=10))
    return out


chart = CandleChart()
chart.resize(900, 640)
base_margin = chart._margin_r
base_px = chart._axis_px(10)
chart.set_font_scale(140)
assert chart.font_scale == 1.4
assert chart._margin_r > base_margin, (chart._margin_r, base_margin)
assert chart._axis_px(10) > base_px, (chart._axis_px(10), base_px)
chart.unit_prefix = "¥"
assert chart._money("1,439.00") == "¥1,439.00"
chart.show_currency = False
assert chart._money("1,439.00") == "1,439.00"
chart.show_currency = True

chart.set_data(make(260))
chart._view_count = 260
chart._pan = 0
g = chart._geom()
labels = chart._time_axis_labels(g)
assert len(labels) >= 2, labels
rects = [r for r, _t, _x in labels]
for a, b in zip(rects, rects[1:]):
    assert a.right() <= b.left() + 1, (a, b)
print("6. 图表字号放大 / 价格轴加宽 / 时间轴不重叠 OK")

# ===== 7. 支撑压力分级：近期有效 vs 历史失效 =====
levels_bars = []
for i in range(120):
    base = 200.0 - i * 0.5              # 单边下跌
    high = base + 2.0
    if i >= 105:
        high = 152.0                     # 最近 15 根反复触及同一个压力位
    if i == 20:
        high = 210.0                     # 很早以前的一个高点（已失效）
    levels_bars.append(Candle(ts=1600000000 + i * 3600, time_label=str(i),
                              open=base, high=high, low=base - 2.0,
                              close=base - 1.0, volume=10))
chart2 = CandleChart()
chart2.resize(900, 640)
auto = chart2._compute_auto(levels_bars)
assert auto, "样本不足"
res = auto["res"]
assert res, res
assert any(d["recent"] for d in res), res
assert any(not d["recent"] for d in res), res
assert all(isinstance(d["recent"], bool) for d in res + auto["sup"])
print("7. 支撑压力近期/历史分级 OK")

# ===== 8. 秒级实时行情（桩行情源，无网络）=====
class _StubManager:
    def __init__(self):
        self.calls = 0

    def fetch_quote(self, symbol):
        self.calls += 1
        return 123.5, 1.25


feed = LiveFeed(_StubManager(), interval_ms=400)
got = []
feed.tick.connect(lambda s, p, c: got.append((s, p, c)))
feed.set_symbol("BTC")
assert feed._timer.isActive()
for _ in range(30):
    app.processEvents()
    if got:
        break
    from PySide6.QtTest import QTest
    QTest.qWait(50)
assert got and got[0][0] == "BTC" and abs(got[0][1] - 123.5) < 1e-9, got
feed.set_symbol("")
assert not feed._timer.isActive()
feed.set_enabled(False)
feed.shutdown()
print("8. 秒级实时行情（单品种轮询）OK")

# ===== 9. 看板娘（默认关闭 / 开启 / 自定义图片回退）=====
mascot_cfg = Config()
mascot_cfg.set("mascot_enabled", False)
m = MascotWindow(mascot_cfg)
m.apply_config()
assert not m.isVisible()
assert os.path.isfile(default_mascot_path())
mascot_cfg.set("mascot_enabled", True)
m.set_image(os.path.join(_ROOT, "no_such_mascot.png"))
assert not m._current_pixmap().isNull(), "图片不存在时应回退内置形象"
m.apply_config()
assert m.width() > 0 and m.height() > 0
m.hide()
print("9. 看板娘开关 / 自定义图片回退 OK")

# ===== 10. 合约地址识别 =====
assert is_contract("0x6982508145454ce325ddbe47a25d4ec3d2311933")
assert is_contract("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
assert is_contract("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
assert not is_contract("BTC")
assert not is_contract("0x123")
print("10. 合约地址识别 OK")


# ===== 11. 设置对话框：外观项可读写 =====
class _StubMarket:
    def list_sources(self):
        return ["Binance", "OKX"]


class _StubWindow:
    def __init__(self, config):
        self.config = config
        self.market = _StubMarket()


dlg = SettingsDialog(_StubWindow(Config()))
s = dlg.get_settings()
assert s["theme"] in THEMES, s["theme"]
assert s["app_icon"] in dict(app_icon_keys()), s["app_icon"]
assert 100 <= s["chart_font_scale"] <= 180
assert 400 <= s["live_interval_ms"] <= 3000
assert "mascot_enabled" in s and "mascot_image" in s
assert s["show_currency"] in (True, False)
dlg.deleteLater()
print("11. 设置对话框外观项 OK")

# ===== 12. 周期预加载在无标的时不发请求 =====
from ui.chart_view import ChartView

cv = ChartView(Config())
cv._symbol = ""
cv._prefetch_intervals()          # 不应抛异常、不应起线程
assert cv._prefetch_threads == []
cv.stop_prefetch()
print("12. 周期预加载空转安全 OK")

print("\nALL v15 CHECKS PASSED")
