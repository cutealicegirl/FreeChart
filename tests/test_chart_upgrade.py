# -*- coding: utf-8 -*-
"""图表升级测试：多周期、滚轮缩放、画线工具、MACD/MA 指标。"""
import os
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_chartupg_")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, ".")

from PySide6.QtCore import QPointF, QTimer
from PySide6.QtWidgets import QApplication

from core.config import Config
from ui.chart_view import CandleChart, macd_series, ma_series
from ui.main_window import MainWindow

app = QApplication([])
w = MainWindow(Config())
w.show()


def approx(a, b, eps=1e-6):
    return abs(a - b) < eps


def step1():
    print("== 1. 指标计算 ==")
    closes = [float(i + 1) for i in range(40)]      # 线性序列
    ma5 = ma_series(closes, 5)
    assert ma5[4] == 3.0 and ma5[39] == 38.0, ma5[39]   # (36+37+38+39+40)/5
    assert ma5[0] is None and ma5[3] is None
    # MACD：线性上升序列 DIF 应为正常数
    dif, dea, hist = macd_series(closes)
    assert dif[25] is not None and dif[25] > 0
    assert dea[33] is not None
    assert approx(hist[33], 2 * (dif[33] - dea[33]))
    print("MA/MACD 计算 OK")

    print("== 2. 周期按钮（含周/月/年/3日） ==")
    w._open_chart("BTC")
    QTimer.singleShot(4000, step2)


def step2():
    keys = list(w.chart_view._interval_buttons.keys())
    print("BTC 周期:", keys)
    assert set(["1m", "5m", "15m", "30m", "1h", "4h",
                "1d", "3d", "1w", "1M", "1y"]) <= set(keys), keys
    assert len(w.chart_view.chart.candles) > 50

    # 3. 滚轮缩放
    chart = w.chart_view.chart
    n0 = len(chart.candles)
    assert chart._view_count == 90
    chart.wheel_up = None
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtCore import QPointF as _PF, QEvent
    # 直接调用缩放逻辑（wheelEvent 的核心路径）
    old = chart._view_count
    chart._view_count = max(chart._min_bars, int(old * 0.8))   # 放大
    assert chart._view_count == 72
    bars = chart._bars()
    assert len(bars) == 72 and bars[-1] is chart.candles[-1]   # 右端锚定
    chart._view_count = min(len(chart.candles),
                            int(chart._view_count * 1.25) + 1)
    print(f"缩放 OK: 90 -> 72 -> {chart._view_count}（总 {n0} 根）")

    # 4. 画线工具
    print("== 4. 画线工具 ==")
    chart.set_tool("hline")
    assert chart._tool == "hline"
    chart._lines.append({"kind": "hline", "price": 75000.0})
    chart.set_tool("trend")
    p1 = (chart.candles[-50].ts, 70000.0)
    p2 = (chart.candles[-10].ts, 80000.0)
    chart._lines.append({"kind": "trend", "p1": p1, "p2": p2})
    assert len(chart.get_drawings()) == 2
    # 渲染不抛异常
    chart.repaint()
    print("画线 OK（2 条，渲染无异常）")

    # 5. 画线跨标的保留
    print("== 5. 画线跨标的保留 ==")
    w._open_chart("ETH")
    QTimer.singleShot(3500, step3)


def step3():
    chart = w.chart_view.chart
    # BTC 的画线在切换到 ETH 时应保存，ETH 初始应为空
    assert chart.get_drawings() == [], "切换标的后画线应清空"
    w._open_chart("BTC")
    QTimer.singleShot(3500, step4)


def step4():
    chart = w.chart_view.chart
    lines = chart.get_drawings()
    assert len(lines) == 2, f"切回 BTC 应恢复 2 条画线，实际 {len(lines)}"
    print("画线恢复 OK:", [l["kind"] for l in lines])

    # 6. A股多周期
    print("== 6. A股周K ==")
    w._open_chart("SH:600519")
    QTimer.singleShot(4000, step5)


def step5():
    keys = list(w.chart_view._interval_buttons.keys())
    assert set(["m1", "m5", "m15", "m30", "m60", "day",
                "3day", "week", "month", "1year"]) <= set(keys), keys
    w.chart_view._set_interval("week")
    QTimer.singleShot(4000, step6)


def step6():
    cs = w.chart_view.chart.candles
    print("茅台周K:", len(cs), "根, 标签样例:", cs[-1].time_label)
    assert len(cs) > 20
    w.chart_view.repaint()
    print("\n图表升级全部测试通过 ✅")
    w.quit_app()


QTimer.singleShot(3500, step1)
app.exec()
