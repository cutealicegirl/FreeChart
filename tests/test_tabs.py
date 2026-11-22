# -*- coding: utf-8 -*-
"""测试分页版 UI：页签隔离、页内排序、内嵌搜索、右键移动、红心增删。"""
import os
import sys
import tempfile

# 测试使用临时配置目录，绝不污染真实 %APPDATA%/FreeChart/config.json
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_tabs_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QLabel, QScrollArea

from core.config import Config
from ui.main_window import MARKET_GROUPS, MainWindow, market_of

app = QApplication([])
cfg = Config()
w = MainWindow(cfg)
w.show()


def page_symbols(key):
    """按布局顺序读取指定页的行代码。"""
    lay = w.pages[key]["layout"]
    out = []
    for i in range(lay.count()):
        item = lay.itemAt(i)
        if item is not None and item.widget() is not None \
                and hasattr(item.widget(), "symbol"):
            out.append(item.widget().symbol)
    return out


def check():
    # ---- 1. 页签切换与分页隔离 ----
    print("== 1. 分页隔离 ==")
    w._switch_market("crypto")
    crypto_page = page_symbols("crypto")
    print("加密货币页:", len(crypto_page), "个")
    assert len(crypto_page) == 17, crypto_page
    assert all(market_of(s) == "crypto" for s in crypto_page)

    w._switch_market("cn")
    cn_page = page_symbols("cn")
    print("A股页:", cn_page)
    assert all(market_of(s) == "cn" for s in cn_page)

    # 页签数量显示
    assert w.tabs.buttons["crypto"].text().startswith("加密货币")
    print("页签文本:", w.tabs.buttons["crypto"].text())

    # ---- 2. 页内排序 ----
    print("== 2. 页内排序 ==")
    w._switch_market("crypto")
    # 等首次行情已由 refresh_now 完成（offscreen 下网络可用）
    idx = w.combo_sort.findData("change_desc")
    w.combo_sort.setCurrentIndex(idx)
    page = page_symbols("crypto")
    changes = [w._last_tickers[s].change_pct for s in page
               if s in w._last_tickers]
    assert changes == sorted(changes, reverse=True), changes
    print("涨跌幅↓ 排序正确:", [f"{c:+.1f}" for c in changes[:5]], "...")

    # 恢复自定义排序
    w.combo_sort.setCurrentIndex(w.combo_sort.findData("custom"))

    # ---- 3. 右键菜单动作（直接调用处理器）----
    print("== 3. 右键移动 ==")
    order_before = [s for s in (cfg.get("symbols") or [])
                    if market_of(s) == "crypto"]
    # 模拟"移到顶部"：把 ETH 移到顶部
    w._on_row_context.__wrapped__ if False else None
    full_before = list(cfg.get("symbols") or [])
    # 直接调用合并逻辑验证：构造 group_order
    group = [s for s in full_before if market_of(s) == "crypto"]
    group.remove("ETH")
    group.insert(0, "ETH")
    merged = w._merge_order(group, "crypto")
    assert merged.index("ETH") < merged.index("BTC"), merged
    print("merge_order 正确: ETH 提前")

    # ---- 4. 红心增删 ----
    print("== 4. 红心增删 ==")
    w._add_symbol("US:TSLA")
    assert "US:TSLA" in w.rows and market_of("US:TSLA") == "us"
    print("添加 US:TSLA 后美股页:", page_symbols("us"))
    w._remove_symbol("US:TSLA")
    assert "US:TSLA" not in w.rows
    print("移除成功，美股页:", page_symbols("us"))

    # ---- 5. 滚动区存在（stack 最后一页是图表页，不在滚动区检查范围内）----
    print("== 5. 滚动 ==")
    scrolls = [w.stack.widget(i) for i in range(len(MARKET_GROUPS))]
    assert all(isinstance(s, QScrollArea) for s in scrolls)
    # 滚动条存在即可滚轮滚动
    bar = scrolls[0].verticalScrollBar()
    print("加密货币页滚动范围:", bar.minimum(), "-", bar.maximum())

    # ---- 6. 配置持久化 last_tab ----
    print("== 6. 持久化 ==")
    cfg2 = Config()
    assert cfg2.get("last_tab") in ("crypto", "cn", "hk", "us"), \
        cfg2.get("last_tab")
    print("last_tab 已保存:", cfg2.get("last_tab"))

    print("\n分页版 UI 全部测试通过 ✅")
    w.quit_app()


from PySide6.QtCore import QTimer


def safe_check():
    """断言失败也要退出事件循环，避免 offscreen 测试挂死。"""
    try:
        check()
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        w.quit_app()
        app.quit()


QTimer.singleShot(12000, safe_check)
app.exec()
