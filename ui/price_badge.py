# -*- coding: utf-8 -*-
"""任务栏右侧「常驻实时价格」——单行自适应宽度的任务栏小工具。

布局演进：旧版是 158x40 的两行方块（上行 图标/代码/涨跌幅，下行 价格），
在任务栏这条水平细带上显得笨重、占地方。现在改成**单行胶囊**：

    [图标] BTC  97,234.58  +1.23%

- 高度 28px（旧版 40px），垂直居中，和任务栏图标同一水平线；
- 宽度按内容实时测量：价格位数变化不会留下固定空白；
- 字号分三级（代码 10 / 价格 13 半粗 / 涨跌 10），价格最醒目，
  名称与数值用不同颜色分开，不糊成一团；
- 极淡的胶囊底（跟随任务栏浅色 / 深色），任何壁纸下文字都可读，
  但不会像卡片那样抢眼；
- 右键可在「完整 / 紧凑 / 极简」三档之间切换，嫌占地方就切极简。
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QColor, QFont, QFontMetricsF, QPainter,
                           QPainterPath)
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from core import brand
from core.taskbar import BADGE_TITLE, dock_geometry, system_is_light
from ui.icons import display_code, symbol_icon
from ui.theme import (C_DOWN, C_TEXT_DIM, C_TEXT_MAIN, C_TEXT_SUB, C_UP,
                      menu_qss)
from ui import units
from ui.ticker_widget import format_price
from ui.units import with_unit

_DARK = {"main": C_TEXT_MAIN, "sub": C_TEXT_SUB, "dim": C_TEXT_DIM,
         "up": C_UP, "down": C_DOWN}
_LIGHT = {"main": "#14171c", "sub": "#454b54", "dim": "#6b7280",
          "up": "#c62828", "down": "#0b8a55"}

# 三档信息密度：完整 / 紧凑 / 极简
STYLES = (("full", "完整（代码 + 价格 + 涨跌幅）"),
          ("slim", "紧凑（价格 + 涨跌幅）"),
          ("mini", "极简（只显示价格）"))


def _mono(px: int, bold: bool = False) -> QFont:
    """等宽数字字体：价格跳动时不会左右抖。"""
    f = QFont()
    f.setFamilies(["IBM Plex Mono", "Consolas", "Courier New", "monospace"])
    f.setPixelSize(px)
    f.setBold(bold)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


class PriceBadge(QWidget):
    show_requested = Signal()
    symbol_changed = Signal(str)
    visibility_changed = Signal(bool)

    HEIGHT = 28          # 单行高度：旧版两行方块是 40
    PAD = 8              # 左右内边距
    ICON = 14            # 品种图标边长
    W_MIN = 74
    W_MAX = 208

    def __init__(self, config, parent=None):
        # 不设父窗口：主窗口 hide() 时小工具不会被连带隐藏
        super().__init__(None)
        self._cfg = config
        self._symbol = ""
        self._price_text = "--"
        self._change_raw = ""      # 原始涨跌幅文本，按样式决定是否绘制
        self._has_data = False
        self._up = True
        self._light = system_is_light()
        self._pal = _LIGHT if self._light else _DARK
        self._icon_pm = None
        self._lay = None
        self._candidates = []        # 主窗口注入的可指定品种清单
        self._fonts = {"code": _mono(10), "price": _mono(13, True),
                       "chg": _mono(10)}
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint |
                            Qt.WindowStaysOnTopHint |
                            Qt.WindowDoesNotAcceptFocus)
        self.setWindowTitle(BADGE_TITLE)     # 标记，多实例时互不当成别人小工具
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(self.W_MIN, self.HEIGHT)
        self.setCursor(Qt.ArrowCursor)
        self.setToolTip(brand.BADGE_TOOLTIP)

        # 任务栏可能被系统重绘覆盖，定时重新贴靠并置顶
        self._dock_timer = QTimer(self)
        self._dock_timer.setInterval(1500)
        self._dock_timer.timeout.connect(self.dock)

    # ---- 布局：按内容测量宽度，绝不留固定空白 ----
    def _style(self) -> str:
        style = str(self._cfg.get("price_badge_style") or "full")
        return style if style in ("full", "slim", "mini") else "full"

    def _build(self, f_price: QFont, code: str, price: str, chg: str,
               show_code: bool, show_chg: bool):
        fm_p = QFontMetricsF(f_price)
        fm_c = QFontMetricsF(self._fonts["code"])
        fm_g = QFontMetricsF(self._fonts["chg"])
        x = self.PAD + self.ICON
        x_code = x_price = x_chg = 0.0
        if show_code:
            x += 5
            x_code = x
            x += fm_c.horizontalAdvance(code) + 6
        else:
            x += 5                 # 没有代码时也要和图标拉开，避免贴在一起
        x_price = x
        x += fm_p.horizontalAdvance(price)
        if show_chg:
            x += 5
            x_chg = x
            x += fm_g.horizontalAdvance(chg)
        w = int(math.ceil(x + self.PAD))
        return {"w": max(self.W_MIN, w),
                "x_code": x_code, "x_price": x_price, "x_chg": x_chg,
                "f_price": f_price, "show_code": show_code,
                "show_chg": show_chg}

    def _layout(self):
        """内容超宽时依次：降一档字号 → 隐藏代码 → 隐藏涨跌幅。

        注意不能直接把宽度夹到上限就完事，那样文字会画出胶囊外面。
        """
        if self._lay is not None:
            return self._lay
        style = self._style()
        code = display_code(self._symbol) if self._symbol else "---"
        price = self._price_text or "--"
        chg = self._change_raw
        show_code = style == "full"
        show_chg = style in ("full", "slim") and bool(chg)
        lay = self._build(self._fonts["price"], code, price, chg,
                          show_code, show_chg)
        if lay["w"] > self.W_MAX:            # 超长价格：降字号
            alt = self._build(_mono(12, True), code, price, chg,
                              show_code, show_chg)
            if alt["w"] < lay["w"]:
                lay = alt
        if lay["w"] > self.W_MAX and lay["show_code"]:
            alt = self._build(lay["f_price"], code, price, chg,
                              False, lay["show_chg"])
            if alt["w"] < lay["w"]:
                lay = alt
        if lay["w"] > self.W_MAX and lay["show_chg"]:
            alt = self._build(lay["f_price"], code, price, chg,
                              lay["show_code"], False)
            lay = alt
        lay["w"] = min(lay["w"], self.W_MAX)
        self._lay = lay
        return lay

    # ---- 绘制 ----
    def paintEvent(self, event):
        lay = self._layout()
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing |
                         QPainter.SmoothPixmapTransform)
        # 极淡胶囊底：保证任意壁纸下可读，又不像卡片那样抢眼
        # 浅色任务栏接近纯白，胶囊要非常淡，否则像贴了一块灰补丁
        bg = QColor("#000000" if self._light else "#ffffff")
        bg.setAlpha(10 if self._light else 16)
        radius = (h - 1) / 2.0
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0),
                            radius, radius)
        p.fillPath(path, bg)

        if self._icon_pm is not None and not self._icon_pm.isNull():
            p.drawPixmap(QPointF(self.PAD, (h - self.ICON) / 2.0),
                         self._icon_pm)

        cy = h / 2.0
        pal = self._pal
        if self._has_data:
            col = QColor(pal["up"] if self._up else pal["down"])
        else:
            col = QColor(pal["dim"])
        chg_col = QColor(col)
        chg_col.setAlpha(205)

        code = display_code(self._symbol) if self._symbol else "---"
        items = []
        if lay["show_code"]:
            items.append((self._fonts["code"], code, QColor(pal["dim"]),
                          lay["x_code"]))
        items.append((lay["f_price"], self._price_text or "--", col,
                      lay["x_price"]))
        if lay["show_chg"]:
            items.append((self._fonts["chg"], self._change_raw, chg_col,
                          lay["x_chg"]))
        for font, text, color, x in items:
            fm = QFontMetricsF(font)
            p.setFont(font)
            p.setPen(color)
            # 各段各自垂直居中：不同字号看起来在同一条水平线上
            p.drawText(QPointF(x, cy + (fm.ascent() - fm.descent()) / 2.0),
                       text)
        p.end()

    # ---- 行情 ----
    def update_ticker(self, ticker, symbol: str, stale: bool = False):
        """由主窗口在每次刷新后调用，实时刷新小工具上的价格。

        stale=True 表示本轮数据源没返回该品种、展示的是上次成功报价，
        tooltip 会明确标注，避免把缓存价格误当成实时价。
        """
        if symbol != self._symbol:
            self._symbol = symbol
            self._icon_pm = symbol_icon(symbol, self.ICON)
        if ticker is None:
            self._has_data = False
            self._price_text = "--"
            self._change_raw = "WAIT"
            self.setToolTip(f"{display_code(symbol)} 等待行情")
        else:
            self._has_data = True
            up = ticker.change_pct >= 0
            self._up = up
            sign = "+" if up else ""
            price = with_unit(format_price(ticker.last_price), symbol,
                              units.ENABLED)
            self._price_text = price
            self._change_raw = f"{sign}{ticker.change_pct:.2f}%"
            note = ("数据来源：上次成功刷新的缓存（非实时）" if stale
                    else "数据来源：本轮实时行情")
            self.setToolTip(
                f"{display_code(symbol)}  {price}  "
                f"{sign}{ticker.change_pct:.2f}%\n"
                f"高 {with_unit(format_price(ticker.high_24h), symbol, units.ENABLED)}  "
                f"低 {with_unit(format_price(ticker.low_24h), symbol, units.ENABLED)}\n"
                f"{note}\n"
                "固定在任务栏右侧 · 右键切换品种 / 样式 · 双击显示主窗口")
        self._lay = None
        if self._layout()["w"] != self.width():
            self.dock()
        self.update()

    # ---- 贴靠任务栏 ----
    def dock(self):
        """贴到任务栏右侧：自动避让通知区与其它小工具，并保持置顶。"""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        shift = int(self._cfg.get("price_badge_shift") or 0)
        try:
            exclude = (int(self.winId()),)
        except Exception:
            exclude = ()
        w = self._layout()["w"]
        x, y, w, h = dock_geometry(screen, w, self.HEIGHT,
                                   exclude=exclude, shift=shift)
        if self.width() != w or self.height() != h:
            self.setFixedSize(w, h)
        if self.x() != x or self.y() != y:
            self.move(x, y)
        self.raise_()
        self._force_topmost()

    def _force_topmost(self):
        """任务栏自身也是置顶窗，用 Win32 再压一次 Z 序。"""
        try:
            ctypes = __import__("ctypes")
            ctypes.windll.user32.SetWindowPos(
                int(self.winId()), -1, 0, 0, 0, 0,
                0x0001 | 0x0002 | 0x0010)  # NOSIZE|NOMOVE|NOACTIVATE
        except Exception:
            pass

    def apply_config(self):
        """按配置恢复显隐；位置始终由任务栏决定，不再读取拖动坐标。"""
        self._light = system_is_light()
        self._pal = _LIGHT if self._light else _DARK
        self._lay = None
        self.dock()
        self.setVisible(bool(self._cfg.get("price_badge", True)))
        if not self._dock_timer.isActive():
            self._dock_timer.start()

    def setVisible(self, visible):
        # 只有状态真的变了才广播：主窗口每次刷新都会调 _sync_badge，
        # 无脑 emit 会让托盘菜单反复 setChecked。
        visible = bool(visible)
        changed = self.isVisible() != visible
        super().setVisible(visible)
        if changed:
            self.visibility_changed.emit(visible)

    def set_candidates(self, symbols):
        """主窗口注入可指定的品种清单（与托盘右键菜单共用同一份）。"""
        self._candidates = [str(s) for s in symbols if s][:60]

    def _save_pos(self):
        """位置固定在任务栏，不再持久化拖动坐标（保留退出流程接口）。"""

    # ---- 交互：固定位置，只保留双击与右键 ----
    def mouseDoubleClickEvent(self, event):
        self.show_requested.emit()
        event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(menu_qss())
        act_show = QAction("显示主窗口", self)
        act_show.triggered.connect(self.show_requested.emit)
        menu.addAction(act_show)
        menu.addSeparator()

        sub = QMenu("常驻显示品种", menu)
        sub.setStyleSheet(menu_qss())
        current = self._cfg.get("tray_symbol") or "BTC"
        # 候选由主窗口注入（自选 + 当前市场「全部」页 + 当前指定品种），
        # 非自选品种也能直接在价格条右键里指定，不必进设置页手输。
        candidates = list(dict.fromkeys(
            (self._candidates or list(self._cfg.get("symbols") or []))
            + [current]))[:60]
        for sym in candidates:
            act = QAction(display_code(sym), sub)
            act.setCheckable(True)
            act.setChecked(sym == current)
            act.triggered.connect(
                lambda checked=False, s=sym: self.symbol_changed.emit(s))
            sub.addAction(act)
        menu.addMenu(sub)

        style_menu = QMenu("显示样式（省空间）", menu)
        style_menu.setStyleSheet(menu_qss())
        cur_style = self._style()
        for key, label in STYLES:
            act = QAction(label, style_menu)
            act.setCheckable(True)
            act.setChecked(key == cur_style)
            act.triggered.connect(
                lambda checked=False, k=key: self._set_style(k))
            style_menu.addAction(act)
        menu.addMenu(style_menu)
        menu.addSeparator()
        nudge = QMenu("位置微调（避开其它小工具）", menu)
        nudge.setStyleSheet(menu_qss())
        act_l = QAction("向左移 16px", nudge)
        act_l.triggered.connect(lambda: self._nudge(16))
        nudge.addAction(act_l)
        act_r = QAction("向右移 16px", nudge)
        act_r.triggered.connect(lambda: self._nudge(-16))
        nudge.addAction(act_r)
        act_reset = QAction("恢复自动贴靠", nudge)
        act_reset.triggered.connect(self._reset_shift)
        nudge.addAction(act_reset)
        menu.addMenu(nudge)
        act_dock = QAction("重新贴靠任务栏", self)
        act_dock.triggered.connect(self.dock)
        menu.addAction(act_dock)
        act_hide = QAction("隐藏（可在设置里重新开启）", self)
        act_hide.triggered.connect(self._hide_from_menu)
        menu.addAction(act_hide)
        menu.exec(event.globalPosition().toPoint())

    def _set_style(self, key: str):
        """切换信息密度：完整 / 紧凑 / 极简，立即生效并持久化。"""
        self._cfg.set("price_badge_style", key)
        self._cfg.save()
        self._lay = None
        self.dock()
        self.update()

    def _nudge(self, delta: int):
        """手动微调：正数左移，负数右移；结果持久化。"""
        cur = int(self._cfg.get("price_badge_shift") or 0)
        val = max(-400, min(900, cur + int(delta)))
        self._cfg.set("price_badge_shift", val)
        self._cfg.save()
        self.dock()

    def _reset_shift(self):
        self._cfg.set("price_badge_shift", 0)
        self._cfg.save()
        self.dock()

    def _hide_from_menu(self):
        self._cfg.set("price_badge", False)
        self._cfg.save()
        # 必须走重写的 setVisible：hide() 是 C++ slot，会绕过 Python 实现，
        # 导致托盘菜单的「任务栏右侧实时价格」勾选状态不同步（再点一次
        # 反而把它关掉，看起来像按钮失灵）。
        self.setVisible(False)
