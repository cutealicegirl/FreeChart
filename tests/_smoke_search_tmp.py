import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if os.path.dirname(os.path.abspath(__file__)) else ".")
import os, time
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QEvent, QPointF
from PySide6.QtGui import QKeyEvent, QMouseEvent
app = QApplication([])
sys.path.insert(0, r"C://Users//13051//WorkBuddy//2026-11-07-00-14-41//CryptoTicker")
from core.config import Config
from ui.main_window import MainWindow
from ui.search_panel import SearchResultRow, SearchHistoryRow
from tests.qt_exit import finish
ADDR='9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump'
from data import onchain
SYM = onchain.make_symbol(ADDR)
cfg = Config(); cfg.set("mascot_enabled", False); cfg.set("search_history", [])
syms=[s for s in cfg.get("symbols") or [] if s!=SYM]; cfg.set("symbols", syms)
w = MainWindow(cfg)
w.scheduler.stop(); w.scheduler.refresh_now = lambda: None
w.show(); app.processEvents()
ok_=[]
def ok(n,c,e=""):
    ok_.append((n,c,e)); print(("PASS " if c else "FAIL ")+n+("  "+str(e) if e and not c else ""))
def click(wgt):
    app.sendEvent(wgt, QMouseEvent(QEvent.MouseButtonPress, QPointF(5,5),
        QPointF(5,5), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
# 1 空内容点搜索按钮→历史页
w.btn_search.click(); app.processEvents()
ok("1 空内容点搜索按钮→历史页", w.stack.currentWidget() is w.search_panel)
ok("1 历史页标题", "搜索历史" in w.search_panel.lbl_title.text())
ok("1 历史为空不显示清空按钮", not w.search_panel.btn_clear_history.isVisible())
# 2 Esc 关闭
app.sendEvent(w.edit_search, QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)); app.processEvents()
ok("2 Esc 回列表页", w.stack.currentWidget() is w.pages[w._current_market()]["scroll"])
# 3 搜索 BTC → 结果页 + 点击行进图表（不默认收藏）
before=set(w.config.get("symbols") or [])
w.edit_search.setText("BTC"); w.edit_search.textEdited.emit("BTC")
t0=time.time()
while time.time()-t0<15:
    app.processEvents(); time.sleep(0.1)
    if w.stack.currentWidget() is w.search_panel and any(
        isinstance(w.search_panel._layout.itemAt(i).widget(), SearchResultRow)
        for i in range(w.search_panel._layout.count())): break
rows=[w.search_panel._layout.itemAt(i).widget() for i in range(w.search_panel._layout.count())]
rows=[r for r in rows if isinstance(r,SearchResultRow)]
ok("3 BTC 搜索结果出现", len(rows)>=1, len(rows))
ok("3 结果在独立页面", w.stack.currentWidget() is w.search_panel)
ok("3 历史已记录 BTC", (w.config.get("search_history") or []).count("BTC")==1)
if rows:
    click(rows[0]); app.processEvents()
    ok("3 点击结果行→图表页", w.stack.currentWidget() is w.chart_view)
    ok("3 点击行不默认收藏", set(w.config.get("symbols") or [])==before)
# 4 返回
w._navigate_back(); app.processEvents()
ok("4 返回回列表", w.stack.currentWidget() is w.pages[w._current_market()]["scroll"])
# 5 历史点击→重新搜索（先清空搜索框，返回列表时文本保留是既定行为）
w.edit_search.clear(); app.processEvents()
w.btn_search.click(); app.processEvents()
hist=[w.search_panel._layout.itemAt(i).widget() for i in range(w.search_panel._layout.count())]
hist=[r for r in hist if isinstance(r,SearchHistoryRow)]
ok("5 历史条目出现(BTC 最近)", len(hist)>=1 and hist[0].text_value=="BTC")
if hist:
    click(hist[0]); app.processEvents(); time.sleep(0.2); app.processEvents()
    ok("5 点击历史后仍在搜索页", w.stack.currentWidget() is w.search_panel)
    ok("5 搜索框已填入", w.edit_search.text().strip()=="BTC")
# 6 合约地址→显式收藏
w.edit_search.setText(ADDR); w.edit_search.textEdited.emit(ADDR)
t0=time.time(); oc_row=None
while time.time()-t0<25:
    app.processEvents(); time.sleep(0.15)
    rows=[w.search_panel._layout.itemAt(i).widget() for i in range(w.search_panel._layout.count())]
    for r in rows:
        if isinstance(r,SearchResultRow) and r.item["symbol"]==SYM: oc_row=r; break
    if oc_row: break
ok("6 合约解析结果出现", oc_row is not None)
if oc_row:
    ok("6 合约历史已记录", (w.config.get("search_history") or [None])[0]==ADDR)
    oc_row.btn_add.click(); app.processEvents(); time.sleep(0.3); app.processEvents()
    ok("6 显式收藏成功", SYM in w.rows and SYM in (w.config.get("symbols") or []))
    click(oc_row); app.processEvents()
    ok("6 点击行→图表页(无K线标注)", w.stack.currentWidget() is w.chart_view and getattr(w.chart_view,"_no_kline",False))
# 7 历史 100 上限 + 清空
for i in range(120): w._record_search_history("kw%d"%i)
hist=w.config.get("search_history") or []
ok("7 历史最多100条", len(hist)==100 and hist[0]=="kw119" and "BTC" not in hist)
w._on_history_cleared()
ok("7 清空历史", (w.config.get("search_history") or [])==[])
fails=[x for x in ok_ if not x[1]]
print("\n=== smoke: %d checks, %d failed ===" % (len(ok_), len(fails)))
finish(1 if fails else 0)
