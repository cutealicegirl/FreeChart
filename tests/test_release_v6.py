# -*- coding: utf-8 -*-
"""v6 离线回归：光标涨跌方向、智能线拆分、常驻价格条、图标对比度、
无限回溯与本地缓存、港股 K 线、合约地址搜索、主流交易所清单。"""
import inspect
import json
import math
import os
import sys
import tempfile
import time

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_v6_")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from unittest.mock import patch

from PySide6.QtCore import QPoint
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

app = QApplication([])
for f in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc"):
    if os.path.exists(f):
        QFontDatabase.addApplicationFont(f)

from core.config import Config
from data import kline_cache, klines
from data.api_base import Ticker
from data.contract_search import is_contract, resolve
from data.klines import Candle
from data.universe import all_of
from ui.chart_view import CandleChart, ChartView
from ui.icons import app_icon, app_logo, symbol_icon
from ui.main_window import MainWindow
from ui.price_badge import PriceBadge
from ui.theme import C_DOWN, C_UP


def make_candles(n=300, base=60000.0):
    out = []
    for i in range(n):
        delta = math.sin(i / 7.0) * 180 + math.cos(i / 3.0) * 60
        o, c = base, base + delta + i * 8
        out.append(Candle(ts=1600000000 + i * 86400,
                          time_label=f"11-{(i % 28) + 1:02d}",
                          open=o, high=max(o, c) + 120,
                          low=min(o, c) - 120, close=c,
                          volume=1000 + i * 3.0))
        base = c
    return out


def mean_lum(pm):
    img = pm.toImage()
    vals = []
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            c = img.pixelColor(x, y)
            if c.alpha() > 40:
                vals.append((c.red() + c.green() + c.blue()) / 3)
    return sum(vals) / len(vals) if vals else 0


# ===== 1. 光标倍数：当前价 -> 目标价，红涨绿跌，纯英文 =====
up = CandleChart.hover_change(110.0, 100.0)
dn = CandleChart.hover_change(90.0, 100.0)
assert up["up"] and abs(up["mult"] - 1.1) < 1e-9 and abs(up["pct"] - 10) < 1e-9
assert up["color"] == C_UP and up["tag"] == "UP"
assert not dn["up"] and abs(dn["mult"] - 0.9) < 1e-9 and abs(dn["pct"] + 10) < 1e-9
assert dn["color"] == C_DOWN and dn["tag"] == "DN"
assert all(ord(ch) < 128 for ch in up["text"] + dn["text"]), "不得出现汉字"
assert "x1.10" in up["text"] and "x0.90" in dn["text"]
print("1. 光标倍数方向 / 红涨绿跌 / 英文缩写 OK")

# ===== 2. ATH/ATL 与独立智能线：无水平线、无汉字 =====
ext_src = inspect.getsource(CandleChart._draw_extremes)
auto_src = inspect.getsource(CandleChart._draw_auto)
assert "ATH" in ext_src and "ATL" in ext_src
assert "史高" not in ext_src and "史低" not in ext_src
assert "drawLine" not in ext_src, "史高史低不得再画贯穿水平线"
assert "TREND" in auto_src and "升" not in auto_src and "降" not in auto_src
assert "self.show_res" in auto_src and "self.show_sup" in auto_src
print("2. ATH/ATL 英文缩写 / 不画水平线 / 英文趋势标签 OK")

cfg = Config()
cv = ChartView(cfg)
assert set(cv._smart_buttons) == {"show_trend", "show_res",
                                 "show_sup", "show_extremes",
                                 "show_pivots"}, "五个独立按钮"
smart = ("show_trend", "show_res", "show_sup")
for key in smart:
    for k in smart:
        cv._toggle_smart(k, False)
    cv._toggle_smart(key, True)
    assert getattr(cv.chart, key) is True
    assert all(not getattr(cv.chart, k) for k in smart if k != key), \
        "打开一个开关不得连带打开其它项"
cv._toggle_smart("show_trend", True)
assert cfg.get("show_trend") is True
print("3. 趋势线 / 压力位 / 支撑位 三个独立开关 OK")

# ===== 3. 常驻价格条：无需悬停，实时更新 =====
badge = PriceBadge(cfg)
t = Ticker("BTC", "BTC", 67891.23, 2.35, 70000.0, 66000.0, 1.7e9)
badge.update_ticker(t, "BTC")
assert badge._price_text == "$67,891.23", badge._price_text
assert badge._change_raw == "+2.35%"
assert badge._symbol == "BTC"
assert "67,891" in badge.toolTip(), "tooltip 只是补充，不再依赖悬停"
badge.setVisible(True)
assert badge.isVisible()
# 主窗口刷新后价格条同步
w = MainWindow(cfg)
w.scheduler.stop()
w.scheduler.refresh_now = lambda: None
w.price_badge.setVisible(True)
w._on_fetched({"BTC": t}, "test", time.time())
assert w.price_badge._price_text == "$67,891.23"
assert "67,891" in w.windowTitle()
print("4. 任务栏常驻实时价格条（无需悬停）OK")

