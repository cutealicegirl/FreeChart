# -*- coding: utf-8 -*-
"""v22 回归：悬停资料弹窗 / 弹窗主题统一 / 设置独立页 / 缩放锚点 /
跨图表视口保留 / 项目与创始人介绍。

全部离线（临时 APPDATA + offscreen + CT_OFFLINE）。
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v22_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CT_OFFLINE"] = "1"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QDialog, QFrame

from core.config import Config
from data import fundamentals
from data.klines import Candle
from data.universe import market_of
from ui.chart_view import CandleChart, ChartView
from ui.detail_dialog import SymbolDetailDialog
from ui.main_window import MainWindow
from ui.popup import popup_qss
from ui.settings_dialog import SettingsPage
from ui.theme import dialog_qss

app = QApplication([])


def pump(sec=0.1):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def make_candles(n=300):
    return [Candle(ts=1600000000 + i * 86400, time_label=str(i),
                   open=100 + i % 7, high=105 + i % 9, low=95 + i % 5,
                   close=101 + i % 6, volume=1000 + i) for i in range(n)]


def wheel(chart, down=True, x=400):
    d = -120 if down else 120
    ev = QWheelEvent(QPointF(x, 200), QPointF(x, 200), QPoint(0, 0),
                     QPoint(0, d), Qt.NoButton, Qt.NoModifier,
                     Qt.ScrollUpdate, False)
    chart.wheelEvent(ev)


def anchor_index(chart, x):
    """屏幕 x 处对应第几根 K 线（浮点索引）。"""
    w = max(60.0, chart.width() - chart._margin_l - chart._margin_r)
    right_px = chart._margin_l + w
    return chart._right_edge() - (right_px - x) / (w / chart._view_count)


cfg = Config()
cfg.set("mascot_enabled", False)
cfg.set("price_badge", False)
w = MainWindow(cfg)
w.resize(900, 760)
w.prepare_show()
w.show()
pump(0.2)

# ============ 1. 行情资料弹窗（v23 起右键菜单选中才弹出） ============
assert w.info_panel is not None
assert w.info_panel not in w._list_controls, "资料卡不该再占列表上方布局"
assert w.info_panel.parentWidget() is not None, "浮层应挂在主窗口内"
assert not w.info_panel.isVisible(), "未选中前不该显示"
sym = next(iter(w.rows))
row = w.rows[sym]
assert row.isVisible(), "测试行应可见"
# 悬停不再自动弹出（v23：只走右键菜单）
row.hovered.emit(sym)
pump(0.2)
assert not w.info_panel.isVisible(), "悬停不该自动弹出资料卡"
# 右键菜单 -> 查看资料
w._show_info_popup(sym)
pump(0.05)
assert w.info_panel.isVisible(), "右键选中「查看资料」后应弹出资料卡"
assert w.info_panel._symbol == sym, (w.info_panel._symbol, sym)
tl = w.info_panel.mapToGlobal(QPoint(0, 0))
frame = w.frameGeometry()
assert frame.left() - 4 <= tl.x() <= frame.right(), \
    f"浮层跑出软件左侧: {tl.x()} / {frame}"
assert frame.top() - 4 <= tl.y() <= frame.bottom(), \
    f"浮层跑出软件上下: {tl.y()} / {frame}"
# 用户主动打开的弹窗必须有关闭按钮
assert not w.info_panel.btn_close.isHidden(), "资料卡应带 ✕ 关闭按钮"
w.info_panel.hide_popup()
assert not w.info_panel.isVisible(), "关闭后应收起"
print("1. 右键菜单弹出资料卡 / 可关闭 / 不出软件边界 OK")

# ============ 2. 全程序弹窗风格主题统一 ============
assert dialog_qss() == popup_qss(), "theme.dialog_qss 应转发到统一弹窗样式"
assert w.info_panel.objectName() == "popupSurface"
assert w.info_panel.head.objectName() == "popupHead"
assert w.info_panel.findChild(QFrame, "popupCard") is not None
assert w.settings_page.styleSheet() == popup_qss()
assert w.settings_page.findChild(QFrame, "popupHead") is not None
dlg = SymbolDetailDialog("BTC", "Bitcoin", parent=w)
assert dlg.styleSheet() == popup_qss()
assert dlg.findChild(QFrame, "popupHead") is not None
assert dlg.findChild(QFrame, "popupCard") is not None
assert "popupPrimary" in popup_qss() and "popupNote" in popup_qss()
print("2. 设置页 / 详情抽屉 / 悬停卡共用一套弹窗规格 OK")

# ============ 3. 设置是独立界面，不是弹窗 ============
assert not isinstance(w.settings_page, QDialog), "设置不该是 QDialog 弹窗"
assert w.stack.indexOf(w.settings_page) >= 0, "设置应是主窗口的一页"
before = w.stack.currentWidget()
w.open_settings()
pump(0.05)
assert w.stack.currentWidget() is w.settings_page, "点设置应切到独立页面"
w._close_settings_page()
pump(0.05)
assert w.stack.currentWidget() is before, "取消后应回到原页面"
print("3. 设置改为 QStackedWidget 独立页面 OK")

# ============ 4. 滚轮缩放以原 K 线为锚点，不再强制对齐最右侧 ============
c = CandleChart()
c.resize(1000, 600)
c.set_data(make_candles(300))
c.history_exhausted = True
c._view_count = 90.0
c._pan = 12.0                    # 用户已平移过，不在最新一根
ax = 400
for down in (False, True, True, False):
    before_idx = anchor_index(c, ax)
    before_vc = c._view_count
    wheel(c, down=down, x=ax)
    after_idx = anchor_index(c, ax)
    assert abs(before_idx - after_idx) < 1e-6, \
        f"缩放锚点漂移: {before_idx} -> {after_idx}"
    assert c._pan != 0.0, "缩放不得把最新一根强制对齐到最右侧"
    assert abs(c._pan + (c._view_count - len(c.candles)) / 2) > 1e-6, \
        "缩放不得强制整块居中"
    assert (c._view_count > before_vc) == down, "上滚放大 / 下滚缩小"
print("4. 缩放锚点保持、不贴右 / 不强制居中 OK")

# ============ 5. 进入新图表保留缩放级别与位置 ============
import ui.chart_view as cv_mod
cv_mod.ChartView._load = lambda self: None            # 离线：不发起 K 线请求
cv_mod.ChartView._ensure_extremes_history = lambda self: None
cv_mod.ChartView._prefetch_intervals = lambda self: None
cv_mod.kline_cache.is_fresh = lambda *a, **k: True

cv = ChartView(cfg)
cv.chart.set_data(make_candles(300))
cv.chart._view_count = 137.0
cv.chart._pan = 9.0
cv._on_view_changed()
state = cv.chart.view_state()
cv._symbol = "BTC"
cv.close_chart()                 # 离开图表：记下并写盘
assert abs(Config().get("chart_view_count") - 137.0) < 1e-6
cv.open("ETH")
pump(0.1)
assert abs(cv.chart._view_count - state["view_count"]) < 1e-6, \
    (cv.chart._view_count, state)
assert abs(cv.chart._pan - state["pan"]) < 1e-6, (cv.chart._pan, state)
assert cv.chart._view_touched, "恢复后不得被新数据自动居中回去"
# 重启后也能从配置恢复
cv2 = ChartView(Config())
assert abs(cv2._view_state["view_count"] - 137.0) < 1e-6
print("5. 换品种 / 重启保留缩放与位置 OK")

# ============ 6. 项目 / 公司 / 产品 / 创始人介绍 ============
a = fundamentals.about("BTC", "Bitcoin")
assert "中本聪" in (a.get("founder") or ""), a
assert len(a.get("summary") or "") > 30
assert a.get("product") and a.get("category")
w.info_panel.set_symbol("BTC", "Bitcoin")
assert "中本聪" in w.info_panel.lbl_about.text(), \
    w.info_panel.lbl_about.text()
assert "创始人" in w.info_panel.lbl_about.text()
assert "中本聪" in dlg.lbl_about.text(), "详情抽屉也要有创始人介绍"
assert dlg.lbl_about_meta.text(), "详情抽屉应显示项目名 / 类型 / 创立年份"
# 未收录品种也要有兜底介绍，不能空白
fallback = fundamentals.about("US:ZZZZ", "未知公司")
assert fallback.get("summary") and fallback.get("category")
print("6. 悬停卡 / 详情抽屉均含项目 · 创始人介绍（含兜底）OK")

# ============ 收尾 ============
try:
    w.live.shutdown()
except Exception:
    pass
w.scheduler.stop()
cv.close_chart()
cv2.close_chart()
dlg.close()
w.close()
pump(0.05)
from qt_exit import finish       # 跳过 offscreen 的 Qt 卸载竞态
print("\nv22 全部回归测试通过 ✅")
finish()
