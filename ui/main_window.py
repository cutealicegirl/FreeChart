# -*- coding: utf-8 -*-
"""主窗口：币安风格多市场行情看板。

结构：
- 顶部品牌标题栏 + 四个市场页签（加密货币/A股/港股/美股，分页隔离）；
- 每个市场下「自选 / 全部」二级子菜单，全部页可一键加入自选；
- 搜索（内嵌结果面板）/ 排序 / 设置工具条；
- 点击条目进入全宽 K 线图表页；右键菜单管理顺序、自选与托盘品种；
- 系统托盘：开机自启可自动隐藏，图标上实时显示自定义品种价格。
"""
import sys
import threading
import time
import html

if sys.platform == "win32":
    import ctypes.wintypes as _cwin    # 无边框窗口原生边缘缩放（WM_NCHITTEST）
else:                                  # 非 Windows：仅标题栏拖动 + 最大化按钮
    _cwin = None

from PySide6.QtCore import (QEvent, QObject, QPoint, QRect, QSize, Qt,
                            QThread, QTimer, Signal)
from PySide6.QtGui import QAction, QIcon, QCursor
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QMenu,
                               QPushButton, QScrollArea, QScroller, QSizePolicy,
                               QStackedWidget, QSystemTrayIcon, QToolButton,
                               QToolTip, QVBoxLayout, QWidget)

from core.autostart import set_enabled as set_autostart
from core.config import DEFAULT_SYMBOLS, Config
from core import brand, onchain_history, asset_search
from core.live_feed import LiveFeed
from core.thread_cleanup import _ORPHAN_THREADS
from core.updater import RefreshScheduler, SearchWorker
from data import onchain, rank_meta, stock_logo
from data.contract_search import ContractWorker, is_contract
from data.market_manager import MarketManager
from data.prefetch import PrefetchWorker
from data.universe import all_of, names
from ui import units
from ui.chart_view import ChartView
from ui.detail_dialog import SymbolDetailDialog
from ui.icons import (app_icon, app_icon_keys, app_icon_pixmap, app_logo,
                      display_code, invalidate_symbol, nav_glyph,
                      search_glyph, set_app_icon_key, symbol_icon,
                      tray_app_icon, tray_price_icon)
from ui.info_panel import SymbolInfoPanel, format_cap
from ui.mascot import MascotWindow
from ui.popup import popup_qss
from ui.price_badge import PriceBadge
from ui.search_panel import SearchResultsPanel
from ui.settings_dialog import SettingsPage
from ui.theme import (C_ACCENT, C_BG_BASE, C_BG_HOVER, C_BG_PANEL,
                      C_BORDER, C_TEXT_DIM, C_TEXT_MAIN, C_TEXT_SUB,
                      THEME_LABELS, apply_global, badge_qss, bottom_nav_qss,
                      chip_qss, combo_qss, icon_btn_qss, label_qss,
                      line_edit_qss, menu_qss, panel_qss, recolor_styles,
                      scroll_qss, segment_qss, set_theme, sort_btn_qss,
                      tab_qss)
from ui.ticker_widget import (StatusPanel, TickerWidget, begin_tooltip_hold,
                              end_tooltip_hold, format_price,
                              install_tooltip_guard, tooltip_hold_count)

COIN_NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana",
    "BNB": "BNB", "XRP": "XRP", "DOGE": "Dogecoin",
    "HYPE": "Hyperliquid", "ENA": "Ethena", "TAO": "Bittensor",
    "ZEC": "Zcash", "ONDO": "Ondo", "PUMP": "Pump.fun",
    "NEAR": "NEAR Protocol", "ARB": "Arbitrum", "RENDER": "Render",
    "FIL": "Filecoin", "AR": "Arweave",
}

# 阶段 3：前 5 项顺序必须保持（v5 回归依赖 findData 索引），新增项一律追加。
# 分组顺序：涨跌幅 → 价格 → 成交额 → 市值 → 流动性 → 上市/创立 → 默认/自定义。
SORT_MODES = [
    ("custom", "自定义排序"),
    ("change_desc", "涨跌幅 高→低"),
    ("change_asc", "涨跌幅 低→高"),
    ("price_desc", "价格 高→低"),
    ("amount_desc", "成交额 高→低"),
    ("price_asc", "价格 低→高"),
    ("amount_asc", "成交额 低→高"),
    ("cap_desc", "市值 高→低"),
    ("cap_asc", "市值 低→高"),
    ("liquidity_desc", "流动性 高→低"),
    ("liquidity_asc", "流动性 低→高"),
    ("listed_desc", "上市/创立 新→旧"),
    ("listed_asc", "上市/创立 旧→新"),
    ("default", "默认（市值榜单序）"),
]

# 排序按钮上的短标签（单击循环切换）
SORT_SHORT = {
    "custom": "自定义", "change_desc": "涨幅 ↓",
    "change_asc": "涨幅 ↑", "price_desc": "价格 ↓",
    "amount_desc": "成交额 ↓", "price_asc": "价格 ↑",
    "amount_asc": "成交额 ↑", "cap_desc": "市值 ↓",
    "cap_asc": "市值 ↑", "liquidity_desc": "流动性 ↓",
    "liquidity_asc": "流动性 ↑", "listed_desc": "上市 新",
    "listed_asc": "上市 旧", "default": "默认",
}

# 单击「⇅」在当前维度内翻转升/降序
REVERSE_SORT = {
    "change_desc": "change_asc", "change_asc": "change_desc",
    "price_desc": "price_asc", "price_asc": "price_desc",
    "amount_desc": "amount_asc", "amount_asc": "amount_desc",
    "cap_desc": "cap_asc", "cap_asc": "cap_desc",
    "liquidity_desc": "liquidity_asc", "liquidity_asc": "liquidity_desc",
    "listed_desc": "listed_asc", "listed_asc": "listed_desc",
}

# 排序菜单分组：(分组名, [(模式, 显示名)])
SORT_GROUPS = [
    ("行情", ["change_desc", "change_asc", "price_desc", "price_asc",
              "amount_desc", "amount_asc"]),
    ("规模", ["cap_desc", "cap_asc"]),
    ("流动性", ["liquidity_desc", "liquidity_asc"]),
    ("时间", ["listed_desc", "listed_asc"]),
    ("其它", ["default", "custom"]),
]

# 需要额外元数据的排序（走后台批量取数，不阻塞 UI）
META_SORT_MODES = {"cap_desc", "cap_asc", "liquidity_desc", "liquidity_asc",
                   "listed_desc", "listed_asc"}

# ---- 阶段 2：按需加载参数 ----
# 打开「全部」页只把首屏 PAGE_SIZE 行挂进布局、只请求这些标的的行情；
# 滚动接近底部时再追加下一页。行对象仍分批预建（保持既有回归兼容），
# 但不再一次性把 500 个 QWidget 塞进布局，也不再整页刷新 500 行。
PAGE_SIZE = 60
PREFETCH_ROWS = 60           # 请求比已挂载行数多预取一页，滚动时无缝
MAX_REFRESH_SYMBOLS = 300    # 单次请求上限，避免 URL 过长 / 触发限流
MAX_RETRY = 3                # 手动重试次数上限，绝不无限弹窗/无限重试

# 市场分组定义：(分组键, 页签标题, 强调色)
MARKET_GROUPS = [
    ("crypto", "加密货币", "#f7931a"),
    ("cn",     "A股",     "#f6465d"),
    ("hk",     "港股",    "#f0b90b"),
    ("us",     "美股",    "#4b9cff"),
]


def market_of(symbol: str) -> str:
    """根据统一代码判断所属市场分组。"""
    if symbol.startswith(("SH:", "SZ:")):
        return "cn"
    if symbol.startswith("HK:"):
        return "hk"
    if symbol.startswith("US:"):
        return "us"
    return "crypto"


def make_tray_icon():
    """兼容旧引用：返回项目图标。"""
    return app_icon()


class _RankSignals(QObject):
    """后台元数据线程回主线程的桥（跨线程必须用 Qt 信号）。

    载荷带 key 与请求序号：
      - key 让回调用「请求所属市场」重排，而非回调瞬间当前市场（防错配）；
      - seq 让旧请求结果被丢弃（防慢请求覆盖新请求）。
    """

    ready = Signal(str, dict, int)


class OnchainWorker(QThread):
    """后台批量取链上合约品种的真实报价，不阻塞 UI 线程。

    链上报价响应比交易所行情大（Rugcheck 内含市场明细），所以单独走
    60 秒低频刷新，也不塞进 15 秒的交易所请求集合里。
    """

    ready = Signal(dict)

    def __init__(self, symbols: list, parent=None):
        super().__init__(parent)
        self._symbols = list(symbols)

    def run(self):
        out = {}
        for sym in self._symbols:
            addr = onchain.address_of(sym)
            if not addr:
                continue
            q = onchain.quote(addr)
            if q:
                out[sym] = q
        self.ready.emit(out)


class SortCycleButton(QPushButton):
    """排序按钮：单击直接切到下一种排序方式，不再弹下拉选择。

    保留 currentData/findData/setCurrentIndex/currentIndexChanged 这组
    下拉框式接口，主窗口逻辑与既有测试无需改动。
    """

    currentIndexChanged = Signal(int)

    def __init__(self, modes, current="custom", parent=None):
        super().__init__(parent)
        self._modes = list(modes)
        self._index = 0
        for i, (key, _label) in enumerate(self._modes):
            if key == current:
                self._index = i
                break
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet(sort_btn_qss())
        self.setToolTip(
            "单击循环切换排序；点 ⇅ 翻转升/降序；点 ☰ 打开完整排序菜单"
            "（市值 / 流动性 / 上市时间基于真实数据源）")
        self.clicked.connect(self._advance)
        self._sync()

    def _sync(self):
        key = self._modes[self._index][0]
        self.setText(f"排序 · {SORT_SHORT.get(key, key)}")

    def _advance(self):
        self._index = (self._index + 1) % len(self._modes)
        self._sync()
        self.currentIndexChanged.emit(self._index)

    def currentData(self):
        return self._modes[self._index][0]

    def findData(self, key):
        for i, (k, _label) in enumerate(self._modes):
            if k == key:
                return i
        return -1

    def currentIndex(self):
        return self._index

    def setCurrentIndex(self, index):
        i = max(0, min(len(self._modes) - 1, int(index)))
        if i == self._index:
            return
        self._index = i
        self._sync()
        self.currentIndexChanged.emit(i)


