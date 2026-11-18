# -*- coding: utf-8 -*-
"""搜索页（独立图层）：搜索结果 / 搜索历史不再挤在行情列表上方。

交互约定（用户明确要求）：
- 点击搜索结果行 → 进入该品种图表（不默认加入自选）。
- 加入自选只通过行尾显式「＋ 添加 / ✓ 已添加」按钮。
- 搜索历史保留最近 50 条**资产对象**：有 symbol 的历史点击直接打开资产；
  旧版纯查询历史点击后回填搜索框重新搜索。历史条目支持单条删除。
- 网络失败 / 无结果 / 加载中分别显示，不把失败伪装成「无匹配」。
- 「← 返回」回行情列表，搜索文本保留。
"""
import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from core import asset_search as A
from ui.icons import (display_code, register_symbol_name, symbol_icon)
from ui.theme import (C_ACCENT, C_BG_HOVER, C_BG_PANEL, C_BORDER,
                      C_TEXT_DIM, C_TEXT_MAIN, FONT_UI_BOLD, chip_qss,
                      label_qss, mini_btn_qss, panel_qss, scroll_qss)

KIND_TAG_COLOR = {"加密货币": "#f7931a",
                  "沪市A股": "#f6465d",
                  "深市A股": "#4b9cff",
                  "港股": "#f0b90b",
                  "美股": "#b39ddb",
                  "链上合约": "#26a69a"}

SEARCH_HISTORY_MAX = A.HISTORY_MAX   # 50：与 core.asset_search / Android 同口径


def _find_panel(widget):
    panel = widget.parent()
    while panel is not None and not isinstance(panel, SearchResultsPanel):
        panel = panel.parent()
    return panel


def _entry_text(entry) -> str:
    """历史条目的主显示文本（资产 label 优先，兼容旧字符串）。"""
    if not isinstance(entry, dict):
        return str(entry)
    return str(entry.get("label") or entry.get("query")
                or entry.get("symbol") or "")


def _entry_meta(entry) -> str:
    """历史条目副标题：资产类型 · 市场/链 · 短地址，全部来自真实数据。"""
    if not isinstance(entry, dict):
        return "关键词"
    t = entry.get("asset_type") or ""
    parts = []
    if t == A.ASSET_ONCHAIN:
        parts.append("链上代币")
        chain = str(entry.get("chain") or "")
        if chain:
            parts.append(chain)
        addr = str(entry.get("address") or entry.get("symbol") or "")
        if addr.startswith("ONCHAIN:"):
            addr = addr[len("ONCHAIN:"):]
        if addr:
            parts.append(addr[:6] + "…" + addr[-4:] if len(addr) > 12 else addr)
    elif t == A.ASSET_STOCK:
        parts.append("股票")
        market = str(entry.get("market") or "")
        if market:
            parts.append(market.upper())
    elif t == A.ASSET_CEX:
        parts.append("加密货币")
    else:
        parts.append("关键词")
    return " · ".join(parts)


class SearchResultRow(QFrame):
    """一条搜索结果：图标 + 代码/名称 + 市场标签 + 显式添加按钮。

    点击整行 → 进入图表；「＋ 添加」按钮 → 加入/移出自选。
    """

    def __init__(self, item: dict, in_watchlist: bool, parent=None):
        super().__init__(parent)
        self.item = item
        self._in_watchlist = bool(in_watchlist)
        self.setObjectName("searchRow")
        self.setFixedHeight(44)
        self.setToolTip("点击进入图表")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"#searchRow {{ background:transparent; border-radius:4px; }}"
            f"#searchRow:hover {{ background:{C_BG_HOVER}; }}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(8)

        icon = QLabel()
        icon.setFixedSize(24, 24)
        if item.get("name"):
            register_symbol_name(item["symbol"], item["name"])
        icon.setPixmap(symbol_icon(item["symbol"], 24))
        icon.setStyleSheet("background:transparent; border:none;")
        layout.addWidget(icon)

        # 链上合约品种用代币代码显示（ANSEM），而不是 44 位合约地址
        code = item.get("label") or display_code(item["symbol"])
        lbl = QLabel(f"<b style='color:{C_TEXT_MAIN};font-size:12px;'>{code}</b>"
                     f"&nbsp;&nbsp;<span style='color:{C_TEXT_DIM};"
                     f"font-size:11px;'>{item['name']}</span>")
        lbl.setStyleSheet("background:transparent;")
        layout.addWidget(lbl, 1)

        kind = str(item.get("kind") or "")
        tag_color = KIND_TAG_COLOR.get(kind, C_TEXT_DIM)
        atype = item.get("asset_type") or ""
        if atype == A.ASSET_ONCHAIN:
            tag_color = KIND_TAG_COLOR["链上合约"]
        elif atype == A.ASSET_CEX:
            tag_color = KIND_TAG_COLOR["加密货币"]
        tag = QLabel(kind or "资产")
        tag.setStyleSheet(chip_qss(tag_color, 10))
        layout.addWidget(tag)

        self.btn_add = QPushButton()
        self.btn_add.setFixedSize(70, 36)
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.setFocusPolicy(Qt.NoFocus)
        self.btn_add.clicked.connect(self._on_add_click)
        self._sync_button()
        layout.addWidget(self.btn_add)

    def _sync_button(self):
        self.btn_add.setText("✓ 已添加" if self._in_watchlist else "＋ 收藏")
        self.btn_add.setToolTip("移出自选" if self._in_watchlist
                                else "加入自选")
        if self._in_watchlist:
            self.btn_add.setStyleSheet(
                f"QPushButton {{ color:{C_TEXT_DIM};"
                f" background:{C_BG_HOVER}; border:1px solid {C_BORDER};"
                f" border-radius:4px; font-size:11px;"
                f" font-family:{FONT_UI_BOLD}; }}"
                f"QPushButton:hover {{ border:1px solid {C_ACCENT}; }}")
        else:
            self.btn_add.setStyleSheet(mini_btn_qss(False, C_ACCENT))

    def _on_add_click(self):
        panel = _find_panel(self)
        if panel is not None:
            panel._on_toggle(self.item)

    def set_in_watchlist(self, value: bool):
        self._in_watchlist = bool(value)
        self._sync_button()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            panel = _find_panel(self)
            if panel is not None:
                panel._on_open(self.item)
        super().mousePressEvent(event)


