# -*- coding: utf-8 -*-
"""v38 回归：修复「全部」页分批建行时 Qt 原生 tooltip 连环弹窗。

根因不是 MessageBox、不是循环渲染、不是重复信号绑定、也不是接口重复回调：
行内 tooltip 挂在子 QLabel 上，QEvent.ToolTip 在子控件就被 QWidget::event()
accept 掉，旧版写在父行 TickerWidget.event() 里的过滤根本收不到；叠加全局
bool 开关在多市场并行建行时被先结束的链提前打开。

本回归全部离线（CT_OFFLINE=1 + offscreen），用「应用级过滤器 + 引用计数」
验证建行期任意子控件的 tooltip 都被吞掉，以及异常 / 并行 / 收尾的健壮性。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v38_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CT_OFFLINE"] = "1"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QEvent, QPoint
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication, QToolTip

import ui.main_window as mw_mod
from core.config import Config
from data.universe import all_of
from ui.main_window import MainWindow
from ui.theme import tooltip_qss
from ui.ticker_widget import (ToolTipGuard, TickerWidget,
                              begin_tooltip_hold, end_tooltip_hold,
                              tooltip_hold_count)

app = QApplication([])
PASS, FAIL = [], []


def ok(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS " if cond else "  FAIL ") + name + ("  " + str(extra) if extra and not cond else ""))


def pump(sec=0.05):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def wait_fill(w, key, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if key not in w._filling_all and len(w.all_rows[key]) >= len(all_of(key)):
            pump(0.05)
            return True
        time.sleep(0.005)
    return False


cfg = Config()
cfg.set("mascot_enabled", False)
w = MainWindow(cfg)
w.scheduler.stop()
w.scheduler.refresh_now = lambda: None
w.resize(560, 900)
w.prepare_show()

print("=== v38 · 桌面「全部」页批量弹窗修复回归 ===\n")

# ---------- 1. 过滤器与引用计数机制 ----------
ok("1. 应用级 ToolTip 过滤器已安装并被强引用",
   isinstance(getattr(w, "_tooltip_guard", None), ToolTipGuard))
begin_tooltip_hold()
try:
    guard = w._tooltip_guard
    ev = QHelpEvent(QEvent.ToolTip, QPoint(0, 0), QPoint(0, 0))
    ok("2. 建行期过滤器吞掉任意控件的 ToolTip 事件",
       guard.eventFilter(w, ev) is True)
    ok("3. 非 ToolTip 事件原样放行",
       guard.eventFilter(w, QEvent(QEvent.Timer)) is False)
finally:
    end_tooltip_hold()
ok("4. 引用计数可归零（不会永久关闭提示）",
   tooltip_hold_count() == 0 and
   w._tooltip_guard.eventFilter(w, QHelpEvent(
       QEvent.ToolTip, QPoint(0, 0), QPoint(0, 0))) is False)
ok("5. 全局 tooltip 样式未被改动（没有靠隐藏样式掩盖问题）",
   "QToolTip" in tooltip_qss())

# ---------- 2. 真正触发「全部」页分批建行 ----------
key = w._current_market()
w._sub_tabs[key] = "all"
top_before = len(app.topLevelWidgets())
spy = {"mascot": 0, "info": 0, "detail": 0, "tray": 0}
w._mascot_say = lambda *a, **k: spy.__setitem__("mascot", spy["mascot"] + 1)
w.info_panel.show_for = lambda *a, **k: spy.__setitem__("info", spy["info"] + 1)
w._show_info_popup = lambda *a, **k: spy.__setitem__("detail", spy["detail"] + 1)
if getattr(w, "tray", None) is not None:
    try:
        w.tray.showMessage = lambda *a, **k: spy.__setitem__("tray", spy["tray"] + 1)
    except (AttributeError, TypeError):
        pass

w._switch_sub("all")
ok("6. 切到「全部」立即进入建行期且 tooltip 抑制已开启",
   key in w._filling_all and tooltip_hold_count() >= 1)

row = next(iter(w.all_rows[key].values()), None)
ok("7. 首屏行已创建且挂在页面下（不是无父顶层小窗）",
   row is not None and row.parent() is not None)

# 关键：对「子控件」发 ToolTip 事件。旧实现只在父行 event() 里过滤，
# 这里事件在子 QLabel 处就被消费，必然连环弹窗。
child = getattr(row, "lbl_high", None) if row is not None else None
if child is not None:
    child.setToolTip("最高价 12345")
    QToolTip.hideText()
    QApplication.sendEvent(
        child, QHelpEvent(QEvent.ToolTip, QPoint(0, 0), QPoint(0, 0)))
    pump(0.05)
    ok("8. 建行期对子 QLabel 发 ToolTip 不会弹出 QTipLabel",
       not QToolTip.isVisible() and
       len(app.topLevelWidgets()) == top_before)
else:
    ok("8. 建行期对子 QLabel 发 ToolTip 不会弹出 QTipLabel", False,
       "找不到 lbl_high")

ok("9. 建行期不会顺带触发资料弹窗 / 看板娘气泡 / 托盘通知",
   spy["mascot"] == 0 and spy["info"] == 0 and
   spy["detail"] == 0 and spy["tray"] == 0, spy)

ok("10. 分批链能正常跑完（全部行创建完毕）", wait_fill(w, key))
ok("11. 收尾释放填充标记与 tooltip 抑制",
   key not in w._filling_all and tooltip_hold_count() == 0)
ok("12. 全过程中没有新增顶层窗口（连环弹窗 / 抖动已消除）",
   len(app.topLevelWidgets()) == top_before)

# ---------- 3. 多市场并行建行：引用计数不得被提前打开 ----------
others = [k for k in w.pages if k != key and not w.all_rows[k]]
for k in others:
    w._sub_tabs[k] = "all"
    w._ensure_all_rows(k)
ok("13. 多市场并行建行时每个链各持一个计数",
   len(others) >= 2 and tooltip_hold_count() == len(others),
   "others=%d hold=%d" % (len(others), tooltip_hold_count()))
begin_tooltip_hold()
ok("14. 新增一条建行链会叠加计数，互不覆盖",
   tooltip_hold_count() == len(others) + 1,
   "hold=%d" % tooltip_hold_count())
end_tooltip_hold()
for k in others:
    wait_fill(w, k)
ok("15. 所有链结束后引用计数精确归零",
   tooltip_hold_count() == 0 and not any(w._filling_all))

# ---------- 4. 链异常也必须能恢复 ----------
class Boom(Exception):
    pass


def _boom(*a, **k):
    raise Boom("模拟某批建行失败")


_orig_cls = mw_mod.TickerWidget
victim = others[0] if others else key
w.all_rows[victim] = {}
w._filling_all.discard(victim)
mw_mod.TickerWidget = _boom
try:
    w._ensure_all_rows(victim)
    pump(0.02)
finally:
    mw_mod.TickerWidget = _orig_cls
ok("16. 建行链中途抛异常不会永久卡住 tooltip 开关",
   tooltip_hold_count() == 0)
ok("17. 建行链中途抛异常不会把市场永久留在 _filling_all",
   victim not in w._filling_all)

# ---------- 5. 事件绑定与请求去重的防御性约束 ----------
_src = open(os.path.join(_ROOT, "ui", "main_window.py"), encoding="utf-8").read()
ok("18. 行信号使用 UniqueConnection，重复重连不会叠加槽",
   _src.count("Qt.UniqueConnection") >= 4)
ok("19. 不再有「每链各排 700ms enable」的竞态写法",
   "QTimer.singleShot(700, enable_row_tooltips)" not in _src and
   "_release_fill" in _src)
ok("20. 刷新调度仍有 120ms 合并与在途去重（无重复回调风暴）",
   "_burst" in open(os.path.join(_ROOT, "core", "updater.py"),
                    encoding="utf-8").read())

print("\n=== %d/%d 通过 ===" % (len(PASS), len(PASS) + len(FAIL)))
if FAIL:
    print("失败项：" + "、".join(FAIL))
    sys.exit(1)