class TitleBar(QWidget):
    """无边框模式下的自绘标题栏：项目 logo + 拖动 + 窗口按钮。"""

    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.window = window
        self._drag_pos = None
        self.setFixedHeight(48)
        self.setObjectName("titleBar")
        self.setStyleSheet(
            f"#titleBar {{ background:{C_BG_PANEL};"
            f" border-bottom:1px solid {C_BORDER}; }}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 8, 0)
        layout.setSpacing(8)

        logo = QLabel()
        logo.setFixedSize(22, 22)
        logo.setPixmap(app_logo(44).scaled(
            22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setStyleSheet("background:transparent;")
        layout.addWidget(logo)
        lbl = QLabel(brand.APP_NAME)
        lbl.setStyleSheet(label_qss(13, C_TEXT_MAIN, True))
        lbl.setToolTip(brand.about_text())
        self._brand_lbl = lbl
        layout.addWidget(lbl)
        # 阶段 5：标题栏统一显示当前页面名；设置入口收到底部导航，
        # 右上角不再有重复的设置按钮，改为统一的「返回」。
        self.lbl_page = QLabel("行情")
        self.lbl_page.setStyleSheet(chip_qss(C_ACCENT, 9))
        layout.addWidget(self.lbl_page)
        layout.addStretch(1)

        self._window_buttons = []

        def mkbtn(text, tip, danger=False):
            btn = QPushButton(text)
            btn.setFixedSize(44, 44)      # 触控目标；窄窗口下由 set_compact 缩小
            btn.setToolTip(tip)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(icon_btn_qss(14, danger))
            self._window_buttons.append(btn)
            return btn

        self.btn_back = mkbtn("←", "返回上一页")
        btn_min = mkbtn("–", "隐藏到右下角托盘")
        self.btn_max = mkbtn("□", "最大化 / 还原（双击标题栏同样生效）")
        self.btn_full = mkbtn("⛶", "全屏显示")
        # 窄窗口只压缩按钮，不隐藏最大化 / 全屏：用户反馈「窗口无法最大化」
        # 正是因为旧版把这两颗按钮藏了起来，窄窗口下没有可点击入口。
        btn_close = mkbtn("×", "退出程序", danger=True)
        self.btn_back.clicked.connect(window._navigate_back)
        btn_min.clicked.connect(window.hide_to_tray)
        self.btn_max.clicked.connect(window.toggle_maximize)
        self.btn_full.clicked.connect(window.toggle_fullscreen)
        btn_close.clicked.connect(window.quit_app)
        layout.addWidget(self.btn_back)
        layout.addWidget(btn_min)
        layout.addWidget(self.btn_max)
        layout.addWidget(self.btn_full)
        layout.addWidget(btn_close)
        self.set_page("行情", False)
        self.sync_window_state()

    def set_page(self, text: str, can_back: bool = True):
        """统一标题栏：页面名 + 返回按钮显隐。"""
        self.lbl_page.setText(text)
        self.btn_back.setVisible(bool(can_back))

    def sync_window_state(self):
        """窗口状态（常规 / 最大化 / 全屏）变化时刷新按钮图标与提示。"""
        w = self.window
        if w.isFullScreen():
            self.btn_max.setText("□")
            self.btn_max.setToolTip("退出全屏后可用")
            self.btn_full.setToolTip("退出全屏")
        elif w.isMaximized():
            self.btn_max.setText("❐")
            self.btn_max.setToolTip("还原窗口大小")
            self.btn_full.setToolTip("全屏显示")
        else:
            self.btn_max.setText("□")
            self.btn_max.setToolTip("最大化 / 还原（双击标题栏同样生效）")
            self.btn_full.setToolTip("全屏显示")

    def set_compact(self, compact: bool):
        """窄窗口压缩标题栏按钮，但保留最大化 / 全屏入口。

        旧版在宽度 < 440 时直接隐藏这两颗按钮，导致窄窗口下既看不到
        也点不到最大化，用户只能靠双击标题栏（并非人人知道）。现在改为
        缩小按钮 + 隐藏页面名，保证任何宽度都能直接最大化 / 全屏。
        """
        if getattr(self, "_compact", None) == bool(compact):
            return
        self._compact = bool(compact)
        size = QSize(30, 36) if compact else QSize(44, 44)
        for btn in self._window_buttons:
            btn.setFixedSize(size)
        if hasattr(self, "lbl_page"):
            self.lbl_page.setVisible(not compact)
        if hasattr(self, "_brand_lbl"):
            # 极窄窗口再收起品牌名，给窗口按钮让位；标题栏本身仍可拖动
            self._brand_lbl.setVisible(self.width() >= 340 or not compact)
        lay = self.layout()
        if lay is not None:
            lay.setSpacing(4 if compact else 8)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.set_compact(self.width() < 440)
        # 极窄时品牌名也要随宽度恢复
        if hasattr(self, "_brand_lbl") and self._compact:
            self._brand_lbl.setVisible(self.width() >= 340)

    def _move_locked(self) -> bool:
        """最大化 / 全屏时不允许拖动移动窗口。"""
        w = self.window
        return w.isMaximized() or w.isFullScreen()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._move_locked():
            self._drag_pos = event.globalPosition().toPoint() \
                - self.window.frameGeometry().topLeft()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and not self.window.isFullScreen():
            self.window.toggle_maximize()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None \
                and event.buttons() & Qt.LeftButton \
                and not self._move_locked():
            self.window.move(event.globalPosition().toPoint()
                             - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self.window.save_geometry()


class MarketTabs(QFrame):
    """顶部市场页签：币安式黄色下划线，点击切换市场页面。"""

    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._titles = {k: t for k, t, _ in MARKET_GROUPS}
        self._counts = {k: 0 for k, _, _ in MARKET_GROUPS}
        self.setStyleSheet(panel_qss(0, C_BG_PANEL, C_BORDER))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(0)
        self.buttons = {}
        for key, title, color in MARKET_GROUPS:
            btn = QPushButton(title)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setStyleSheet(tab_qss(False, color))
            btn.clicked.connect(
                lambda checked=False, k=key: self.changed.emit(k))
            layout.addWidget(btn)
            self.buttons[key] = btn
        layout.addStretch(1)

    def set_active(self, key: str):
        for k, _, color in MARKET_GROUPS:
            btn = self.buttons[k]
            active = (k == key)
            btn.setChecked(active)
            btn.setStyleSheet(tab_qss(active, color))

    def set_count(self, key: str, n: int):
        """只更新内部计数，页签上不再显示数字（用户要求去掉）。"""
        self._counts[key] = n
        self.buttons[key].setText(self._titles[key])
        _, _, color = next(g for g in MARKET_GROUPS if g[0] == key)
        self.buttons[key].setStyleSheet(tab_qss(
            self.buttons[key].isChecked(), color))


class BottomNav(QFrame):
    """手机式底部导航（行情 / 图表 / 设置）。

    阶段 5：图表恢复为独立主入口，同时保留「点行情行进图表」的原有
    路径。整栏 64px、单项 ≥ 48px，按触摸目标设计，桌面鼠标同样可点。
    """

    changed = Signal(str)
    ITEMS = (("list", "行情"), ("chart", "图表"), ("settings", "设置"))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bottomNav")
        self.setStyleSheet(bottom_nav_qss())
        self.setFixedHeight(64)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(2)
        self.buttons = {}
        for key, label in self.ITEMS:
            btn = QToolButton()
            btn.setText(label)
            btn.setIconSize(QSize(22, 22))
            btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            btn.clicked.connect(
                lambda checked=False, k=key: self.changed.emit(k))
            lay.addWidget(btn)
            self.buttons[key] = btn
        self.set_active("list")

    def set_active(self, key: str):
        for k, btn in self.buttons.items():
            active = (k == key)
            btn.setChecked(active)
            btn.setIcon(QIcon(nav_glyph(
                k, 22, C_ACCENT if active else C_TEXT_DIM)))


class SubTabs(QFrame):
    """每个市场的二级子菜单：自选 / 全部。"""

    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(panel_qss(0, C_BG_BASE, C_BORDER))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(4)
        self.buttons = {}
        for key, label, tip in (("watch", "自选", "只看我添加的品种"),
                                ("all", "全部", "浏览该市场热门品种并加入自选")):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setStyleSheet(segment_qss(False))
            btn.clicked.connect(
                lambda checked=False, k=key: self.changed.emit(k))
            layout.addWidget(btn)
            self.buttons[key] = btn
        layout.addSpacing(6)
        self.lbl_hint = QLabel("全部页可一键添加 · 点击行查看图表")
        self.lbl_hint.setStyleSheet(label_qss(9, C_TEXT_DIM))
        layout.addWidget(self.lbl_hint)
        layout.addStretch(1)

    def set_active(self, key: str):
        for k, btn in self.buttons.items():
            active = (k == key)
            btn.setChecked(active)
            btn.setStyleSheet(segment_qss(active))
        self.lbl_hint.setText(
            "全部页可一键添加 · 点击行查看图表" if key == "all" else
            "右键管理顺序 · 点击行查看图表")


class MainWindow(QMainWindow):
    def __init__(self, config: Config):
        super().__init__()
        # 构造期间不上屏：打包版启动时 Qt 会先建出原生窗口，尺寸还没算好就
        # 露一个小空框（约 170x63）在屏幕中间一两秒才变成全屏。设了这个
        # 属性后窗口照常布局但不显示，最后由 prepare_show() 一次性亮出来。
        self.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.config = config
        # 主题 / 应用图标 / 货币单位必须在任何控件创建之前生效：
        # 控件构造时按「当前调色板常量」生成 QSS，晚一步设置就会残留旧色。
        self._theme_name, self._theme_old, self._theme_new = set_theme(
            config.get("theme") or "binance")
        set_app_icon_key(config.get("app_icon") or "classic")
        units.set_enabled(bool(config.get("show_currency", True)))
        self.setWindowTitle(brand.APP_TITLE)
        self.setWindowIcon(app_icon())

        # ---- 行情层 ----
        self.market = MarketManager(preferred=config.get("source") or "")
        self._last_tickers = {}
        # 指定品种（托盘图标 / 任务栏价格条共用）最近一次真实报价。
        # 行情是按数据源合并的，某一组临时失败时返回的字典会缺个别代码；
        # 旧版整体替换 _last_tickers 后直接 .get()，价格条会闪回 "-- WAIT"，
        # 下一轮又恢复，看起来就像失灵。这里保留 5 分钟内的上次有效值。
        self._tray_ticker_cache = {}     # symbol -> (ts, Ticker)
        self._current_batch = set()      # 本轮数据源真正返回的标的集合
        self._last_meta = ("", 0.0, False)
        self._force_quit = False
        self._search_worker = None
        self._contract_worker = None
        # 统一搜索：请求序号，旧回执（旧关键词/过期结果）不得覆盖最新结果
        self._search_seq = 0
        self._active_search_query = ""
        self._prefetch = None     # 后台 K 线历史预缓存线程（由 main.py 启动）
        # ---- 链上合约品种（无 K 线，但可收藏 / 看真实链上报价）----
        # 元数据落盘：重启后自选行仍显示代币代码与名称，而不是 44 位地址。
        # 老配置可能只把 ONCHAIN:<addr> 加进 symbols 而没写元数据：
        # ensure_meta 补最小记录并落盘，界面显示可读短地址与真实链名。
        self.onchain_meta = onchain.ensure_meta(config)
        self._onchain_quotes = {}       # symbol -> 最近一次真实链上报价
        self._onchain_worker = None
        self._onchain_timer = QTimer(self)
        self._onchain_timer.setInterval(60000)   # 链上响应较大，低频刷新
        self._onchain_timer.timeout.connect(self._refresh_onchain)
        # 股票真实 logo 抓取完成后刷新对应行（后台串行线程，见 data/stock_logo）
        stock_logo.signals.logo_ready.connect(self._on_stock_logo)
        self._watchlist = list(config.get("symbols") or DEFAULT_SYMBOLS)
        # 阶段 4：独立的置顶状态（不复用 symbols 数组顺序，不被数值排序覆盖）
        self.pinned = [s for s in (config.get("pinned_symbols") or []) if s]
        self._list_geometry = None
        self.rows = {}                                   # 自举行
        self.all_rows = {k: {} for k, _, _ in MARKET_GROUPS}  # 全部页行（懒创建）
        self._filling_all = set()      # 正在分批创建中的市场
        self._resort_at = 0.0          # 上次实时自动重排的时间戳（限频用）
        self._in_relayout = False      # 正在整页重排（分批建行时不要再插队）
        # 阶段 2：每个市场各自记住已挂载到第几页 / 当前排序后的完整顺序
        self._page_limit = {k: PAGE_SIZE for k, _, _ in MARKET_GROUPS}
        self._all_order = {k: [] for k, _, _ in MARKET_GROUPS}
        self._detail_cache = {}        # symbol -> 详情抽屉（复用，不重复创建）
        self._detail_order = []
        self._retry_left = MAX_RETRY
        self._loading_pages = set()    # 正在等待增量页行情的市场
        # 阶段 3：筛选条件、排序元数据（真实市值 / 换手率 / 创立年份）
        self._filter_text = ""
        self._last_long_press = ""    # 阶段 6：最近一次长按的品种
        self._narrow = False
        self._rank_meta = rank_meta.load_cached()
        self._rank_ready = {k: False for k, _, _ in MARKET_GROUPS}
        # 元数据异步任务状态机：IDLE / LOADING / SUCCESS / FAILED。
        # _rank_ready 保留旧含义「已成功取到可用数据」供既有测试断言，
        # 真正的并发/重试控制改用 _rank_state + 退避时间戳。
        self._rank_state = {k: "IDLE" for k, _, _ in MARKET_GROUPS}
        self._rank_seq = {k: 0 for k, _, _ in MARKET_GROUPS}  # 每市场请求序号
        self._rank_fail = {k: 0 for k, _, _ in MARKET_GROUPS}  # 连续失败次数
        self._rank_next_at = {k: 0.0 for k, _, _ in MARKET_GROUPS}  # 退避截止
        self._rank_signals = _RankSignals(self)
        self._rank_signals.ready.connect(self._on_rank_meta)
        # 内置清单本身由真实市值榜生成，预建位次表供「默认排序」使用
        self._default_rank = {
            k: {s: i for i, s in enumerate(all_of(k))}
            for k, _, _ in MARKET_GROUPS}
        saved_subs = config.get("sub_tabs") or {}
        self._sub_tabs = {k: ("all" if saved_subs.get(k) == "all"
                              else "watch") for k, _, _ in MARKET_GROUPS}

        # ---- 界面骨架 ----
        central = QWidget()
        central.setObjectName("centralRoot")
        central.setStyleSheet(f"#centralRoot {{ background:{C_BG_BASE}; }}")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 0, 8, 8)
        layout.setSpacing(6)

        self.title_bar = TitleBar(self)
        layout.addWidget(self.title_bar)

        self.tabs = MarketTabs(self)
        self.tabs.changed.connect(self._switch_market)
        layout.addWidget(self.tabs)

        self.sub_tabs = SubTabs(self)
        self.sub_tabs.changed.connect(self._switch_sub)
        layout.addWidget(self.sub_tabs)

        # ---- 工具条：搜索 + 排序 + 设置 ----
        tools = QFrame()
        tools.setStyleSheet(panel_qss())
        toolbar = QHBoxLayout(tools)
        toolbar.setContentsMargins(9, 5, 9, 5)
        toolbar.setSpacing(6)
        # 搜索按钮：此前只是装饰图标、点了没反应（用户反馈）。
        # 现在点击 = 聚焦搜索框；有内容立即搜索，无内容打开搜索历史页。
        self.btn_search = QPushButton()
        self.btn_search.setFixedSize(44, 44)
        self.btn_search.setToolTip("搜索（无内容时查看搜索历史）")
        self.btn_search.setCursor(Qt.PointingHandCursor)
        self.btn_search.setFocusPolicy(Qt.NoFocus)
        self.btn_search.setIcon(QIcon(search_glyph(18, C_ACCENT)))
        self.btn_search.setIconSize(QSize(18, 18))
        self.btn_search.setStyleSheet(
            f"QPushButton {{ background:transparent; border:none; }}"
            f"QPushButton:hover {{ background:{C_BG_HOVER};"
            f" border-radius:6px; }}")
        self.btn_search.clicked.connect(self._on_search_button)
        toolbar.addWidget(self.btn_search)
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("搜索代码 / 名称 / 链上合约地址")
        self.edit_search.setToolTip(
            "支持币圈代码、中文名称、股票代码，以及 0x… / Solana / Tron 合约地址")
        self.edit_search.setClearButtonEnabled(True)
        self.edit_search.setStyleSheet(line_edit_qss())
        # QSS 里的 min-height 会覆盖 minimumHeight，用固定高度锁定触控目标
        self.edit_search.setFixedHeight(44)
        toolbar.addWidget(self.edit_search, 1)

        self.combo_sort = SortCycleButton(
            SORT_MODES, self.config.get("sort_mode") or "custom")
        self.combo_sort.setFixedSize(138, 44)
        self.combo_sort.currentIndexChanged.connect(self._on_sort_changed)
        toolbar.addWidget(self.combo_sort)

        # 阶段 3：升降序一键翻转 + 分组排序菜单（触屏也能用）
        self.btn_sort_dir = QPushButton("⇅")
        self.btn_sort_dir.setFixedSize(44, 44)
        self.btn_sort_dir.setToolTip("切换当前排序的升序 / 降序")
        self.btn_sort_dir.setCursor(Qt.PointingHandCursor)
        self.btn_sort_dir.setStyleSheet(icon_btn_qss(15))
        self.btn_sort_dir.clicked.connect(self._on_sort_flip)
        toolbar.addWidget(self.btn_sort_dir)

        self.btn_sort_menu = QPushButton("☰")
        self.btn_sort_menu.setFixedSize(44, 44)
        self.btn_sort_menu.setToolTip(
            "排序菜单：涨跌幅 / 价格 / 成交额 / 市值 / 流动性 / 上市时间")
        self.btn_sort_menu.setCursor(Qt.PointingHandCursor)
        self.btn_sort_menu.setStyleSheet(icon_btn_qss(14))
        self.btn_sort_menu.clicked.connect(self._on_sort_menu)
        toolbar.addWidget(self.btn_sort_menu)

        # 阶段 5：设置入口统一到底部导航，工具条不再放重复的右上角设置键
        layout.addWidget(tools)

        # ---- 搜索页（独立图层，加入 stack；不再挤在行情列表上方） ----
        self.search_panel = SearchResultsPanel(self)
        self.search_panel.item_toggled.connect(self._on_search_toggle)
        # 点击结果行 → 进入图表；显式「＋收藏」按钮才加自选
        self.search_panel.open_requested.connect(self._on_search_open)
        self.search_panel.back_requested.connect(self._close_search_page)
        self.search_panel.history_picked.connect(self._on_history_pick)
        self.search_panel.history_deleted.connect(self._on_history_deleted)
        self.search_panel.history_cleared.connect(self._on_history_cleared)
        self._search_debounce = QTimer(self)
        self._search_debounce.setInterval(350)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.timeout.connect(lambda: self._do_search(True))
        self.edit_search.textEdited.connect(
            lambda _: self._search_debounce.start())
        # 阶段 3：搜索框同时是列表筛选器；排序 / 切页都不清空它
        self._filter_debounce = QTimer(self)
        self._filter_debounce.setInterval(200)
        self._filter_debounce.setSingleShot(True)
        self._filter_debounce.timeout.connect(self._apply_filter)
        self.edit_search.textChanged.connect(
            lambda _: self._filter_debounce.start())
        self.edit_search.installEventFilter(self)
        # 无边框窗口的边缘缩放：子控件铺满时 QWidget 鼠标事件拿不到边缘，
        # 用应用级事件过滤器在任何子控件上识别边缘并交给系统原生缩放。
        _app = QApplication.instance()
        if _app is not None:
            _app.installEventFilter(self)

        # ---- 品种资料弹窗：不占布局；右键菜单「查看资料」时浮到行旁边 ----
        self.info_panel = SymbolInfoPanel(central)
        self._focus_symbol = ""       # 用户最近点开 / 查看资料的品种
        self._settings_return = None

        # ---- 列表区标题 ----
        section = QFrame()
        section.setObjectName("sectionHeader")
        section.setStyleSheet(
            "#sectionHeader { background:transparent; border:none; }")
        sh = QHBoxLayout(section)
        sh.setContentsMargins(2, 0, 2, 0)
        sh.setSpacing(8)
        self.lbl_section = QLabel("自选行情")
        self.lbl_section.setStyleSheet(label_qss(12, C_TEXT_MAIN, True))
        sh.addWidget(self.lbl_section)
        self.lbl_count = QLabel("0")
        self.lbl_count.setStyleSheet(badge_qss(C_TEXT_SUB, C_BG_HOVER, 10))
        sh.addWidget(self.lbl_count)
        sh.addStretch(1)
        self.lbl_hint = QLabel("最新价 / 24h 涨跌")
        self.lbl_hint.setStyleSheet(label_qss(9, C_TEXT_DIM))
        sh.addWidget(self.lbl_hint)
        layout.addWidget(section)

        # ---- 市场分页（4 个滚动页 + 图表页）----
        self.stack = QStackedWidget()
        self.stack.setMinimumSize(240, 200)
        self.pages = {}
        for key, _title, _color in MARKET_GROUPS:
            page = QWidget()
            page.setStyleSheet("background:transparent;")
            page_lay = QVBoxLayout(page)
            page_lay.setContentsMargins(2, 0, 2, 0)
            page_lay.setSpacing(4)
            empty = QLabel("本市场暂无自选\n使用上方搜索框添加")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                f"color:{C_TEXT_DIM}; font-size:12px; padding:28px 8px;"
                f" background:{C_BG_PANEL}; border:1px dashed {C_BORDER};"
                f" border-radius:6px;")
            page_lay.addWidget(empty)
            page_lay.addStretch(1)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setStyleSheet(scroll_qss())
            scroll.setWidget(page)
            # 阶段 6：触摸惯性滚动（手指上下滑动），桌面滚轮照常工作
            try:
                QScroller.grabGesture(
                    scroll.viewport(),
                    QScroller.ScrollerGestureType.TouchGesture)
            except Exception:
                pass
            # 列表一滚动，行就离开了弹窗锚点：资料弹窗跟着收起，不留悬空卡片
            scroll.verticalScrollBar().valueChanged.connect(
                lambda _v, _p=self.info_panel: _p.hide_popup())
            # 阶段 2：滚到底部再加载下一页，同时只请求新窗口的行情
            scroll.verticalScrollBar().valueChanged.connect(
                lambda _v, _k=key: self._on_list_scroll(_k, _v))
            self.stack.addWidget(scroll)
            self.pages[key] = {"layout": page_lay, "empty": empty,
                               "scroll": scroll, "page": page}

        self.chart_view = ChartView(self.config)
        self.chart_view.back_requested.connect(self._leave_chart)
        self.chart_view.detail_requested.connect(self._open_detail)
        self.stack.addWidget(self.chart_view)
        # 设置是主窗口里的一页，不再是模态弹窗
        # 从构造起就挂在 stack 上：不带父对象的 QWidget 会被 Qt 当成顶层
        # 窗口创建原生句柄，offscreen / 硬退出时容易留下悬空窗口。
        self.settings_page = SettingsPage(self, self.stack)
        self.settings_page.saved.connect(self._apply_settings)
        self.settings_page.cancelled.connect(self._close_settings_page)
        self.stack.addWidget(self.settings_page)
        # 阶段 8：搜索结果独立成页（与行情列表不同图层）
        self.stack.addWidget(self.search_panel)
        layout.addWidget(self.stack, 1)

        self._list_controls = [self.tabs, self.sub_tabs, tools, section]
        self.status = StatusPanel()
        self.status.retry_requested.connect(self._on_retry)
        layout.addWidget(self.status)

        # ---- 手机式底部导航：行情 / 图表 / 设置 ----
        self.bottom_nav = BottomNav(self)
        self.bottom_nav.changed.connect(self._on_bottom_nav)
        layout.addWidget(self.bottom_nav)

        # ---- 行情行 ----
        for symbol in self._watchlist:
            self._create_row(symbol)
        self._update_counts()

        # ---- 刷新调度 ----
        self.scheduler = RefreshScheduler(self.market, self._refresh_symbols(),
                                          self)
        self.scheduler.fetched.connect(self._on_fetched)
        self.scheduler.failed.connect(self._on_failed)
        self.scheduler.refresh_now()

        # 链上品种走独立的低频后台刷新，不占交易所请求集合、不阻塞 UI
        self._onchain_timer.start()
        QTimer.singleShot(1500, self._refresh_onchain)

        # ---- 托盘 / 任务栏常驻价格条 / 窗口设置 ----
        self._setup_tray()
        self.price_badge = PriceBadge(self.config)
        self.price_badge.show_requested.connect(self._show_from_badge)
        self.price_badge.symbol_changed.connect(self.set_tray_symbol)
        self.price_badge.visibility_changed.connect(self._on_badge_visibility)
        self.price_badge.apply_config()
        self._sync_badge()
        # 托盘菜单是在价格条之前建的（_setup_tray 更靠前），那次重建时
        # price_badge 还不存在；这里补一次，把可指定品种清单同步给价格条。
        self._rebuild_tray_symbol_menu()
        # ---- 秒级实时价（只服务当前图表品种，驱动最新 K 线连续动画）----
        self.live = LiveFeed(self.market,
                             int(self.config.get("live_interval_ms") or 900),
                             self)
        self.live.tick.connect(self._on_live_tick)
        self.live.set_enabled(bool(self.config.get("live_feed", True)))
        # ---- 看板娘（默认关闭，可在设置里开启并自定义图片）----
        self.mascot = None
        try:
            self.mascot = MascotWindow(self.config)
            self.mascot.apply_config()
        except Exception:
            self.mascot = None
        self.apply_window_settings(save=False)
        # 看板娘重叠度轮询（只在图表页跑，400ms 一次很轻）
        self._mascot_timer = QTimer(self)
        self._mascot_timer.setInterval(400)
        self._mascot_timer.timeout.connect(self._update_mascot_overlap)
        self._sync_mascot_visibility()
        apply_global(QApplication.instance())
        # 「全部」页分批建行时，Qt 会对鼠标下的子 QLabel 连发原生 tooltip，
        # 形成一串小窗。应用级过滤器只在建行期生效（引用计数管理）。
        self._tooltip_guard = install_tooltip_guard(QApplication.instance())

        last_tab = self.config.get("last_tab") or "crypto"
        self._switch_market(last_tab if last_tab in self.pages else "crypto")

    # ================= 行管理 =================
    def _create_row(self, symbol: str, mode: str = "watch"):
        if mode == "watch":
            if symbol in self.rows:
                return
            key = market_of(symbol)
            page = self.pages[key]
            # 父控件必须是页面本身：无父控件的 QWidget 是顶层窗口，一旦被
            # 显示就会在屏幕上多出一个「小窗」，这正是批量建行时的抖动来源。
            meta = (getattr(self, "onchain_meta", {}) or {}).get(symbol) or {}
            row = TickerWidget(
                symbol,
                meta.get("name") or COIN_NAMES.get(symbol, ""),
                parent=page["page"],
                code=meta.get("code") or "")
            self.rows[symbol] = row
            if onchain.is_onchain(symbol):
                # 没有 K 线也照常渲染：有真实链上价就显示，没有就明确标「—」
                row.update_onchain(
                    getattr(self, "_onchain_quotes", {}).get(symbol))
        else:
            return
        row.context_menu.connect(self._on_row_context)
        row.long_pressed.connect(self._on_row_long_press)
        row.row_clicked.connect(self._open_chart)
        if hasattr(row, "toggled"):
            row.toggled.connect(self._on_row_toggle)
        lay = page["layout"]
        # 只有当前正看着这个市场的「自选」页时才直接插进布局；正在看「全部」
        # 时插进去会让一行自选混进全部列表，等 _relayout_page 再归位。
        if self._current_market() == key and \
                self._sub_tabs.get(key, "watch") != "all":
            lay.insertWidget(max(0, lay.count() - 1), row)
            row.show()

    def _release_fill(self, key: str):
        """建行链收尾（正常 / 异常都走）：释放 tooltip 抑制与填充标记。

        旧版是全局 bool + 每条链各排一个 700ms 的 enable 定时器：多市场并行
        建行时先结束的链会提前把开关打开；链中途抛异常还会永久关掉提示并
        把 key 永远留在 _filling_all。现在用引用计数 + 单一收尾路径。
        """
        self._filling_all.discard(key)
        end_tooltip_hold()
        if tooltip_hold_count() == 0:
            QToolTip.hideText()       # 收掉建行期间可能残留的最后一个气泡

    def _ensure_all_rows(self, key: str):
        """懒创建某市场「全部」页的行：按页建，滚动到底再补下一页。

        旧版虽然只挂载前 60 行，但会把全市场（美股 500 个）行对象
        全部预创建：对象还是要 1.8 秒才建完、内存照占、进度提示照样
        跑到 500。现在改成真正的按页按需——首屏只建并挂载
        PAGE_SIZE 行；排序变化 / 滚动翻页时由 _relayout_page 现场
        补建新进入窗口的行。
        """
        if self.all_rows[key] or key in self._filling_all:
            return
        self._filling_all.add(key)
        begin_tooltip_hold()          # 建行期间别让原生提示小窗连环弹
        nm = names(key)
        self._fill_rows(key, nm, list(all_of(key))[:PAGE_SIZE])

    def _create_all_rows(self, key: str, syms: list):
        """补建「全部」页指定标的的行对象（不挂载，交给 _relayout_page）。"""
        if not syms:
            return
        nm = names(key)
        for symbol in syms:
            if symbol in self.all_rows[key]:
                continue
            try:
                row = TickerWidget(symbol, nm.get(symbol, ""), mode="all",
                                   in_watchlist=(symbol in self.rows),
                                   parent=self.pages[key]["page"],
                                   defer_icon=True)
            except Exception:
                # 单行失败不拖垮整页；下一轮进入窗口时会再试
                continue
            # UniqueConnection：即使将来行被复用 / 重连，也不会重复绑定
            row.toggled.connect(self._on_row_toggle, Qt.UniqueConnection)
            row.context_menu.connect(self._on_row_context,
                                     Qt.UniqueConnection)
            row.long_pressed.connect(self._on_row_long_press,
                                     Qt.UniqueConnection)
            row.row_clicked.connect(self._open_chart, Qt.UniqueConnection)
            self.all_rows[key][symbol] = row

    def _fill_rows(self, key: str, nm: dict, syms: list):
        """按需创建传入标的的行（只建这一批，绝不递归全量预建）。

        旧版「分批预建全市场对象」已移除；后续页由 _relayout_page /
        _load_more_page 在滚动翻页时现场补建。
        """
        page = self.pages[key]
        frozen = page["page"].updatesEnabled()
        try:
            page["page"].setUpdatesEnabled(False)
            self._create_all_rows(key, syms)
        finally:
            page["page"].setUpdatesEnabled(frozen)
        # 当前正在看这个「全部」页：立即挂载并只刷新窗口内的行
        if self._current_market() == key \
                and self._sub_tabs.get(key) == "all" \
                and not self._in_relayout:
            self._relayout_page(key)
            self._paint_page_rows(key)
            self._load_icons([self.all_rows[key][s] for s in syms
                              if s in self.all_rows[key]])
        self._release_fill(key)
        self._update_load_progress(key)

    def _append_rows(self, key: str, rows: list):
        """把新行追加到页面末尾，不重排已有行（避免整页反复重建）。"""
        if not rows:
            return
        lay = self.pages[key]["layout"]
        page = self.pages[key]
        stretch = None
        if lay.count():
            last = lay.itemAt(lay.count() - 1)
            if last and last.spacerItem() is not None:
                stretch = lay.takeAt(lay.count() - 1)
        page["empty"].hide()
        for row in rows:
            lay.addWidget(row)
            row.show()
        if stretch is not None:
            lay.addItem(stretch)

    def _load_icons(self, rows, batch: int = 70):
        pending = [r for r in rows if not getattr(r, "_icon_loaded", True)]

        def step():
            for row in pending[:batch]:
                try:
                    row.load_icon()
                except RuntimeError:
                    pass
            del pending[:batch]
            if pending:
                QTimer.singleShot(0, step)

        if pending:
            QTimer.singleShot(0, step)

    def _update_counts(self):
        counts = {key: 0 for key in self.pages}
        for symbol in self.rows:
            counts[market_of(symbol)] += 1
        for key, n in counts.items():
            self.tabs.set_count(key, n)
        self._update_section_count()

    def _current_market(self) -> str:
        key = self.config.get("last_tab") or "crypto"
        return key if key in self.pages else "crypto"

    def _update_section_count(self):
        key = self._current_market()
        sub = self._sub_tabs.get(key, "watch")
        if sub == "all":
            base = list(all_of(key))
            title = "全部行情"
        else:
            base = [s for s in self.rows if market_of(s) == key]
            title = "自选行情"
        # _all_order 保存的是「排序 + 筛选后」的顺序，计数跟着筛选走
        order = self._all_order.get(key)
        n = len(order) if order else len(base)
        if self._filter_text:
            title += f" · 筛选「{self._filter_text}」"
        self.lbl_section.setText(title)
        self.lbl_count.setText(str(n))

    def _relayout_page(self, key: str):
        """按当前排序与子页重排指定市场页（不同市场绝不混排）。"""
        page = self.pages[key]
        lay = page["layout"]
        sub = self._sub_tabs.get(key, "watch")
        if sub == "all":
            # 首次建行会同步建出第一批 80 行，随后按帧续建；建行过程中先别
            # 往布局里插（本函数马上要整体归位一次，插了也是白插）。
            prev = self._in_relayout
            self._in_relayout = True
            try:
                self._ensure_all_rows(key)
            finally:
                self._in_relayout = prev
            rows = self.all_rows[key]
            syms = list(all_of(key))
        else:
            rows = self.rows
            syms = [s for s in self.rows if market_of(s) == key]
        mode = self.combo_sort.currentData() or "custom"
        if mode == "custom" and sub == "watch":
            cfg_order = [s for s in (self.config.get("symbols") or [])
                         if s in rows and market_of(s) == key]
            order = cfg_order + [s for s in syms if s not in cfg_order]
        elif mode == "custom":
            order = syms
        elif mode == "default":
            order = sorted(syms, key=lambda s: self._default_key(s))
        else:
            order = sorted(syms, key=lambda s: self._sort_key(s, mode))
        # 阶段 3：排序之后仍保持筛选条件。搜索框里的文本是本地筛选器，
        # 匹配代码或品种名；排序 / 切页 / 切市场都不会把它清掉。
        q = getattr(self, "_filter_text", "").strip().upper()
        if q:
            nm = names(key)

            def _match(s):
                return (q in s.upper()
                        or q in str(nm.get(s, "") or "").upper())

            order = [s for s in order if _match(s)]
        # 阶段 4：置顶品种优先于一切排序规则（市值 / 涨跌幅 / 默认…），
        # 且多个置顶之间保持用户置顶的先后顺序；筛选之后才应用，
        # 被筛掉的置顶品种不会强行插进结果。
        pinned = [s for s in self.pinned if s in order]
        if pinned:
            pset = set(pinned)
            order = pinned + [s for s in order if s not in pset]
        # 记住筛选后的完整顺序（供计数 / 请求窗口 / 滚动分页 / 排序取值）
        self._all_order[key] = list(order)
        if sub == "all":
            # 布局里只挂载已加载的页数 —— 首屏 60 行，而非 500 行。
            order = order[:self._page_limit.get(key, PAGE_SIZE)]
            # 按页补建窗口内尚不存在的行：排序变化 / 滚动翻页后，新进入
            # 窗口的标的现场创建，绝不再一次性预建整个市场的行对象
            missing = [s for s in order if s not in rows]
            if missing:
                self._create_all_rows(key, missing)
        target = [rows[s] for s in order if s in rows]
        self._load_icons(target)      # 图标也只为挂载中的行补，不预热 500 个
        pset = set(self.pinned)
        for row in target:            # 新挂载出来的行同步置顶徽章
            row.set_pinned(row.symbol in pset)
        # ★ 残影修正：takeAt() 只是把控件从布局里摘下来，控件本身仍是页面的
        #   子控件、仍处于「可见」状态，会保持旧坐标叠在新列表上。切「全部→
        #   自选」时那几百行就变成了「我根本没添加却出现在自选里」的幽灵行，
        #   鼠标扫过去还会连带弹出一串提示小窗（就是那个「疯狂弹窗+抖动」）。
        #   这里每轮都按目标集合显式 show/hide，绝不残留。
        keep = {id(w) for w in target}
        for child in page["page"].findChildren(TickerWidget):
            if id(child) not in keep:
                child.hide()
        # 顺序没变就原地不动：全部页最多 500 行，每次刷新都 takeAt/addWidget
        # 会把整页反复重建（视觉抖动、鼠标下的提示框反复弹出），这里先比对。
        current = []
        for i in range(lay.count()):
            w = lay.itemAt(i).widget()
            if w is not None:
                current.append(w)
        if current == target and len(current) == len(target) and syms:
            page["empty"].setVisible(False)
            for row in target:
                if not row.isVisible():
                    row.show()
            return
        # 真需要搬家时冻结重绘：500 行 takeAt/addWidget 会产生几十帧中间状态，
        # 不冻结的话整页会明显闪一下（鼠标下的行还会丢 tooltip）。
        frozen = self.updatesEnabled()
        if frozen:
            self.setUpdatesEnabled(False)
        self._in_relayout = True
        try:
            while lay.count():
                lay.takeAt(0)
            page["empty"].setVisible(not syms)
            if syms:
                for row in target:
                    lay.addWidget(row)
                    row.show()
            else:
                lay.addWidget(page["empty"])
                page["empty"].show()
            lay.addStretch(1)
        finally:
            self._in_relayout = False
            if frozen:
                self.setUpdatesEnabled(True)

    def _relayout_all(self):
        for key in self.pages:
            self._relayout_page(key)

    def _refresh_symbols(self):
        """本次需要刷新的标的：自选 + 当前全部页 + 指定品种。

        「任务栏常驻价格条」(price_badge) 与「托盘图标显示价格」
        (tray_show_price) 是两个独立开关。旧版这里只看 tray_show_price：
        用户关掉托盘价格后，指定品种就不再进入请求集合，价格条即使还
        开着也永远拿不到行情（一直 -- WAIT）。任一开关开启都必须取数。
        """
        syms = list(self.rows)
        key = self._current_market()
        if self._sub_tabs.get(key) == "all":
            # 阶段 2：只请求「已挂载 + 预取一页」的品种，而不是 500 个全量。
            # 旧版每 15 秒把整个市场的代码都塞进 URL 发一次，滚动到哪里
            # 都一样，既是无效轮询也是卡屏来源。
            order = self._all_order.get(key) or list(all_of(key))
            window = self._page_limit.get(key, PAGE_SIZE) + PREFETCH_ROWS
            syms += order[:window]
        seen, out = set(), []
        # 指定品种排最前：即使请求集合被上限截断，价格条也一定能拿到数据
        if (bool(self.config.get("price_badge", True))
                or bool(self.config.get("tray_show_price", True))):
            tray = self.config.get("tray_symbol")
            if tray and not onchain.is_onchain(tray):
                out.append(tray)
                seen.add(tray)
        for s in syms:
            # 链上合约品种没有交易所交易对，发给币安只会得到无效请求；
            # 它们由 _onchain_timer 单独走链上报价源。
            if s and s not in seen and not onchain.is_onchain(s) \
                    and len(out) < MAX_REFRESH_SYMBOLS:
                seen.add(s)
                out.append(s)
        if hasattr(self, "scheduler"):
            self.scheduler.set_symbols(out)
        return out

    def _save_watchlist(self):
        cfg_order = [s for s in (self.config.get("symbols") or [])
                     if s in self.rows]
        cfg_order += [s for s in self.rows if s not in cfg_order]
        self._watchlist = cfg_order
        self.config.set("symbols", cfg_order)
        self.config.save()
        self._refresh_symbols()

    # ---- 增删 ----
    def _add_symbol(self, symbol: str):
        if symbol in self.rows:
            return
        self._create_row(symbol)
        self._save_watchlist()
        self._relayout_page(market_of(symbol))
        self._update_counts()
        for group in self.all_rows.values():
            row = group.get(symbol)
            if row:
                row.set_in_watchlist(True)
        self._rebuild_tray_symbol_menu()
        self.scheduler.refresh_now()
        if onchain.is_onchain(symbol):
            self._refresh_onchain()   # 新收藏的链上币立刻取一次真实报价
        self._mascot_say("add", sym=display_code(symbol))

    def _remove_symbol(self, symbol: str):
        row = self.rows.pop(symbol, None)
        if row:
            row.setParent(None)
            row.deleteLater()
        self._save_watchlist()
        self._relayout_page(market_of(symbol))
        self._update_counts()
        for group in self.all_rows.values():
            r = group.get(symbol)
            if r:
                r.set_in_watchlist(False)
        self.search_panel.refresh_watch_state(set(self.rows))
        self._rebuild_tray_symbol_menu()
        self._mascot_say("remove", sym=display_code(symbol))

    def _on_row_toggle(self, symbol: str, add: bool):
        if add:
            self._add_symbol(symbol)
        else:
            self._remove_symbol(symbol)

    def _on_search_toggle(self, item: dict, added: bool):
        symbol = item["symbol"]
        if added:
            self._add_symbol(symbol)
        else:
            self._remove_symbol(symbol)
        self.search_panel.refresh_watch_state(set(self.rows))

    def set_symbols(self, symbols):
        """整体更新自选列表（设置对话框调用）。"""
        symbols = [s for s in symbols if s]
        for symbol in list(self.rows.keys()):
            if symbol not in symbols:
                self._remove_symbol_quiet(symbol)
        for symbol in symbols:
            self._create_row(symbol)
        self._watchlist = list(symbols)
        self.config.set("symbols", symbols)
        self.config.save()
        self._refresh_symbols()
        self._relayout_all()
        self._update_counts()
        for key, group in self.all_rows.items():
            for s, row in group.items():
                row.set_in_watchlist(s in self.rows)
        self._rebuild_tray_symbol_menu()
        self.scheduler.refresh_now()

    def _remove_symbol_quiet(self, symbol):
        row = self.rows.pop(symbol, None)
        if row:
            row.setParent(None)
            row.deleteLater()

    # ---- 右键菜单 ----
    def _on_row_context(self, symbol: str, global_pos):
        key = market_of(symbol)
        row = self.rows.get(symbol) or self.all_rows[key].get(symbol)
        is_watch = symbol in self.rows
        syms = [s for s in self.rows if market_of(s) == key]
        cfg_order = [s for s in (self.config.get("symbols") or [])
                     if s in self.rows and market_of(s) == key]
        cfg_order += [s for s in syms if s not in cfg_order]

        menu = QMenu(self)
        menu.setStyleSheet(menu_qss())
        act_tray = menu.addAction("● 设为托盘价格品种")
        act_info = menu.addAction("ℹ 查看资料")
        menu.addSeparator()
        # 阶段 4：置顶是独立状态，对所有品种（不只自选）可用，且能取消
        is_pinned = symbol in self.pinned
        act_unpin = (menu.addAction("⬇ 取消置顶") if is_pinned else None)
        acts = []
        if is_watch:
            acts.append((menu.addAction("⬆ 移到顶部"), "top"))
            acts.append((menu.addAction("↑ 上移"), "up"))
            acts.append((menu.addAction("↓ 下移"), "down"))
            idx = cfg_order.index(symbol)
            acts[1][0].setEnabled(idx > 0)
            acts[2][0].setEnabled(idx < len(cfg_order) - 1)
            menu.addSeparator()
            act_toggle = menu.addAction("移出自选")
        else:
            act_toggle = menu.addAction("＋ 加入自选")

        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        if chosen is act_tray:
            self.set_tray_symbol(symbol)
            return
        if chosen is act_info:
            self._show_info_popup(symbol)
            return
        if act_unpin is not None and chosen is act_unpin:
            self._set_pinned(symbol, False)
            return
        if chosen is act_toggle:
            self._on_row_toggle(symbol, not is_watch)
            return
        action = dict((a, k) for a, k in acts).get(chosen)
        if action == "top":
            # 旧版只是挪动 config["symbols"] 数组，在数值排序下完全无效，
            # 也没有取消入口；现在改成独立的持久化置顶状态。
            self._set_pinned(symbol, True)
            return
        elif action == "up":
            i = cfg_order.index(symbol)
            cfg_order[i - 1], cfg_order[i] = cfg_order[i], cfg_order[i - 1]
        elif action == "down":
            i = cfg_order.index(symbol)
            cfg_order[i], cfg_order[i + 1] = cfg_order[i + 1], cfg_order[i]
        else:
            return
        full = self._merge_order(cfg_order, key)
        self.config.set("symbols", full)
        self.config.save()
        self._watchlist = full
        self._relayout_page(key)

    def _set_pinned(self, symbol: str, pinned: bool):
        """设置 / 取消置顶：立即重排 + 落盘 + 同步所有行上的置顶徽章。"""
        cur = [s for s in self.pinned if s]
        if pinned:
            if symbol not in cur:
                cur.append(symbol)
        else:
            cur = [s for s in cur if s != symbol]
        self.pinned = cur
        self.config.set("pinned_symbols", list(cur))
        self.config.save()
        pset = set(cur)
        # 自选行与「全部」页行是两套 widget，都要同步
        for group in [self.rows] + list(self.all_rows.values()):
            for s, row in group.items():
                row.set_pinned(s in pset)
        key = market_of(symbol)
        self._relayout_page(key)
        self._update_section_count()

    def _merge_order(self, group_order: list, key: str) -> list:
        """把某市场的新顺序合并进完整列表（其它市场相对顺序不变）。"""
        result, inserted = [], False
        for s in (self.config.get("symbols") or []):
            if market_of(s) == key:
                if not inserted:
                    result.extend(group_order)
                    inserted = True
                continue
            result.append(s)
        if not inserted:
            result.extend(group_order)
        for s in self.rows:
            if s not in result:
                result.append(s)
        return result

    # ================= 看板娘互动 =================
    def _mascot_say(self, kind: str, **fields):
        """让看板娘说一句（看板娘没启用时什么都不做，永不影响主流程）。"""
        if self.mascot is None:
            return ""
        try:
            return self.mascot.react(kind, **fields)
        except Exception:
            return ""

    def _mascot_market(self):
        """行情播报：挑一个在盯的品种，涨跌够大才开口（内部有冷却）。"""
        if self.mascot is None or not self._last_tickers:
            return
        symbol = self.config.get("tray_symbol") or ""
        t = self._last_tickers.get(symbol)
        if t is None:
            symbol = ""
            for s in self.rows:
                if s in self._last_tickers:
                    symbol, t = s, self._last_tickers[s]
                    break
        if t is None:
            return
        try:
            self.mascot.react_market(
                display_code(symbol), float(t.change_pct),
                getattr(t, "name", "") or display_code(symbol))
        except Exception:
            pass

    # ================= 排序 =================
    def _on_sort_changed(self):
        """切换排序：只重排当前可见页。

        以前这里对四个市场全部重排（美股「全部」页 500 行），再立刻触发一次
        网络刷新，回来的数据又排一遍——点一下排序按钮整窗要冻结半秒、列表
        整体闪两轮，鼠标下的行被反复重建还会让提示框疯弹。排序只影响当前
        页，其它市场页等切过去时再按新顺序排（_switch_market 会重排）。
        """
        self.config.set("sort_mode", self.combo_sort.currentData())
        self.config.save()
        key = self._current_market()
        # 换排序规则后回到首屏：既符合「打开页面只加载首屏」，也避免
        # 带着上一规则已加载的几百行做整页重排（旧版点排序卡半秒）。
        if self._sub_tabs.get(key) == "all":
            self._page_limit[key] = PAGE_SIZE
            self.pages[key]["scroll"].verticalScrollBar().setValue(0)
        self._relayout_page(key)
        self._update_section_count()
        self._update_load_progress(key)
        self._ensure_rank_meta(key)

    def _rank_value(self, symbol, mode):
        """取该排序维度的真实数值；无公开数据一律返回 None（排末尾）。"""
        base = mode.rsplit("_", 1)[0]
        t = self._last_tickers.get(symbol)
        if base in ("change", "price", "amount"):
            if t is None:
                return None
            try:
                if base == "change":
                    return float(t.change_pct)
                if base == "price":
                    return float(t.last_price)
                return float(t.quote_volume_24h)
            except (TypeError, ValueError):
                return None
        meta = self._rank_meta.get(symbol) or {}
        if base == "cap":
            return rank_meta.metric(meta, "cap")
        if base == "liquidity":
            # 口径：换手率 %（股票取行情源 f[38]，加密=24h 成交额/流通市值）
            return rank_meta.metric(meta, "turnover")
        if base == "listed":
            return rank_meta.metric(meta, "listed_year")
        return None

    def _sort_key(self, symbol, mode):
        """(是否有数据, 排序值)：无数据排在末尾，绝不参与比较。"""
        v = self._rank_value(symbol, mode)
        if v is None:
            return (1, 0.0)
        return (0, -v if mode.endswith("_desc") else v)

    def _default_key(self, symbol):
        idx = self._default_rank.get(market_of(symbol), {}).get(symbol)
        return (0, idx) if idx is not None else (1, 0)

    # ---- 阶段 3：筛选 / 排序菜单 / 升降序 / 元数据 -----------------------
    def _apply_filter(self):
        text = self.edit_search.text().strip()
        if text == self._filter_text:
            return
        self._filter_text = text
        key = self._current_market()
        self.pages[key]["scroll"].verticalScrollBar().setValue(0)
        self._relayout_page(key)
        self._update_section_count()
        self._update_load_progress(key)

    def _on_sort_flip(self):
        cur = self.combo_sort.currentData()
        rev = REVERSE_SORT.get(cur)
        if rev is None:
            self.status.set_progress(
                "当前为自定义 / 默认顺序，无升降序；请从排序菜单选一个维度")
            return
        idx = self.combo_sort.findData(rev)
        if idx >= 0:
            self.combo_sort.setCurrentIndex(idx)

    def _on_sort_menu(self):
        """分组排序菜单：所有维度都能一次点到，不依赖右键 / 悬停。"""
        menu = QMenu(self)
        menu.setStyleSheet(menu_qss())
        cur = self.combo_sort.currentData()
        for group, modes in SORT_GROUPS:
            menu.addSeparator()
            head = menu.addAction(group)
            head.setEnabled(False)
            for mode in modes:
                label = dict(SORT_MODES).get(mode, mode)
                act = menu.addAction(("● " if mode == cur else "   ") + label)
                act.setData(mode)
                act.triggered.connect(
                    lambda _checked=False, m=mode: self.combo_sort.setCurrentIndex(
                        self.combo_sort.findData(m)))
        menu.exec(self.btn_sort_menu.mapToGlobal(
            self.btn_sort_menu.rect().bottomLeft()))

    @staticmethod
    def _rank_data_valid(data: dict) -> bool:
        """判断元数据结果是否「有效」（区别于离线/失败的纯 None 空壳）。

        只要有一个品种拿到真实数值（cap / turnover / listed_year 任一），
        就算本次取数成功；全部是 None 或空字典视为失败，允许退避后重试。
        """
        if not data:
            return False
        for row in data.values():
            if not isinstance(row, dict):
                continue
            for field in ("cap", "turnover", "listed_year"):
                v = row.get(field)
                if v is not None and v != "":
                    return True
        return False

    def _ensure_rank_meta(self, key: str):
        """需要市值 / 流动性 / 上市时间时，后台批量取真实元数据。

        状态机：IDLE -> LOADING -> SUCCESS / FAILED ->（退避后）IDLE。
          - 只挡 LOADING（同一市场不并发），且 SUCCESS 后不重复取；
          - FAILED 允许重试，但按 5/10/20…秒指数退避，防网络故障时刷屏；
          - 请求带序号，旧请求结果即便迟到也不会覆盖新请求;
          - 每个市场状态独立。
        """
        state = self._rank_state.get(key, "IDLE")
        if state == "LOADING":
            return                       # 同一市场不并发
        # SUCCESS 且 ready 仍为真才跳过；若 ready 被手动置 False（强制重试
        # 契约，见 test_release_v28）则视为需要重新取数。
        if state == "SUCCESS" and self._rank_ready.get(key):
            return
        if state == "FAILED" and time.time() < self._rank_next_at.get(key, 0):
            return                       # 退避期内，不重复请求
        mode = self.combo_sort.currentData()
        if mode not in META_SORT_MODES:
            return
        syms = list(self._all_order.get(key) or all_of(key))
        if not syms:
            return
        self._rank_state[key] = "LOADING"
        self._rank_seq[key] = self._rank_seq.get(key, 0) + 1
        seq = self._rank_seq[key]
        self.status.set_progress("正在获取市值 / 流动性 / 上市时间…")

        def work(k=key, s=seq, symbols=syms):
            try:
                data = rank_meta.snapshot(symbols)
            except Exception:
                data = {}
            self._rank_signals.ready.emit(k, data or {}, s)

        threading.Thread(target=work, daemon=True).start()

    def _on_rank_meta(self, key_or_data, data=None, seq=None):
        """元数据回执。兼容两种调用：

          - 信号路径：_on_rank_meta(key, data, seq)  —— 带市场与序号；
          - 旧式直接调用：_on_rank_meta(data)        —— 测试/内部，按当前市场。
        """
        if data is None:
            data = key_or_data or {}
            key = self._current_market()
            seq = None
        else:
            key = key_or_data
        # 迟到请求：只接受序号匹配当前最新一次的结果
        if seq is not None and seq != self._rank_seq.get(key):
            return

        valid = self._rank_data_valid(data)
        if valid:
            self._rank_state[key] = "SUCCESS"
            self._rank_ready[key] = True
            self._rank_fail[key] = 0
        else:
            # 失败 / 纯 None 空结果：允许重试，并按指数退避抑制刷屏
            self._rank_state[key] = "FAILED"
            self._rank_ready[key] = False
            fails = self._rank_fail.get(key, 0) + 1
            self._rank_fail[key] = fails
            backoff = min(5 * (2 ** (fails - 1)), 120)
            self._rank_next_at[key] = time.time() + backoff

        # 只补真实数值，绝不让离线 / 断网兜底的 None 覆盖已有真实数据
        # （与阶段 1 资料卡同源问题：异步兜底回来把页上的真值洗掉了）。
        for sym, row in (data or {}).items():
            if not isinstance(row, dict):
                continue
            cur = dict(self._rank_meta.get(sym) or {})
            for k, v in row.items():
                if v is not None and v != "":
                    cur[k] = v
                elif k not in cur:
                    cur[k] = v
            self._rank_meta[sym] = cur
        # 用「请求所属市场」重排，而非回调瞬间的当前市场，避免切页错配
        if self.combo_sort.currentData() in META_SORT_MODES:
            self._relayout_page(key)
            have = sum(1 for s in (self._all_order.get(key) or [])
                       if (self._rank_meta.get(s) or {}).get("cap") is not None)
            self.status.set_progress(
                f"排序依据：CoinLore / 腾讯行情真实数据 · 有市值 {have} 个品种"
                + ("" if valid else "（本次取数失败，稍后自动重试）"))
        else:
            self._update_load_progress(key)

    # ================= 图表页 =================
    def _open_chart(self, symbol: str):
        row = self.rows.get(symbol) or \
            self.all_rows[market_of(symbol)].get(symbol)
        name = (row._name or row._code) if row else ""
        self._focus_symbol = symbol
        self.info_panel.hide_popup()
        # 搜索页是 stack 里的独立图层，切到图表页自动离开；筛选文本保留
        self._enter_chart_layout()
        is_oc = onchain.is_onchain(symbol)
        self.chart_view.open(symbol, name, self._last_tickers.get(symbol))
        self.stack.setCurrentWidget(self.chart_view)
        self._sync_mascot_visibility()   # 看板娘只在这里出现
        if is_oc:
            # 链上品种没有交易所秒级实时价 / K 线：停掉 live 轮询，
            # 只展示真实链上报价，并按需拉一次最新价。
            self.live.stop()
            self.chart_view.show_onchain(
                symbol, self.onchain_meta.get(symbol) or {},
                self._onchain_quotes.get(symbol) or {})
            self._refresh_onchain()
        else:
            # 进入图表后开启秒级实时价：最新 K 线随成交价连续伸缩
            self.live.set_interval(
                int(self.config.get("live_interval_ms") or 900))
            self.live.set_symbol(symbol)
            self.live.start()
        self._mascot_say("chart", sym=display_code(symbol))

    def _open_detail(self):
        """图表页「ⓘ 详情」：弹出当前品种的完整资料抽屉。"""
        symbol = self.chart_view._symbol
        if not symbol:
            return
        row = self.rows.get(symbol) or \
            self.all_rows.get(market_of(symbol), {}).get(symbol)
        name = (getattr(row, "_name", "") or "") if row else ""
        # 阶段 2：详情抽屉按品种复用（最多 3 个），不再每次点击都新建
        # 一整套卡片 / 线程；也改成非模态，移动端可边看边操作。
        dlg = self._detail_cache.get(symbol)
        if dlg is None:
            dlg = SymbolDetailDialog(symbol, name,
                                     self._last_tickers.get(symbol), self)
            self._detail_cache[symbol] = dlg
            self._detail_order.append(symbol)
            while len(self._detail_order) > 3:
                old = self._detail_order.pop(0)
                stale = self._detail_cache.pop(old, None)
                if stale is not None:
                    stale.close()
                    stale.deleteLater()
        else:
            if symbol in self._detail_order:
                self._detail_order.remove(symbol)
            self._detail_order.append(symbol)
            dlg.set_ticker(self._last_tickers.get(symbol))
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _leave_chart(self):
        self.chart_view.close_chart()
        self.live.stop()
        self._switch_market(self._current_market())

    def _on_live_tick(self, symbol: str, price: float, change: float):
        """秒级实时价回到主线程：驱动图表 + 任务栏价格条 + 托盘。"""
        if self.chart_view.isVisible():
            self.chart_view.on_live(symbol, price, change)
        tray = (self.config.get("tray_symbol") or "")
        if tray and symbol == tray:
            t = self._last_tickers.get(symbol)
            if t is not None:
                try:
                    t.last_price = float(price)
                    t.change_pct = float(change)
                except (TypeError, ValueError, AttributeError):
                    return
                self._update_tray_price()

    def _current_symbol(self) -> str:
        """当前页「最该看」的品种：取列表第一行（跟排序一致）。"""
        key = self._current_market()
        lay = self.pages[key]["layout"]
        for i in range(lay.count()):
            w = lay.itemAt(i).widget()
            if isinstance(w, TickerWidget) and w.isVisible():
                return w.symbol
        if self._sub_tabs.get(key) == "all":
            lst = all_of(key)
            return lst[0] if lst else ""
        for s in self.rows:
            if market_of(s) == key:
                return s
        lst = all_of(key)
        return lst[0] if lst else ""

    # ================= 看板娘：场景与遮挡 =================
    def _sync_mascot_visibility(self):
        """看板娘只在图表（K 线）页出现。

        行情列表页、设置页、最小化状态一律收起；显示时把主窗口的范围
        交给立绘做钳制，立绘不会被拖出软件窗口。
        """
        if self.mascot is None:
            return
        try:
            on_chart = self.stack.currentWidget() is self.chart_view \
                and not self.isMinimized()
            self.mascot.set_scene_visible(bool(on_chart))
            if on_chart:
                self.mascot.set_host_rect(self.frameGeometry())
            else:
                # 只在离开图表页时清掉重叠标记；在图表页若正被 K 线
                # 挡住而隐藏，这里绝不能强行 set_overlap(0)，否则会
                # 出现「显示→隐藏」反复横跳，气泡也跟着被反复打断。
                self.mascot.set_overlap(0.0)
        except (RuntimeError, AttributeError):
            pass

    def _update_mascot_overlap(self):
        """图表页：立绘压住 K 线就整个让位，离开重叠区自动回来。

        注意不能因为立绘当前不可见就跳过计算——否则一旦被藏起来，
        没人再算重叠度，它就永远回不来了。
        """
        if self.mascot is None:
            return
        if self.stack.currentWidget() is not self.chart_view:
            self.mascot.set_overlap(0.0)
            return
        try:
            rect = self.chart_view.candles_global_rect()
            geo = self.mascot.frameGeometry()
        except (RuntimeError, AttributeError):
            return
        if rect.isEmpty() or geo.isEmpty():
            self.mascot.set_overlap(0.0)
            return
        inter = geo.intersected(rect.toRect())
        if inter.isEmpty():
            self.mascot.set_overlap(0.0)
            return
        ratio = (inter.width() * inter.height()) / float(
            geo.width() * geo.height())
        self.mascot.set_overlap(ratio)

    def moveEvent(self, event):
        super().moveEvent(event)
        # 主窗口挪动后，立绘的允许范围跟着变（防止悬在软件外）
        self._start_mascot_vis_timer()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._start_mascot_vis_timer()

    def _start_mascot_vis_timer(self):
        if not hasattr(self, "_mascot_vis_timer"):
            self._mascot_vis_timer = QTimer(self)
            self._mascot_vis_timer.setSingleShot(True)
            self._mascot_vis_timer.setInterval(180)
            self._mascot_vis_timer.timeout.connect(self._sync_mascot_visibility)
        self._mascot_vis_timer.start()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self._sync_mascot_visibility()
            tb = getattr(self, "title_bar", None)
            if tb is not None:
                tb.sync_window_state()

    # ============ 窗口：最大化 / 全屏 / 无边框边缘缩放 ============
    def toggle_maximize(self):
        """最大化 / 还原（标题栏 □ 按钮，双击标题栏同样生效）。"""
        if self.isFullScreen():
            return
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def toggle_fullscreen(self):
        """全屏 / 退出全屏；退出时回到进入前的状态（最大化或常规）。"""
        if self.isFullScreen():
            if getattr(self, "_was_maximized", False):
                self.showMaximized()
            else:
                self.showNormal()
        else:
            self._was_maximized = self.isMaximized()
            self.showFullScreen()

    def keyPressEvent(self, event):
        # 全屏时按 ESC 退出，保证永远有办法回到窗口模式
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen()
            event.accept()
            return
        super().keyPressEvent(event)

    _RESIZE_EDGE = 6

    def _frameless_resize_enabled(self) -> bool:
        """只有无边框、非最大化 / 全屏、窗口已显示时才接管边缘缩放。"""
        return bool(self.isVisible()
                    and not self.isMaximized() and not self.isFullScreen()
                    and bool(self.windowFlags() & Qt.FramelessWindowHint))

    def _edges_at(self, gpos) -> Qt.Edges:
        """全局坐标落在哪几条窗口边缘上（返回 Qt.Edges 组合，0 表示不在边缘）。"""
        g = self.frameGeometry()
        edges = Qt.Edges()
        if 0 <= gpos.x() - g.left() < self._RESIZE_EDGE:
            edges |= Qt.LeftEdge
        if 0 <= g.right() - gpos.x() < self._RESIZE_EDGE:
            edges |= Qt.RightEdge
        if 0 <= gpos.y() - g.top() < self._RESIZE_EDGE:
            edges |= Qt.TopEdge
        if 0 <= g.bottom() - gpos.y() < self._RESIZE_EDGE:
            edges |= Qt.BottomEdge
        return edges

    def _frameless_hit_test(self):
        """鼠标是否位于无边框窗口的可缩放边缘，返回 Windows HT* 值。"""
        edges = self._edges_at(QCursor.pos())
        if not edges:
            return None
        combos = (
            (Qt.TopEdge | Qt.LeftEdge, 13),      # HTTOPLEFT
            (Qt.TopEdge | Qt.RightEdge, 14),     # HTTOPRIGHT
            (Qt.BottomEdge | Qt.LeftEdge, 16),   # HTBOTTOMLEFT
            (Qt.BottomEdge | Qt.RightEdge, 17),  # HTBOTTOMRIGHT
            (Qt.LeftEdge, 10),                   # HTLEFT
            (Qt.RightEdge, 11),                  # HTRIGHT
            (Qt.TopEdge, 12),                    # HTTOP
            (Qt.BottomEdge, 15),                 # HTBOTTOM
        )
        for mask, ht in combos:
            if edges == mask:
                return ht
        return None

    def nativeEvent(self, eventType, message):
        """无边框窗口的边缘拉伸：用原生 WM_NCHITTEST 把四边声明成缩放边。

        必须在系统层处理——Qt 子控件铺满了窗口，QWidget 的鼠标事件
        拿不到边缘区域；原生 hit-test 无视子控件，可以在任意控件上
        直接拖边缩放。仅 Windows 且无边框模式生效。
        """
        if (_cwin is not None
                and eventType == b"windows_generic_MSG"
                and self._frameless_resize_enabled()):
            msg = _cwin.MSG.from_address(int(message))
            if msg.message == 0x0084:          # WM_NCHITTEST
                hit = self._frameless_hit_test()
                if hit is not None:
                    return True, hit
        return super().nativeEvent(eventType, message)


    # ================= 品种资料弹窗（右键菜单触发） =================
    def _show_info_popup(self, symbol: str):
        """右键菜单「ℹ 查看资料」：在该行旁边浮出资料弹窗。

        只有用户明确选中才弹出；弹窗可交互、右上角 ✕ 关闭，
        切页 / 进图表 / 滚动列表时自动收起。
        """
        if not symbol:
            return
        row = self.rows.get(symbol) or \
            self.all_rows.get(market_of(symbol), {}).get(symbol)
        if row is None or not row.isVisible():
            return
        self._focus_symbol = symbol
        self._sync_info_panel(force=True)
        anchor = QRect(row.mapToGlobal(QPoint(0, 0)), row.size())
        self.info_panel.show_for(anchor, self)

    def _info_symbol(self) -> str:
        """资料卡显示的品种：优先用户刚点过的，其次当前市场第一个。"""
        sym = self._focus_symbol
        if sym and market_of(sym) == self._current_market():
            return sym
        return self._current_symbol()

    def _sync_info_panel(self, force: bool = False):
        """把资料卡对齐到当前品种，并用最近一次行情快照刷新数值。"""
        if not hasattr(self, "info_panel"):
            return
        sym = self._info_symbol()
        if not sym:
            self.info_panel.clear()
            return
        if force or sym != self.info_panel._symbol:
            name = ""
            row = self.rows.get(sym) or \
                self.all_rows.get(market_of(sym), {}).get(sym)
            if row is not None:
                name = getattr(row, "_name", "") or ""
            self.info_panel.set_symbol(sym, name)
        self.info_panel.update_ticker(self._last_tickers.get(sym))

    def _on_bottom_nav(self, key: str):
        """底部导航：行情 / 图表 / 设置（阶段 5 统一入口）。"""
        if key == "list":
            cur = self.stack.currentWidget()
            if cur is self.settings_page:
                # 设置页里点「行情」：回到进设置前的页面（列表页或图表页），
                # 之前只处理了图表页分支，导致设置页里点行情毫无反应。
                self._close_settings_page()
            elif cur is self.search_panel:
                self._close_search_page()
            elif self._list_geometry is not None:
                self._leave_chart()
            else:
                self.stack.setCurrentWidget(
                    self.pages[self._current_market()]["scroll"])
            # 从设置页点「行情」有可能回到的是图表页（进来前就在图表），
            # 必须按最终实际页面同步高亮 / 标题，不能无条件标成「行情」。
            now = self.stack.currentWidget()
            if now is self.chart_view:
                self.bottom_nav.set_active("chart")
                self.title_bar.set_page("图表", True)
            else:
                self.bottom_nav.set_active("list")
                self.title_bar.set_page("行情", False)
        elif key == "chart":
            self._open_chart_tab()
        elif key == "settings":
            self.open_settings()   # 设置是独立页面，取消/保存后回原页面

    def _open_chart_tab(self):
        """独立「图表」选项卡：回到上次看的品种，没有就取第一个自选。"""
        sym = self._focus_symbol or self.chart_view._symbol
        known = (sym in self.rows
                 or sym in self.all_rows.get(market_of(sym or ""), {}))
        if not sym or not known:
            sym = next(iter(self.rows), "")
            if not sym:
                lst = all_of(self._current_market())
                sym = lst[0] if lst else ""
        if sym:
            self._open_chart(sym)

    def _navigate_back(self):
        """统一返回逻辑：浮层 → 设置页 → 搜索页 → 图表页 → 列表页。"""
        for dlg in list(getattr(self, "_detail_cache", {}).values()):
            try:
                if dlg.isVisible():
                    dlg.hide()
                    return
            except RuntimeError:
                pass
        cur = self.stack.currentWidget()
        if cur is self.settings_page:
            self._close_settings_page()
        elif cur is self.search_panel:
            self._close_search_page()
        elif cur is self.chart_view:
            self._leave_chart()
        else:
            self.info_panel.hide_popup()

    # ---- 阶段 6：触摸与响应式 -------------------------------------------
    def _on_row_long_press(self, symbol: str):
        """长按反馈（菜单本身由行的 context_menu 信号打开）。"""
        self._last_long_press = symbol
        self._mascot_say("chart", sym=display_code(symbol))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            self._apply_responsive(event.size().width())
        except Exception:
            pass        # 构造早期控件还没建齐

    def _apply_responsive(self, width: int):
        """单列优先：窄屏收起次要信息，所有主操作仍是 44px 触控目标。"""
        narrow = width < 600
        self._narrow = narrow
        self.lbl_hint.setVisible(not narrow)
        self.combo_sort.setFixedWidth(112 if narrow else 138)
        self.edit_search.setPlaceholderText(
            "搜索 / 筛选" if narrow else "搜索代码 / 名称 / 链上合约地址")

    def _enter_chart_layout(self):
        for widget in self._list_controls:
            widget.hide()
        self.status.hide()
        self.info_panel.hide_popup()
        if hasattr(self, "_mascot_timer"):
            self._mascot_timer.start()      # 图表页才需要算与 K 线的重叠
        if hasattr(self, "bottom_nav"):
            self.bottom_nav.set_active("chart")
        if hasattr(self, "title_bar"):
            self.title_bar.set_page("图表", True)
        if self._list_geometry is not None:
            return
        self._list_geometry = (self.x(), self.y(),
                               self.width(), self.height())
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        target_w = max(self.width(), min(1020, avail.width() - 24))
        target_h = max(self.height(), min(680, avail.height() - 24))
        if (target_w, target_h) != (self.width(), self.height()):
            self.resize(target_w, target_h)
        nx = min(self.x(), avail.right() - self.width() - 8)
        ny = min(self.y(), avail.bottom() - self.height() - 8)
        self.move(max(avail.left() + 8, nx), max(avail.top() + 8, ny))

    def _leave_chart_layout(self):
        for widget in self._list_controls:
            widget.show()
        self.status.show()
        if hasattr(self, "_mascot_timer"):
            self._mascot_timer.stop()
        if self.mascot is not None:
            self.mascot.set_overlap(0.0)
            # 离开图表布局必然意味着回列表页：直接收起。
            # （此时 stack 可能还停在图表页，不能走 _sync_mascot_visibility，
            #   否则它会把刚收起的看板娘又放出来；stack 切换后 _switch_market
            #   会再同步一次。）
            self.mascot.set_scene_visible(False)
        if hasattr(self, "bottom_nav"):
            self.bottom_nav.set_active("list")
        if hasattr(self, "title_bar"):
            self.title_bar.set_page("行情", False)
        if self._list_geometry is None:
            return
        x, y, w, h = self._list_geometry
        self._list_geometry = None
        self.move(x, y)
        self._resize_for_restore(w, h)

    def _resize_for_restore(self, w: int, h: int):
        """还原较窄的记忆宽度前先解除对最小宽度的钳制。

        图表页时窗口被放大，其最小宽度（minimumSizeHint / minimumSize）
        会被顶到 ~439px；直接 resize 到记忆里的窄宽度（默认 380）会被
        钳住，还原不回去。这里临时把窗口最小尺寸降到 0，resize 成功后再
        恢复一个不超过目标宽度的安全最小值，保证窄窗口几何能精确还原。
        同时若当前停在图表页，先切回列表页并收起最大化 / 全屏按钮。
        """
        tb = getattr(self, "title_bar", None)
        stack = getattr(self, "stack", None)
        chart = getattr(self, "chart_view", None)
        if w < 440:
            if tb is not None and hasattr(tb, "set_compact"):
                tb.set_compact(True)   # 压缩按钮，不再隐藏最大化 / 全屏
            if stack is not None and chart is not None \
                    and stack.currentWidget() is chart:
                key = self._current_market()
                for i, (gkey, _, _) in enumerate(MARKET_GROUPS):
                    if gkey == key:
                        stack.setCurrentIndex(i)
                        break
        # 临时解除钳制：否则 offscreen / 某些平台上 minimumSize 已偏高，
        # resize 会被静默钳到该值，窄窗口几何永远回不去。
        prev_min = self.minimumSize()
        self.setMinimumSize(0, 0)
        self.resize(w, h)
        safe_min_w = prev_min.width() if prev_min.width() else 0
        self.setMinimumSize(min(safe_min_w, w), 0)

    # ================= 页签 / 子菜单 =================
    def _switch_market(self, key: str):
        if key not in self.pages:
            return
        self.chart_view.close_chart()
        self.info_panel.hide_popup()      # 换市场：右键资料弹窗跟着收起
        # 先切回该市场的列表页：否则 _leave_chart_layout 还原几何时
        # chart_view 仍可见、其控件最小宽度会钳住窄窗口的恢复。
        for i, (gkey, _, _) in enumerate(MARKET_GROUPS):
            if gkey == key:
                self.stack.setCurrentIndex(i)
                break
        self._leave_chart_layout()
        # 搜索页是 stack 独立图层，切市场自动离开；筛选文本保留
        self.tabs.set_active(key)
        # stack 已在上面临时切回列表页，这里重新同步看板娘 / 标题：
        # 此刻 chart_view 不可见，看板娘必然隐藏。
        self._sync_mascot_visibility()
        self.title_bar.set_page("行情", False)
        self.config.set("last_tab", key)
        self.config.save()
        # 该市场还没有任何自选时（A股/港股/美股默认即是），自动落到「全部」，
        # 否则切过去看到的是一张空页，会被误认为「其它市场没有品种」。
        if self._sub_tabs.get(key) == "watch" and not any(
                market_of(s) == key for s in self.rows):
            self._sub_tabs[key] = "all"
            self.config.set("sub_tabs", dict(self._sub_tabs))
            self.config.save()
        self.sub_tabs.set_active(self._sub_tabs.get(key, "watch"))
        self._focus_symbol = ""
        self._update_section_count()
        self.pages[key]["scroll"].verticalScrollBar().setValue(0)
        self._relayout_page(key)
        if self._sub_tabs.get(key) == "all":
            self._paint_page_rows(key)
        self._update_load_progress(key)
        self._refresh_symbols()
        if hasattr(self, "scheduler"):
            self.scheduler.refresh_now()
        self._ensure_rank_meta(key)
        self._sync_info_panel(force=True)
        self._mascot_say("market", market=dict(
            (g[0], g[1]) for g in MARKET_GROUPS).get(key, key))

    def _switch_sub(self, key: str):
        if key not in ("watch", "all"):
            return
        market = self._current_market()
        self._sub_tabs[market] = key
        self.config.set("sub_tabs", dict(self._sub_tabs))
        self.config.save()
        self.sub_tabs.set_active(key)
        # 搜索页独立成图层，切子页自动离开；筛选文本保留
        self._focus_symbol = ""        # 换页后不要沿用上一页的品种
        self.pages[market]["scroll"].verticalScrollBar().setValue(0)
        self._relayout_page(market)
        if key == "all":
            self._paint_page_rows(market)
        self._update_section_count()
        self._update_load_progress(market)
        self._refresh_symbols()
        self.scheduler.refresh_now()
        self._ensure_rank_meta(market)
        self._sync_info_panel(force=True)

    # ================= 搜索 =================
    def _do_search(self, from_timer=False):
        # 防抖/重试是「用户仍在搜索上下文」才成立的假设。用户点结果进了
        # 图表页后，这些延时回调必须放弃，否则旧回执会把图表页拉回搜索页。
        if from_timer and self.stack.currentWidget() is self.chart_view:
            self._search_seq += 1
            self._active_search_query = ""
            return
        query = self.edit_search.text().strip()
        # 统一搜索：每次真正发起查询都递增序号；空查询也让在途回执全部失效。
        # 防抖期间用户继续输入时，旧 worker 的回执不得覆盖最新结果。
        self._search_seq += 1
        seq = self._search_seq
        self._active_search_query = query
        if not query:
            # 空关键词：已在搜索页时展示搜索历史（保留最近 50 条）
            if self.stack.currentWidget() is self.search_panel:
                self._show_search_history()
            else:
                self._close_search_page()
            return
        # 链上合约地址：合约地址优先精确解析（名称搜索由统一搜索覆盖）
        if is_contract(query):
            if self._contract_worker is not None:
                try:
                    if self._contract_worker.isRunning():
                        QTimer.singleShot(220, lambda: self._do_search(True))
                        return
                except RuntimeError:
                    self._contract_worker = None
            self.search_panel.show_loading("正在解析链上合约地址…")
            self._open_search_page()
            cw = ContractWorker(query, self)
            cw.resolved.connect(self._on_contract_result)
            cw.finished.connect(cw.deleteLater)
            self._contract_worker = cw
            cw.start()
            return
        if self._search_worker is not None:
            try:
                if self._search_worker.isRunning():
                    QTimer.singleShot(200, lambda: self._do_search(True))
                    return
            except RuntimeError:
                self._search_worker = None
        # 加载中状态与「无结果 / 网络失败」明确区分；先备好内容，结果回来再切页
        self.search_panel.show_loading(
            f"正在搜索「{html.escape(query)}」：股票 / CEX / 链上代币…")
        worker = SearchWorker(self.market, query, seq, self)
        worker.results.connect(self._on_search_results)
        worker.failed.connect(self._on_search_failed)
        worker.finished.connect(self._on_search_done)
        self._search_worker = worker
        worker.start()

    def _on_search_done(self):
        worker = self.sender()
        if worker is self._search_worker:
            self._search_worker = None
        try:
            worker.deleteLater()
        except (RuntimeError, AttributeError):
            pass

    def _on_search_results(self, results, req_seq=-1):
        """统一搜索回执：过期序号 / 空查询 / 关键词已变 / 已进图表一律丢弃。"""
        if self.stack.currentWidget() is self.chart_view:
            return
        if req_seq != -1 and req_seq != self._search_seq:
            return
        query = self.edit_search.text().strip()
        if not query or query != self._active_search_query:
            return
        self.search_panel.show_results(results, set(self.rows))
        self._open_search_page()
        # 只有真正有命中才记录，失败 / 无结果 / 空输入不写历史。
        if results:
            self._record_search_history(query)

    def _on_search_failed(self, message, req_seq=-1):
        """网络失败 / 数据源不可用：明确报错，不记录历史、不伪装成无结果。"""
        if self.stack.currentWidget() is self.chart_view:
            return
        if req_seq != -1 and req_seq != self._search_seq:
            return
        if not self.edit_search.text().strip():
            return
        self.search_panel.show_error(
            "网络或数据源不可用，本次搜索未完成",
            f"原因：{message}。请检查网络后重试；已收藏品种与缓存行情不受影响。")
        self._open_search_page()

    def _on_contract_result(self, info):
        """合约地址解析结果：链上真实存在即可收藏，与有没有 K 线无关。

        旧逻辑把「币安有现货交易对 / 有 K 线」当成加入自选的前提，
        pump.fun 上的新币因此既不能收藏也看不到价格。现在三件事解耦：
        可收藏（链上账户存在）、可看价（链上真实报价）、可看 K 线（没有
        就明确标注）。所有展示值都来自真实接口，缺失的一律不显示。
        """
        cur = self.edit_search.text().strip()
        if not cur or not is_contract(cur):
            return
        addr = info.get("address") or cur
        sym = (info.get("symbol") or "").upper()
        short = onchain.short_address(addr) or addr
        parts = [f"合约 {short}"]
        if info.get("chain"):
            parts.append(str(info["chain"]).title())
        if info.get("program"):
            parts.append(str(info["program"]))
        if sym:
            parts.append(f"→ {sym} {info.get('name') or ''}".strip())
        supply = info.get("supply") or 0
        if supply:
            parts.append(f"总量 {format_cap(supply)}")
        for key, fmt in (("price", "${:.6g}"), ("change", "{:+.2f}%")):
            v = info.get(key)
            if v:
                try:
                    parts.append(fmt.format(float(v)))
                except (TypeError, ValueError):
                    pass
        if info.get("liquidity"):
            parts.append(f"链上流动性 {format_cap(float(info['liquidity']))}")
        if info.get("holders"):
            parts.append(f"持有地址 {int(float(info['holders'])):,}")
        if info.get("price_source"):
            when = time.strftime("%H:%M:%S",
                                 time.localtime(info.get("price_ts") or time.time()))
            parts.append(f"来源 {info['price_source']} {when}")
        note = " · ".join(parts)
        # 链上账户都不存在的地址（复制不全 / 打错）单独提示，别让人以为是网络问题
        if not info.get("exists"):
            self.search_panel.show_results(
                [], set(self.rows),
                note + " · 链上查不到该地址，请确认地址完整")
            return

        chain = info.get("chain") or onchain.chain_of(addr)
        sym_oc = onchain.make_symbol(addr)
        meta = onchain.blank_meta(
            addr, sym, info.get("name") or "", chain,
            info.get("supply") or 0.0, info.get("decimals") or 0,
            info.get("program") or "")
        self.onchain_meta[sym_oc] = meta
        self.config.set("onchain_symbols", self.onchain_meta)
        self.config.save()
        # 首次解析的真实报价直接进缓存：加入自选后立刻能看到价格，
        # 不用等下一轮 60 秒刷新。没有报价就留空，行会明确显示「—」。
        q = {
            "price": info.get("price") or None,
            "change": info.get("change") or None,
            "liquidity": info.get("liquidity"),
            "holders": info.get("holders"),
            "source": info.get("price_source") or onchain.SOURCE,
            "ts": info.get("price_ts") or time.time(),
        }
        if q["price"]:
            self._onchain_quotes[sym_oc] = q

        label = sym or onchain.short_address(addr)
        item = {"symbol": sym_oc, "label": label,
                "name": (info.get("name") or label) + f" · {chain}",
                "kind": "链上合约"}
        suffix = " · 可加入自选 / 查看链上价格"
        if not info.get("tradable"):
            suffix += " · 暂无 K 线（不影响收藏与价格）"
        if not info.get("price"):
            suffix += " · 当前无公开报价，稍后自动重试"
        self.search_panel.show_results(
            [item], set(self.rows), note + suffix)
        # 合约解析成功 → 记录为资产对象历史（身份 = chain + address）
        self._record_search_history(asset_search.make_hit(
            sym_oc, label=label, name=(info.get("name") or label),
            asset_type=asset_search.ASSET_ONCHAIN, market=chain,
            chain=chain, address=addr, query=cur))

    # ---- 搜索页导航 / 搜索历史（阶段 8 起 v2 资产对象） ------------------
    def _on_search_button(self):
        """工具条搜索按钮：聚焦搜索框；有内容立即搜索，无内容看历史。"""
        self.edit_search.setFocus()
        if self.edit_search.text().strip():
            self._search_debounce.stop()
            self._do_search()
        else:
            self._show_search_history()
            self._open_search_page()

    def _open_search_page(self):
        """进入搜索页（独立图层），标题「搜索」，底部导航高亮行情。"""
        if self.stack.currentWidget() is not self.search_panel:
            self._leave_chart_layout()
        self.stack.setCurrentWidget(self.search_panel)
        self.bottom_nav.set_active("list")
        self.title_bar.set_page("搜索", True)

    def _close_search_page(self):
        """返回行情列表（搜索文本保留，Esc 清空）。"""
        self.stack.setCurrentWidget(
            self.pages[self._current_market()]["scroll"])
        self.bottom_nav.set_active("list")
        self.title_bar.set_page("行情", False)

    def _show_search_history(self):
        # 配置里可能仍是旧版纯字符串，归一后交给搜索页渲染（资产类型/链/市场）
        self.search_panel.show_history(
            list(self.config.get("search_history") or []))

    SEARCH_HISTORY_MAX = asset_search.HISTORY_MAX   # 50：与 Android / 共享模型一致

    def _record_search_history(self, entry):
        """记录一次**成功**搜索（资产对象或关键词）：按 asset_id 去重、
        重复移至最前、上限 50。空 / 失败 / 无结果由调用方保证不进来。
        """
        hist = asset_search.record_history(
            self.config.get("search_history") or [], entry,
            max_items=self.SEARCH_HISTORY_MAX)
        self.config.set("search_history", hist)
        self.config.save()
        if (self.stack.currentWidget() is self.search_panel
                and getattr(self.search_panel, "_mode", "") == "history"):
            self._show_search_history()

    def _on_search_open(self, item: dict):
        """点击搜索结果行 → 进入该品种图表（不默认加入自选）；同时把
        历史从「关键词」升级为带身份的资产对象，便于下次一键打开。
        """
        self._record_search_history(item)
        self._open_chart(str(item.get("symbol") or ""))

    def _on_history_pick(self, entry):
        """点击历史：有资产身份 → 直接打开；旧关键词 → 回填并重新搜索。"""
        sym = asset_search.history_symbol(entry)
        if sym:
            self._record_search_history(entry)   # 重复使用，移至最前
            self._open_chart(sym)
            return
        query = asset_search.history_query(entry)
        self.edit_search.setText(query)
        self._search_debounce.stop()
        self._do_search()

    def _on_history_deleted(self, entry):
        """单条删除：按 asset_id，不用显示文本（同名资产可跨链共存）。"""
        key = entry.get("id") if isinstance(entry, dict) else entry
        hist = asset_search.delete_history(
            self.config.get("search_history") or [], key)
        self.config.set("search_history", hist)
        self.config.save()
        self._show_search_history()

    def _on_history_cleared(self):
        self.config.set("search_history", asset_search.clear_history())
        self.config.save()
        self._show_search_history()

    def eventFilter(self, obj, event):
        if obj is self.edit_search and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.edit_search.clear()
                if self.stack.currentWidget() is self.search_panel:
                    self._close_search_page()
                return True
        # 边缘缩放兜底：Windows 原生 hit-test 对某些 Qt 子控件 / DPI 组合
        # 不生效时，用 QWindow.startSystemResize 在系统层完成同样的操作。
        if (self._frameless_resize_enabled()
                and event.type() == QEvent.MouseButtonPress
                and event.button() == Qt.LeftButton):
            try:
                gpos = event.globalPosition().toPoint()
            except AttributeError:
                gpos = event.globalPos()
            edges = self._edges_at(gpos)
            if edges:
                handle = self.windowHandle()
                if handle is not None and hasattr(handle, "startSystemResize"):
                    handle.startSystemResize(edges)
                    return True
        return super().eventFilter(obj, event)

    # ================= 窗口设置 =================
    def apply_window_settings(self, save=True):
        cfg = self.config
        if save:
            self._save_current_geometry_before_reapply()
        flags = Qt.Window
        if cfg.get("frameless"):
            flags |= Qt.FramelessWindowHint
        if cfg.get("always_on_top"):
            flags |= Qt.WindowStaysOnTopHint
        if getattr(self, "_win_flags", None) != flags:
            # setWindowFlags 会让窗口先隐藏再重建，尺寸/位置不对时会闪一下；
            # 只在标志真的变了（置顶 / 无边框切换）才调用。
            self._win_flags = flags
            self.setWindowFlags(flags)
        self.title_bar.setVisible(bool(cfg.get("frameless")))
        self.setWindowOpacity(max(0.3, cfg.get("opacity", 100) / 100.0))
        if self._list_geometry is not None:
            if self.isVisible():
                self.show()
            self._sync_mascot_visibility()
            return
        x, y = cfg.get("x"), cfg.get("y")
        w, h = int(cfg.get("w") or 0), int(cfg.get("h") or 0)
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            if w > 0 and h > 0:
                w = min(w, avail.width())
                h = min(h, avail.height())
            # 顶边/左边出屏（例如上次最大化后残留的负坐标）直接归位，
            # 否则标题栏点不到、窗口看着像在跳。
            if y < avail.top():
                y = avail.top()
            if x < avail.left():
                x = avail.left()
            if w > 0 and x > avail.right() - 120:
                x = avail.left()
            if h > 0 and y > avail.bottom() - 80:
                y = avail.top()
        if x >= 0 and y >= 0:
            self.move(x, y)
        if w > 0 and h > 0:
            self._resize_for_restore(w, h)
        if self.isVisible():
            self.show()
        self._sync_mascot_visibility()

    def _save_current_geometry_before_reapply(self):
        if self._list_geometry is not None:
            return
        if self.isMaximized() or self.isFullScreen():
            return      # 最大化 / 全屏时不动记忆中的常规尺寸
        self.config.set("x", self.x())
        self.config.set("y", self.y())
        self.config.set("w", self.width())
        self.config.set("h", self.height())

    def save_geometry(self):
        if self._list_geometry is not None:
            return
        if self.isMaximized() or self.isFullScreen():
            return      # 最大化 / 全屏不覆盖常规几何，下次启动尺寸正常
        self.config.set("x", self.x())
        self.config.set("y", self.y())
        self.config.set("w", self.width())
        self.config.set("h", self.height())
        self.config.save()

    # ================= 系统托盘 =================
    def _setup_tray(self):
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("Free Chart 行情看板")
        self.tray_menu = QMenu()
        self.tray_menu.setStyleSheet(menu_qss())

        self.act_price = QAction("托盘价格 --", self)
        self.act_price.setEnabled(False)
        self.tray_menu.addAction(self.act_price)
        self.tray_symbol_menu = QMenu("托盘显示品种", self.tray_menu)
        self.tray_symbol_menu.setStyleSheet(menu_qss())
        self.tray_menu.addMenu(self.tray_symbol_menu)
        self._rebuild_tray_symbol_menu()
        self.tray_menu.addSeparator()

        act_show = QAction("显示 / 隐藏窗口", self)
        act_show.triggered.connect(self.toggle_visible)
        self.tray_menu.addAction(act_show)
        self.act_badge = QAction("任务栏右侧实时价格", self)
        self.act_badge.setCheckable(True)
        self.act_badge.setChecked(bool(self.config.get("price_badge", True)))
        self.act_badge.setToolTip(
            "贴合任务栏固定在通知区左侧，不是悬浮窗；右键可换品种")
        self.act_badge.triggered.connect(self._toggle_price_badge)
        self.tray_menu.addAction(self.act_badge)
        act_fix_icon = QAction("修复快捷方式图标", self)
        act_fix_icon.setToolTip(
            "把桌面 / 开始菜单快捷方式的图标刷成当前程序图标\n"
            "（Windows 会缓存旧图标，重打包后需要这一步）")
        act_fix_icon.triggered.connect(self._fix_shortcut_icons)
        self.tray_menu.addAction(act_fix_icon)
        self.act_top = QAction("窗口置顶", self)
        self.act_top.setCheckable(True)
        self.act_top.setChecked(bool(self.config.get("always_on_top")))
        self.act_top.triggered.connect(self.toggle_on_top)
        self.tray_menu.addAction(self.act_top)
        act_refresh = QAction("手动刷新", self)
        act_refresh.triggered.connect(self.scheduler.refresh_now)
        self.tray_menu.addAction(act_refresh)
        act_prefetch = QAction("立即预缓存主流品种 K 线", self)
        act_prefetch.setToolTip(
            "后台把自选 + 四市场主流品种的历史 K 线写入本地，之后浏览直接读盘")
        act_prefetch.triggered.connect(lambda: self.start_prefetch(force=True))
        self.tray_menu.addAction(act_prefetch)
        self.tray_menu.addSeparator()
        act_settings = QAction("设置…", self)
        act_settings.triggered.connect(self.open_settings)
        self.tray_menu.addAction(act_settings)
        act_quit = QAction("退出", self)
        act_quit.triggered.connect(self.quit_app)
        self.tray_menu.addAction(act_quit)

        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        self._update_tray_price()

    def _rebuild_tray_symbol_menu(self):
        """托盘右键可直接切换要显示的品种。"""
        if not hasattr(self, "tray_symbol_menu"):
            return
        menu = self.tray_symbol_menu
        menu.clear()
        current = self.config.get("tray_symbol") or "BTC"
        show = bool(self.config.get("tray_show_price"))
        off = QAction("不显示价格", self)
        off.setCheckable(True)
        off.setChecked(not show)
        off.triggered.connect(lambda: self._set_tray_price_enabled(False))
        menu.addAction(off)
        menu.addSeparator()
        # 自选 + 当前市场「全部」页前 40 + 当前指定品种：托盘菜单与
        # 任务栏价格条右键菜单共用同一份清单，非自选品种也能直接指定。
        candidates = list(dict.fromkeys(
            list(self.rows) + list(all_of(self._current_market()))[:40]
            + ([current] if current else [])))
        if hasattr(self, "price_badge"):
            self.price_badge.set_candidates(candidates)
        for s in candidates[:60]:
            act = QAction(display_code(s), self)
            act.setCheckable(True)
            act.setChecked(show and s == current)
            act.triggered.connect(
                lambda checked=False, sym=s: self.set_tray_symbol(sym))
            menu.addAction(act)

    def _set_tray_price_enabled(self, enabled: bool):
        self.config.set("tray_show_price", bool(enabled))
        self.config.save()
        self._rebuild_tray_symbol_menu()
        self._update_tray_price()
        self._refresh_symbols()

    def set_tray_symbol(self, symbol: str):
        self.config.set("tray_symbol", symbol)
        self.config.set("tray_show_price", True)
        self.config.save()
        self._rebuild_tray_symbol_menu()
        self._update_tray_price()
        self._refresh_symbols()
        self.scheduler.refresh_now()

    # ---- 常驻价格条 ----
    def prepare_show(self):
        """构造完成、尺寸算好之后再真正上屏（避免启动闪小空框）。"""
        self.setAttribute(Qt.WA_DontShowOnScreen, False)
        self.show()
        self.raise_()

    def reveal(self):
        """把窗口从托盘 / 最小化恢复到前台（单实例唤醒、托盘单击共用）。"""
        if self.testAttribute(Qt.WA_DontShowOnScreen):
            self.setAttribute(Qt.WA_DontShowOnScreen, False)
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        self.scheduler.start()   # 幂等：确保隐藏期间若被停过也能恢复刷新

    def _show_from_badge(self):
        self.reveal()

    def _on_badge_visibility(self, visible):
        if hasattr(self, "act_badge"):
            self.act_badge.setChecked(bool(visible))

    def _fix_shortcut_icons(self):
        """手动修复：桌面 / 开始菜单快捷方式图标跟随当前 EXE。"""
        try:
            from core.shortcut import sync_shortcuts
            changed = sync_shortcuts(force=True)
        except Exception as exc:            # 权限 / COM 异常都不该影响主程序
            self.tray.showMessage("快捷方式图标修复失败", str(exc),
                                  QSystemTrayIcon.Warning, 4000)
            return
        msg = (f"已刷新 {len(changed)} 个快捷方式图标" if changed
               else "没有找到指向本程序的快捷方式")
        self.tray.showMessage("Free Chart", msg,
                              QSystemTrayIcon.Information, 3500)

    def _toggle_price_badge(self, checked):
        self.config.set("price_badge", bool(checked))
        self.config.save()
        self._sync_badge()

    _TRAY_CACHE_TTL = 300.0

    def _cache_tray_ticker(self, tickers):
        """记住指定品种本轮的真实报价（只保留当前指定的那一个）。"""
        sym = self.config.get("tray_symbol") or "BTC"
        t = tickers.get(sym)
        if t is not None:
            self._tray_ticker_cache = {sym: (time.time(), t)}

    def _ticker_for(self, sym):
        """返回 (Ticker|None, 是否来自缓存)。

        优先用本轮快照；本轮缺该品种时沿用 5 分钟内的上次有效报价，
        避免股票源 / 加密某一批临时失败时价格条闪成 "-- WAIT"。
        """
        # 阶段 2 起 _last_tickers 是「合并快照」（分页请求只覆盖可见窗口），
        # 里面还留着上一页 / 上一次刷新的值。因此「是否本轮实时」必须看
        # 本轮返回集合，不能只看字典里有没有，否则会把缓存价标成实时价。
        if sym in self._current_batch:
            t = self._last_tickers.get(sym)
            if t is not None:
                return t, False
        hit = self._tray_ticker_cache.get(sym)
        if hit and time.time() - hit[0] <= self._TRAY_CACHE_TTL:
            return hit[1], True
        return None, False

    def _sync_badge(self):
        """把指定品种价格推给任务栏常驻价格条（与托盘价格开关互不干涉）。"""
        if not hasattr(self, "price_badge"):
            return
        sym = self.config.get("tray_symbol") or "BTC"
        show = bool(self.config.get("price_badge", True))
        if self.price_badge.isVisible() != show:
            self.price_badge.setVisible(show)
        if show:
            ticker, stale = self._ticker_for(sym)
            self.price_badge.update_ticker(ticker, sym, stale=stale)

    def _update_tray_price(self):
        """托盘图标直接显示自定义品种实时价格（红涨绿跌）+ 完整 tooltip。"""
        if not hasattr(self, "tray"):
            return
        symbol = self.config.get("tray_symbol") or "BTC"
        show = bool(self.config.get("tray_show_price"))
        code = display_code(symbol)
        t, _stale = self._ticker_for(symbol)
        if not show or t is None:
            self.tray.setIcon(app_icon())
            self.act_price.setText(f"{code}  --  等待行情" if show
                                   else "托盘价格：未启用")
            self.tray.setToolTip(
                "Free Chart 行情看板" +
                (f"\n{code} 等待行情" if show else "\n右键可设置显示品种"))
        else:
            style = str(self.config.get("tray_icon_style") or "app")
            if style == "price":
                self.tray.setIcon(tray_price_icon(
                    symbol, t.last_price, t.change_pct))
            else:
                # 与桌面 / 任务栏图标同一套方案，角上一个红绿点表示涨跌
                self.tray.setIcon(tray_app_icon(t.change_pct))
            sign = "+" if t.change_pct >= 0 else ""
            txt = (f"{code}  {format_price(t.last_price)}  "
                   f"{sign}{t.change_pct:.2f}%")
            self.act_price.setText("● " + txt)
            self.tray.setToolTip(
                f"Free Chart · {txt}\n"
                f"高 {format_price(t.high_24h)}  低 {format_price(t.low_24h)}\n"
                f"右键菜单可更换显示的品种")
        self._update_window_title()
        self._sync_badge()

    def _update_window_title(self):
        """窗口标题同步选定品种实时价格，任务栏按钮/预览即可看到。"""
        symbol = self.config.get("tray_symbol") or "BTC"
        t, _stale = self._ticker_for(symbol)
        code = display_code(symbol)
        if t is not None:
            sign = "+" if t.change_pct >= 0 else ""
            title = (f"{code} {format_price(t.last_price)}  "
                     f"{sign}{t.change_pct:.2f}%  ·  Free Chart")
        else:
            title = brand.APP_TITLE
        if getattr(self.market, "last_errors", []):
            title += "  [部分数据源异常]"
        if self._last_meta[1] > 0 and not self._last_meta[2]:
            title += "  [网络异常]"
        self.setWindowTitle(title)

    def _paint_page_rows(self, key: str):
        """只刷新当前挂载窗口内的行（阶段 2）。

        旧版每次行情回来都遍历 500 行调用 update_ticker，其中 440 行根本
        没显示；500 次 QLabel.setText + 重绘就是列表卡屏的直接原因。
        """
        group = self.all_rows[key]
        order = self._all_order.get(key) or []
        for symbol in order[:self._page_limit.get(key, PAGE_SIZE)]:
            row = group.get(symbol)
            if row is None:
                continue
            self._paint_row(symbol, row)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_visible()

    # ================= 主流品种 K 线历史后台预缓存 =================
    # ================= 股票真实 logo =================
    def start_stock_logos(self):
        """由 main.py 启动：后台串行抓取已显示股票的公司 logo 并缓存。

        离线回归测试不会调用本方法，因此不会产生任何网络线程。
        """
        stock_logo.start()
        for symbol in list(self.rows):
            stock_logo.request(symbol)
        for group in self.all_rows.values():
            for symbol in group:
                stock_logo.request(symbol)
        # 三个股票市场全量预热（已缓存的不再请求）：首次启动后台跑几分钟，
        # 之后打开任何市场页都是现成图标，不用边看边等
        for key in ("cn", "hk", "us"):
            for symbol in all_of(key):
                stock_logo.request(symbol)

    def _on_stock_logo(self, symbol: str, path: str):
        """某只股票的真实 logo 落盘后，立即换掉它所有行上的字徽。"""
        invalidate_symbol(symbol)
        targets = []
        row = self.rows.get(symbol)
        if row is not None:
            targets.append(row)
        for group in self.all_rows.values():
            w = group.get(symbol)
            if w is not None:
                targets.append(w)
        pm = symbol_icon(symbol, 30)
        for w in targets:
            try:
                w.icon.setPixmap(pm)
            except RuntimeError:
                pass      # 行已被销毁

    def start_prefetch(self, force: bool = False):
        """把自选 + 四市场主流品种的历史 K 线批量写入本地。

        由 main.py 在窗口显示后调用（延迟若干秒避开实时行情刷新），
        或由托盘菜单手动触发；离线回归测试不会自动启动本线程。
        """
        if not force and not bool(self.config.get("prefetch_enabled", True)):
            return
        self.stop_prefetch()
        worker = PrefetchWorker(
            self.config, self,
            delay_s=0 if force else int(self.config.get("prefetch_delay") or 0))
        worker.progress.connect(self._on_prefetch_progress)
        worker.finished_all.connect(self._on_prefetch_done)
        worker.finished.connect(worker.deleteLater)
        self._prefetch = worker
        self.status.set_note(
            f"缓存 0/{worker.queue_size()}",
            "正在把主流品种 K 线历史写入本地，完成后浏览无需等待网络")
        worker.start()

    def stop_prefetch(self):
        worker = self._prefetch
        self._prefetch = None
        if worker is None:
            return
        try:
            worker.progress.disconnect(self._on_prefetch_progress)
            worker.finished_all.disconnect(self._on_prefetch_done)
        except (RuntimeError, TypeError):
            pass
        clean = worker.stop()
        if not clean:
            # wait 超时仍在运行：脱离对象树并保活，禁止随父对象析构销毁
            # 用 getattr 兼容测试里的 duck-typed worker（无 setParent）。
            setter = getattr(worker, "setParent", None)
            if callable(setter):
                try:
                    setter(None)
                except (RuntimeError, TypeError):
                    pass
            if worker not in _ORPHAN_THREADS:
                _ORPHAN_THREADS.append(worker)

    def _on_prefetch_progress(self, text: str):
        # 状态栏空间有限：只显示简短进度，完整信息放 tooltip
        head = text.split(" · ", 1)[0]
        self.status.set_note(head.replace("预缓存", "缓存"), text)

    def _on_prefetch_done(self, ok: int, total: int):
        self.status.set_note(
            f"缓存完成 {ok}/{total}",
            f"已把 {ok} 个品种/周期的历史 K 线写入本地 SQLite；"
            f"共 {total} 项，其余为已有本地数据或网络跳过")
        QTimer.singleShot(8000, lambda: self.status.set_note(""))

    def start_minimized(self):
        """开机自启：直接隐藏到右下角托盘，常驻价格条仍然可见。"""
        self.hide()
        self.tray.show()
        self._sync_badge()
        self.tray.showMessage(
            "Free Chart", "已启动并隐藏到托盘，单击图标可显示窗口",
            QSystemTrayIcon.Information, 3500)

    # ================= 交互动作 =================
    def toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.activateWindow()
            self.scheduler.start()   # 幂等：托盘恢复时确保刷新在运行

    def hide_to_tray(self):
        self.hide()

    def toggle_on_top(self):
        self.config.set("always_on_top",
                        not self.config.get("always_on_top"))
        self.act_top.setChecked(bool(self.config.get("always_on_top")))
        self.config.save()
        self.apply_window_settings()

    # ================= 外观：主题 / 图标 / 字号 / 看板娘 =================
    def apply_theme(self, name: str):
        """即时换肤：广播新调色板常量 + 把已生成的 QSS 整体换色。

        不重建窗口，所以换主题不会丢当前页签、搜索框、图表缩放位置。
        """
        name, old, new = set_theme(name, QApplication.instance())
        self._theme_name = name
        self.config.set("theme", name)
        self.config.save()
        recolor_styles(self, old, new)
        if self.mascot is not None:
            recolor_styles(self.mascot, old, new)
        if hasattr(self, "price_badge"):
            recolor_styles(self.price_badge, old, new)
        # 依赖调色板且需要重新计算的样式（不能只靠换色）
        self.centralWidget().setStyleSheet(
            f"#centralRoot {{ background:{C_BG_BASE}; }}")
        self.tabs.set_active(self._current_market())
        self.sub_tabs.set_active(self._sub_tabs.get(self._current_market(),
                                                    "watch"))
        self.chart_view.setStyleSheet(f"background:{C_BG_BASE};")
        self.chart_view.apply_appearance()
        if hasattr(self, "price_badge"):
            self.price_badge.apply_config()
        # 不调用 _relayout_all：那会在换肤时把四个市场的「全部」页一次性
        # 建满（最多上千行）。已有控件已被 recolor_styles 整体换色。
        self.tabs.update()
        self.sub_tabs.update()
        self.stack.update()
        self.update()
        self._mascot_say("theme")

    def apply_app_icon(self, key: str, sync_shortcut: bool = True):
        """切换桌面 / 托盘图标方案，并让快捷方式跟着换。"""
        key = set_app_icon_key(key)
        self.config.set("app_icon", key)
        self.config.save()
        icon = app_icon()
        self.setWindowIcon(icon)
        if hasattr(self, "tray"):
            self.tray.setIcon(icon)
            self._update_tray_price()
        if sync_shortcut:
            import threading

            def _run():
                try:
                    from core.shortcut import sync_shortcuts
                    sync_shortcuts(force=True)
                except Exception:
                    pass
            threading.Thread(target=_run, daemon=True).start()

    def apply_appearance(self):
        """字号 / 货币单位 / 实时刷新间隔：统一从当前配置重新应用。"""
        units.set_enabled(bool(self.config.get("show_currency", True)))
        self.chart_view.apply_appearance()
        self.live.set_interval(
            int(self.config.get("live_interval_ms") or 900))
        self.live.set_enabled(bool(self.config.get("live_feed", True)))
        self.chart_view.chart.set_live_speed(
            int(self.config.get("live_interval_ms") or 900))
        # 列表行、任务栏价格条、托盘都用最新缓存重绘一次
        for symbol, row in self.rows.items():
            t = self._last_tickers.get(symbol)
            self._paint_row(symbol, row)
        for key in self.pages:
            if self._sub_tabs.get(key) == "all":
                self._paint_page_rows(key)
        self._update_tray_price()
        self.chart_view.update()

    def apply_mascot(self):
        """看板娘配置变更后立即生效（位置 / 尺寸 / 图片 / 显隐）。"""
        try:
            if self.mascot is None:
                self.mascot = MascotWindow(self.config)
            self.mascot.apply_config()
        except Exception:
            self.mascot = None

    def open_settings(self):
        """切换进设置页（独立界面，不再弹模态窗口）。"""
        if self.stack.currentWidget() is self.settings_page:
            return                       # 已经在设置页，重复点击不重置回退目标
        self._mascot_say("settings")
        self.info_panel.hide_popup()
        self._settings_return = self.stack.currentWidget()
        if self._settings_return is not self.chart_view:
            for widget in self._list_controls:
                widget.hide()
            self.status.hide()
        self.stack.setCurrentWidget(self.settings_page)
        self.bottom_nav.set_active("settings")
        self.title_bar.set_page("设置", True)

    def _close_settings_page(self):
        """取消 / 保存后回到进来之前的页面（列表页或图表页）。"""
        target = self._settings_return
        self._settings_return = None
        if target is None or target is self.settings_page:
            target = self.pages[self._current_market()]["scroll"]
        if target is self.chart_view:
            self.stack.setCurrentWidget(self.chart_view)
            self._enter_chart_layout()
            self.bottom_nav.set_active("chart")
            self.title_bar.set_page("图表", True)
        else:
            self._leave_chart_layout()
            self.stack.setCurrentWidget(target)
            self.bottom_nav.set_active("list")
            self.title_bar.set_page("行情", False)
        self._sync_mascot_visibility()

    def _apply_settings(self, settings: dict):
        """设置页点「保存」：把整份配置应用回程序。"""
        prefetch_before = (bool(self.config.get("prefetch_enabled", True)),
                           int(self.config.get("prefetch_top") or 0))
        theme_before = self._theme_name
        icon_before = self.config.get("app_icon")
        for key, value in settings.items():
            self.config.set(key, value)
        self.config.save()
        self.scheduler.set_interval(settings["interval"])
        if settings["source"]:
            self.market.set_source(settings["source"])
        set_autostart(bool(settings["autostart"]))
        self.apply_window_settings()
        # 换肤要放在其它样式应用之前，保证后续控件用新配色生成
        if settings.get("theme") and settings["theme"] != theme_before:
            self.apply_theme(settings["theme"])
        if settings.get("app_icon") and settings["app_icon"] != icon_before:
            self.apply_app_icon(settings["app_icon"])
        self.apply_appearance()
        self.apply_mascot()
        self.chart_view.sync_indicators()
        self.settings_page.setStyleSheet(popup_qss())
        self.info_panel.refresh_style()
        self.set_symbols(settings["symbols"])
        self.chart_view.sync_smart_buttons()
        self.price_badge.apply_config()
        self._update_tray_price()
        self._rebuild_tray_symbol_menu()
        self._refresh_symbols()
        prefetch_after = (bool(self.config.get("prefetch_enabled", True)),
                          int(self.config.get("prefetch_top") or 0))
        if prefetch_after != prefetch_before:
            if prefetch_after[0]:
                self.start_prefetch()
            else:
                self.stop_prefetch()
                self.status.set_note("")
        self._close_settings_page()

    def _shutdown_search_workers(self):
        """退出时收尾搜索 / 合约 / 链上三类短命 QThread。

        这些线程 parent 都是本窗口，退出瞬间若在途，会被 Qt 对象树销毁
        而触发 "Destroyed while thread is still running" 崩溃。统一走
        中断 -> 等待 -> 保活范式（保活列表见 core.thread_cleanup）。
        """
        for attr in ("_search_worker", "_contract_worker", "_onchain_worker"):
            worker = getattr(self, attr, None)
            if worker is None:
                continue
            from core.thread_cleanup import safe_stop_thread
            safe_stop_thread(worker, wait_ms=1500)
            setattr(self, attr, None)

    def quit_app(self):
        self._force_quit = True
        # 复用的详情抽屉是顶层窗口，退出前必须逐个收掉，否则 Qt 卸载时
        # 会留下悬空窗口（offscreen 回归里表现为 127/139 异常退出）。
        for dlg in list(getattr(self, "_detail_cache", {}).values()):
            try:
                dlg.close()
                dlg.deleteLater()
            except RuntimeError:
                pass
        self._detail_cache.clear()
        self.stop_prefetch()
        if hasattr(self, "live"):
            self.live.shutdown()
        if getattr(self, "mascot", None) is not None:
            try:
                self.mascot.hide()
            except RuntimeError:
                pass
        try:
            self.chart_view.shutdown_threads()
        except Exception:
            pass
        self._shutdown_search_workers()
        stock_logo.stop()
        self.tray.hide()
        if hasattr(self, "price_badge"):
            self.price_badge._save_pos()
            self.price_badge.hide()
        self.close()
        QApplication.instance().quit()

    # ================= 刷新回调 =================
    # ============ 链上合约品种：无 K 线也能收藏 / 看真实报价 ============
    def _paint_row(self, symbol, row):
        """链上合约品种不套交易所模板：没有 H/L/V 和 24h 涨跌就显示「—」。"""
        if onchain.is_onchain(symbol):
            row.update_onchain(self._onchain_quotes.get(symbol))
            return
        t = self._last_tickers.get(symbol)
        row.update_ticker(t) if t else row.mark_stale()

    def _refresh_onchain(self):
        """后台低频刷新链上报价。在途请求未结束时不重复触发，避免竞争。"""
        syms = [s for s in self.rows if onchain.is_onchain(s)]
        if not syms:
            return
        w = getattr(self, "_onchain_worker", None)
        if w is not None:
            try:
                if w.isRunning():
                    return
            except RuntimeError:
                pass
        worker = OnchainWorker(syms, self)
        worker.ready.connect(self._on_onchain_quote)
        worker.finished.connect(worker.deleteLater)
        self._onchain_worker = worker
        worker.start()

    def _on_onchain_quote(self, quotes: dict):
        """链上真实报价回到主线程：同步行、价格条、图表页与详情抽屉。"""
        now = time.time()
        for sym, raw in (quotes or {}).items():
            q = dict(raw or {})
            q["ts"] = q.get("ts") or now
            # 每次取到真实链上价就记一个采样点：图表页据此画真实走势，
            # 不伪造 OHLC，也不因为「没有 K 线」就留一张空画布。
            if q.get("price"):
                onchain_history.record(sym, q["price"], q["ts"])
            q["series"] = onchain_history.series(sym)
            self._onchain_quotes[sym] = q
            t = onchain.as_ticker(sym, q)
            if t is not None:
                self._last_tickers[sym] = t
                self._current_batch.add(sym)
                self._tray_ticker_cache[sym] = (q["ts"], t)
            row = self.rows.get(sym)
            if row is not None:
                try:
                    row.update_onchain(q)
                except RuntimeError:
                    pass
            for group in self.all_rows.values():
                r = group.get(sym)
                if r is not None and r is not row:
                    try:
                        r.update_onchain(q)
                    except RuntimeError:
                        pass
        view = getattr(self, "chart_view", None)
        if view is not None and onchain.is_onchain(getattr(view, "_symbol", "")):
            q = self._onchain_quotes.get(view._symbol)
            if q:
                view.update_onchain(q)
        self._update_tray_price()
        self._sync_badge()
        for dlg in list(getattr(self, "_detail_cache", {}).values()):
            try:
                if dlg.isVisible() and onchain.is_onchain(dlg.symbol):
                    dlg.set_ticker(self._last_tickers.get(dlg.symbol))
            except (RuntimeError, AttributeError):
                pass

    def _on_fetched(self, tickers, source, ts):
        # 合并而非整体替换：分页请求一次只覆盖可见窗口，若整体替换会把
        # 已加载的其它页行情清掉，回滚时又闪成 -- WAIT。
        self._last_tickers.update(tickers)
        self._current_batch = set(tickers)
        self._cache_tray_ticker(tickers)
        self._last_meta = (source, ts, True)
        self._retry_left = MAX_RETRY
        for symbol, row in self.rows.items():
            t = self._last_tickers.get(symbol)
            self._paint_row(symbol, row)
        cur = self._current_market()
        self._loading_pages.discard(cur)
        if self._sub_tabs.get(cur) == "all":
            self._paint_page_rows(cur)
        self._update_load_progress(cur)
        for dlg in list(getattr(self, "_detail_cache", {}).values()):
            try:
                if dlg.isVisible():
                    dlg.set_ticker(self._last_tickers.get(dlg.symbol))
            except RuntimeError:
                pass
        self.status.set_status(source, ts, True)
        if tickers.get(self.chart_view._symbol) is not None:
            self.chart_view.update_ticker(
                tickers[self.chart_view._symbol])
        self._update_tray_price()
        self._sync_info_panel()
        self._mascot_market()
        if (self.combo_sort.currentData() or "custom") != "custom":
            self._auto_resort(cur)

    def _auto_resort(self, key: str):
        """实时刷新引起的自动重排：限频，且不动超长列表。

        500 行的美股「全部」页每 5 秒整体搬一次，会让鼠标下的行不断跳位
        （提示框闪烁的老问题）。这里 3 秒内最多排一次，且超过 300 行的
        页面交给用户手动点排序，实时刷新只更新数值不搬行。
        """
        now = time.time()
        if now - getattr(self, "_resort_at", 0.0) < 3.0:
            return
        if self._sub_tabs.get(key) == "all" and \
                len(self.all_rows.get(key) or {}) > 300:
            return
        self._resort_at = now
        self._relayout_page(key)

    def _on_failed(self, msg):
        # 只给自选中确实没有缓存的行打上失效标记，弹窗一律不创建。
        for symbol, row in self.rows.items():
            if symbol not in self._last_tickers:
                row.mark_stale()
        ts = self._last_meta[1] or 0
        self._last_meta = (self._last_meta[0], ts, False)
        self._loading_pages.clear()
        self.status.set_status("网络错误 - 显示缓存", ts, False)
        tip = (msg or "")[:60]
        self.status.set_progress(
            f"加载失败{('：' + tip) if tip else ''} · 可重试 "
            f"{max(0, self._retry_left)} 次",
            can_retry=self._retry_left > 0)
        self._update_window_title()

    def _on_retry(self):
        """状态栏「重试」：有限次数，失败不弹窗、不无限重试。"""
        if self._retry_left <= 0:
            self.status.set_progress("重试次数已用完，请稍后再试", False)
            return
        self._retry_left -= 1
        self.status.set_progress(f"重试中…（剩余 {self._retry_left} 次）")
        self._refresh_symbols()
        self.scheduler.refresh_now()

    # ---- 阶段 2：滚动分页 / 轻量加载状态 -------------------------------
    def _on_list_scroll(self, key: str, value: int):
        """滚动接近底部时追加下一页（不是重新请求整页）。"""
        if key != self._current_market() or \
                self._sub_tabs.get(key) != "all":
            return
        bar = self.pages[key]["scroll"].verticalScrollBar()
        if bar.maximum() <= 0:
            return
        # 距离底部不足两屏：提前加载，滚动不会撞到空白
        if value < max(0, bar.maximum() - bar.pageStep() * 2):
            return
        self._load_more_page(key)

    def _load_more_page(self, key: str):
        total = len(self._all_order.get(key) or all_of(key))
        cur = self._page_limit.get(key, PAGE_SIZE)
        now = time.time()
        # 重建布局本身也会触发滚动条信号：限频，避免一次滚动连跳好几页
        if cur >= total or now - getattr(self, "_last_page_at", 0.0) < 0.4:
            return
        self._last_page_at = now
        self._page_limit[key] = min(total, cur + PAGE_SIZE)
        self._loading_pages.add(key)
        # 顺序未变时只把新增行追加到末尾，不重建已有 60/120 行
        self._relayout_page(key)
        self._paint_page_rows(key)
        self._update_load_progress(key)
        self._refresh_symbols()
        self.scheduler.refresh_now()

        def settle():
            self._loading_pages.discard(key)
            if self._current_market() == key:
                self._update_load_progress(key)

        # 离线 / 网络失败时不会有 fetched 回调，600ms 后自行收尾，
        # 保证状态栏不卡在「正在加载」，也不会反复排队请求。
        QTimer.singleShot(600, settle)

    def _update_load_progress(self, key: str):
        """状态栏一行文字说明当前加载进度，绝不弹模态窗口。"""
        if self._sub_tabs.get(key) != "all":
            self.status.set_progress("")
            return
        total = len(self._all_order.get(key) or all_of(key))
        shown = min(self._page_limit.get(key, PAGE_SIZE), total)
        if key in self._filling_all:
            self.status.set_progress(
                f"列表准备中 {len(self.all_rows[key])}/{total} · "
                "首屏已可浏览")
        elif key in self._loading_pages:
            self.status.set_progress(f"正在加载第 {shown} 行附近的行情…")
        elif shown < total:
            self.status.set_progress(f"已显示 {shown}/{total} · 滚动加载更多")
        else:
            self.status.set_progress(f"已显示全部 {total} 个品种")

    # ================= 关闭行为 =================
    def closeEvent(self, event):
        # 严格区分「隐藏到托盘」与「真正退出」：
        # 只有真正退出才停刷新调度器。旧实现无条件 stop()，导致 Alt+F4
        # 隐藏到托盘后行情永久停止刷新（RefreshScheduler 又无 start()）。
        if self._list_geometry is not None:
            x, y, w, h = self._list_geometry
            self._list_geometry = None
            self.move(x, y)
            self._resize_for_restore(w, h)
        self.save_geometry()
        if self._force_quit:
            self.scheduler.stop()
            event.accept()
        else:
            event.ignore()
            self.hide()              # 隐藏到托盘：调度器继续运行
