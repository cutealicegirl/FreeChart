# -*- coding: utf-8 -*-
"""升级功能回归：红涨绿跌、页内排序、增删自选、内嵌搜索面板、BOLL 开关。"""
import os
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_upgrade_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from core.config import Config
from ui.main_window import MainWindow, market_of
from ui.ticker_widget import TickerWidget

app = QApplication([])

# ---- 1. 红涨绿跌配色 ----
row = TickerWidget("TEST", "测试")
t = type("T", (), {"symbol": "TEST", "name": "测试", "last_price": 100.0,
                   "change_pct": 2.5, "high_24h": 101, "low_24h": 99,
                   "quote_volume_24h": 5e8})()
row.update_ticker(t)
assert "#f6465d" in row.lbl_change.styleSheet(), "上涨应为红色"
t.change_pct = -2.5
row._last_price = 100.0
row.update_ticker(t)
assert "#0ecb81" in row.lbl_change.styleSheet(), "下跌应为绿色"
print("1. 红涨绿跌 OK")

# ---- 2. 主窗口 + 混合市场 ----
cfg = Config()
cfg.set("symbols", ["BTC", "ETH", "SOL", "SH:600519", "US:AAPL"])
mw = MainWindow(cfg)
mw.show()


def page_symbols(key):
    lay = mw.pages[key]["layout"]
    return [lay.itemAt(i).widget().symbol for i in range(lay.count())
            if lay.itemAt(i).widget() is not None
            and hasattr(lay.itemAt(i).widget(), "symbol")]


def check():
    print("行情行数:", len(mw.rows), "(期望 5)")
    assert len(mw.rows) == 5
    assert all(market_of(s) == "crypto" for s in page_symbols("crypto"))

    # ---- 3. 页内排序 ----
    def ticker(symbol, change, price, amount):
        return type("T", (), {"symbol": symbol, "change_pct": change,
                              "last_price": price,
                              "quote_volume_24h": amount})()

    mw._last_tickers = {
        "BTC": ticker("BTC", -1, 75000, 1e9),
        "ETH": ticker("ETH", 5, 3200, 6e9),
        "SOL": ticker("SOL", 0.5, 180, 2e9),
        "SH:600519": ticker("SH:600519", 2, 1453, 3e9),
        "US:AAPL": ticker("US:AAPL", -2, 240, 7e9),
    }
    for mode, expected in (("change_desc", ["ETH", "SOL", "BTC"]),
                           ("change_asc", ["BTC", "SOL", "ETH"]),
                           ("price_desc", ["BTC", "ETH", "SOL"]),
                           ("amount_desc", ["ETH", "SOL", "BTC"])):
        mw.combo_sort.setCurrentIndex(mw.combo_sort.findData(mode))
        codes = page_symbols("crypto")
        print(f"  排序[{mode}]:", codes)
        assert codes == expected, f"{mode} 排序错误: {codes}"
    mw.combo_sort.setCurrentIndex(mw.combo_sort.findData("custom"))
    print("3. 页内多种排序 OK")

    # ---- 4. 增删自选 ----
    before = len(mw.rows)
    mw._remove_symbol("SOL")
    assert "SOL" not in mw.rows and len(mw.rows) == before - 1
    mw._add_symbol("SOL")
    print("4. 移出 / 恢复自选 OK")

    # ---- 5. 内嵌搜索面板（添加按钮可点击）----
    panel = mw.search_panel
    fake = [{"symbol": "DOGE", "name": "DOGE", "kind": "加密货币"},
            {"symbol": "SH:600036", "name": "招商银行", "kind": "沪市A股"}]
    panel.show_results(fake, set(mw.rows))
    assert panel.isVisible()
    first = panel._layout.itemAt(0).widget()
    assert first.layout().indexOf(first.btn_add) >= 0
    first.btn_add.click()
    assert "DOGE" in mw.rows, "搜索结果按钮应能加入自选"
    first.btn_add.click()
    assert "DOGE" not in mw.rows, "再次点击应移出自选"
    print("5. 内嵌搜索面板增删 OK")

    # ---- 6. BOLL 指标开关 ----
    btn = mw.chart_view._indicator_buttons["show_boll"]
    assert btn.isChecked(), "BOLL 默认应显示"
    btn.click()
    assert not mw.chart_view.chart.show_boll and not cfg.get("show_boll")
    btn.click()
    assert mw.chart_view.chart.show_boll and cfg.get("show_boll")
    print("6. BOLL 显隐 + 持久化 OK")

    print("\n升级功能测试通过 ✅")
    mw.quit_app()


def safe_check():
    try:
        check()
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        mw.quit_app()
        app.quit()


QTimer.singleShot(9000, safe_check)
app.exec()
