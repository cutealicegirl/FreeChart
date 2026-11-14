# -*- coding: utf-8 -*-
"""v9 离线回归：图例 / 标注里「指标名称」与「价格数值」分色显示。

之前 `MA7 67891.23`、`O 67891.23`、`ATH 70000.00` 都是整段字符串
用同一个颜色画，名称与数值糊在一起；现在名称用暗色（或指标色暗化版），
数值用语义色 / 指标本色，必须验证两者确实不同。
"""
import inspect
import math
import os
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_v9_")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import QApplication

app = QApplication([])
for f in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc"):
    if os.path.exists(f):
        QFontDatabase.addApplicationFont(f)

from data.klines import Candle
from ui.chart_view import (BOLL_BAND, MA_COLORS, CandleChart)
from ui.theme import C_TEXT_DIM, C_TEXT_MAIN, C_UP


class RecordingPainter:
    """只记录 setPen 的颜色，用来验证同一行里出现了不同颜色。"""

    def __init__(self):
        self.pens = []

    def setPen(self, c):
        try:
            self.pens.append(QColor(c).name())
        except Exception:
            self.pens.append(None)

    def setFont(self, f):
        pass

    def drawText(self, *args):
        pass


def candles(n=200):
    out = []
    for i in range(n):
        base = 100 + 18 * math.sin(i / 11.0) + 5 * math.sin(i / 3.0)
        out.append(Candle(ts=1600000000 + i * 86400,
                          time_label=f"d{i:03d}", open=base,
                          high=base + 8, low=base - 8,
                          close=base + 1, volume=1000 + i))
    return out


# ===== 1. 名称色确实比数值色暗，且不是同一个值 =====
chart = CandleChart()
for color in (C_UP, BOLL_BAND, *MA_COLORS.values(), C_TEXT_MAIN):
    dim = chart._dim_color(color)
    assert dim != color
    q1, q2 = QColor(color), QColor(dim)
    lum = lambda q: q.red() * 0.299 + q.green() * 0.587 + q.blue() * 0.114
    assert lum(q2) < lum(q1) * 0.75, (color, dim, lum(q1), lum(q2))
print("1. 名称暗化色 / 数值本色 明度差 OK")

# ===== 2. _draw_pair 真的用两种颜色分别绘制 =====
pair_src = inspect.getsource(CandleChart._draw_pair)
assert "name_color" in pair_src and "value_color" in pair_src
assert pair_src.count("self._text(") == 2
rp = RecordingPainter()
chart._draw_pair(rp, 10, 2, 120, 16, "MA7", "67,891.23",
                 C_TEXT_DIM, C_TEXT_MAIN, 10)
assert rp.pens == [QColor(C_TEXT_DIM).name(), QColor(C_TEXT_MAIN).name()], \
    rp.pens
print("2. 名称与数值分两次、用不同颜色绘制 OK")

# ===== 3. 图例：OHLC 与 MA/BOLL 都不再是整段同色字符串 =====
legend = inspect.getsource(CandleChart._draw_legend)
assert '_draw_pair' in legend and '_dim_color' in legend
assert 'f"O {format_price' not in legend
assert 'f"MA{period} {format_price' not in legend
assert 'f"BOLL {name} {format_price' not in legend
assert '("O", self._money(format_price(c.open))' in legend
macd = inspect.getsource(CandleChart._draw_macd_labels)
assert '_draw_pair' in macd and 'f"{name} {v:.3f}"' not in macd
print("3. 图例 / MACD 标签拆成名称+数值分色 OK")

# ===== 4. 图上标注同样分色（ATH/ATL、R/S、LH/LL）=====
for fn in (CandleChart._draw_extremes, CandleChart._draw_auto,
           CandleChart._draw_pivots):
    s = inspect.getsource(fn)
    assert '_draw_pair' in s, fn.__name__
    assert 'f"{label} {format_price(price)}"' not in s, fn.__name__
    assert 'f"{kind}{seq} {format_price(price)}"' not in s, fn.__name__
print("4. ATH/ATL / R/S / LH/LL 标注名称与价格分色 OK")

# ===== 5. 实际渲染一遍图例，出现的颜色里必须同时有名称色和数值色 =====
chart.resize(1020, 690)
chart.set_data(candles())
g = {"x0": 10, "bars": chart.candles, "offset": 0, "n": len(chart.candles)}
rp2 = RecordingPainter()
chart._draw_legend(rp2, g, None, len(chart.candles))
colors = {c for c in rp2.pens if c}
assert QColor(C_TEXT_DIM).name() in colors, "OHLC 名称暗色缺失"
assert QColor(C_TEXT_MAIN).name() in colors, "OHLC 数值亮色缺失"
first_ma = next(iter(MA_COLORS.values()))
assert QColor(chart._dim_color(first_ma)).name() in colors, \
    "指标名称暗化色缺失"
assert QColor(first_ma).name() in colors, "指标数值本色缺失"
assert len(colors) >= 5, f"颜色种类过少: {colors}"
print(f"5. 图例实际绘制出现 {len(colors)} 种颜色，名称/数值可区分 OK")

print("\nv9 全部回归测试通过 ✅")
