# -*- coding: utf-8 -*-
"""行情行右键菜单「查看资料」弹出的「品种资料」浮层。

v23 起不再随鼠标悬停自动弹出：只有用户在行情行上点右键并选择
「ℹ 查看资料」才显示，弹窗右上有 ✕ 可手动关闭；切页 / 进图表 /
进设置 / 滚动列表时自动收起。卡片内容与图表详情抽屉同源：

- 代码 / 名称 / 市场 / 市值排名 / 最新价 / 涨跌幅；
- 24h 高低、振幅、成交额、总市值、流通市值、市盈率；
- 项目 / 公司 / 产品 / 创始人介绍（离线资料库，断网也有内容）。

数据分工：价格类字段来自刷新调度器推来的 Ticker；市值 / 股本 / 市盈率
来自 data.fundamentals（后台守护线程取，带缓存）；介绍来自 data.about。
外观统一走 ui.popup，与详情抽屉、设置页共用一套圆角 / 标题栏 / 按钮规格。
"""
import threading

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QVBoxLayout, QWidget)

from data import fundamentals
from data.universe import market_of, name_of
from ui import units
from ui.icons import display_code, symbol_icon
from ui.popup import PopupSurface, popup_card
from ui.theme import (C_ACCENT, C_BG_HOVER, C_DOWN, C_TEXT_DIM, C_TEXT_MAIN,
                      C_TEXT_SUB, C_UP, badge_qss, chip_qss, label_qss)
from ui.ticker_widget import format_price

# 市场标签与强调色（与顶部页签保持同一套色）
MARKETS = {
    "crypto": ("加密", "#f7931a"),
    "cn": ("A股", "#f6465d"),
    "hk": ("港股", "#f0b90b"),
    "us": ("美股", "#4b9cff"),
}

# 面板字段（顺序即展示顺序）；pe 只有股票有。
FIELDS = ("high", "low", "amp", "vol", "cap", "fcap", "pe")
ALL_FIELDS = FIELDS + ("rank",)
CAPTIONS = {
    "high": "24h最高", "low": "24h最低", "amp": "振幅",
    "vol": "成交额", "cap": "总市值", "fcap": "流通市值",
    "pe": "市盈率", "rank": "市值排名",
}

_PROFILE_CACHE: dict = {}


