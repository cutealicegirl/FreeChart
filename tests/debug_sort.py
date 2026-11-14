# -*- coding: utf-8 -*-
"""单独调试排序逻辑。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from core.config import Config
from ui.main_window import MainWindow
from ui.ticker_widget import TickerWidget

app = QApplication([])
cfg = Config()
cfg.set("symbols", ["BTC", "SH:600519", "SZ:000001", "HK:00700", "US:AAPL"])
mw = MainWindow(cfg)
mw.show()

FAKE = {
    "BTC": {"change_pct": -1, "last_price": 75000, "quote_volume_24h": 1e9},
    "SH:600519": {"change_pct": 5, "last_price": 1453,
                  "quote_volume_24h": 6e9},
    "SZ:000001": {"change_pct": 0.5, "last_price": 11.8,
                  "quote_volume_24h": 2e9},
    "HK:00700": {"change_pct": -2, "last_price": 419.8,
                 "quote_volume_24h": 1.2e10},
    "US:AAPL": {"change_pct": -0.1, "last_price": 343.7,
                "quote_volume_24h": 7e9},
}


class FakeT:
    def __init__(self, d):
        self.symbol = "x"
        self.name = ""
        for k, v in d.items():
            setattr(self, k, v)


def read_layout_order():
    layout = mw.centralWidget().layout()
    codes = []
    for i in range(layout.count()):
        it = layout.itemAt(i)
        wdg = it.widget() if it else None
        if isinstance(wdg, TickerWidget):
            codes.append(wdg.symbol)
    return codes


def check():
    mw._last_tickers = {k: FakeT(v) for k, v in FAKE.items()}
    print("排序键:", {s: mw._sort_key(s, "change_desc")
                      for s in FAKE})
    mw.combo_sort.setCurrentIndex(mw.combo_sort.findData("change_desc"))
    print("当前模式:", mw.combo_sort.currentData())
    print("布局顺序:", read_layout_order())
    mw._apply_sort()
    print("手动排序后:", read_layout_order())
    mw.quit_app()
    sys.exit(0)


QTimer.singleShot(8000, check)
app.exec()
