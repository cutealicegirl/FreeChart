# -*- coding: utf-8 -*-
"""回归测试：布林线、画线方向、滚轮缩放、时间轴完整性、图表页布局。

全部离线（构造假 K 线），不依赖网络；使用临时 APPDATA 避免污染真实配置。
"""
import math
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="ct_fix2_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, ".")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

from core.config import Config
from data.klines import Candle
from ui.chart_view import CandleChart, boll_series
from ui.main_window import MainWindow

app = QApplication([])


def make_candles(n=200):
    out = []
    price = 60000.0
    for i in range(n):
        delta = math.sin(i / 7.0) * 180 + math.cos(i / 3.0) * 60
        open_ = price
        close = price + delta
        out.append(Candle(
            ts=1700000000 + i * 900, time_label=f"11-{(i % 28) + 1:02d} 09:30",
            open=open_, high=max(open_, close) + 120,
            low=min(open_, close) - 120, close=close,
            volume=1000 + i * 3.0))
        price = close
    return out


def wheel(delta_y):
    return QWheelEvent(QPointF(400, 300), QPointF(400, 300),
                       QPoint(0, 0), QPoint(0, delta_y),
                       Qt.NoButton, Qt.NoModifier,
                       Qt.NoScrollPhase, False)


def mouse(kind, pos, buttons=Qt.NoButton):
    p = QPointF(pos)
    return QMouseEvent(kind, p, p, Qt.LeftButton, buttons, Qt.NoModifier)


# ================= 1. BOLL 布林线计算 =================
closes = [float(i + 1) for i in range(40)]
up, mid, dn = boll_series(closes)
std = math.sqrt(sum((x - 10.5) ** 2 for x in range(1, 21)) / 20)
assert up[:19] == [None] * 19
assert abs(mid[19] - 10.5) < 1e-9
assert abs(up[19] - (10.5 + 2 * std)) < 1e-9
assert abs(dn[19] - (10.5 - 2 * std)) < 1e-9
assert abs(up[39] - dn[39] - 4 * std) < 1e-9
print("1. BOLL(20,2) 计算 OK", round(up[19], 4), round(dn[19], 4))

# ================= 2. 坐标映射 / 画线方向 =================
chart = CandleChart()
chart.resize(1000, 640)
chart.set_data(make_candles())
g = chart._geom()
for y in (g["price"].top() + 10, g["price"].top() + 80,
          g["price"].bottom() - 10):
    assert abs(chart._y_price(g, chart._price_at(g, y)) - y) < 1e-6, \
        "y->price->y 必须是恒等映射（否则拖动方向反转）"
print("2a. 价格轴坐标互逆 OK")

y0 = int(g["price"].top() + g["price"].height() * 0.35)
x0 = int(g["x0"] + 180)
hline = {"kind": "hline", "price": chart._price_at(g, y0)}
chart.set_drawings([hline])
line = chart._lines[0]
pts = chart._line_points(g, line)
assert abs(pts[1] - y0) < 0.01, "水平线应画在鼠标点击的位置"
chart._drag = {"line": line, "mode": "hline",
               "start": (x0, y0), "orig": dict(line)}
chart._apply_drag(g, QPoint(x0 + 20, y0 + 24))
pts2 = chart._line_points(g, line)
assert abs(pts2[1] - (y0 + 24)) < 0.01, \
    f"鼠标下移 24px，线也应下移 24px，实际 {pts2[1] - y0:.1f}"
print("2b. 水平线拖动方向 OK（下移 24px -> 下移 24px）")

trend = {"kind": "trend",
         "p1": (chart.candles[-60].ts, chart._price_at(g, y0)),
         "p2": (chart.candles[-20].ts, chart._price_at(g, y0 - 60))}
chart.set_drawings([trend])
line = chart._lines[0]
p_before = chart._line_points(g, line)
chart._drag = {"line": line, "mode": "p1",
               "start": (int(p_before[0]), int(p_before[1])),
               "orig": dict(line)}
chart._apply_drag(g, QPoint(int(p_before[0]) + 30,
                            int(p_before[1]) + 18))
p_after = chart._line_points(g, line)
assert abs((p_after[0] - p_before[0]) - 30) < 1.0, "端点应随鼠标右移"
assert abs((p_after[1] - p_before[1]) - 18) < 1.0, "端点应随鼠标下移"
print("2c. 趋势线端点拖动方向 OK（+30,+18 -> +30,+18）")

# ================= 3. 滚轮缩放双向生效 =================
chart._view_count = 90
chart.wheelEvent(wheel(120))              # 上滚：放大
zoomed_in = chart._view_count
assert zoomed_in < 90, f"放大失效: {zoomed_in}"
chart.wheelEvent(wheel(-120))             # 下滚：缩小
assert chart._view_count > zoomed_in, "缩小失效"
for _ in range(10):
    chart.wheelEvent(wheel(-120))
