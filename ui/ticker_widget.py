# -*- coding: utf-8 -*-
"""单品种/证券行情行控件 + 底部状态栏（币安风格）。

- 每行左侧为品种官方原图标（无官方图标时用项目原图标 + 市场色）；
- 名称只显示一次：代码旁显示项目名，行情源返回的重复代码名会被忽略；
- 高/低/额改用英文 H / L / V 紧凑标签 + 加大加亮的等宽字体，
  完整数值放在 tooltip；
- 红心机制已移除：增删自选统一用「全部」页按钮、搜索结果按钮或右键菜单；
- A 股惯例配色：红涨绿跌；价格用 IBM Plex Mono 等等宽字体。
"""
from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QToolTip, QVBoxLayout)

from ui import units
from ui.icons import display_code, register_symbol_name, symbol_icon
from ui.theme import (C_ACCENT, C_BG_HOVER, C_BG_PANEL, C_BG_ROW,
                      C_BORDER, C_BORDER_SOFT, C_DOWN, C_TEXT_DIM,
                      C_TEXT_MAIN, C_TEXT_SUB, C_UP, FONT_NUM, FONT_NUM_BOLD,
                      FONT_UI_BOLD, badge_qss, label_qss, mini_btn_qss)

C_FLASH_UP = "#3a1c24"      # 价格上涨短暂高亮背景（暗红）
C_FLASH_DOWN = "#12352a"    # 价格下跌短暂高亮背景（暗绿）
C_OK = "#0ecb81"            # 状态正常

# 批量建行期间关掉提示：几百行在鼠标下快速插入时，Qt 会给每行弹一个原生
# QToolTip 小窗（QTipLabel 顶层窗），视觉上就是「疯狂弹窗 + 抖动」。
#
# 旧实现只在 TickerWidget.event() 里吞 QEvent.ToolTip，实际**无效**：tooltip
# 挂在 lbl_price / lbl_high / btn_action 等子 QLabel 上，QWidget::event() 在
# 子控件处就 showText + accept，事件根本不会传播到父行；而且父行自身从未
# 设置过 tooltip。现在改成「应用级事件过滤器 + 引用计数」：
#   - 过滤器在 QApplication 派发事件前拦住任意 widget 的 ToolTip 事件；
#   - 引用计数让多个市场并行建行时，不会被先结束的链提前恢复。
_TOOLTIP_HOLD = 0
_TOOLTIPS_ON = True          # 兼容既有读取：等价于 _TOOLTIP_HOLD == 0
_GUARD_REF = None            # 强引用，防止 Python 对象被 GC 后过滤器失效


def _sync_tooltip_flag():
    global _TOOLTIPS_ON
    _TOOLTIPS_ON = (_TOOLTIP_HOLD == 0)


def begin_tooltip_hold():
    global _TOOLTIP_HOLD
    _TOOLTIP_HOLD += 1
    _sync_tooltip_flag()


def end_tooltip_hold():
    global _TOOLTIP_HOLD
    _TOOLTIP_HOLD = max(0, _TOOLTIP_HOLD - 1)
    _sync_tooltip_flag()


def tooltip_hold_count():
    return _TOOLTIP_HOLD


def disable_row_tooltips():
    """兼容旧调用名：进入一次建行期。"""
    begin_tooltip_hold()


def enable_row_tooltips():
    """兼容旧调用名：退出一次建行期。"""
    end_tooltip_hold()


class ToolTipGuard(QObject):
    """应用级过滤器：建行期吞掉所有 QEvent.ToolTip（含子 QLabel）。"""

    def eventFilter(self, obj, ev):
        # 不要调 super().eventFilter()：PySide6 会把它再次分派回本 Python
        # 覆写，造成无限递归（表现为退出时成片的 eventFilter 报错）。
        # QObject 的默认实现本来就是返回 False。
        if _TOOLTIP_HOLD > 0 and ev.type() == QEvent.ToolTip:
            return True
        return False


def install_tooltip_guard(app):
    """安装一次全局过滤器并返回它；app 作为 parent 持有 C++ 生命周期。"""
    global _GUARD_REF
    if app is None:
        return None
    if _GUARD_REF is not None:
        return _GUARD_REF
    guard = ToolTipGuard(app)
    app.installEventFilter(guard)
    QToolTip.hideText()
    _GUARD_REF = guard
    return guard


def format_price(price: float) -> str:
    """按价格大小自适应小数位，避免小数位过长。"""
    if price >= 1000:
        return f"{price:,.2f}"
    if price >= 1:
        return f"{price:.4f}"
    if price >= 0.01:
        return f"{price:.5f}"
    return f"{price:.8f}"


