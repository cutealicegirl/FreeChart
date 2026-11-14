# -*- coding: utf-8 -*-
"""v33 回归：MA / EMA 可设参数、天数、周期作用域，新增 EMA 均线。

验收点（全部离线，不联网、不启动刷新线程）：
1. 参数模型默认值、脏数据清洗、天数越界钳制、重复天数去重；
2. 「全部周期 / 仅当前周期」作用域：周期覆盖只影响自己，未覆盖字段
   回落全局；恢复默认不误伤其它周期；
3. EMA 计算与 MA 不同且数值可验证；
4. CandleChart 按参数绘制：改天数后无需重新联网即重算，BOLL / MACD
   参数与副图标题同步，绘制过程不抛异常；
5. ChartView 有 EMA 开关与「⚙ 参数」入口，参数面板可打开 / 应用 /
   关闭，应用后配置落盘且图表立即生效；
6. 切换 K 线周期时自动换用该周期的参数；
7. 设置页含 EMA 复选框并写回 show_ema；
8. 旧配置缺 indicator_params 键时安全回退到默认参数。
"""
import math
import os
import sys
import tempfile
import types

_TMP = tempfile.mkdtemp(prefix="ct_v33_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CT_OFFLINE"] = "1"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import QApplication

from core import indicator_params as ip
from core.config import Config, DEFAULTS
from data.klines import Candle
from ui.chart_view import (CandleChart, ChartView, MA_COLORS,
                           _ema_series, ma_series)

app = QApplication([])
FAILS = []
CHECKS = [0]


def ok(name, cond, extra=""):
    CHECKS[0] += 1
    print(("PASS " if cond else "FAIL ") + name +
          ("  " + str(extra) if extra else ""))
    if not cond:
        FAILS.append(name)


def candles(n=220):
    out = []
    for i in range(n):
        base = 100 + 12 * math.sin(i / 13.0) + i * 0.08
        out.append(Candle(ts=1700000000 + i * 900,
                          time_label=f"{i:02d}", open=base - 0.4,
                          high=base + 1.1, low=base - 1.3,
                          close=base, volume=100 + i))
    return out


BARS = candles()

# ---- 1. 参数模型 ----
d = ip.default_params()
ok("1. 默认 MA 天数", [x["period"] for x in d["ma"]] == [5, 10, 20, 30])
ok("1. 默认 EMA 天数", [x["period"] for x in d["ema"]] == [12, 26, 50, 99]
   and d["ema"][3]["enabled"] is False)
ok("1. 默认 BOLL/MACD", d["boll"] == {"period": 20, "k": 2.0}
   and d["macd"] == {"fast": 12, "slow": 26, "signal": 9})
ok("1. 每条最多 4 条线", len(ip.normalize({
    "ma": [{"period": 7, "enabled": True}] * 9})["ma"]) == ip.MAX_LINES)
ok("1. 天数越界被钳制", ip.normalize({
    "ma": [{"period": -3, "enabled": True}, {"period": 99999,
                                             "enabled": True}]})["ma"][0]
   == {"period": ip.MIN_PERIOD, "enabled": True}
   and ip.normalize({"ema": [{"period": 99999, "enabled": True}]})
   ["ema"][0]["period"] == ip.MAX_PERIOD)
ok("1. 脏数据不抛异常", ip.normalize({
    "ma": "oops", "ema": [None, 3, {"period": "abc"}],
    "boll": {"k": "bad"}, "macd": None})["boll"]["k"] == 2.0)
ok("1. 慢线小于快线自动调整", ip.normalize({
    "macd": {"fast": 30, "slow": 5, "signal": 9}})["macd"]["slow"] == 31)
ok("1. 重复天数去重", ip.enabled_periods({
    "ma": [{"period": 20, "enabled": True},
           {"period": 20, "enabled": True},
           {"period": 20, "enabled": False},
           {"period": 60, "enabled": True}]}, "ma") == [20, 60])
ok("1. 旧配置缺键安全回退", "indicator_params" in DEFAULTS
   and Config().get("indicator_params") == {}
   and ip.params_for(Config(), "1h") == d)

# ---- 2. 周期作用域 ----
cfg = Config()
cfg.set("show_ema", True)
global_p = ip.default_params()
global_p["ma"] = [{"period": 7, "enabled": True},
                  {"period": 21, "enabled": True},
                  {"period": 60, "enabled": False},
                  {"period": 120, "enabled": False}]