class SearchHistoryRow(QFrame):
    """一条搜索历史：点击直接打开对应资产；旧关键词则回填重新搜索。

    资产身份来自 core.asset_search（链上 chain+address / 股票 CEX
    market+symbol），单条删除按 id 上报，不靠字符串文本判断。
    """

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.text_value = _entry_text(entry)   # 兼容旧调用 / 测试
        self._has_asset = isinstance(entry, dict) and bool(entry.get("symbol"))
        self.setObjectName("searchRow")
        self.setFixedHeight(48)
        self.setToolTip("点击打开该资产" if self._has_asset else "点击重新搜索")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"#searchRow {{ background:transparent; border-radius:4px; }}"
            f"#searchRow:hover {{ background:{C_BG_HOVER}; }}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(8)
        icon = QLabel("🕘")
        icon.setStyleSheet("background:transparent; border:none;")
        icon.setFixedSize(20, 20)
        layout.addWidget(icon)

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(0)
        lbl = QLabel(
            f"<b style='color:{C_TEXT_MAIN};font-size:12px;'>"
            f"{html.escape(self.text_value)}</b>")
        lbl.setStyleSheet("background:transparent;")
        text_box.addWidget(lbl)
        meta = QLabel(
            f"<span style='color:{C_TEXT_DIM};font-size:10px;'>"
            f"{html.escape(_entry_meta(entry))}</span>")
        meta.setStyleSheet("background:transparent;")
        text_box.addWidget(meta)
        layout.addLayout(text_box, 1)

        self.btn_delete = QPushButton("×")
        self.btn_delete.setFixedSize(24, 24)
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.setFocusPolicy(Qt.NoFocus)
        self.btn_delete.setToolTip("删除这条历史")
        self.btn_delete.setStyleSheet(
            f"QPushButton {{ color:{C_TEXT_DIM}; background:transparent;"
            f" border:none; font-size:16px; }}"
            f"QPushButton:hover {{ color:{C_ACCENT}; }}")
        self.btn_delete.clicked.connect(self._on_delete)
        layout.addWidget(self.btn_delete)

    def _on_delete(self):
        if self.sender() is not self.btn_delete:
            return
        panel = _find_panel(self)
        if panel is not None:
            panel._on_history_delete(self.entry)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            panel = _find_panel(self)
            if panel is not None:
                panel._on_history_pick(self.entry)
        super().mousePressEvent(event)


