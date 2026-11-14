# -*- coding: utf-8 -*-
"""v20 预览图：悬停资料卡 / 全部页 / 图表详情按钮 / 详情抽屉 / 气泡风格。

运行：
    QT_QPA_PLATFORM=windows python tools/make_preview_v20.py
输出到 preview/ 目录（PNG）。
"""
import os
import sys
import tempfile
import time

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_prev20_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import QApplication

from core.config import Config
from ui.main_window import MainWindow
from ui.mascot import BUBBLE_STYLES, MascotBubble

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
    cfg.set("sort_mode", "change_desc")
    w = MainWindow(cfg)
    w.resize(460, 880)
    w.prepare_show()
    pump(app, 6.0)                       # 等一轮行情 + 市值资料

    # ---- 1. 自选页：悬停第三行，资料卡跟着换成它 ----
    w._switch_sub("watch")
    pump(app, 0.5)
    syms = [s for s in w.rows][:5]
    if len(syms) >= 3:
        row = w.rows[syms[2]]
        row.enterEvent(QEnterEvent(QPointF(8, 8), QPointF(8, 8),
                                   QPointF(8, 8)))
    pump(app, 0.8)
    save(w, "70_main_watch.png")

    # ---- 2. 全部页 ----
    w._switch_sub("all")
    end = time.time() + 20
    while w._filling_all and time.time() < end:
        app.processEvents()
        time.sleep(0.01)
    pump(app, 0.6)
    w._paint_page_rows(w._current_market())
    pump(app, 0.4)
    save(w, "71_main_all.png")

    # ---- 3. 图表页（头部有「ⓘ 详情」）----
    w._open_chart(syms[0])
    pump(app, 2.2)
    save(w, "72_chart_with_detail.png")

    # ---- 4. 详情抽屉 ----
    from ui.detail_dialog import SymbolDetailDialog
    dlg = SymbolDetailDialog(w.chart_view._symbol, "",
                             w._last_tickers.get(w.chart_view._symbol), w)
    dlg.resize(430, 640)
    dlg.show()
    pump(app, 3.0)
    save(dlg, "73_detail_sheet.png")
    dlg.close()

    # ---- 5. 五套气泡 ----
    b = MascotBubble()
    shots = []
    for key in BUBBLE_STYLES:
        b.set_style(key)
        b._text = "主人，ETH 涨了 +7.80% 啦，我帮你盯着～"
        b.resize(b._measure())
        shots.append(b.grab())
    from PySide6.QtGui import QColor, QPainter, QPixmap
    W = max(p.width() for p in shots)
    H = sum(p.height() + 8 for p in shots) + 8
    out = QPixmap(W + 16, H)
    out.fill(QColor("#1b2233"))
    pt = QPainter(out)
    y = 8
    for pm in shots:
        pt.drawPixmap(8, y, pm)
        y += pm.height() + 8
    pt.end()
    os.makedirs(OUT, exist_ok=True)
    out.save(os.path.join(OUT, "60_bubble_styles.png"))
    print("saved", os.path.join(OUT, "60_bubble_styles.png"))

    try:
        w.live.shutdown()
    except Exception:
        pass
    w.scheduler.stop()
    w.close()


if __name__ == "__main__":
    main()
    os._exit(0)