global_p["boll"]["k"] = 3.0
ip.write_params(cfg, ip.SCOPE_ALL, global_p)
# 模拟「只在 1h 里改 MA 天数」：其余字段与全局保持一致
hour_p = ip.params_for(cfg, "1h")
hour_p["ma"] = [{"period": 20, "enabled": True},
                {"period": 60, "enabled": True},
                {"period": 120, "enabled": False},
                {"period": 200, "enabled": False}]
ip.write_params(cfg, "1h", hour_p)
g = ip.params_for(cfg, "1d")
h = ip.params_for(cfg, "1h")
ok("2. 全局参数对其它周期生效",
   [x["period"] for x in g["ma"]] == [7, 21, 60, 120]
   and g["boll"]["k"] == 3.0)
ok("2. 周期覆盖只影响自己",
   [x["period"] for x in h["ma"]] == [20, 60, 120, 200])
ok("2. 周期未覆盖字段回落全局", h["boll"]["k"] == 3.0
   and h["macd"] == ip.DEFAULT_MACD)
ok("2. 参数已落盘", isinstance(Config().get("indicator_params"), dict)
   and "1h" in Config().get("indicator_params"))
ok("2. 周期只保存差异字段",
   set(Config().get("indicator_params")["1h"]) == {"ma"})
gp2 = ip.params_for(cfg, "1d")
gp2["boll"]["k"] = 1.8
ip.write_params(cfg, ip.SCOPE_ALL, gp2)
ok("2. 全局改动传导到周期未覆盖字段",
   ip.params_for(cfg, "1h")["boll"]["k"] == 1.8
   and ip.params_for(cfg, "1h")["ma"][0]["period"] == 20)
gp3 = ip.params_for(cfg, "1d")
gp3["boll"]["k"] = 3.0
ip.write_params(cfg, ip.SCOPE_ALL, gp3)
ip.reset_scope(cfg, "1h")
ok("2. 恢复周期默认不误伤全局",
   ip.params_for(cfg, "1h")["ma"][0]["period"] == 7
   and ip.params_for(cfg, "1d")["boll"]["k"] == 3.0)

# ---- 3. EMA 算法 ----
closes = [1.0, 2.0, 3.0, 4.0, 5.0]
e3 = _ema_series(closes, 3)
ok("3. EMA 预热段为空", e3[:2] == [None, None] and e3[2] == 2.0)
ok("3. EMA 递推正确", e3[3] == 3.0 and e3[4] == 4.0)
ok("3. EMA 与 MA 不同", ma_series(closes, 3)[-1] == 4.0
   and e3[-1] != ma_series(closes, 4)[-1])
ok("3. 数据不足时全为空", _ema_series([1, 2], 5) == [None, None])

# ---- 4. CandleChart 绘制 ----
c = CandleChart()
c.resize(820, 520)
c.set_data(BARS)
ok("4. 默认 MA 缓存键", sorted(c._ind["ma"]) == [5, 10, 20, 30])
ok("4. 默认 EMA 缓存键", sorted(c._ind["ema"]) == [12, 26, 50])
ok("4. MA5 数值正确",
   abs(c._ind["ma"][5][4] - sum(x.close for x in BARS[:5]) / 5) < 1e-9)
ok("4. EMA 序列长度对齐", all(len(s) == len(BARS) for s in
                            c._ind["ema"].values()))
ok("4. 默认 MACD 标题", c.macd_title() == "MACD(12,26,9)")
p2 = ip.default_params()
p2["ma"] = [{"period": 8, "enabled": True},
            {"period": 55, "enabled": True},
            {"period": 9, "enabled": False},
            {"period": 10, "enabled": False}]
p2["ema"] = [{"period": 34, "enabled": True},
             {"period": 7, "enabled": False},
             {"period": 50, "enabled": False},
             {"period": 99, "enabled": False}]
p2["boll"] = {"period": 30, "k": 1.5}
p2["macd"] = {"fast": 5, "slow": 10, "signal": 4}
c.set_indicator_params(p2)
ok("4. 改参数无需重新 set_data 即重算",
   sorted(c._ind["ma"]) == [8, 55] and sorted(c._ind["ema"]) == [34],
   sorted(c._ind["ma"]))
ok("4. 停用线不绘制",
   sum(1 for l in c.ma_lines if l["enabled"]) == 2)
ok("4. BOLL 周期生效", len([v for v in c._ind["boll"][1]
                           if v is not None]) == len(BARS) - 30 + 1)
