# -*- coding: utf-8 -*-
"""测试市场分组隔离：每个分页只放本市场的行，排序只在页内生效。"""
import os
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_groups_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from core.config import Config
from ui.main_window import MARKET_GROUPS, MainWindow, market_of

app = QApplication([])
cfg = Config()
w = MainWindow(cfg)
w.show()


def page_symbols(key):
    lay = w.pages[key]["layout"]
    return [item.widget().symbol for i in range(lay.count())
            if (item := lay.itemAt(i)) is not None
            and item.widget() is not None
            and hasattr(item.widget(), "symbol")]


def check():
    print("== 1. 分页隔离 ==")
    for key, title, _ in MARKET_GROUPS:
        syms = page_symbols(key)
        assert all(market_of(s) == key for s in syms), \
            f"[{title}] 混入了其它市场的标的: {syms}"
        print(f"  {title}: {len(syms)} 项，全部属于 {key}")
    assert len(page_symbols("crypto")) == 17

    print("== 2. 组内排序（涨跌幅升序）==")
    idx = w.combo_sort.findData("change_asc")
    w.combo_sort.setCurrentIndex(idx)
    for key, title, _ in MARKET_GROUPS:
        vals = [w._last_tickers[s].change_pct for s in page_symbols(key)
                if s in w._last_tickers]
        assert vals == sorted(vals), f"[{title}] 页内排序异常: {vals}"
        print(f"  {title} 排序正确:", [f"{v:+.2f}" for v in vals[:4]])
    w.combo_sort.setCurrentIndex(w.combo_sort.findData("custom"))

    print("== 3. 图表页独立于市场分页 ==")
    assert w.stack.count() == len(MARKET_GROUPS) + 1
    assert w.stack.widget(w.stack.count() - 1) is w.chart_view

    print("\n分组隔离测试通过 ✅")
    w.quit_app()


def safe_check():
    try:
        check()
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        w.quit_app()
        app.quit()


QTimer.singleShot(9000, safe_check)
app.exec()