def format_volume(vol: float) -> str:
    """成交额人性化显示：1.23亿 / 4567万 / 8.9万。"""
    if vol >= 1e8:
        return f"{vol / 1e8:.2f}亿"
    if vol >= 1e4:
        return f"{vol / 1e4:.1f}万"
    return f"{vol:,.0f}"


def format_compact(v: float) -> str:
    """行内高低额紧凑数值：68.1k / 1.24M / 0.0832。"""
    if v >= 1e9:
        return f"{v / 1e9:.2f}B"
    if v >= 1e6:
        return f"{v / 1e6:.2f}M"
    if v >= 1e3:
        return f"{v / 1e3:.1f}k"
    if v >= 1:
        return f"{v:.2f}"
    if v >= 0.01:
        return f"{v:.4f}"
    return f"{v:.6f}"


class TickerWidget(QFrame):
    """一行行情：品种图标 / 代码名称 / 高低额 / 价格涨跌幅 / 可选操作按钮。"""

    context_menu = Signal(str, object)      # 右键 / 长按 / ⋯ 按钮：(代码, 全局坐标)
    long_pressed = Signal(str)              # 触摸长按 ≥500ms
    row_clicked = Signal(str)              # 左键：进入图表页
    hovered = Signal(str)                  # 鼠标移入：悬停资料弹窗跟着换
    hover_left = Signal(str)               # 鼠标移出：延时收起资料弹窗
    toggled = Signal(str, bool)            # 全部页：加入 / 移出自选

    def __init__(self, symbol: str, name_cn: str = "",
                 mode: str = "watch", in_watchlist: bool = True,
                 parent=None, defer_icon: bool = False, code: str = ""):
        super().__init__(parent)
        self.symbol = symbol
        self.mode = mode
        self._in_watchlist = in_watchlist
        self._last_price = 0.0
        self._name = (name_cn or "").strip()
        # 链上合约品种：显示代币代码（ANSEM）而不是 44 位合约地址
        self._code = (code or "").strip() or display_code(symbol)
        # 每行复用一个单次定时器做价格闪烁，避免每帧刷新都 new 一个 QTimer
        # （「全部」页 300 行时尤为重要）。
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.setInterval(600)
        self._flash_timer.timeout.connect(
            lambda: self.setStyleSheet(self._row_style()))
        # 阶段 6：长按 500ms 触发菜单（Qt 会把触摸合成为鼠标事件），
        # 这样手机上不依赖右键也能做置顶 / 查看资料 / 加自选。
        self._long_timer = QTimer(self)
        self._long_timer.setSingleShot(True)
        self._long_timer.setInterval(500)
        self._long_timer.timeout.connect(self._on_long_press)
        self._long_start = None
        self._long_fired = False
        self.setObjectName("tickerRow")
        self.setStyleSheet(self._row_style())

        root = QHBoxLayout(self)
        # 触摸友好行高：内容 + 上下留白 ≈ 64px，手指点得准
        root.setContentsMargins(11, 10, 11, 10)
        root.setSpacing(10)
        self.setMinimumHeight(64)

        # ---- 品种图标（替代原来的红心）----
        if self._name:
            register_symbol_name(symbol, self._name)   # 字徽用中文名首字
        from data import stock_logo
        stock_logo.request(symbol)      # 有真实公司 logo 就换成真实图
        self.icon = QLabel()
        self.icon.setFixedSize(30, 30)
        self.icon.setStyleSheet("background:transparent; border:none;")
        # 「全部」页最多 500 行，逐行画图标要 1 秒以上；先建行、图标分批补，
        # 点开「全部」时列表立刻出现，不会整页白屏等一下。
        self._icon_loaded = False
        if not defer_icon:
            self.load_icon()
        root.addWidget(self.icon)

        # ---- 左侧信息区 ----
        left = QVBoxLayout()
        left.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(7)
        self.lbl_symbol = QLabel(self._code)
        self.lbl_symbol.setStyleSheet(
            f"color:{C_TEXT_MAIN}; font-size:13px;"
            f" font-family:{FONT_NUM_BOLD}; background:transparent;")
        top.addWidget(self.lbl_symbol)
        # 阶段 4：置顶徽章，明确「置顶品种」与「普通排序品种」的优先级
        self.lbl_pin = QLabel("置顶")
        self.lbl_pin.setStyleSheet(badge_qss(C_ACCENT, C_BG_HOVER, 9))
        self.lbl_pin.setToolTip("已置顶：始终排在所有排序规则之前")
        self.lbl_pin.setVisible(False)
        top.addWidget(self.lbl_pin)
        self._pinned = False
        # 名称只显示一次；与代码同名（如行情源返回 BTC）时直接隐藏
        self.lbl_name = QLabel(self._name)
        self.lbl_name.setStyleSheet(label_qss(10, C_TEXT_SUB))
        self.lbl_name.setMinimumWidth(0)
        top.addWidget(self.lbl_name, 1)
        self._sync_name()
        left.addLayout(top)

        stats = QHBoxLayout()
        stats.setSpacing(8)
        self.lbl_high = QLabel("H --")
        self.lbl_low = QLabel("L --")
        self.lbl_vol = QLabel("V --")
        for lbl in (self.lbl_high, self.lbl_low, self.lbl_vol):
            lbl.setStyleSheet(label_qss(11, C_TEXT_SUB, True, True))
            stats.addWidget(lbl)
        stats.addStretch(1)
        left.addLayout(stats)
        root.addLayout(left, 1)

        # ---- 右侧：价格 + 涨跌幅 ----
        right = QVBoxLayout()
        right.setSpacing(2)
        right.setAlignment(Qt.AlignRight)
        self.lbl_price = QLabel("--")
        self.lbl_price.setAlignment(Qt.AlignRight)
        self.lbl_price.setStyleSheet(
            f"color:{C_TEXT_MAIN}; font-size:15px;"
            f" font-family:{FONT_NUM_BOLD}; background:transparent;")
        self.lbl_change = QLabel("--")
        self.lbl_change.setMinimumWidth(66)
        self.lbl_change.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_change.setStyleSheet(badge_qss(C_TEXT_DIM, C_BG_HOVER, 11))
        right.addWidget(self.lbl_price)
        right.addWidget(self.lbl_change)
        root.addLayout(right, 0)

        # ---- 全部页：明确的加入/移除按钮 ----
        self.btn_action = None
        if mode == "all":
            self.btn_action = QPushButton()
            self.btn_action.setFixedWidth(66)
            self.btn_action.setCursor(Qt.PointingHandCursor)
            self.btn_action.setFocusPolicy(Qt.NoFocus)
            self.btn_action.clicked.connect(self._on_action)
            self.set_in_watchlist(in_watchlist)
            root.addWidget(self.btn_action)

        # 品种菜单入口：右键菜单 + 触屏长按（阶段 8 起按用户要求移除行内
        # 「⋯」方框，操作路径不再依赖额外按钮）。

    def set_pinned(self, pinned: bool):
        """显示 / 隐藏置顶徽章（由主窗口在每次重排时同步）。"""
        flag = bool(pinned)
        if flag == self._pinned:
            return
        self._pinned = flag
        self.lbl_pin.setVisible(flag)

    def load_icon(self):
        """补上品种图标（延后加载用；重复调用无副作用）。"""
        if self._icon_loaded:
            return
        self._icon_loaded = True
        self.icon.setPixmap(symbol_icon(self.symbol, 30))

    # ---- 自选按钮 ----
    def _on_action(self):
        self.toggled.emit(self.symbol, not self._in_watchlist)

    def set_in_watchlist(self, value: bool):
        self._in_watchlist = bool(value)
        if self.btn_action is None:
            return
        self.btn_action.setText("✓ 已选" if value else "＋ 添加")
        self.btn_action.setToolTip("移出自选" if value else "加入自选")
        self.btn_action.setStyleSheet(
            mini_btn_qss(False, C_ACCENT) if not value else
            f"QPushButton {{ color:{C_TEXT_DIM}; background:{C_BG_HOVER};"
            f" border:1px solid {C_BORDER}; border-radius:4px;"
            f" padding:2px 8px; font-family:{FONT_UI_BOLD}; font-size:11px; }}")

    # ---- 名称：只显示一次，且与代码同名时隐藏 ----
    def _sync_name(self):
        visible = bool(self._name) and \
            self._name.upper() != self._code.upper()
        self.lbl_name.setText(self._name)
        self.lbl_name.setVisible(visible)

    # ---- 右键菜单 / 点击 ----
    def contextMenuEvent(self, event):
        self.context_menu.emit(self.symbol, event.globalPos())

    def _on_long_press(self):
        self._long_fired = True
        self.long_pressed.emit(self.symbol)
        self.context_menu.emit(self.symbol, QCursor.pos())

    def enterEvent(self, event):
        # 悬停信号保留给需要跟随高亮的场景；资料弹窗 v23 起只走右键菜单
        self.hovered.emit(self.symbol)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover_left.emit(self.symbol)
        super().leaveEvent(event)

    def event(self, ev):
        """兜底：父行自身的 ToolTip 事件也吞掉。

        真正的防护是 install_tooltip_guard() 装的应用级过滤器 —— Qt 会把
        QEvent.ToolTip 直接交给鼠标下的子 QLabel 并在那里 accept，父行的
        event() 收不到；这里只负责父行自己收到事件的极端情况。
        """
        if ev.type() == QEvent.ToolTip and not _TOOLTIPS_ON:
            return True
        return super().event(ev)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 短按 = 进图表；长按 = 菜单；拖动 = 滚动（都不误触）
            self._long_start = event.globalPosition().toPoint()
            self._long_fired = False
            self._long_timer.start()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._long_start is not None:
            delta = event.globalPosition().toPoint() - self._long_start
            if delta.manhattanLength() > 12:      # 判为滑动，取消点击与长按
                self._long_timer.stop()
                self._long_start = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        fired = self._long_fired
        was_tap = self._long_start is not None
        self._long_timer.stop()
        self._long_start = None
        self._long_fired = False
        if event.button() == Qt.LeftButton and was_tap and not fired:
            self.row_clicked.emit(self.symbol)
        super().mouseReleaseEvent(event)

    # ---- 数据更新 ----
    def update_ticker(self, t):
        # 加密货币行情源返回的 name 就是代码本身（BTC），属于重复显示，
        # 直接忽略；股票行情源返回中文名且初始为空时才更新一次。
        n = (t.name or "").strip()
        if n and n.upper() != self._code.upper() and n != self._name:
            self._name = n
            self._sync_name()
        self.lbl_price.setText(
            units.with_unit(format_price(t.last_price), t.symbol, units.ENABLED))
        self.lbl_high.setText(f"H {format_compact(t.high_24h)}")
        self.lbl_low.setText(f"L {format_compact(t.low_24h)}")
        self.lbl_vol.setText(f"V {format_compact(t.quote_volume_24h)}")
        self.lbl_high.setToolTip(
            f"最高价  {units.with_unit(format_price(t.high_24h), t.symbol, units.ENABLED)}")
        self.lbl_low.setToolTip(
            f"最低价  {units.with_unit(format_price(t.low_24h), t.symbol, units.ENABLED)}")
        self.lbl_vol.setToolTip(
            f"成交额  {format_volume(t.quote_volume_24h)}")

        up = t.change_pct >= 0
        color = C_UP if up else C_DOWN
        bg = "rgba(246,70,93,0.14)" if up else "rgba(14,203,129,0.14)"
        sign = "+" if up else ""
        self.lbl_change.setText(f"{sign}{t.change_pct:.2f}%")
        self.lbl_change.setStyleSheet(badge_qss(color, bg, 11))

        self.lbl_price.setStyleSheet(
            f"color:{color}; font-size:15px;"
            f" font-family:{FONT_NUM_BOLD}; background:transparent;")
        if self._last_price and abs(t.last_price - self._last_price) > 1e-12:
            flash = C_FLASH_UP if t.last_price > self._last_price \
                else C_FLASH_DOWN
            self.setStyleSheet(self._row_style(flash))
            self._flash_timer.start()
        self._last_price = t.last_price

    def update_onchain(self, q: dict):
        """链上合约品种专用渲染：只有真实 USD 报价，没有 K 线 / H-L-V / 涨跌幅。

        数据源（Rugcheck.xyz 链上代币报告）不提供 24h 涨跌幅与最高最低价，
        这里一律显示为「—」并在 tooltip 里写明来源与取数时间，绝不把 0
        当成真实数值，也不用交易所价格冒充链上价格。
        """
        price = (q or {}).get("price")
        src = (q or {}).get("source") or "链上报价源"
        ts = (q or {}).get("ts")
        import datetime
        when = (datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                if ts else "—")
        liq = (q or {}).get("liquidity")
        holders = (q or {}).get("holders")
        detail = [f"来源：{src}", f"取数时间：{when}",
                  f"链上流动性：${liq:,.0f}" if liq is not None else "链上流动性：—",
                  f"持有地址数：{holders:,.0f}" if holders is not None else "持有地址数：—",
                  "说明：该币种暂无 K 线与 24h 涨跌幅数据"]
        tip = "\n".join(detail)

        self.lbl_change.setText("—")
        self.lbl_change.setStyleSheet(badge_qss(C_TEXT_DIM, C_BG_HOVER, 11))
        self.lbl_change.setToolTip("链上数据源未提供 24h 涨跌幅，不显示估算值")
        for lbl, text in ((self.lbl_high, "H —"), (self.lbl_low, "L —"),
                          (self.lbl_vol, "V —")):
            lbl.setText(text)
            lbl.setToolTip("链上数据源未提供该字段")
        if price is None or price <= 0:
            self.lbl_price.setText("--")
            self.lbl_price.setStyleSheet(
                f"color:{C_TEXT_DIM}; font-size:15px;"
                f" font-family:{FONT_NUM_BOLD}; background:transparent;")
            self.lbl_price.setToolTip(tip + "\n暂无公开链上报价（数据源不可达或未收录）")
            return
        self.lbl_price.setText("$" + format_price(float(price)))
        self.lbl_price.setStyleSheet(
            f"color:{C_TEXT_MAIN}; font-size:15px;"
            f" font-family:{FONT_NUM_BOLD}; background:transparent;")
        self.lbl_price.setToolTip(tip)
        if self._last_price and abs(float(price) - self._last_price) > 1e-12:
            flash = C_FLASH_UP if float(price) > self._last_price \
                else C_FLASH_DOWN
            self.setStyleSheet(self._row_style(flash))
            self._flash_timer.start()
        self._last_price = float(price)

    def mark_stale(self):
        self.lbl_price.setStyleSheet(
            f"color:{C_TEXT_DIM}; font-size:15px;"
            f" font-family:{FONT_NUM_BOLD}; background:transparent;")

    def _row_style(self, bg: str = "") -> str:
        background = bg or C_BG_ROW
        return (f"#tickerRow {{ background:{background};"
                f" border:1px solid {C_BORDER_SOFT}; border-radius:12px; }}"
                f"#tickerRow:hover {{ background:{C_BG_HOVER};"
                f" border-color:{C_ACCENT}; }}")


