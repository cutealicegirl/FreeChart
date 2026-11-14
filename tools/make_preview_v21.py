# -*- coding: utf-8 -*-
"""v21 预览图：看板娘只在图表页 / 遮挡 K 线完全消失 / 悬停工具条 / 日文气泡。

运行：
    QT_QPA_PLATFORM=windows python tools/make_preview_v21.py
输出到 preview/ 目录（PNG）。
"""
import os
import sys
import tempfile
import time

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_prev21_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication

from core.config import Config
from ui.main_window import MainWindow
from ui.mascot import MascotBubble

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "preview")


def save(widget, name, mascot=None):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    pm = widget.grab()
    if mascot is not None and mascot.isVisible():
        # grab() 只截主窗口本身；看板娘是独立顶层窗口，手动合成进来
        pos = widget.mapFromGlobal(mascot.frameGeometry().topLeft())
        scaled = mascot._current_pixmap().scaled(
            mascot.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pt = QPainter(pm)
        pt.setRenderHint(QPainter.SmoothPixmapTransform, True)
        pt.drawPixmap(pos, scaled)
        pt.end()
    pm.save(path)
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
    cfg.set("mascot_enabled", True)
    cfg.set("mascot_scale", 50)     # 配置下限是 50
    # 预览窗口不大，直接用更小的内部比例，保证有"不遮挡"的位置可放
    cfg.set("mascot_x", 60)
    cfg.set("mascot_y", 420)
    w = MainWindow(cfg)
    w.resize(1080, 820)
    w.prepare_show()
    pump(app, 3.0)

    # ---- 1. 列表页：看板娘不出现 ----
    save(w, "80_list_no_mascot.png")
    assert not w.mascot.isVisible()

    # ---- 2. 图表页：看板娘出现（放在 K 线区域外，不重叠）----
    sym = next(iter(w.rows))
    w._open_chart(sym)
    pump(app, 1.0)
    # 先把立绘缩小，再放到不遮挡的位置（默认尺寸在小窗口里必然压住 K 线）
    w.mascot._scale = 28
    w.mascot._apply_geometry()
    pump(app, 0.3)

    rect = w.chart_view.candles_global_rect().toRect()
    assert not rect.isEmpty(), "图表应已渲染出 K 线区域"
    host = w.frameGeometry()
    geo = w.mascot.frameGeometry()

    def place_mascot_outside():
        """在主窗口内挑一个与 K 线矩形不相交的位置放立绘。"""
        cands = [
            (rect.right() + 8, rect.bottom() - geo.height()),   # 右侧
            (rect.left() + 40, rect.top() - geo.height() - 4),  # 上方
            (rect.left() + 40, rect.bottom() + 6),              # 下方
        ]
        for x, y in cands:
            x = min(max(x, host.left() + 2),
                    host.right() - geo.width() - 2)
            y = min(max(y, host.top() + 2),
                    host.bottom() - geo.height() - 2)
            cand = geo.translated(x - geo.left(), y - geo.top())
            if not cand.intersects(rect):
                w.mascot.move(x, y)
                return True
        return False

    if not place_mascot_outside():
        print("DEBUG host", host, "geo", geo, "rect", rect)
        sys.exit(3)
    print("placed ok")
    pump(app, 1.2)
    assert w.mascot.isVisible(), "放在不遮挡位置应重新出现"
    save(w, "81_chart_mascot_visible.png", mascot=w.mascot)

    # ---- 3. 拖进 K 线区域：完全消失 ----
    w.mascot.move(rect.center().x() - geo.width() // 2,
                  rect.bottom() - geo.height() - 8)
    pump(app, 1.2)
    assert not w.mascot.isVisible(), "压住 K 线应完全消失"
    save(w, "82_chart_mascot_hidden.png")

    # ---- 4. 移出重叠区：重新出现 ----
    assert place_mascot_outside()
    pump(app, 1.2)
    assert w.mascot.isVisible(), "离开重叠区应重新出现"

    # ---- 5. 悬停工具条自动展开 ----
    w.chart_view._tools_hovered = True
    w.chart_view._apply_tools_visible()
    pump(app, 0.2)
    assert w.chart_view.tools_panel.isVisible()
    save(w, "83_chart_tools_hover.png")
    w.chart_view._tools_hovered = False
    w.chart_view._apply_tools_visible()
    pump(app, 0.2)

    # ---- 6. 日文气泡 ----
    b = MascotBubble()
    b.set_style("candy")
    b._text = "おかえりなさい、ご主人様～一緒に K 緿を見ましょうね！"
    b._text = "おかえりなさい、ご主人様～一緒にK線を見ましょうね！"
    b.resize(b._measure())
    pm = b.grab()
    pm.save(os.path.join(OUT, "84_bubble_jp.png"))
    print("saved", os.path.join(OUT, "84_bubble_jp.png"))

    try:
        w.live.shutdown()
    except Exception:
        pass
    w.scheduler.stop()
    w.close()
    pump(app, 0.1)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