def format_cap(value) -> str:
    """市值：1.45万亿 / 3721亿 / 45.2亿 / 8600万；拿不到返回 —"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if v <= 0:
        return "—"
    if v >= 1e12:
        return f"{v / 1e12:.2f}万亿"
    if v >= 1e10:
        return f"{v / 1e8:,.0f}亿"
    if v >= 1e8:
        return f"{v / 1e8:.2f}亿"
    if v >= 1e4:
        return f"{v / 1e4:.0f}万"
    return f"{v:,.0f}"


class ProfileWorker(threading.Thread):
    """后台取市值 / 股本 / 市盈率，避免网络慢时卡住主线程。

    刻意不用 QThread：普通守护线程不参与解释器退出等待，关窗时网络请求
    还没回来也不会让进程卡住（QThread 在退出时未结束会让进程异常退出）。
    """

    def __init__(self, symbol: str, price: float, signals: "_ProfileSignals"):
        super().__init__(daemon=True, name="profile-%s" % symbol)
        self.symbol = symbol
        self.price = float(price or 0.0)
        self._signals = signals

    def run(self):
        try:
            data = fundamentals.profile(self.symbol, self.price, timeout=6.0)
        except Exception:
            data = {}
        try:
            self._signals.ready.emit(self.symbol, data or {})
        except RuntimeError:      # 窗口已销毁
            pass


class _ProfileSignals(QObject):
    """线程 -> 界面的信号载体（挂在主线程对象上，跨线程用队列连接）。"""

    ready = Signal(str, dict)


class _Metric(QWidget):
    """一个字段：上面小标题，下面数值。"""

    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.cap = QLabel(caption)
        self.cap.setStyleSheet(label_qss(9, C_TEXT_DIM))
        lay.addWidget(self.cap)
        self.val = QLabel("—")
        self.val.setStyleSheet(label_qss(12, C_TEXT_MAIN, True, True))
        lay.addWidget(self.val)

    def set_value(self, text: str, color: str = None):
        self.val.setText(text or "—")
        self.val.setStyleSheet(
            label_qss(12, color or C_TEXT_MAIN, True, True))


class SymbolInfoPanel(PopupSurface):
    """右键弹出的浮层：跟随行情行定位的品种资料卡（不是常驻控件）。"""

    def __init__(self, parent=None):
        super().__init__("品种资料", parent, closable=True)
        # 用户主动打开的弹窗：可交互，右上角 ✕ 关闭。
        self.closed.connect(self.hide)
        self.setMinimumWidth(320)
        self._symbol = ""
        self._name = ""
        self._ticker = None
        self._profile: dict = {}
        self._worker = None
        self._pending = False
        self._cols = 0
        self._sig = ()

        body = self.body_lay
        body.setContentsMargins(12, 10, 12, 12)

        # ---- 第一行：图标 + 代码 / 名称 + 市场 / 排名 + 价格 ----
        head = QHBoxLayout()
        head.setSpacing(8)
        self.icon = QLabel()
        self.icon.setFixedSize(30, 30)
        self.icon.setStyleSheet("background:transparent;")
        head.addWidget(self.icon)

        left = QVBoxLayout()
        left.setSpacing(1)
        line1 = QHBoxLayout()
        line1.setSpacing(6)
        self.lbl_code = QLabel("--")
        self.lbl_code.setStyleSheet(label_qss(14, C_TEXT_MAIN, True, True))
        line1.addWidget(self.lbl_code)
        self.lbl_market = QLabel("")
        self.lbl_market.setStyleSheet(chip_qss(C_ACCENT, 9))
        line1.addWidget(self.lbl_market)
        self.lbl_rank = QLabel("")
        self.lbl_rank.setStyleSheet(badge_qss(C_TEXT_SUB, C_BG_HOVER, 9))
        line1.addWidget(self.lbl_rank)
        line1.addStretch(1)
        left.addLayout(line1)
        self.lbl_name = QLabel("")
        self.lbl_name.setStyleSheet(label_qss(10, C_TEXT_DIM))
        left.addWidget(self.lbl_name)
        head.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(0)
        self.lbl_price = QLabel("--")
        self.lbl_price.setAlignment(Qt.AlignRight)
        self.lbl_price.setStyleSheet(label_qss(16, C_TEXT_MAIN, True, True))
        right.addWidget(self.lbl_price)
        self.lbl_change = QLabel("--")
        self.lbl_change.setAlignment(Qt.AlignRight)
        self.lbl_change.setStyleSheet(label_qss(11, C_TEXT_SUB, True, True))
        right.addWidget(self.lbl_change)
        head.addLayout(right)
        body.addLayout(head)

        # ---- 指标网格 ----
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(2)
        body.addLayout(self.grid)

        self._cells = {key: _Metric(CAPTIONS[key], self)
                      for key in ALL_FIELDS}
        for cell in self._cells.values():
            cell.hide()

        # ---- 项目 / 公司 / 创始人介绍 ----
        about_card, about_lay = popup_card("项目 · 公司介绍", self)
        self.lbl_about_meta = QLabel("")
        self.lbl_about_meta.setWordWrap(True)
        self.lbl_about_meta.setStyleSheet(label_qss(9, C_ACCENT))
        about_lay.addWidget(self.lbl_about_meta)
        self.lbl_about = QLabel("")
        self.lbl_about.setWordWrap(True)
        self.lbl_about.setStyleSheet(label_qss(10, C_TEXT_SUB))
        about_lay.addWidget(self.lbl_about)
        body.addWidget(about_card)

        # ---- 数据来源与更新时间：精简版也要能追溯 ----
        self.lbl_source = QLabel("")
        self.lbl_source.setWordWrap(True)
        self.lbl_source.setStyleSheet(label_qss(9, C_TEXT_DIM))
        body.addWidget(self.lbl_source)

        self._signals = _ProfileSignals(self)
        self._signals.ready.connect(self._on_profile)
        # ---- 标题栏拖动整个弹窗 ----
        self._drag_offset = None
        self._last_pos = None            # 用户拖动后的落点（全局坐标，本次会话记住）
        self.head.setCursor(Qt.SizeAllCursor)
        self.head.installEventFilter(self)
        self._reflow(force=True)
        self._render_about()
        self.hide()

    # ---------------------------------------------------------------- 定位
    def eventFilter(self, obj, event):
        """按住标题栏即可拖动资料弹窗（关闭按钮是子控件，不受影响）。"""
        if obj is self.head:
            t = event.type()
            if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_offset = (event.globalPosition().toPoint()
                                     - self.mapToGlobal(QPoint(0, 0)))
            elif (t == QEvent.MouseMove and self._drag_offset is not None):
                self._move_to(event.globalPosition().toPoint()
                              - self._drag_offset)
            elif (t == QEvent.MouseButtonRelease
                    and self._drag_offset is not None):
                self._drag_offset = None
                self._last_pos = self.mapToGlobal(QPoint(0, 0))
        return super().eventFilter(obj, event)

    def _move_to(self, global_pos: QPoint):
        """移动到全局坐标，整体钳制在宿主窗口内（不会拖出软件）。"""
        host = self.window()
        w, h = self.width(), self.height()
        if host is not None and host.isVisible():
            frame = host.frameGeometry()
            x = max(frame.left() + 4,
                    min(int(global_pos.x()), frame.right() - w - 4))
            y = max(frame.top() + 4,
                    min(int(global_pos.y()), frame.bottom() - h - 4))
        else:
            x, y = int(global_pos.x()), int(global_pos.y())
        parent = self.parentWidget() or host
        if parent is not None:
            self.move(parent.mapFromGlobal(QPoint(x, y)))
        else:
            self.move(x, y)

    def show_for(self, anchor: QRect = QRect(), host: QWidget = None):
        """浮出资料弹窗。

        默认位置优先「不遮挡」：
        1. 用户拖动过的落点（整个弹窗仍在窗口内就沿用）；
        2. 行右侧 / 左侧有整块空位（宽窗口）→ 贴着这一行；
        3. 两侧都放不下（窄窗口）→ 停靠窗口右下角，
           不压右键点开的那一行，也不挡上方页签 / 搜索区。
        上下始终钳制在窗口内，不会跑到软件外。
        """
        self.adjustSize()
        w, h = max(320, self.width()), max(180, self.height())
        if host is None or anchor.isNull():
            self.show()
            self.raise_()
            return
        frame = host.frameGeometry()
        parent = self.parentWidget() or host
        # 1) 用户拖过的位置
        if self._last_pos is not None:
            r = QRect(self._last_pos, QSize(w, h))
            if frame.adjusted(4, 4, -4, -4).contains(r):
                self.move(parent.mapFromGlobal(QPoint(self._last_pos)))
                self.show()
                self.raise_()
                return
        # 2) 行侧面的整块空位（不经过钳制才算真的放得下）
        x = anchor.right() + 10
        side_fit = False
        if x + w <= frame.right() - 8:
            side_fit = True
        else:
            x = anchor.left() - w - 10
            if x >= frame.left() + 8:
                side_fit = True
        if side_fit:
            y = anchor.top() - 8
            y = max(frame.top() + 8, min(y, frame.bottom() - h - 8))
        else:
            # 3) 停靠右下角
            x = frame.right() - w - 12
            y = frame.bottom() - h - 12
        self.move(parent.mapFromGlobal(QPoint(int(x), int(y))))
        self.show()
        self.raise_()

    def hide_popup(self):
        self.hide()

    def refresh_style(self):
        super().refresh_style()

    # ---------------------------------------------------------------- 数据
    def set_symbol(self, symbol: str, name: str = ""):
        """切换到某个品种：立刻清空旧数值，再后台补市值资料。"""
        if not symbol:
            self.clear()
            return
        if symbol == self._symbol and self._ticker is not None:
            return
        self._symbol = symbol
        self._name = name or name_of(symbol) or ""
        self._ticker = None
        self._profile = dict(_PROFILE_CACHE.get(symbol) or {})
        code = display_code(symbol)
        self.lbl_code.setText(code)
        self.lbl_name.setText(self._name or symbol)
        pm = symbol_icon(symbol, 30)
        self.icon.setPixmap(pm)
        label, color = MARKETS.get(market_of(symbol), ("", C_ACCENT))
        self._paint_market(color, label)
        self.lbl_price.setText("--")
        self.lbl_change.setText("--")
        self._render()
        self._render_about()
        self._fetch_profile()

    def clear(self):
        self._symbol = ""
        self._ticker = None
        self._profile = {}
        self.lbl_code.setText("--")
        self.lbl_name.setText("")
        self.lbl_price.setText("--")
        self.lbl_change.setText("--")
        self._paint_market(C_ACCENT, "")
        self._render()
        self._render_about()

    def update_ticker(self, ticker):
        """刷新调度器每次回来都会调；价格类字段即时更新。"""
        self._ticker = ticker
        if ticker is None:
            self.lbl_price.setText("--")
            self.lbl_change.setText("--")
            self._render()
            return
        try:
            price = float(getattr(ticker, "last_price", 0) or 0)
            change = float(getattr(ticker, "change_pct", 0) or 0)
        except (TypeError, ValueError):
            return
        sym = self._symbol
        self.lbl_price.setText(
            units.with_unit(format_price(price), sym, units.ENABLED))
        arrow = "▲" if change > 0 else ("▼" if change < 0 else "·")
        color = C_UP if change > 0 else (C_DOWN if change < 0 else C_TEXT_SUB)
        self.lbl_change.setText(f"{arrow} {change:+.2f}%")
        self.lbl_change.setStyleSheet(label_qss(11, color, True, True))
        self._render()

    def set_profile(self, data: dict):
        self._profile = dict(data or {})
        if self._symbol:
            _PROFILE_CACHE[self._symbol] = dict(self._profile)
        self._render()

    # ---------------------------------------------------------------- 内部
    def _paint_market(self, color: str, label: str):
        self.lbl_market.setText(label)
        self.lbl_market.setVisible(bool(label))
        if label:
            self.lbl_market.setStyleSheet(chip_qss(color, 9))

    def _render_about(self):
        """项目 / 公司 / 产品 / 创始人（离线资料，不依赖网络线程）。"""
        if not self._symbol:
            self.lbl_about_meta.setText("")
            self.lbl_about.setText(
                "在行情行上点右键 → 「ℹ 查看资料」查看背景介绍。")
            return
        a = fundamentals.about(self._symbol, self._name)
        bits = [a.get("category") or "", a.get("since") or ""]
        self.lbl_about_meta.setText(" · ".join(x for x in bits if x and x != "—"))
        founder = a.get("founder") or ""
        product = a.get("product") or ""
        lines = []
        if founder and founder != "—":
            lines.append(f"创始人 / 创办团队：{founder}")
        if product and product != "—":
            lines.append(f"代表产品 / 主营：{product}")
        lines.append(a.get("summary") or "")
        self.lbl_about.setText("\n".join(lines))

    def _fetch_profile(self):
        sym = self._symbol
        if not sym:
            return
        if sym in _PROFILE_CACHE and _PROFILE_CACHE[sym]:
            return                                  # 本次会话已取过
        if self._worker is not None and self._worker.is_alive():
            self._pending = True
            return
        price = float(getattr(self._ticker, "last_price", 0) or 0)
        worker = ProfileWorker(sym, price, self._signals)
        self._worker = worker
        self._pending = False
        worker.start()

    def _on_profile(self, symbol: str, data: dict):
        self._worker = None
        # 后到的资料要**并入**而不是整体替换：详情抽屉 / 调用方可能已经
        # 塞进更完整的字段，后台线程只带回离线介绍时不能把它们抹掉。
        fresh = {k: v for k, v in (data or {}).items() if v is not None}
        # 后台线程在离线兜底时会带回「离线资料库 / 未联网」这类说明，
        # 不能把调用方已经塞进来的真实来源与采集时间覆盖掉（阶段 1
        # 要求数据来源与更新时间可追溯）。
        if (fresh.get("source") == "离线资料库"
                and self._profile.get("source") not in
                (None, "", "离线资料库")):
            for k in ("source", "source_note", "updated_text",
                      "updated_kind"):
                fresh.pop(k, None)
        if fresh:
            cached = dict(_PROFILE_CACHE.get(symbol) or {})
            cached.update(fresh)
            _PROFILE_CACHE[symbol] = cached
        if symbol == self._symbol and fresh:
            merged = dict(self._profile or {})
            merged.update(fresh)
            self.set_profile(merged)
        if self._pending:
            self._pending = False
            self._fetch_profile()

    def _render(self):
        """按当前数据刷新全部字段与可见性。"""
        sym = self._symbol
        t = self._ticker
        prof = self._profile or {}
        is_stock = market_of(sym) != "crypto" if sym else True

        high = float(getattr(t, "high_24h", 0) or 0)
        low = float(getattr(t, "low_24h", 0) or 0)
        vol = float(getattr(t, "quote_volume_24h", 0) or 0)
        price = float(getattr(t, "last_price", 0) or 0)
        amp = ((high - low) / low * 100.0) if (low > 0 and high > 0) else 0.0

        self._cells["high"].set_value(
            units.with_unit(format_price(high), sym, units.ENABLED)
            if high else "—")
        self._cells["low"].set_value(
            units.with_unit(format_price(low), sym, units.ENABLED)
            if low else "—")
        self._cells["amp"].set_value(f"{amp:.2f}%" if amp else "—")
        self._cells["vol"].set_value(format_cap(vol) if vol else "—")

        cap = prof.get("cap")
        shares = prof.get("shares")
        if shares and price:
            cap = float(shares) * price        # 市值永远跟最新价走
        self._cells["cap"].set_value(format_cap(cap))
        self._cells["fcap"].set_value(format_cap(prof.get("float_cap")))
        pe = prof.get("pe")
        try:
            pe_val = float(pe) if pe else 0.0
        except (TypeError, ValueError):
            pe_val = 0.0
        self._cells["pe"].set_value(f"{pe_val:.1f}" if pe_val > 0 else "—")
        rank = prof.get("rank")
        self._cells["rank"].set_value(f"#{rank}" if rank else "—")
        self.lbl_rank.setText(f"市值 #{rank}" if rank else "")
        self.lbl_rank.setVisible(bool(rank))

        # 加密没有市盈率；没排名的不占位。rank 单元格只做数据落点（不进网格，
        # 头部徽章已经在显示它），所以永远保持隐藏。
        self._cells["pe"].setVisible(is_stock and bool(sym))
        self._cells["rank"].hide()
        for key in ("high", "low", "amp", "vol", "cap", "fcap"):
            visible = bool(sym)
            self._cells[key].setVisible(visible)
        # 数值来源 / 真实采集时间 / 介绍来源；没有数据就明确说没有
        src = prof.get("source") or "—"
        ts = prof.get("updated_text") or "— 暂无数据"
        a = prof.get("about") or {}
        self.lbl_source.setText(
            f"数值来源：{src} · 更新时间：{ts} · "
            f"介绍：{a.get('source_note') or '—'} · "
            "暂无数据的字段显示「—」，不做估算")
        self._reflow()

    def _reflow(self, force: bool = False):
        """按宽度决定列数：窄屏 2 列 / 常规 3 列 / 宽屏 4 列。

        可见字段变化（加密没有市盈率、没排名时）也必须重排，否则新露出的
        单元格没被加进网格，会以 (0,0) 飘在卡片左上角。
        """
        w = max(self.width(), 240)
        cols = 2 if w < 340 else (3 if w < 500 else 4)
        sig = tuple(k for k in FIELDS if not self._cells[k].isHidden())
        if cols == self._cols and sig == self._sig and not force:
            return
        self._cols = cols
        self._sig = sig
        for cell in self._cells.values():
            self.grid.removeWidget(cell)
        for i, key in enumerate(sig):
            self.grid.addWidget(self._cells[key], i // cols, i % cols)
        # 列宽固定、最后一列吃掉剩余空间：横屏宽窗时字段不会散得像天女散花
        for col in range(5):
            self.grid.setColumnMinimumWidth(col, 118 if col < cols else 0)
            self.grid.setColumnStretch(col, 1 if col == cols else 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()

    def sizeHint(self):
        return QSize(380, max(230, super().sizeHint().height()))