assert chart._view_count > 150, f"缩小无法扩展视野: {chart._view_count}"
zoomed_out = chart._view_count
chart.wheelEvent(wheel(120))
assert chart._view_count < zoomed_out, "缩小后再放大失效"
print(f"3. 滚轮缩放 OK 90 -> {zoomed_in} -> {zoomed_out} -> "
      f"{chart._view_count}")

# 切换周期时不可永久压缩用户缩放级别
short = make_candles()[:12]
before = chart._view_count
chart.set_data(short)
assert chart._view_count == before, "set_data 不应改变缩放级别"
chart.set_data(make_candles())
assert chart._view_count == before, "切回长周期后缩放级别应保留"
print("3b. set_data 不压缩缩放级别 OK")

# ================= 4. 时间轴标签完整不越界 =================
chart.set_data(make_candles())
g = chart._geom()
view_x = g["x0"] + g["w"]
labels = chart._time_axis_labels(g, view_x)
assert labels, "时间轴应有标签"
for rect, text, _tick in labels:
    assert rect.x() >= 0 and rect.right() <= chart.width() + 0.01, \
        f"时间标签横向越界: {rect}"
    assert rect.top() >= g["bottom"] - 0.01, "时间标签侵入 K 线区"
    assert rect.bottom() <= chart.height() + 0.01, \
        f"时间标签底部被裁切: {rect}"
print(f"4. 时间轴 OK：{len(labels)} 个标签，全部落在 "
      f"[{g['bottom']:.0f}, {chart.height()}] 独立区域内")

# ================= 5. 价格范围包含布林轨 =================
chart.show_boll = True
g2 = chart._geom()
upper_visible = [v for v in chart._ind["boll"][0][g2["offset"]:]
                 if v is not None]
assert g2["hi"] >= max(upper_visible), "布林上轨超出价格范围会被裁掉"
chart.show_boll = False
g3 = chart._geom()
assert g3["hi"] <= g2["hi"] + 1e-6
print("5. BOLL 参与价格范围自适应 OK")

# ================= 6. 左右拖动平移 =================
chart.set_drawings([])
chart.set_tool("none")
chart.reset_view()
g = chart._geom()
p = QPoint(int(g["x0"] + 120), int(g["price"].top() + 50))
chart.mousePressEvent(mouse(QEvent.MouseButtonPress, p, Qt.LeftButton))
assert chart._panning, "在空白处按下应进入平移模式"
p2 = QPoint(p.x() + 160, p.y())
chart.mouseMoveEvent(mouse(QEvent.MouseMove, p2, Qt.LeftButton))
expected = int(round(160 / g["step"]))
assert abs(chart._pan - expected) <= 1, \
    f"向右拖 160px 应平移约 {expected} 根，实际 {chart._pan}"
assert chart._bars()[-1].ts < chart.candles[-1].ts, "右端应离开最新一根"
chart.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, p2))
assert not chart._panning
chart.reset_view()
assert chart._pan == 0 and chart._bars()[-1] is chart.candles[-1]
print(f"6. 左右拖动平移 OK（右拖 160px -> 回看 {expected} 根，复位正常）")

# ================= 7. 渲染 / 布局 =================
chart.show_boll = True
chart.repaint()
cfg = Config()
assert cfg.get("show_boll") is True, "BOLL 默认值应写入配置"
w = MainWindow(cfg)
w.show()
QApplication.processEvents()
orig_w, orig_h = w.width(), w.height()
assert orig_w <= 520, f"列表窗口被图表页撑宽到 {orig_w}px"
w._open_chart("BTC")
QApplication.processEvents()
assert w.stack.currentWidget() is w.chart_view
assert all(c.isHidden() for c in w._list_controls), "图表页应隐藏列表控件"
assert w.width() >= orig_w, "图表页窗口应放大"
w._leave_chart()
QApplication.processEvents()
assert not any(c.isHidden() for c in w._list_controls), "返回后控件应恢复"
assert w.width() == orig_w and w.height() == orig_h, \
    f"返回后窗口尺寸应恢复 {orig_w}x{orig_h}，实际 {w.width()}x{w.height()}"
assert w.chart_view.chart.show_boll is True
assert "show_boll" in w.chart_view._indicator_buttons
print(f"7. 图表页布局 / BOLL 开关 / 窗口恢复 OK（列表宽 {orig_w}px）")

w.quit_app()
QTimer.singleShot(50, app.quit)
app.exec()
print("\n全部回归测试通过 ✅")
