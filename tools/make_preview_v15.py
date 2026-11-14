# -*- coding: utf-8 -*-
"""v15 预览图：新主题 / 分级支撑压力 / 放大字号 / 货币单位 / 看板娘。

运行：
    QT_QPA_PLATFORM=windows python tools/make_preview_v15.py
输出到 preview/ 目录（PNG）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core.config import Config
from data.klines import fetch_klines
from ui.main_window import MainWindow
from ui.theme import theme_names

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "preview")


def save(widget, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    widget.grab().save(path)
    print("saved", path)


def main():
    app = QApplication(sys.argv)
    cfg = Config()
    cfg.set("theme", "binance")
    cfg.set("chart_font_scale", 120)
    cfg.set("show_currency", True)
    w = MainWindow(cfg)
    w.resize(460, 820)
    w.show()
    app.processEvents()

    # ---- 1. 主窗口：币安深色 ----
    save(w, "30_v15_main_binance.png")

    # ---- 2. 六个主题各一张 ----
    for name in theme_names():
        w.apply_theme(name)
        app.processEvents()
        save(w, f"31_v15_theme_{name}.png")
    w.apply_theme("binance")
    app.processEvents()

    # ---- 3. 图表：分级支撑压力 + 货币单位 + 放大字号 ----
    w.resize(1200, 780)
    for _ in range(4):
        app.processEvents()
    w.chart_view.layout().activate()
    candles = fetch_klines("BTC", "4h")
    if candles:
        w.chart_view.open("BTC", "Bitcoin", None)
        for key in ("show_res", "show_sup", "show_trend"):
            setattr(w.chart_view.chart, key, True)
            w.chart_view._smart_buttons[key].setChecked(True)
        w.chart_view.chart.set_data(candles[-260:])
        w.chart_view.chart.font_scale = 1.2
        w.chart_view.chart.unit_prefix = "$"
        from data.api_base import Ticker
        last = candles[-1]
        w.chart_view._update_ticker(Ticker(
            symbol="BTC", name="Bitcoin", last_price=last.close,
            change_pct=1.86, high_24h=max(c.high for c in candles[-6:]),
            low_24h=min(c.low for c in candles[-6:]),
            quote_volume_24h=1.2e9))
        for _ in range(4):
            app.processEvents()
        w.chart_view.layout().activate()
        save(w.chart_view, "32_v15_chart_levels.png")

    # ---- 4. A 股图表（¥ 单位）----
    cn = fetch_klines("SH:600519", "day")
    if cn:
        w.chart_view.open("SH:600519", "贵州茅台", None)
        w.chart_view.chart.set_data(cn[-180:])
        w.chart_view.chart.unit_prefix = "¥"
        last = cn[-1]
        from data.api_base import Ticker
        w.chart_view._update_ticker(Ticker(
            symbol="SH:600519", name="贵州茅台", last_price=last.close,
            change_pct=-0.42, high_24h=last.high, low_24h=last.low,
            quote_volume_24h=3.1e9))
        for _ in range(4):
            app.processEvents()
        w.chart_view.layout().activate()
        save(w.chart_view, "33_v15_chart_cn.png")

    # ---- 5. 看板娘 ----
    cfg.set("mascot_enabled", True)
    cfg.set("mascot_scale", 100)
    w.apply_mascot()
    app.processEvents()
    if w.mascot is not None:
        save(w.mascot, "34_v15_mascot.png")
    print("done")


if __name__ == "__main__":
    main()