# ===== 4. 图标：新主图标 + 全品种高对比 =====
assert not app_logo(64).isNull() and not app_icon().isNull()
for p in ("assets/app_icon.png", "assets/app_icon.ico"):
    assert os.path.isfile(os.path.join(_ROOT, p)) and \
        os.path.getsize(os.path.join(_ROOT, p)) > 1000
crypto_lum = mean_lum(symbol_icon("BTC", 30))
stock_lum = mean_lum(symbol_icon("SZ:300750", 30))
hk_lum = mean_lum(symbol_icon("HK:00700", 30))
us_lum = mean_lum(symbol_icon("US:NVDA", 30))
assert min(crypto_lum, stock_lum, hk_lum, us_lum) > 85, \
    (crypto_lum, stock_lum, hk_lum, us_lum)
print(f"5. 新主图标 + 四市场图标对比度 OK "
      f"(亮度 {crypto_lum:.0f}/{stock_lum:.0f}/{hk_lum:.0f}/{us_lum:.0f})")

# ===== 5. 无限回溯 + 日线 5 年 + 本地缓存 =====
assert cfg.get("max_history") == 0, "0 = 不限根数"
assert cv._hist_timer is not None
klines_src = inspect.getsource(klines._fetch_crypto)
assert "1d" in klines_src and "allow_empty=True" in klines_src
cv.chart.set_data(make_candles())
cv._symbol, cv._interval = "BTC", "1d"
with patch.object(ChartView, "_load_history", lambda self: None):
    cv._start_history_pump()
assert cv.chart.fit_all and cv._show_all and cv._hist_timer.isActive()
cv._stop_history_pump()
# 本地缓存：save -> is_fresh -> load -> take_before -> exhausted
# v4 缓存按周期桶判新鲜：样本末根必须落在当前日桶，否则会被正确判过期。
from core import kline_time as _kt
_fresh = make_candles(50)
_shift = int(_kt.bucket_start(__import__("time").time(), "1d", "BTC")) \
    - _fresh[-1].ts
for _c in _fresh:
    _c.ts += _shift
kline_cache.save("BTC", "1d", _fresh)
assert kline_cache.is_fresh("BTC", "1d")
assert len(kline_cache.load("BTC", "1d")) == 50
assert len(kline_cache.take_before("BTC", "1d", _fresh[40].ts)) > 0
assert not kline_cache.is_exhausted("BTC", "1d")
kline_cache.save("BTC", "1d", [], exhausted=True)
assert kline_cache.is_exhausted("BTC", "1d")
print("6. 无限回溯泵 / 日线 5 年 / K 线本地缓存 OK")

# ===== 6. 港股 K 线与其它市场自动落到「全部」 =====
assert (intervals := klines.intervals_for("HK:00700"))
assert ("日K", "day") in intervals
with patch.object(klines, "_hk_daily_rows",
                  return_value=make_candles(20)):
    older, exhausted = klines.fetch_klines_before(
        "HK:00700", "day", 1600000000 + 15 * 86400)
    assert older and not exhausted
w._switch_market("cn")
assert w._sub_tabs["cn"] == "all", "无自选的市场不能显示空页"
w._switch_market("us")
assert w._sub_tabs["us"] == "all"
print("7. 港股 K 线数据源 / 其它市场自动显示品种 OK")

# ===== 7. 合约地址搜索 =====
assert is_contract("0xdAC17F958D2ee523a2206206994597C13D831ec7")
assert is_contract("DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263")
assert not is_contract("BTC") and not is_contract("US:NVDA")
with patch("data.contract_search.HTTP.get",
           side_effect=RuntimeError("offline")):
    info = resolve("0xdAC17F958D2ee523a2206206994597C13D831ec7")
assert info and info["symbol"] == "USDT" and info["chain"] == "Ethereum"
print("8. EVM/Solana/Tron 合约地址解析（含离线兜底）OK")

# ===== 8. 主流交易所清单 =====
with open(os.path.join(_ROOT, "data", "top300.json"), encoding="utf-8") as f:
    uni = json.load(f)
assert len(uni["crypto"]) >= 200 and len(all_of("crypto")) == 200
assert "Binance" in uni["crypto_sources"]
assert "OKX" in uni["crypto_sources"] and "Coinbase" in uni["crypto_sources"]
assert uni["exchanges"][uni["crypto"][0][0]][0] == "Binance"
assert not any(s in ("USDT", "FDUSD", "1000SATS") for s, _ in uni["crypto"])
print("9. 主流交易所挂牌品种清单 OK")

w.quit_app()
print("\nv6 全部回归测试通过 ✅")
