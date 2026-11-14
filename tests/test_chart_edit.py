# -*- coding: utf-8 -*-
"""指标开关 / 搜索提示词 / 画线二次调整 测试。"""
import os
import sys
import tempfile

# 关键：测试使用临时配置目录，绝不污染真实 %APPDATA%/CryptoTicker/config.json
_TMP = tempfile.mkdtemp(prefix="ct_test_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, ".")

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import QApplication

from core.config import Config
from ui.main_window import MainWindow

app = QApplication([])
cfg = Config()
w = MainWindow(cfg)
w.show()
cv = w.chart_view
chart = cv.chart


def step1():
    print("== 1. 搜索框提示词 ==")
    ph = w.edit_search.placeholderText()
    print("placeholder:", repr(ph))
    assert len(ph) <= 6, "提示词仍过长"

    print("== 2. 指标显示/隐藏 + 持久化 ==")
    assert chart.show_ma and chart.show_macd and chart.show_vol
    btn_macd = cv._indicator_buttons["show_macd"]
    btn_macd.click()
    assert not chart.show_macd and not cfg.get("show_macd")
    # 隐藏 MACD 后主图应自动占更多高度（几何重算）
    w._open_chart("BTC")
    QTimer.singleShot(4000, step2)


def step2():
    g = chart._geom()
    assert g["macd"] is None and g["vol"] is not None
    price_ratio_hidden = g["price"].height() / (
        chart.height() - chart._margin_t - chart._margin_b)
    # 打开 MACD 再比较
    cv._indicator_buttons["show_macd"].click()
    g2 = chart._geom()
    price_ratio_full = g2["price"].height() / (
        chart.height() - chart._margin_t - chart._margin_b)
    print(f"主图高度占比: 隐藏MACD {price_ratio_hidden:.2f} "
          f"-> 显示MACD {price_ratio_full:.2f}")
    assert price_ratio_hidden > price_ratio_full + 0.05
    assert cfg.get("show_macd") is True
    # MA / VOL 独立开关
    cv._indicator_buttons["show_ma"].click()
    cv._indicator_buttons["show_vol"].click()
    assert not chart.show_ma and not chart.show_vol
    g3 = chart._geom()
    assert g3["vol"] is None and g3["macd"] is not None
    # 全关时主图占满
    cv._indicator_buttons["show_macd"].click()
    g4 = chart._geom()
    full_h = chart.height() - chart._margin_t - chart._margin_b
    assert abs(g4["price"].height() - full_h) < 1.0
    # 恢复全开（避免影响后续绘制断言）
    for k in ("show_ma", "show_macd", "show_vol"):
        if not getattr(chart, k):
            cv._indicator_buttons[k].click()
    chart.repaint()
    print("指标开关 OK（含配置持久化与几何自适应）")

    print("== 3. 画完自动回光标模式 ==")
    cv._set_tool("hline")
    assert chart._tool == "hline"
    assert cv._tool_buttons["hline"].isChecked()
    # 直接触发绘制完成信号链路
    chart._lines.append({"kind": "hline", "price": 75000.0})
    chart._selected = chart._lines[-1]
    chart.tool_finished.emit()
    assert chart._tool == "none" and not cv._tool_buttons["hline"].isChecked()
    print("自动回光标 OK")

    print("== 4. 二次调整：拖动端点 / 整体平移 ==")
    chart.set_drawings([
        {"kind": "trend", "p1": (chart.candles[-60].ts, 70000.0),
         "p2": (chart.candles[-10].ts, 80000.0)},
    ])
    line = chart._lines[0]
    g = chart._geom()
    orig = dict(line)
    start = QPoint(int(chart.width() * 0.5), int(chart.height() * 0.3))
    # 模拟：在端点处按下 -> 拖动 +40px / +20px -> 松开
    pts = chart._line_points(g, line)
    chart._drag = {"line": line, "mode": "p1",
                   "start": (int(pts[0]), int(pts[1])), "orig": orig}
    chart._apply_drag(g, QPoint(int(pts[0]) + 40, int(pts[1]) + 20))
    assert line["p1"] != orig["p1"], "拖动端点后坐标应改变"
    print("端点拖动 OK:", orig["p1"], "->", line["p1"])
    # 整体平移：两个点都变，斜率保持
    chart._drag = {"line": line, "mode": "move",
                   "start": (start.x(), start.y()), "orig": dict(line)}
    chart._apply_drag(g, QPoint(start.x() + 25, start.y() + 15))
    assert line["p1"] != orig["p1"] and line["p2"] != orig["p2"]
    print("整体平移 OK")

    # Delete 删除选中线
    chart._selected = line
    chart.keyPressEvent(_key(Qt.Key_Delete))
    assert len(chart._lines) == 0, "Delete 应删除选中线"
    # 清空按钮
    chart.set_drawings([{"kind": "hline", "price": 1.0}])
    cv._tool_buttons["none"].click()
    chart.clear_drawings()
    assert len(chart._lines) == 0
    print("Delete / 清空 OK")

    # 渲染一遍确认无异常（三面板 + 选中态 + 画线）
    chart.repaint()
    print("\n全部测试通过 ✅")
    w.quit_app()


class _key:
    """极简 QKeyEvent 替身（仅用于 keyPressEvent 分支判断）。"""
    def __init__(self, k):
        self._k = k

    def key(self):
        return self._k


QTimer.singleShot(3500, step1)
app.exec()
