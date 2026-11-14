# -*- coding: utf-8 -*-
"""v20 回归：页面残留行（幽灵自选）/ 悬停资料卡 / 图表详情 / 底栏合并 /
多套可爱气泡 / 遮挡即完全隐藏。

覆盖：
1. 「全部 → 自选」切换后，页面上只留下自选行，不再残留上一子页的行；
2. 正在看「全部」时新增自选，不会往全部列表里插一行；
3. 鼠标悬停哪一行，上方资料卡就切到哪一只（70ms 防抖）；
4. 底部导航只剩 行情 / 设置（图表并入行情：点行即进图）；
5. 图表页有「详情」按钮且能弹出详情抽屉，字段有值；
6. 气泡 5 套风格可切，配置持久化，绘制不抛异常；
7. 看板娘压住 K 线时完全消失，离开重叠区重新出现。

全部离线（临时 APPDATA + offscreen）。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v20_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QPointF
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import QApplication

from core.config import Config
from data.universe import market_of
from ui.main_window import MainWindow
from ui.mascot import BUBBLE_STYLES, MascotBubble
from ui.ticker_widget import TickerWidget

app = QApplication([])


def pump(sec=0.05):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def wait_fill(window, timeout=15.0):
    end = time.time() + timeout
    while window._filling_all and time.time() < end:
        app.processEvents()
        time.sleep(0.01)
    pump(0.1)


def visible_rows(page_widget):
    return [w for w in page_widget.findChildren(TickerWidget) if w.isVisible()]


# ================= 0. 准备 =================
w = MainWindow(Config())
w.resize(560, 900)
w.prepare_show()
pump(0.4)
key = w._current_market()
page = w.pages[key]["page"]
watch_syms = [s for s in w.rows if market_of(s) == key]
assert watch_syms, "测试环境应有自选品种"

# 先把某个市场的「全部」页建出来（分批建行 + 图标补全）
w._switch_sub("all")
wait_fill(w)
pump(0.3)
assert len(w.all_rows[key]) > len(watch_syms), "全部页应远多于自选"
print("0. 「全部」页建行完成：%d 行 OK" % len(w.all_rows[key]))

# ================= 1. 切回自选不留残影 =================
w._switch_sub("watch")
pump(0.3)
vis = visible_rows(page)
assert len(vis) == len(watch_syms), \
    f"自选页应只剩 {len(watch_syms)} 行，实际可见 {len(vis)} 行（有幽灵行）"
ghosts = [r.symbol for r in vis if r.symbol not in w.rows]
assert not ghosts, f"自选页出现了没添加的品种：{ghosts[:5]}"
layout_rows = [page.layout().itemAt(i).widget()
               for i in range(page.layout().count())]
layout_rows = [r for r in layout_rows if r is not None]
assert len(layout_rows) == len(watch_syms), \
    f"布局里也只该有自选行，实际 {len(layout_rows)}"
print("1. 全部→自选 无残留行（可见 %d / 期望 %d）OK"
      % (len(vis), len(watch_syms)))

# ================= 2. 「全部」页新增自选不插队 =================
w._switch_sub("all")
wait_fill(w)
pump(0.2)
candidate = next((s for s in w.all_rows[key] if s not in w.rows), None)
assert candidate, "全部页应有未加入自选的品种"
before = len(page.layout().count() and
             [page.layout().itemAt(i).widget()
              for i in range(page.layout().count())
              if page.layout().itemAt(i).widget() is not None])
w._add_symbol(candidate)
pump(0.3)
after_rows = [page.layout().itemAt(i).widget()
              for i in range(page.layout().count())
              if page.layout().itemAt(i).widget() is not None]
assert all(isinstance(r, TickerWidget) for r in after_rows)
assert len(after_rows) >= before, "加入自选不应让全部页少行"
# 全部页里仍然是全部品种（新加的那个不算重复插入）
counts = {}
for r in after_rows:
    counts[r.symbol] = counts.get(r.symbol, 0) + 1
dups = [s for s, n in counts.items() if n > 1]
assert not dups, f"全部页出现重复行：{dups[:5]}"
print("2. 全部页加入自选不插队、不重复 OK")

# ================= 3. 右键「查看资料」切换资料卡（v23 起不再悬停自动弹） =================
w._switch_sub("watch")
pump(0.2)
targets = watch_syms[:3]
for sym in targets:
    row = w.rows[sym]
    assert row.isVisible()
    row.hovered.emit(sym)              # 悬停不再改变焦点
    pump(0.15)
    w._show_info_popup(sym)            # 右键菜单 -> 查看资料
    pump(0.05)
    assert w._focus_symbol == sym, f"查看 {sym} 后焦点应为它"
    assert w.info_panel._symbol == sym, \
        f"资料卡应切到 {sym}，实际 {w.info_panel._symbol}"
    assert w.info_panel.isVisible(), "右键选中后资料卡应弹出"
    w.info_panel.hide_popup()
print("3. 右键「查看资料」弹出的资料卡跟着行切换 OK")

# ================= 4. 三选项卡底栏 + 点行进图 =================
assert set(w.bottom_nav.buttons) == {"list", "chart", "settings"}, \
    f"阶段 5 底栏应为行情/图表/设置，实际 {set(w.bottom_nav.buttons)}"
w._open_chart(targets[0])
pump(0.3)
assert w.stack.currentWidget() is w.chart_view, "点行应进入图表页"
assert w.bottom_nav.buttons["chart"].isChecked(), "图表页应高亮「图表」"
print("4. 三选项卡底栏 + 点品种进图表 OK")

# ================= 5. 图表页详情按钮 =================
assert hasattr(w.chart_view, "btn_detail"), "图表页应有详情按钮"
assert "详情" in w.chart_view.btn_detail.text()
from ui.detail_dialog import SymbolDetailDialog
dlg = SymbolDetailDialog(w.chart_view._symbol, "测试",
                         w._last_tickers.get(w.chart_view._symbol), w)
pump(0.4)
assert dlg.lbl_code.text(), "详情应显示代码"
assert dlg._quote_cells["unit"].val.text() not in ("", "—"), "应有计价货币"
assert dlg._fund_cells["cap"].val.text() not in ("",), "应有总市值字段"
dlg.close()
dlg.deleteLater()
pump(0.1)
print("5. 图表页「ⓘ 详情」弹出完整资料 OK")

# ================= 6. 多套二次元气泡 =================
assert len(BUBBLE_STYLES) >= 4, "至少提供 4 套气泡风格"
b = MascotBubble()
seen = []
for k in BUBBLE_STYLES:
    b.set_style(k)
    assert b.style_key() == k, f"风格应为 {k}，实际 {b.style_key()}"
    b._text = "主人，ETH 涨了 +7.80% 啦～"
    b.resize(b._measure())
    pm = b.grab()                 # 绘制一遍，确保 paintEvent 不抛异常
    assert not pm.isNull() and pm.width() > 40
    seen.append(pm.toImage().pixelColor(pm.width() // 2, 6).name())
assert len(set(seen)) >= 3, f"不同风格的配色应不同：{seen}"
cfg = Config()
cfg.set("mascot_bubble_style", "sakura")
cfg.save()
assert Config().get("mascot_bubble_style") == "sakura", "气泡风格应持久化"
w.config.set("mascot_bubble_style", "candy")
print("6. 气泡风格 %d 套，可切换 / 可持久化 OK" % len(BUBBLE_STYLES))

# ================= 7. 遮挡 K 线时完全消失 / 离开重现 =================
m = w.mascot
assert m is not None, "测试环境应有看板娘对象"
# 这一节单测看板娘自己的隐藏/重现语义；把主窗口的重叠轮询停掉，
# 否则它会按真实几何（立绘不在 K 线上）立刻把立绘放回来
w._mascot_timer.stop()
m._opacity = 100
m._enabled = True
m._hidden_by_overlap = False
m._scene_ok = True          # 直接给场景许可（本节不走主窗口事件）
m.show()
m._apply_opacity()
pump(0.15)
assert m.isVisible() and abs(m.windowOpacity() - 1.0) < 0.05, \
    (m.isVisible(), m.windowOpacity())

m.set_overlap(0.3)          # 压住 K 线
for _ in range(30):
    pump(0.02)
assert not m.isVisible(), f"重叠应完全消失（opacity={m.windowOpacity()}）"

m.set_overlap(0.9)          # 更重叠：保持隐藏
for _ in range(10):
    pump(0.02)
assert not m.isVisible()

m.set_overlap(0.0)          # 不重叠了：重新出现并淡回原不透明度
for _ in range(30):
    pump(0.02)
assert m.isVisible(), "离开重叠区应重新出现"
assert abs(m.windowOpacity() - 1.0) < 0.06, m.windowOpacity()
m._scene_ok = False         # 还原场景状态，避免影响收尾
if m._fade is not None:     # 收掉还在跑的淡入淡出动画，否则退出码会变 127
    m._fade.stop()
    m._fade = None
m._bubble.dismiss()
m.hide()
m._sync_visible()
print("7. 看板娘：遮挡完全消失 / 离开重现 OK")

# ================= 收尾 =================
try:
    w.live.shutdown()
except Exception:
    pass
w.scheduler.stop()
if getattr(w, "mascot", None) is not None:
    try:
        if w.mascot._fade is not None:
            w.mascot._fade.stop()
        w.mascot._bubble.dismiss()
        w.mascot.hide()
    except RuntimeError:
        pass
w.close()
pump(0.1)
from qt_exit import finish           # 跳过 offscreen 的 Qt 卸载竞态
print("\nv20 全部回归测试通过 ✅")
finish()
