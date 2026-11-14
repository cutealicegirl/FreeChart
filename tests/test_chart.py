# -*- coding: utf-8 -*-
"""测试图表页：数据加载、周期切换、返回导航、点击条目进入。"""
import os
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_chart_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from core.config import Config
from data.klines import fetch_klines
from ui.main_window import MainWindow

app = QApplication([])
cfg = Config()
w = MainWindow(cfg)
w.show()

step = {"n": 0}


def step1():
    """1. K 线数据层：加密货币 + 股票。"""
    print("== 1. K线数据层 ==")
    c = fetch_klines("BTC", "15m")
    print(f"BTC 15m: {len(c)} 根, 最新收盘 {c[-1].close}, 标签 {c[-1].time_label}")
    assert len(c) >= 200 and c[-1].close > 0
    c2 = fetch_klines("SH:600519", "day")
    print(f"茅台 日K: {len(c2)} 根, 最新收盘 {c2[-1].close}, 标签 {c2[-1].time_label}")
    assert len(c2) > 50 and c2[-1].close > 0
    step["n"] = 1
    QTimer.singleShot(200, step2)


def step2():
    """2. 点击条目进入图表页。"""
    print("== 2. 进入图表页 ==")
    w._open_chart("BTC")
    assert w.stack.currentWidget() is w.chart_view
    assert w.chart_view._symbol == "BTC"
    # 等首次 K 线加载完成
    QTimer.singleShot(6000, step3)


def step3():
    print("图表数据根数:", len(w.chart_view.chart.candles))
    assert len(w.chart_view.chart.candles) > 50, "BTC 15m K线未加载"
    # 3. 周期切换到日K
    print("== 3. 周期切换 ==")
    w.chart_view._set_interval("1d")
    QTimer.singleShot(6000, step4)


def step4():
    print("日K根数:", len(w.chart_view.chart.candles))
    assert len(w.chart_view.chart.candles) > 50
    # 4. 美股图表（新浪源）
    print("== 4. 美股图表 ==")
    w._open_chart("US:AAPL")
    assert w.chart_view._symbol == "US:AAPL"
    assert w.chart_view._interval == "day"
    QTimer.singleShot(7000, step5)


def step5():
    print("苹果日线根数:", len(w.chart_view.chart.candles))
    assert len(w.chart_view.chart.candles) > 100
    # 5. 港股降级（无K线源 -> 友好提示）
    print("== 5. 港股降级 ==")
    w._open_chart("HK:00700")
    assert len(w.chart_view.chart.candles) == 0
    assert not w.chart_view._refresh_timer.isActive()
    print("港股显示提示、不加载、无定时刷新 ✅")
    # 6. 返回列表
    print("== 6. 返回导航 ==")
    w._leave_chart()
    assert w.stack.currentWidget() is not w.chart_view
    assert w.stack.currentIndex() == 0  # crypto 页
    assert not w.chart_view._refresh_timer.isActive()
    print("返回列表成功，图表定时器已停止")

    print("\n图表页全部测试通过 ✅")
    w.quit_app()


QTimer.singleShot(12000, step1)   # 先让主窗口行情刷新完成
app.exec()