ok("4. MACD 标题随参数", c.macd_title() == "MACD(5,10,4)")
ok("4. 旧 MA_COLORS 仍可用", set(MA_COLORS) == {5, 10, 20, 30})
try:
    c.show_ma = c.show_ema = c.show_boll = c.show_macd = c.show_vol = True
    pix = c.grab()
    drawn = not pix.isNull() and pix.width() > 0
except Exception as exc:                     # noqa: BLE001
    drawn = False
    print("   paint error:", exc)
ok("4. 全指标开启时绘制不崩", drawn)
c.set_indicator_params(ip.default_params())   # 复位，避免影响后续

# ---- 5/6. ChartView 与参数面板 ----
cfg2 = Config()
cfg2.set("show_ema", False)
ip.write_params(cfg2, ip.SCOPE_ALL, global_p)
ip.write_params(cfg2, "1h", hour_p)
cv = ChartView(cfg2)
cv.resize(420, 760)
cv.show()
ok("5. 工具栏有 EMA 开关",
   ("EMA", "show_ema") in cv.MAIN_INDICATORS
   and "show_ema" in cv._indicator_buttons)
ok("5. EMA 开关从配置读取",
   cv.chart.show_ema is False
   and cv._indicator_buttons["show_ema"].isChecked() is False)
ok("5. 有「⚙ 参数」入口", hasattr(cv, "btn_indicator_settings")
   and cv.btn_indicator_settings.minimumHeight() >= 44)
ok("5. 15m 使用全局参数",
   [l["period"] for l in cv.chart.ma_lines] == [7, 21, 60, 120])
cv._interval = "1h"
cv._apply_indicator_params()
ok("6. 切到 1h 自动换周期参数",
   [l["period"] for l in cv.chart.ma_lines] == [20, 60, 120, 200])
cv._interval = "15m"
cv._apply_indicator_params()
ok("6. 切回 15m 恢复全局参数",
   [l["period"] for l in cv.chart.ma_lines][0] == 7)

sheet = cv.indicator_sheet
sheet.set_interval("15m", "15分")
cv._open_indicator_sheet()
ok("5. 参数面板可打开", sheet.isVisible()
   and sheet.combo_scope.count() == 2)
ok("5. 面板载入当前作用域参数",
   sheet._ma_rows[0][1].value() == 7)
ok("5. 输入控件触控高度 ≥44",
   all(sp.minimumHeight() >= 0 and sp.height() >= 44
       for _chk, sp in sheet._ma_rows + sheet._ema_rows))
sheet._ma_rows[0][1].setValue(13)
sheet._ema_rows[0][0].setChecked(True)
sheet._ema_rows[0][1].setValue(33)
sheet.spin_boll_k.setValue(2.5)
sheet._on_apply()
ok("5. 应用后图表立即生效",
   cv.chart.ma_lines[0]["period"] == 13
   and cv.chart.ema_lines[0]["period"] == 33
   and cv.chart.boll_params["k"] == 2.5)
ok("5. 应用后落盘且面板关闭",
   ip.params_for(Config(), "15m")["ma"][0]["period"] == 13
   and not sheet.isVisible())
ok("5. 面板关闭键存在", sheet.btn_close.height() >= 44)

# sync_indicators：设置页保存后同步 EMA 与参数
cfg2.set("show_ema", True)
cfg2.set("show_ma", False)
cv.sync_indicators()
ok("5. 设置保存后同步开关", cv.chart.show_ema is True
   and cv.chart.show_ma is False
   and cv._indicator_buttons["show_ema"].isChecked() is True)

# ---- 7. 设置页 ----
class _Stub:
    def __init__(self, config):
        self.config = config
        self.market = types.SimpleNamespace(list_sources=lambda: [])
    def width(self):
        return 420
    def height(self):
        return 800

from ui.settings_dialog import SettingsPage     # noqa: E402
sp = SettingsPage(_Stub(cfg2))
ok("7. 设置页有 EMA 复选框", "show_ema" in sp.chk_indicators)
sp.chk_indicators["show_ema"].setChecked(False)
ok("7. get_settings 写回 EMA",
   sp.get_settings().get("show_ema") is False)
ok("7. 设置页不再管理自选列表", "symbols" not in sp.get_settings())

print("\n%d checks, %d failed" % (CHECKS[0], len(FAILS)))
if FAILS:
    for f in FAILS:
        print("  FAILED:", f)
    sys.exit(1)
sys.exit(0)