class SearchResultsPanel(QFrame):
    """独立搜索页：搜索结果与搜索历史（阶段 8 起加入 stack，不与行情同图层）。

    信号：
      item_toggled(item, added)  — 显式「＋收藏」按钮
      open_requested(item)       — 点击结果行 → 进入图表
      back_requested()           — 「← 返回」
      history_picked(entry)      — 点击历史条目（对象或旧字符串）
      history_deleted(entry)     — 单条删除历史
      history_cleared()          — 清空历史
    """

    item_toggled = Signal(dict, bool)
    open_requested = Signal(dict)
    back_requested = Signal()
    history_picked = Signal(object)
    history_deleted = Signal(object)
    history_cleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("searchPanel")
        self.setStyleSheet(panel_qss())
        self._results: list = []
        self._watchlist: set = set()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        # ---- 页头：返回 + 标题 + 清空历史 ----
        head = QHBoxLayout()
        head.setSpacing(6)
        self.btn_back = QPushButton("← 返回")
        self.btn_back.setFixedSize(90, 44)
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.setToolTip("回到行情列表（搜索内容保留）")
        self.btn_back.setStyleSheet(mini_btn_qss())
        self.btn_back.clicked.connect(self.back_requested.emit)
        head.addWidget(self.btn_back)
        self.lbl_title = QLabel("搜索结果")
        self.lbl_title.setStyleSheet(label_qss(13, bold=True))
        head.addWidget(self.lbl_title, 1)
        self.btn_clear_history = QPushButton("清空历史")
        self.btn_clear_history.setFixedSize(80, 36)
        self.btn_clear_history.setCursor(Qt.PointingHandCursor)
        self.btn_clear_history.setToolTip("删除全部搜索历史（不影响自选）")
        self.btn_clear_history.setStyleSheet(mini_btn_qss())
        self.btn_clear_history.clicked.connect(self.history_cleared.emit)
        self.btn_clear_history.hide()
        head.addWidget(self.btn_clear_history)
        outer.addLayout(head)

        # ---- 内容：结果 / 历史列表（占满剩余高度） ----
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(scroll_qss())
        self._container = QWidget()
        self._container.setStyleSheet(f"background:{C_BG_PANEL};")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(1)
        self._layout.addStretch(1)
        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll, 1)

    # ---- 内容填充 ----
    def _clear_rows(self):
        while self._layout.count() > 1:   # 保留末尾 stretch
            child = self._layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _add_widget(self, w):
        self._layout.insertWidget(self._layout.count() - 1, w)

    def _tip(self, text: str, color=C_ACCENT):
        tip = QLabel(text)
        tip.setWordWrap(True)
        tip.setStyleSheet(
            f"QLabel {{ color:{color}; font-size:11px;"
            f" padding:6px 8px; background:{C_BG_HOVER};"
            f" border-radius:4px; }}")
        self._add_widget(tip)

    def _empty_hint(self, text: str):
        empty = QLabel(text)
        empty.setWordWrap(True)
        empty.setStyleSheet(
            f"QLabel {{ color:{C_TEXT_DIM}; font-size:12px;"
            f" padding:10px; background:transparent; }}")
        self._add_widget(empty)

    def show_results(self, results: list, watchlist: set, note: str = ""):
        """填充搜索结果。results: [{symbol,name,kind}]；note 为顶部说明。"""
        self._results = list(results)
        self._watchlist = set(watchlist)
        self._mode = "results"
        self._clear_rows()
        self.lbl_title.setText(
            f"搜索结果 · {len(results)} 条" if results else "搜索结果")
        self.btn_clear_history.hide()
        if note:
            self._tip(note)
        if not results:
            self._empty_hint("无匹配结果（支持代码 / 名称 / 股票代码 / 链上合约地址）")
        for item in results:
            row = SearchResultRow(
                item, item["symbol"] in self._watchlist, self._container)
            self._add_widget(row)

    def show_loading(self, note: str = ""):
        """加载中：只更新本页内容，不切页（切页仍由结果/失败决定）。"""
        self._mode = "loading"
        self._clear_rows()
        self.lbl_title.setText("搜索中")
        self.btn_clear_history.hide()
        self._tip(note or "正在搜索股票 / 加密货币 / 链上代币…")

    def show_error(self, message: str, detail: str = ""):
        """网络失败 / 数据源不可用：与「无匹配结果」明确区分。"""
        self._mode = "error"
        self._clear_rows()
        self.lbl_title.setText("搜索失败")
        self.btn_clear_history.hide()
        self._tip(message or "网络异常，暂时无法完成搜索", "#f6465d")
        if detail:
            self._empty_hint(detail)

    def show_history(self, entries: list):
        """显示搜索历史（最近 50 条资产对象，最新在前；兼容旧字符串）。"""
        items = A.normalize_history(entries)
        self._mode = "history"
        self._clear_rows()
        n = len(items)
        self.lbl_title.setText(f"搜索历史 · {n} 条" if n else "搜索历史")
        self.btn_clear_history.setVisible(bool(n))
        if not n:
            self._empty_hint(
                "暂无搜索历史\n输入代码 / 名称 / 合约地址并确认后自动记录，"
                f"最多保留 {SEARCH_HISTORY_MAX} 条")
            return
        for entry in items:
            self._add_widget(SearchHistoryRow(entry, self._container))

    def refresh_watch_state(self, watchlist: set):
        """自选变化后同步按钮状态（以真实列表为准，避免状态漂移）。"""
        self._watchlist = set(watchlist)
        if self.isVisible():
            for i in range(self._layout.count() - 1):
                w = self._layout.itemAt(i).widget()
                if isinstance(w, SearchResultRow):
                    w.set_in_watchlist(w.item["symbol"] in self._watchlist)

    # ---- 内部分发（由行控件回调） ----
    def _on_toggle(self, item: dict):
        added = item["symbol"] not in self._watchlist
        if added:
            self._watchlist.add(item["symbol"])
        else:
            self._watchlist.discard(item["symbol"])
        self.item_toggled.emit(item, added)

    def _on_open(self, item: dict):
        self.open_requested.emit(item)

    def _on_history_pick(self, entry):
        self.history_picked.emit(entry)

    def _on_history_delete(self, entry):
        self.history_deleted.emit(entry)
