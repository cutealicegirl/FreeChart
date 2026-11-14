# -*- coding: utf-8 -*-
"""v19 预览图：品种资料卡 / 图表工具条收纳 / 看板娘与 K 线重叠淡化。

运行：
    QT_QPA_PLATFORM=windows python tools/make_preview_v19.py
输出到 preview/ 目录（PNG）。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication

from core.config import Config
from data.klines import fetch_klines
from ui.main_window import MainWindow

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "preview")


def save(widget, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    widget.grab().save(path)
    print("saved", path)


def pump(app, seconds=0.4):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def main():
    app = QApplication(sys.argv)
    cfg = Config()
    cfg.set("theme", "binance")
    cfg.set("chart_font_scale", 120)
    cfg.set("show_currency", True)
    cfg.set("chart_tools_open", False)
    w = MainWindow(cfg)

    # ---- 1. 竖屏主界面 + 资料卡 ----
    w.resize(460, 860)
    w.prepare_show()
    pump(app, 6.0)             # 等一轮行情 + 市值资料
    w._sync_info_panel()
    pump(app, 0.3)
    save(w, "50_info_panel_portrait.png")

    # ---- 2. 横屏主界面（资料卡 4 列）----
    w.resize(1180, 760)
    pump(app, 0.6)
    w._sync_info_panel()
    pump(app, 0.3)
    save(w, "51_info_panel_landscape.png")

    # ---- 3. 图表页：工具条收起 ----
    candles = fetch_klines("BTC", "4h")
    w._open_chart("BTC")
    pump(app, 1.6)
    save(w, "52_chart_tools_collapsed.png")

    # ---- 4. 图表页：工具条展开 ----
    w.chart_view.btn_tools.setChecked(True)
    pump(app, 0.4)
    save(w, "53_chart_tools_expanded.png")
    w.chart_view.btn_tools.setChecked(False)

    # ---- 5. 看板娘压住 K 线时的淡化效果 ----
    if w.mascot is not None:
        w._sync_mascot_visibility()
        pump(app, 0.3)
        w.mascot.set_overlap(0.5)
        pump(app, 0.6)
        print("mascot opacity:", round(w.mascot.windowOpacity(), 2))
        w.mascot.set_overlap(0.0)

    print("candles:", len(candles) if candles else 0)
    w.scheduler.stop()
    w.close()


if __name__ == "__main__":
    main()