class StatusPanel(QFrame):
    """底部状态栏：网络状态 / 数据源 / 更新时间 / 轻量加载提示。

    阶段 2：加载与失败一律用这里的一行文字提示，绝不再弹模态窗口；
    失败时给一个「重试」小按钮，重试次数由主窗口限制。
    """

    retry_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusBar")
        self.setStyleSheet(
            f"#statusBar {{ background:{C_BG_PANEL};"
            f" border:1px solid {C_BORDER}; border-radius:4px; }}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 3, 10, 3)
        layout.setSpacing(8)
        self.lbl_net = QLabel("● 连接中")
        self.lbl_source = QLabel("来源 --")
        self.lbl_time = QLabel("更新 --")
        self.lbl_note = QLabel("")
        self.lbl_note.setStyleSheet(label_qss(9, C_TEXT_SUB))
        self.lbl_net.setStyleSheet(label_qss(10, C_TEXT_DIM, True))
        self.lbl_source.setStyleSheet(label_qss(10, C_TEXT_DIM))
        self.lbl_time.setStyleSheet(label_qss(10, C_TEXT_DIM, numeric=True))
        layout.addWidget(self.lbl_net)
        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"QFrame {{ background:{C_BORDER}; }}")
        layout.addWidget(sep)
        layout.addWidget(self.lbl_source)
        layout.addWidget(self.lbl_note)
        self.btn_retry = QPushButton("重试")
        self.btn_retry.setFixedHeight(22)
        self.btn_retry.setCursor(Qt.PointingHandCursor)
        self.btn_retry.setStyleSheet(mini_btn_qss())
        self.btn_retry.setToolTip("重新请求当前可见行情（不会重复弹窗）")
        self.btn_retry.clicked.connect(self.retry_requested.emit)
        self.btn_retry.hide()
        layout.addWidget(self.btn_retry)
        layout.addStretch(1)
        layout.addWidget(self.lbl_time)

    def set_progress(self, text: str, can_retry: bool = False):
        """轻量加载 / 失败提示；空文本即恢复常态。"""
        self.lbl_note.setText(text)
        self.lbl_note.setToolTip(text)
        self.lbl_note.setVisible(bool(text))
        self.btn_retry.setVisible(bool(can_retry))

    def set_note(self, text: str, tip: str = ""):
        """状态栏右侧的临时提示（如后台预缓存进度），空文本即隐藏。"""
        self.lbl_note.setText(text)
        self.lbl_note.setToolTip(tip or text)
        self.lbl_note.setVisible(bool(text))

    def set_status(self, source: str, ts: float, ok: bool):
        from PySide6.QtCore import QDateTime
        self.lbl_source.setText(f"来源 {source}")
        t = QDateTime.fromSecsSinceEpoch(int(ts))
        self.lbl_time.setText(f"更新 {t.toString('HH:mm:ss')}")
        self.lbl_net.setText("● 在线" if ok else "● 异常")
        self.lbl_net.setStyleSheet(
            label_qss(10, C_OK if ok else C_UP, True))
