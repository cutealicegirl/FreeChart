# -*- coding: utf-8 -*-
"""品种详情页（手机式抽屉）：图表页「ⓘ 详情」按钮弹出。

行情行塞不下这些内容，主界面顶部的资料卡也只是精简版；这里给一个完整版：

- 头部：图标 / 代码 / 名称 / 市场 / 市值排名 / 最新价 / 涨跌幅
- 行情：24h 最高、24h 最低、振幅、24h 成交额、计价货币、数据源
- 基本面：总市值、流通市值、市盈率(TTM)、市值排名、总股本 / 流通量

市值 / 股本 / 市盈率来自 data.fundamentals（后台守护线程取，带缓存，
断网时用上次落盘的股本按当前价折算），价格类字段直接用调用方传进来的
Ticker，所以详情页里的数字与列表、图表完全一致。
"""
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QSizeGrip, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from core import brand
from data import fundamentals, history_stats
from data import timeline as timeline_db
from data.universe import market_of, name_of
from ui import units
from ui.icons import display_code, symbol_icon
from ui.popup import popup_card, popup_close_button, popup_qss
from ui.theme import (C_ACCENT, C_BG_BASE, C_BG_HOVER, C_BORDER, C_DOWN,
                      C_TEXT_DIM, C_TEXT_MAIN, C_TEXT_SUB, C_UP, badge_qss,
                      chip_qss, label_qss, panel_qss)
from ui.ticker_widget import format_price, format_volume

MARKETS = {
    "crypto": ("加密货币", "#f7931a"),
    "cn": ("A股", "#f6465d"),
    "hk": ("港股", "#f0b90b"),
    "us": ("美股", "#4b9cff"),
}

_CACHE: dict = {}
# 数据源没有提供时的统一标注：绝不填 0 / 估算值充数
MISSING = fundamentals.MISSING


def _fmt_cap(v) -> str:
    """市值：1.45万亿 / 3721亿 / 45.2亿 / 8600万。"""
    try:
        v = float(v)
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


def _fmt_shares(v) -> str:
    """股本 / 流通量：12.3亿枚 / 8600万 / 1.24万亿。"""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if v <= 0:
        return "—"
    if v >= 1e12:
        return f"{v / 1e12:.2f}万亿"
    if v >= 1e8:
        return f"{v / 1e8:.2f}亿"
    if v >= 1e4:
        return f"{v / 1e4:.0f}万"
    return f"{v:,.0f}"


class _Worker(threading.Thread):
    """后台取基本面（守护线程，窗口关掉也不会拖住进程退出）。"""

    def __init__(self, symbol: str, price: float, signals: "_Signals"):
        super().__init__(daemon=True, name="detail-%s" % symbol)
        self._symbol = symbol
        self._price = float(price or 0.0)
        self._signals = signals

    def run(self):
        try:
            data = fundamentals.profile(self._symbol, self._price, timeout=6.0)
        except Exception:
            data = {}
        try:
            self._signals.ready.emit(self._symbol, data or {})
        except RuntimeError:
            pass


class _HistWorker(threading.Thread):
    """后台算行情里程碑（守护线程，窗口关掉不拖住退出）。"""

    def __init__(self, symbol: str, signals: "_Signals"):
        super().__init__(daemon=True, name="milestone-%s" % symbol)
        self._symbol = symbol
        self._signals = signals

    def run(self):
        try:
            data = history_stats.for_symbol(self._symbol)
        except Exception:
            data = {"ok": False, "reason": "计算失败"}
        try:
            self._signals.hist_ready.emit(self._symbol, data or {})
        except RuntimeError:
            pass


class _Signals(QObject):
    ready = Signal(str, dict)
    hist_ready = Signal(str, dict)


class _Cell(QWidget):
    """一格：小标题 + 数值。"""

    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        self.cap = QLabel(caption)
        self.cap.setStyleSheet(label_qss(9, C_TEXT_DIM))
        lay.addWidget(self.cap)
        self.val = QLabel("—")
        self.val.setStyleSheet(label_qss(13, C_TEXT_MAIN, True, True))
        lay.addWidget(self.val)

    def set(self, text: str, color: str = ""):
        self.val.setText(text or "—")
        self.val.setStyleSheet(
            label_qss(13, color or C_TEXT_MAIN, True, True))


