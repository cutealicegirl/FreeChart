# -*- coding: utf-8 -*-
"""搜索页（独立图层）：搜索结果 / 搜索历史不再挤在行情列表上方。

交互约定（用户明确要求）：
- 点击搜索结果行 → 进入该品种图表（不默认加入自选）。
- 加入自选只通过行尾显式「＋ 添加 / ✓ 已添加」按钮。
- 搜索历史保留最近 100 条，点击历史条目直接重新搜索。
- 「← 返回」回行情列表，搜索文本保留。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

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

SEARCH_HISTORY_MAX = 100


def _find_panel(widget):
    panel = widget.parent()
    while panel is not None and not isinstance(panel, SearchResultsPanel):
        panel = panel.parent()
    return panel


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

        tag_color = KIND_TAG_COLOR.get(item["kind"], C_TEXT_DIM)
        tag = QLabel(item["kind"])
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
    """一条搜索历史：点击重新搜索该关键词。"""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.text_value = text
        self.setObjectName("searchRow")
        self.setFixedHeight(44)
        self.setToolTip("点击重新搜索")
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
        lbl = QLabel(str(text))
        lbl.setStyleSheet(
            f"QLabel {{ color:{C_TEXT_MAIN}; font-size:12px;"
            f" background:transparent; }}")
        lbl.setWordWrap(True)
        layout.addWidget(lbl, 1)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            panel = _find_panel(self)
            if panel is not None:
                panel._on_history_pick(self.text_value)
        super().mousePressEvent(event)


class SearchResultsPanel(QFrame):
    """独立搜索页：搜索结果与搜索历史（阶段 8 起加入 stack，不与行情同图层）。

    信号：
      item_toggled(item, added)  — 显式「＋收藏」按钮
      open_requested(item)       — 点击结果行 → 进入图表
      back_requested()           — 「← 返回」
      history_picked(text)       — 点击历史条目
      history_cleared()          — 清空历史
    """

    item_toggled = Signal(dict, bool)
    open_requested = Signal(dict)
    back_requested = Signal()
    history_picked = Signal(str)
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

    def show_history(self, entries: list):
        """显示搜索历史（最近 100 条，最新在前）。"""
        self._mode = "history"
        self._clear_rows()
        n = len(entries)
        self.lbl_title.setText(f"搜索历史 · {n} 条" if n else "搜索历史")
        self.btn_clear_history.setVisible(bool(n))
        if not n:
            self._empty_hint("暂无搜索历史\n输入代码 / 名称 / 合约地址后自动记录，最多保留 100 条")
            return
        for text in entries:
            self._add_widget(SearchHistoryRow(str(text), self._container))

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

    def _on_history_pick(self, text: str):
        self.history_picked.emit(str(text))
