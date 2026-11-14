# -*- coding: utf-8 -*-
"""v13 离线回归：滚轮缩小不再反向放大（月线短历史 bug）+ 缩小极限
「全部历史居中半屏」+ 最新 K 线实时价伸缩动画 + 股票专属字徽。"""
import os
import random
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_v13_")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import (QAbstractAnimation, QPoint, QPointF, Qt)
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication

app = QApplication([])

from data.klines import Candle
from ui.chart_view import CandleChart
from ui.icons import register_symbol_name, stock_badge, stock_name, symbol_icon


def make(n, seed=7, step=2629800):
    r = random.Random(seed)
    return [Candle(ts=1600000000 + i * step, time_label=str(i),
                   open=100, high=100 + r.random() * 8,
                   low=100 - r.random() * 8, close=100.5, volume=10)
            for i in range(n)]


def wheel(chart, down=True):
    d = -120 if down else 120
    ev = QWheelEvent(QPointF(400, 200), QPointF(400, 200), QPoint(0, 0),
                     QPoint(0, d), Qt.NoButton, Qt.NoModifier,
                     Qt.ScrollUpdate, False)
    chart.wheelEvent(ev)


# ===== 1. 月线短历史：缩小永不反向放大、可还原 =====
c = CandleChart()
c.resize(960, 560)
c.set_data(make(45))
c.history_exhausted = True          # 月线一次已取全历史
steps = [c._view_count]
for _ in range(8):
    wheel(c, down=True)
    steps.append(c._view_count)
assert all(b >= a for a, b in zip(steps, steps[1:])), f"视野被反向压小: {steps}"
assert any(b > a for a, b in zip(steps, steps[1:])), "缩小必须生效"
assert c._view_count == 180.0
assert c._pan != 0.0 and abs(c._pan + (180 - 45) / 2) > 1e-6, \
    "v22：缩放位置由锚点决定，不得强制贴右 / 居中"
assert c._visible_range() == (0, 45)          # 全部历史都在屏内
for _ in range(15):
    wheel(c, down=False)
assert c._view_count >= c._min_bars
print("1. 月线短历史缩小 OK：单调缩小到极限，可还原")

# ===== 2. 长历史：极限 = 2×总根数，全历史仍在屏内 =====
c2 = CandleChart()
c2.resize(960, 560)
c2.set_data(make(20000, seed=3))
for _ in range(40):
    wheel(c2, down=True)
assert abs(c2._view_count - 40000) < 1e-6, c2._view_count
assert abs(c2._pan + 10000.0) > 1e-6, "不得被强制整块居中"
assert c2._visible_range() == (0, 20000)
print("2. 长历史缩小 OK：2 万根全历史仍在屏内")

# ===== 2b. 变窄后每一步都居中，绝不被甩到最右边 =====
cn = CandleChart()
cn.resize(1000, 600)
cn.set_data(make(45, seed=4))
cn.history_exhausted = True
checked = 0
for _ in range(8):
    wheel(cn, down=True)
    if cn._view_count < 45:
        continue
    # v22：不再要求左右留白严格对称（那是旧的强制居中），只要求
    # 锚点不被重排、全部已加载历史仍在屏内、最新一根不被钉死在右边。
    assert cn._visible_range() == (0, 45), \
        f"变窄后应仍看得到全部历史: {cn._visible_range()}"
    assert cn._pan != 0.0, "变窄后不得强制贴右边缘"
    checked += 1
assert checked >= 3
print("2b. 变窄后保留全部历史且不强制对齐 OK")

# ===== 3. 缩到「全部已加载铺满」才请求回溯；越过铺满点退出自动贴合 =====
c3 = CandleChart()
c3.resize(960, 560)
c3.set_data(make(300, seed=9, step=60))
c3.history_exhausted = False
hits = []
c3.need_history.connect(lambda: hits.append(1))
while c3._view_count < 300:
    wheel(c3, down=True)
assert hits, "铺满点必须请求回溯"
wheel(c3, down=True)                       # 越过铺满点
assert c3.fit_all is False, "越过铺满点后不再自动贴合"
print("3. 回溯触发与自动贴合退出 OK")

# ===== 4. 最新 K 线实时价伸缩动画 =====
c4 = CandleChart()
c4.resize(960, 560)
c4.set_data(make(100, seed=5))
last = c4.candles[-1]
base, base_high = last.close, last.high
c4.animate_last_price(base * 1.10)
c4._on_live_anim(0.5)
mid = c4.candles[-1].close
assert base < mid < base * 1.10, "动画中间值应在起点与目标之间"
c4._on_live_anim(1.0)
assert abs(c4.candles[-1].close - base * 1.10) < 1e-9
assert c4.candles[-1].high >= base * 1.10, "高点应随实时价上移"
c4.animate_last_price(base * 0.92)
c4._on_live_anim(1.0)
assert abs(c4.candles[-1].close - base * 0.92) < 1e-9
c4.set_data(make(100, seed=6))
assert c4._anim.state() == QAbstractAnimation.Stopped, \
    "数据整体刷新后动画应作废"
print("4. 最新 K 线实时价伸缩动画 OK")

# ===== 5. 股票专属字徽 =====
assert stock_name("HK:00700") == "腾讯控股"
assert stock_name("SH:600519") == "贵州茅台"
register_symbol_name("SH:688981", "中芯国际")
assert stock_name("SH:688981") == "中芯国际"
pms = [symbol_icon(s, 30) for s in
       ("SH:600519", "SZ:300750", "HK:00700", "US:NVDA", "US:AAPL")]
assert all(not pm.isNull() for pm in pms)
# 不同股票颜色必须不同（取中心点颜色）
colors = {pm.toImage().pixelColor(15, 15).name() for pm in pms}
assert len(colors) >= 4, f"字徽颜色应各不相同: {colors}"
b = stock_badge("SH:600519", "贵州茅台", 30)
img = b.toImage()
n_opaque = sum(1 for y in range(0, 30, 2) for x in range(0, 30, 2)
               if img.pixelColor(x, y).alpha() > 10)
assert n_opaque > 40, "徽章应有实体底"
print("5. 股票字徽 OK：名称映射 + 动态登记 + 颜色互异")

print("\nv13 全部回归测试通过 ✅")