class SymbolDetailDialog(QDialog):
    """品种详情抽屉：无模型乱跳，纯展示，数据回填前先显示已有行情。"""

    def __init__(self, symbol: str, name: str = "", ticker=None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("品种详情")
        self.setStyleSheet(popup_qss())       # 全程序统一弹窗规格
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        # 无边框窗口没有原生标题栏，需要自己实现拖动 + 让出最小尺寸，
        # 否则小屏上窗口可能卡在屏幕外 / 内容被切掉且无法拉伸查看。
        self._drag = None
        self._head = None
        self._close_btn = None
        self.symbol = symbol or ""
        self._name = name or name_of(self.symbol) or self.symbol
        self._ticker = ticker
        self._profile = dict(_CACHE.get(symbol) or {})
        self._worker = None
        self._signals = _Signals(self)
        self._signals.ready.connect(self._on_profile)
        self._signals.hist_ready.connect(self._on_milestones)
        self._hist_worker = None
        self._milestones = {}
        self._tl_rows = []
        self._tl_all = False

        owner = parent
        w = int(getattr(owner, "width", lambda: 480)() or 480)
        h = int(getattr(owner, "height", lambda: 820)() or 820)
        self.resize(max(380, min(620, w - 24)), max(460, min(800, h - 40)))
        self.setMinimumSize(380, 460)
        # 居中到父窗口，避免无边框窗口默认出现在屏幕角落 / 被主窗遮挡
        if isinstance(owner, QWidget) and not owner.isHidden():
            pr = owner.geometry()
            self.move(pr.center() - self.rect().center())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 统一标题栏（与设置页 / 悬停资料卡同一套 objectName + QSS）----
        bar = QFrame()
        self._head = bar
        bar.setObjectName("popupHead")
        bar.setFixedHeight(44)
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(14, 4, 6, 4)
        bh.setSpacing(8)
        title = QLabel("品种详情")
        title.setObjectName("popupTitle")
        bh.addWidget(title)
        bh.addStretch(1)
        btn_close = popup_close_button(bar)
        self._close_btn = btn_close
        btn_close.clicked.connect(self.reject)
        bh.addWidget(btn_close)
        root.addWidget(bar)

        # ---- 内容 ----
        body = QWidget()
        body.setStyleSheet(f"background:{C_BG_BASE};")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(12, 10, 12, 12)
        body_lay.setSpacing(10)

        self.lbl_verified = QLabel(
            f"{brand.APP_NAME} · 品种档案核验于 "
            f"{timeline_db.VERIFIED_AT}（离线公开资料）")
        self.lbl_verified.setWordWrap(True)
        self.lbl_verified.setStyleSheet(label_qss(9, C_TEXT_DIM))
        body_lay.addWidget(self.lbl_verified)
        body_lay.addWidget(self._build_head())
        # 阶段 1：按「行情 → 估值 → 供应/成交 → 介绍 → 进阶 → 来源」
        # 分层，逐层深入；每张卡都是同一套 popup_card 规格。
        quote_card, self._quote_cells = self._build_card(
            "行情数据", (("high", "24h 最高"), ("low", "24h 最低"),
                        ("amp", "振幅"), ("vol", "24h 成交额"),
                        ("unit", "计价货币"), ("src", "行情数据源")))
        body_lay.addWidget(quote_card)
        fund_card, self._fund_cells = self._build_card(
            "市值与估值", (("cap", "总市值"), ("fcap", "流通市值"),
                          ("pe", "市盈率 TTM"), ("rank", "市值排名"),
                          ("shares", "总股本 / 流通量"),
                          ("updated", "更新时间")))
        body_lay.addWidget(fund_card)

        supply_card, self._supply_cells = self._build_card(
            "供应 · 成交 · 流动性",
            (("sc", "流通量"), ("st", "总供应量"), ("sm", "最大供应量"),
             ("vol", "成交量 / 额"), ("turnover", "换手率"),
             ("liquidity", "流动性")))
        body_lay.addWidget(supply_card)

        is_crypto = market_of(self.symbol) == "crypto"
        self._is_crypto = is_crypto
        if is_crypto:
            extra_title = "项目用途 · 代币经济学"
            extra_fields = (("purpose", "项目用途"),
                            ("allocation", "代币分配"),
                            ("unlock", "解锁计划"),
                            ("protocol_rev", "协议收入"),
                            ("pb", "市净率（不适用）"),
                            ("outlook", "发展前景"))
        else:
            extra_title = "公司业务 · 财务指标"
            extra_fields = (("purpose", "主营业务"),
                            ("revenue", "营业收入"),
                            ("profit", "净利润"),
                            ("pb", "市净率 PB"),
                            ("outlook", "发展前景"),
                            ("liquidity", "流动性"))
        extra_card, self._extra_cells = self._build_card(
            extra_title, extra_fields)
        body_lay.addWidget(extra_card)

        # ---- v37：交易所快照里的已核实真实字段（股票）----
        snap_card, self._snap_cells = self._build_card(
            "交易所快照 · 真实字段",
            (("prev", "昨收"), ("open", "今开"),
             ("dhigh", "当日最高"), ("dlow", "当日最低"),
             ("amp2", "振幅"), ("ratio", "量比"),
             ("avg", "均价"), ("pe_dyn", "市盈率(动)"),
             ("pe_sta", "市盈率(静)"), ("updown", "涨停 / 跌停"),
             ("w52", "52 周高 / 低"), ("tz", "行情时区")))
        body_lay.addWidget(snap_card)

        # ---- v37：品种档案（行业 / 交易所 / 上市日 / 官网 …）----
        archive_card, self._archive_cells = self._build_card(
            "品种档案 · 可核对字段",
            tuple((k, c) for k, c in timeline_db.ARCHIVE_FIELDS))
        body_lay.addWidget(archive_card)

        # ---- v37：发展历程时间线（离线公开资料，逐条带来源）----
        self.tl_card, self.tl_lay = popup_card("发展历程 · 里程碑", self)
        self.tl_lay.setContentsMargins(12, 10, 12, 12)
        self.tl_lay.setSpacing(6)
        self.tl_box = QWidget(self.tl_card)
        self.tl_box.setStyleSheet("background:transparent;")
        self.tl_box_lay = QVBoxLayout(self.tl_box)
        self.tl_box_lay.setContentsMargins(0, 0, 0, 0)
        self.tl_box_lay.setSpacing(6)
        self.tl_lay.addWidget(self.tl_box)
        self.lbl_tl_note = QLabel("", self.tl_card)
        self.lbl_tl_note.setWordWrap(True)
        self.lbl_tl_note.setStyleSheet(label_qss(9, C_TEXT_DIM))
        self.tl_lay.addWidget(self.lbl_tl_note)
        self.btn_tl_more = QPushButton("展开全部", self.tl_card)
        self.btn_tl_more.setCursor(Qt.PointingHandCursor)
        self.btn_tl_more.setStyleSheet(
            f"QPushButton{{background:{C_BG_HOVER}; color:{C_ACCENT};"
            f" border:1px solid {C_BORDER}; border-radius:6px;"
            f" padding:6px 10px; font-size:10px;}}")
        self.btn_tl_more.clicked.connect(self._toggle_timeline)
        self.btn_tl_more.setVisible(False)
        self.tl_lay.addWidget(self.btn_tl_more)
        body_lay.addWidget(self.tl_card)

        # ---- v37：行情里程碑（真实历史 K 线算的，不是人工资料）----
        ms_card, self._ms_cells = self._build_card(
            "行情里程碑 · 真实历史数据",
            (("span", "统计区间"), ("mhigh", "区间最高"),
             ("mlow", "区间最低"), ("mchg", "区间涨跌"),
             ("mdd", "最大回撤"), ("bars", "样本 / 来源")))
        body_lay.addWidget(ms_card)

        # ---- 项目 / 公司 / 产品 / 创始人介绍（离线资料，秒开）----
        about_card, about_lay = popup_card("项目 · 公司介绍", self)
        self.lbl_about_meta = QLabel("", about_card)
        self.lbl_about_meta.setWordWrap(True)
        self.lbl_about_meta.setStyleSheet(label_qss(10, C_ACCENT, True))
        about_lay.addWidget(self.lbl_about_meta)
        self.lbl_about = QLabel("", about_card)
        self.lbl_about.setWordWrap(True)
        self.lbl_about.setStyleSheet(label_qss(11, C_TEXT_SUB))
        about_lay.addWidget(self.lbl_about)
        body_lay.addWidget(about_card)
        self._render_about()

        # ---- 数据来源与更新时间（每个数字都要能追溯）----
        src_card, src_lay = popup_card("数据来源与更新时间", self)
        self.lbl_source = QLabel("", src_card)
        self.lbl_source.setWordWrap(True)
        self.lbl_source.setStyleSheet(label_qss(10, C_TEXT_SUB))
        src_lay.addWidget(self.lbl_source)
        body_lay.addWidget(src_card)

        note = QLabel("市值 = 股本 × 当前价，随最新价折算；市盈率为 TTM 口径。"
                      "介绍与发展历程为 AI 依据公开资料整理的离线资料"
                      f"（核验于 {timeline_db.VERIFIED_AT}），"
                      "行情里程碑由真实历史数据计算；暂无数据的字段一律明确标注，"
                      "不以估算值填充。本程序仅展示公开行情，不构成投资建议。")
        note.setObjectName("popupNote")
        note.setWordWrap(True)
        note.setStyleSheet(label_qss(9, C_TEXT_DIM))
        body_lay.addWidget(note)
        body_lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # 右下角缩放手柄：无边框窗口也能拖拽放大 / 缩小查看全部内容
        grip = QSizeGrip(self)
        grip.setCursor(Qt.SizeFDiagCursor)
        root.addWidget(grip, 0, Qt.AlignRight | Qt.AlignBottom)

        self.set_ticker(ticker)
        self._render_profile()
        self._render_archive()
        self._render_timeline()
        self._render_milestones()
        self._fetch()

    # ---------------------------------------------------------------- 构建
    def _build_head(self) -> QWidget:
        card, lay = popup_card("", self)
        lay.setContentsMargins(12, 11, 12, 11)
        lay.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.icon = QLabel()
        self.icon.setFixedSize(38, 38)
        self.icon.setStyleSheet("background:transparent;")
        self.icon.setPixmap(symbol_icon(self.symbol, 38))
        top.addWidget(self.icon)
        left = QVBoxLayout()
        left.setSpacing(1)
        code_row = QHBoxLayout()
        code_row.setSpacing(6)
        self.lbl_code = QLabel(display_code(self.symbol))
        self.lbl_code.setStyleSheet(
            f"color:{C_TEXT_MAIN}; font-size:17px; font-weight:700;"
            f" font-family:'IBM Plex Mono SemiBold', 'Consolas', monospace;")
        code_row.addWidget(self.lbl_code)
        label, color = MARKETS.get(market_of(self.symbol), ("", C_ACCENT))
        self.lbl_market = QLabel(label)
        self.lbl_market.setStyleSheet(chip_qss(color, 9))
        self.lbl_market.setVisible(bool(label))
        code_row.addWidget(self.lbl_market)
        self.lbl_rank = QLabel("")
        self.lbl_rank.setStyleSheet(badge_qss(C_ACCENT, C_BG_HOVER, 9))
        self.lbl_rank.setVisible(False)
        code_row.addWidget(self.lbl_rank)
        code_row.addStretch(1)
        left.addLayout(code_row)
        self.lbl_name = QLabel(self._name)
        self.lbl_name.setStyleSheet(label_qss(11, C_TEXT_SUB))
        left.addWidget(self.lbl_name)
        top.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(0)
        right.setAlignment(Qt.AlignRight)
        self.lbl_price = QLabel("--")
        self.lbl_price.setAlignment(Qt.AlignRight)
        self.lbl_price.setStyleSheet(
            f"color:{C_TEXT_MAIN}; font-size:20px; font-weight:700;"
            f" font-family:'IBM Plex Mono SemiBold', 'Consolas', monospace;")
        self.lbl_change = QLabel("--")
        self.lbl_change.setAlignment(Qt.AlignRight)
        self.lbl_change.setStyleSheet(label_qss(12, C_TEXT_SUB, True, True))
        right.addWidget(self.lbl_price)
        right.addWidget(self.lbl_change)
        top.addLayout(right)
        lay.addLayout(top)
        return card

    def _build_card(self, title: str, fields) -> tuple:
        card, lay = popup_card(title, self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(9)
        cells = {}
        for i, (key, caption) in enumerate(fields):
            cell = _Cell(caption)
            cells[key] = cell
            grid.addWidget(cell, i // 3, i % 3)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        lay.addLayout(grid)
        return card, cells

    # ---------------------------------------------------------------- 数据
    def set_ticker(self, ticker):
        """行情快照（主窗口每次刷新都会推进来）。"""
        self._ticker = ticker
        t = ticker
        sym = self.symbol
        try:
            price = float(getattr(t, "last_price", 0) or 0)
            change = float(getattr(t, "change_pct", 0) or 0)
            high = float(getattr(t, "high_24h", 0) or 0)
            low = float(getattr(t, "low_24h", 0) or 0)
            vol = float(getattr(t, "quote_volume_24h", 0) or 0)
        except (TypeError, ValueError):
            return
        if t is None:
            return
        self.lbl_price.setText(
            units.with_unit(format_price(price), sym, units.ENABLED))
        color = C_UP if change > 0 else (C_DOWN if change < 0 else C_TEXT_SUB)
        arrow = "▲" if change > 0 else ("▼" if change < 0 else "·")
        self.lbl_change.setText(f"{arrow} {change:+.2f}%")
        self.lbl_change.setStyleSheet(label_qss(12, color, True, True))
        self.lbl_price.setStyleSheet(
            f"color:{color}; font-size:20px; font-weight:700;"
            f" font-family:'IBM Plex Mono SemiBold', 'Consolas', monospace;")

        common = units.ENABLED
        self._quote_cells["high"].set(
            units.with_unit(format_price(high), sym, common) if high else "—")
        self._quote_cells["low"].set(
            units.with_unit(format_price(low), sym, common) if low else "—")
        amp = ((high - low) / low * 100.0) if (low > 0 and high > 0) else 0.0
        self._quote_cells["amp"].set(f"{amp:.2f}%" if amp else "—")
        self._quote_cells["vol"].set(
            format_volume(vol) if vol else "—")
        unit = {"cn": "人民币 ¥", "hk": "港币 HK$",
                "us": "美元 $", "crypto": "美元 $"}.get(market_of(sym), "—")
        self._quote_cells["unit"].set(unit)

    def _on_profile(self, symbol: str, data: dict):
        self._worker = None
        if data:
            _CACHE[symbol] = dict(data)
        if symbol == self.symbol:
            self._profile = dict(data or {})
            self._render_profile()

    def _fetch(self):
        if not self.symbol:
            return
        # 行情里程碑与基本面并行取，互不阻塞
        if self._hist_worker is None:
            hw = _HistWorker(self.symbol, self._signals)
            self._hist_worker = hw
            hw.start()
        if self._profile:
            return                      # 本次会话已取过，直接渲染
        price = float(getattr(self._ticker, "last_price", 0) or 0)
        worker = _Worker(self.symbol, price, self._signals)
        self._worker = worker
        worker.start()

    def _render_about(self):
        """项目 / 公司分区介绍（离线资料库，不等网络）。

        四个分区只重组资料库里已核实的字段；没有依据的（发展前景等）
        明确显示「— 暂无公开资料」，不写预测、不编造。
        """
        a = fundamentals.about(self.symbol, self._name)
        self._about_data = a
        meta = [str(a.get(k) or "") for k in ("title", "category", "since")]
        self.lbl_about_meta.setText(" · ".join(
            x for x in meta if x and x != "—"))
        founder = str(a.get("founder") or "")
        rows = ["创始人 / 创办团队：" +
                (founder if founder and founder != "—" else "— 暂无公开资料")]
        for label, key in (("项目背景", "background"),
                           ("业务介绍", "business"),
                           ("核心特点", "highlights"),
                           ("发展前景", "outlook")):
            val = str(a.get(key) or "").strip()
            rows.append(f"【{label}】{val if val else '— 暂无公开资料'}")
        self.lbl_about.setText("\n\n".join(rows))

    # ------------------------------------------------------------ v37 资料
    def _render_archive(self):
        """品种档案：只展示资料库里能核对的字段，未收录的一律留白。"""
        a = getattr(self, "_about_data", None) or {}
        arc = a.get("archive") or timeline_db.archive(self.symbol)
        fields = (a.get("archive_fields")
                  or [list(x) for x in timeline_db.ARCHIVE_FIELDS])
        for key, _cap in fields:
            cell = self._archive_cells.get(key)
            if cell is None:
                continue
            val = arc.get(key)
            cell.set(str(val) if val not in (None, "") else MISSING)
        if not arc.get("covered"):
            self.lbl_verified.setText(
                f"{brand.APP_NAME} · 该品种档案未收录，"
                "仅展示可由代码推断的交易所信息，其余字段留白")

    def _timeline_row(self, ev: dict) -> QWidget:
        """一条里程碑：日期 | 标题 + 说明 + 来源。"""
        row = QFrame(self.tl_box)
        row.setStyleSheet(
            f"QFrame{{background:{C_BG_HOVER}; border-left:2px solid "
            f"{C_ACCENT}; border-radius:5px;}}")
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(8)
        d = QLabel(str(ev.get("date") or "—"), row)
        d.setFixedWidth(84)
        d.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        d.setStyleSheet(label_qss(10, C_ACCENT, True, True))
        h.addWidget(d)
        v = QVBoxLayout()
        v.setSpacing(2)
        t = QLabel(str(ev.get("title") or "—"), row)
        t.setWordWrap(True)
        t.setStyleSheet(label_qss(11, C_TEXT_MAIN, True))
        v.addWidget(t)
        detail = str(ev.get("detail") or "").strip()
        if detail:
            dl = QLabel(detail, row)
            dl.setWordWrap(True)
            dl.setStyleSheet(label_qss(10, C_TEXT_SUB))
            v.addWidget(dl)
        src = QLabel("来源：" + str(ev.get("src") or "公开资料整理"), row)
        src.setWordWrap(True)
        src.setStyleSheet(label_qss(9, C_TEXT_DIM))
        v.addWidget(src)
        h.addLayout(v, 1)
        return row

    def _render_timeline(self):
        a = getattr(self, "_about_data", None) or {}
        rows = a.get("timeline") or timeline_db.timeline(self.symbol)
        self._tl_rows = list(rows)
        note = a.get("timeline_note") or timeline_db.SOURCE_NOTE
        srcs = a.get("timeline_sources") or []
        self.lbl_tl_note.setText(
            note + (("\n引用来源：" + " / ".join(srcs)) if srcs else ""))
        while self.tl_box_lay.count():
            item = self.tl_box_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        if not self._tl_rows:
            empty = QLabel(timeline_db.NO_DATA, self.tl_box)
            empty.setWordWrap(True)
            empty.setStyleSheet(label_qss(10, C_TEXT_DIM))
            self.tl_box_lay.addWidget(empty)
            self.btn_tl_more.setVisible(False)
            return
        shown = self._tl_rows if self._tl_all else self._tl_rows[:6]
        for ev in shown:
            self.tl_box_lay.addWidget(self._timeline_row(ev))
        more = len(self._tl_rows) - len(shown)
        self.btn_tl_more.setVisible(bool(more) or self._tl_all)
        self.btn_tl_more.setText(
            f"展开全部（共 {len(self._tl_rows)} 条）" if more
            else "收起（只看前 6 条）")

    def _toggle_timeline(self):
        self._tl_all = not self._tl_all
        self._render_timeline()

    def _on_milestones(self, symbol: str, data: dict):
        self._hist_worker = None
        if symbol == self.symbol:
            self._milestones = dict(data or {})
            self._render_milestones()

    def _render_milestones(self):
        """真实历史数据统计；明确写「区间」，绝不冒充上市以来全历史。"""
        m = self._milestones or {}
        cells = self._ms_cells
        if not m.get("ok"):
            for cell in cells.values():
                cell.set(MISSING)
            cells["span"].set(
                "— 暂无历史数据" if not m else f"— {m.get('reason') or '未取到'}")
            return

        def px(v):
            return units.with_unit(format_price(v), self.symbol, units.ENABLED)

        cells["span"].set(f"{m['start']} → {m['end']}")
        cells["mhigh"].set(f"{px(m['high'])} · {m['high_date']}")
        cells["mlow"].set(f"{px(m['low'])} · {m['low_date']}")
        chg = float(m["change_pct"])
        color = C_UP if chg > 0 else (C_DOWN if chg < 0 else C_TEXT_SUB)
        cells["mchg"].set(f"{chg:+.2f}%", color)
        cells["mdd"].set(f"{float(m['max_drawdown']):.2f}%", C_DOWN)
        cells["bars"].set(f"{m['bars']} 根 · {m['source']}")
        self._ms_cells["bars"].setToolTip(str(m.get("note") or ""))

    def _render_snapshot(self, prof: dict):
        """交易所快照里已核实含义的真实字段（按市场区分单位）。"""
        c = self._snap_cells
        is_cn = market_of(self.symbol) == "cn"
        cur = prof.get("quote_currency") or ""

        def put(key, value, fmt=None, missing=MISSING):
            cell = c.get(key)
            if cell is None:
                return
            if value is None or value == "":
                cell.set(missing)
                return
            try:
                cell.set(fmt(value) if fmt else str(value))
            except (TypeError, ValueError):
                cell.set(missing)

        def price(v):
            return units.with_unit(format_price(v), self.symbol, units.ENABLED)

        put("prev", prof.get("prev_close"), price)
        put("open", prof.get("open_price"), price)
        put("dhigh", prof.get("day_high"), price)
        put("dlow", prof.get("day_low"), price)
        put("amp2", prof.get("amplitude"), lambda v: f"{float(v):.2f}%")
        put("ratio", prof.get("volume_ratio"), lambda v: f"{float(v):.2f}")
        put("avg", prof.get("avg_price"), price)
        put("pe_dyn", prof.get("pe_dynamic"), lambda v: f"{float(v):.2f}")
        put("pe_sta", prof.get("pe_static"), lambda v: f"{float(v):.2f}")
        up, dn = prof.get("limit_up"), prof.get("limit_down")
        put("updown", f"{price(up)} / {price(dn)}" if (up and dn) else None,
            missing=("— 不适用" if not is_cn else MISSING))
        wh, wl = prof.get("week52_high"), prof.get("week52_low")
        put("w52", f"{price(wh)} / {price(wl)}" if (wh and wl) else None,
            missing=("— 不适用（A 股该字段为涨跌停价）" if is_cn else MISSING))
        put("tz", prof.get("quote_tz") or None)
        c["tz"].setToolTip(f"计价：{cur}；交易所：{prof.get('exchange') or '—'}")

    def _render_profile(self):
        prof = self._profile or {}
        price = float(getattr(self._ticker, "last_price", 0) or 0)
        cap = prof.get("cap")
        fcap = prof.get("float_cap")
        if not cap and price and prof.get("shares"):
            cap = float(prof["shares"]) * price
        if not fcap and price and prof.get("float_shares"):
            fcap = float(prof["float_shares"]) * price
        rank = prof.get("rank") or 0
        self._fund_cells["cap"].set(_fmt_cap(cap))
        self._fund_cells["fcap"].set(_fmt_cap(fcap))
        pe = prof.get("pe")
        self._fund_cells["pe"].set(
            f"{float(pe):.2f}" if pe else ("—" if market_of(self.symbol)
                                           != "crypto" else "不适用"))
        self._fund_cells["rank"].set(f"#{int(rank)}" if rank else "—")
        shares = _fmt_shares(prof.get("shares"))
        fshares = _fmt_shares(prof.get("float_shares"))
        self._fund_cells["shares"].set(
            f"{shares} / {fshares}" if fshares != "—" else shares)
        self._quote_cells["src"].set(prof.get("source") or "行情快照")
        # 真实采集 / 行情时间，不再用「刚刚」这种没有依据的假值
        self._fund_cells["updated"].set(prof.get("updated_text") or MISSING)

        a = (prof.get("about") or getattr(self, "_about_data", None)
             or fundamentals.about(self.symbol, self._name))

        def put(cells, key, value, fmt=None, missing=MISSING):
            """统一判空：任何 None 都明确标注，绝不填 0 或估算值。"""
            cell = cells.get(key)
            if cell is None:
                return
            if value is None or value == "":
                cell.set(missing)
                return
            try:
                cell.set(fmt(value) if fmt else str(value))
            except (TypeError, ValueError):
                cell.set(missing)

        # ---- 供应 · 成交 · 流动性 ----
        put(self._supply_cells, "sc",
            prof.get("supply_circulating") or prof.get("shares"), _fmt_shares)
        put(self._supply_cells, "st", prof.get("supply_total"), _fmt_shares)
        put(self._supply_cells, "sm", prof.get("supply_max"), _fmt_shares)
        vol, unit = prof.get("volume_24h"), prof.get("volume_unit") or ""
        if vol is None:
            vol_text = MISSING
        elif "USD" in unit:
            vol_text = "$" + _fmt_cap(vol)
        elif "手" in unit:
            vol_text = f"{_fmt_shares(vol)} 手"
        else:
            vol_text = _fmt_cap(vol)
        self._supply_cells["vol"].set(vol_text)
        put(self._supply_cells, "turnover", prof.get("turnover_rate"),
            lambda v: f"{float(v):.2f}%")
        put(self._supply_cells, "liquidity", prof.get("liquidity"))

        # ---- 用途 / 代币经济学 或 公司财务 ----
        put(self._extra_cells, "purpose", a.get("purpose"))
        put(self._extra_cells, "allocation", prof.get("token_allocation"))
        put(self._extra_cells, "unlock", prof.get("unlock_schedule"))
        put(self._extra_cells, "protocol_rev", prof.get("protocol_revenue"))
        put(self._extra_cells, "revenue", prof.get("revenue"))
        put(self._extra_cells, "profit", prof.get("profit"))
        put(self._extra_cells, "outlook", a.get("outlook"))
        put(self._extra_cells, "liquidity", prof.get("liquidity"))
        put(self._extra_cells, "pb", prof.get("pb"),
            lambda v: f"{float(v):.2f}",
            missing=("— 不适用（非公司主体）" if self._is_crypto
                     else MISSING))

        # ---- 来源与时间：每个数字都要能追溯 ----
        src = prof.get("source") or "—"
        src_note = prof.get("source_note") or ""
        src_url = prof.get("source_url") or ""
        ts = prof.get("updated_text") or MISSING
        kind = prof.get("updated_kind") or ""
        self.lbl_source.setText("\n".join([
            f"数值来源：{src}" + (f"（{src_note}）" if src_note else ""),
            f"采集 / 行情时间：{ts}" + (f" · {kind}" if kind else ""),
            f"接口：{src_url}" if src_url else "接口：— 暂无",
            f"介绍来源：{a.get('source_note') or '—'}",
            f"发展历程来源：{a.get('timeline_note') or timeline_db.NO_DATA}",
            "行情里程碑：由真实历史 K 线 / 本机报价采样计算，"
            "统计区间以数据源返回范围为准，不等同于上市以来全历史。",
            "未接入数据源的字段显示「— 暂无公开数据」，不做估算或填充。",
        ]))
        if rank:
            self.lbl_rank.setText(f"市值 #{int(rank)}")
            self.lbl_rank.setVisible(True)
        self._render_snapshot(prof)

    # ---------------------------------------------------------------- 事件
    def closeEvent(self, event):
        """关掉时不等待后台线程（守护线程自己会结束）。"""
        self._worker = None
        self._hist_worker = None
        super().closeEvent(event)

    # ------------------------------------------------- 无边框拖动 / 缩放
    def _head_hit(self, pos) -> bool:
        """点在标题栏区域（标题文字 / 标题栏背景）才允许拖动，
        但点关闭按钮不算，避免误触。"""
        if self._head is None:
            return False
        if not self._head.geometry().contains(pos):
            return False
        if self._close_btn is not None and self.childAt(pos) is self._close_btn:
            return False
        return True

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._head_hit(event.pos()):
            self._drag = (event.globalPosition().toPoint()
                          - self.frameGeometry().topLeft())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag = None
        super().mouseReleaseEvent(event)
