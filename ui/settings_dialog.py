# -*- coding: utf-8 -*-
"""设置页（独立界面，不再用弹窗）：外观 / 刷新 / 窗口 / 数据源 / 托盘 /
图表指标 / 自选列表。

v22 起它是主窗口 QStackedWidget 里的一页，由底部导航「设置」切换进去，
保存 / 取消都回到原来的行情页。控件与分组沿用手机式卡片布局，
外观统一走 ui.popup 的弹窗规格，保证与详情抽屉、悬停资料卡一致。
"""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout,
                               QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QSlider, QSpinBox, QVBoxLayout,
                               QWidget)

from core.autostart import is_enabled as _autostart_enabled
from core.config import DEFAULT_SYMBOLS
from data.universe import all_of
from ui.icons import app_icon_keys, app_icon_pixmap
from ui.mascot import BUBBLE_STYLES, default_mascot_path
from ui.popup import popup_qss
from ui.theme import THEME_LABELS, theme_names

EXTRA_SYMBOLS = [
    "LTC", "LINK", "AVAX", "DOT", "UNI", "ADA", "TRX", "SUI",
    "PEPE", "WIF", "OP", "APT", "INJ", "SEI", "TIA", "JUP",
]


class SettingsPage(QWidget):
    """独立设置界面（主窗口内的一页，不是模态弹窗）。"""

    saved = Signal(dict)          # 点「保存」：把设置字典交给主窗口应用
    cancelled = Signal()          # 点「取消 / ✕」：回到原页面

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.config = main_window.config
        self.setObjectName("settingsRoot")
        self.setStyleSheet(popup_qss())
        # 手机式设置页：整屏 sheet + 竖向滚动 + 底栏固定按钮。
        # 宽度跟随主窗口（手机端就是全宽），高度留一点上下边距露出背景。
        owner_w, owner_h = 480, 860
        try:                       # 测试里的桩窗口可能没有尺寸接口
            owner_w = int(main_window.width())
            owner_h = int(main_window.height())
        except (AttributeError, TypeError):
            pass
        self.setMinimumSize(320, 360)
        self.resize(min(560, max(360, owner_w - 16)),
                    max(560, owner_h - 48))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 统一标题栏 ----
        head = QFrame()
        head.setObjectName("popupHead")
        head.setFixedHeight(44)
        hh = QHBoxLayout(head)
        hh.setContentsMargins(14, 4, 6, 4)
        hh.setSpacing(8)
        title = QLabel("设置")
        title.setObjectName("popupTitle")
        hh.addWidget(title)
        hh.addStretch(1)
        # 阶段 5/6：明确的「← 返回」文字按钮，44px 高、适合手指点按。
        # 桌面端标题栏右上角的小叉已取消返回入口，这里必须一眼可见。
        self.btn_back = QPushButton("← 返回")
        self.btn_back.setObjectName("popupClose")
        self.btn_back.setFixedHeight(44)
        self.btn_back.setMinimumWidth(92)
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.setFocusPolicy(Qt.NoFocus)
        self.btn_back.setToolTip("返回上一页（不保存修改）")
        self.btn_back.clicked.connect(self.cancelled.emit)
        hh.addWidget(self.btn_back)
        root.addWidget(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        body = QWidget()
        body.setObjectName("settingsBody")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(12, 12, 12, 12)
        body_lay.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # 底部固定操作栏（滚动时始终可见，拇指可及）
        footer = QFrame()
        footer.setObjectName("settingsFooter")
        footer_lay = QHBoxLayout(footer)
        footer_lay.setContentsMargins(12, 8, 12, 10)
        footer_lay.setSpacing(10)
        root.addWidget(footer)

        form = self._card(body_lay, "行情与窗口")[1]

        # ---- 刷新间隔 ----
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(5, 300)
        self.spin_interval.setSuffix(" 秒")
        self.spin_interval.setValue(int(self.config.get("interval")))
        self.spin_interval.setToolTip("每隔多少秒刷新一次行情（5-300）")
        form.addRow("刷新间隔", self.spin_interval)

        # ---- 数据源 ----
        self.combo_source = QComboBox()
        self.combo_source.addItem("自动（失败时切换）", "")
        for name in self.main_window.market.list_sources():
            self.combo_source.addItem(name, name)
        current = self.config.get("source") or ""
        idx = self.combo_source.findData(current)
        self.combo_source.setCurrentIndex(max(0, idx))
        form.addRow("行情数据源", self.combo_source)

        # ---- 透明度 ----
        opacity_row = QHBoxLayout()
        self.slider_opacity = QSlider(Qt.Horizontal)
        self.slider_opacity.setRange(30, 100)
        self.slider_opacity.setValue(int(self.config.get("opacity")))
        self.lbl_opacity = QLabel(f"{self.config.get('opacity')}%")
        self.slider_opacity.valueChanged.connect(
            lambda v: self.lbl_opacity.setText(f"{v}%"))
        opacity_row.addWidget(self.slider_opacity)
        opacity_row.addWidget(self.lbl_opacity)
        form.addRow("窗口透明度", opacity_row)

        # ---- 开关 ----
        self.chk_top = QCheckBox("窗口总在最前（置顶）")
        self.chk_top.setChecked(bool(self.config.get("always_on_top")))
        form.addRow("", self.chk_top)

        self.chk_frameless = QCheckBox("无边框模式（拖动标题栏移动窗口）")
        self.chk_frameless.setChecked(bool(self.config.get("frameless")))
        form.addRow("", self.chk_frameless)

        self.chk_autostart = QCheckBox("开机自动启动（当前用户，无需管理员）")
        self.chk_autostart.setChecked(_autostart_enabled())
        form.addRow("", self.chk_autostart)

        self.chk_start_tray = QCheckBox("开机启动后自动隐藏到右下角托盘")
        self.chk_start_tray.setChecked(bool(self.config.get("start_in_tray")))
        self.chk_start_tray.setToolTip(
            "仅影响开机自启；手动双击程序仍会正常显示窗口")
        form.addRow("", self.chk_start_tray)

        self.chk_tray_price = QCheckBox("托盘图标显示自定义品种价格")
        self.chk_tray_price.setChecked(
            bool(self.config.get("tray_show_price")))
        form.addRow("", self.chk_tray_price)

        self.chk_price_badge = QCheckBox(
            "任务栏右侧常驻实时价格（贴合任务栏，非悬浮窗）")
        self.chk_price_badge.setChecked(bool(self.config.get("price_badge")))
        self.chk_price_badge.setToolTip(
            "单行胶囊，高 28px，固定在右侧通知区左边；主窗口隐藏时依然可见，"
            "右键可换品种 / 切换信息密度")
        form.addRow("", self.chk_price_badge)

        self.combo_badge_style = QComboBox()
        for key, label in (("full", "完整：代码 + 价格 + 涨跌幅"),
                           ("slim", "紧凑：价格 + 涨跌幅"),
                           ("mini", "极简：只显示价格")):
            self.combo_badge_style.addItem(label, key)
        cur = str(self.config.get("price_badge_style") or "full")
        idx = self.combo_badge_style.findData(cur)
        self.combo_badge_style.setCurrentIndex(max(0, idx))
        self.combo_badge_style.setToolTip(
            "宽度按内容自适应；嫌占地方就选紧凑或极简（右键价格条也能改）")
        form.addRow("任务栏价格条", self.combo_badge_style)

        self.chk_prefetch = QCheckBox(
            "后台预缓存主流品种 K 线历史（浏览免等待网络）")
        self.chk_prefetch.setChecked(
            bool(self.config.get("prefetch_enabled", True)))
        self.chk_prefetch.setToolTip(
            "启动后延迟若干秒，按节流顺序把自选 + 四市场主流品种的"
            "默认周期与日线历史写入本地 SQLite；已有数据不会重复请求")
        form.addRow("", self.chk_prefetch)

        self.spin_prefetch_top = QSpinBox()
        self.spin_prefetch_top.setRange(0, 300)
        self.spin_prefetch_top.setSingleStep(10)
        self.spin_prefetch_top.setSuffix(" 个/市场")
        self.spin_prefetch_top.setValue(
            int(self.config.get("prefetch_top") or 0))
        self.spin_prefetch_top.setToolTip(
            "每个市场预取排名靠前的主流品种数量；0 表示只预取自选")
        form.addRow("预缓存范围", self.spin_prefetch_top)

        # ---- 托盘显示品种 ----
        self.combo_tray = QComboBox()
        self.combo_tray.setEditable(True)
        self.combo_tray.setToolTip("可输入任意代码，如 BTC / SH:600519 / US:NVDA")
        current_tray = self.config.get("tray_symbol") or "BTC"
        candidates = list(dict.fromkeys(
            list(self.config.get("symbols") or DEFAULT_SYMBOLS)
            + all_of("crypto")[:20] + [current_tray]))
        for s in candidates:
            self.combo_tray.addItem(s)
        self.combo_tray.setCurrentText(current_tray)
        form.addRow("托盘显示品种", self.combo_tray)

        # ---- 图表默认指标 ----
        indicator_box = QWidget()
        indicator_row = QHBoxLayout(indicator_box)
        indicator_row.setContentsMargins(0, 0, 0, 0)
        indicator_row.setSpacing(14)
        self.chk_indicators = {}
        for label, key in (("MA 均线", "show_ma"),
                           ("EMA 均线", "show_ema"),
                           ("BOLL 布林线", "show_boll"),
                           ("VOL 成交量", "show_vol"),
                           ("MACD", "show_macd")):
            chk = QCheckBox(label)
            chk.setChecked(bool(self.config.get(key)))
            indicator_row.addWidget(chk)
            self.chk_indicators[key] = chk
        indicator_row.addStretch(1)
        form.addRow("图表指标", indicator_box)
        note = QLabel("MA / EMA 的天数、启停与按周期分别设置，"
                      "在图表页工具条的「⚙ 参数」中调整；"
                      "BOLL、MACD 参数也在同一处。")
        note.setObjectName("popupNote")
        note.setWordWrap(True)
        form.addRow("", note)

        # ================= 外观 =================
        look = self._card(
            body_lay, "外观 · 主题 / 图标 / 字号 / 看板娘")[1]

        # 全局主题
        self.combo_theme = QComboBox()
        for key in theme_names():
            self.combo_theme.addItem(THEME_LABELS.get(key, key), key)
        cur_theme = str(self.config.get("theme") or "binance")
        idx = self.combo_theme.findData(cur_theme)
        self.combo_theme.setCurrentIndex(max(0, idx))
        self.combo_theme.setToolTip(
            "币安深色 / 午夜蓝 / OLED 纯黑 / 明亮浅色 / 赛博霓虹 / 护眼米黄，"
            "保存后立即生效，不用重启")
        look.addRow("全局主题", self.combo_theme)

        # 应用图标（桌面 + 托盘）
        self.combo_icon = QComboBox()
        self.combo_icon.setIconSize(QSize(22, 22))
        for key, label in app_icon_keys():
            self.combo_icon.addItem(QIcon(app_icon_pixmap(48, key)),
                                    label, key)
        cur_icon = str(self.config.get("app_icon") or "classic")
        idx = self.combo_icon.findData(cur_icon)
        self.combo_icon.setCurrentIndex(max(0, idx))
        self.combo_icon.setToolTip(
            "桌面 / 开始菜单 / 托盘图标；保存后自动重写快捷方式图标")
        look.addRow("应用图标", self.combo_icon)

        # 托盘图标：默认与程序图标一致
        self.combo_tray_icon = QComboBox()
        self.combo_tray_icon.addItem("跟随程序图标（推荐）", "app")
        self.combo_tray_icon.addItem("显示实时价格方块", "price")
        cur_tray = str(self.config.get("tray_icon_style") or "app")
        tidx = self.combo_tray_icon.findData(cur_tray)
        self.combo_tray_icon.setCurrentIndex(max(0, tidx))
        self.combo_tray_icon.setToolTip(
            "跟随程序图标：托盘图标与桌面 / 任务栏同一套，右下角红绿点显示涨跌；"
            "价格方块：托盘图标直接画价格数字")
        look.addRow("托盘图标", self.combo_tray_icon)

        # 图表字号
        self.spin_font = QSpinBox()
        self.spin_font.setRange(100, 180)
        self.spin_font.setSingleStep(5)
        self.spin_font.setSuffix(" %")
        self.spin_font.setValue(int(self.config.get("chart_font_scale") or 120))
        self.spin_font.setToolTip(
            "图表右侧价格轴、指标数值、标注文字的字号倍率")
        look.addRow("图表字号", self.spin_font)

        self.chk_currency = QCheckBox("价格前显示货币单位（$ / ¥ / HK$）")
        self.chk_currency.setChecked(bool(self.config.get("show_currency", True)))
        self.chk_currency.setToolTip(
            "加密货币与美股 $、A股 ¥、港股 HK$；列表、图表、任务栏价格条同步")
        look.addRow("", self.chk_currency)

        # 秒级实时价
        self.chk_live = QCheckBox("打开图表时秒级刷新最新价（K 线连续伸缩）")
        self.chk_live.setChecked(bool(self.config.get("live_feed", True)))
        self.chk_live.setToolTip(
            "只对当前查看的品种做轻量单条请求，不影响列表行情刷新")
        look.addRow("", self.chk_live)

        self.spin_live = QSpinBox()
        self.spin_live.setRange(400, 3000)
        self.spin_live.setSingleStep(100)
        self.spin_live.setSuffix(" 毫秒")
        self.spin_live.setValue(int(self.config.get("live_interval_ms") or 900))
        self.spin_live.setToolTip("越小越灵敏，但请求更频繁；建议 600-1200")
        look.addRow("实时刷新间隔", self.spin_live)

        # ---- 看板娘 ----
        self.chk_mascot = QCheckBox("显示看板娘（可自定义图片）")
        self.chk_mascot.setChecked(bool(self.config.get("mascot_enabled")))
        self.chk_mascot.setToolTip(
            "左上角悬浮立绘；右键可换图 / 调大小 / 透明度 / 点击穿透")
        look.addRow("", self.chk_mascot)

        self.chk_mascot_speech = QCheckBox(
            "互动气泡：按行情涨跌和你的操作说话")
        self.chk_mascot_speech.setChecked(
            bool(self.config.get("mascot_speech", True)))
        self.chk_mascot_speech.setToolTip(
            "涨跌超过 2% 会提醒；添加自选 / 看图表 / 换主题也会吐槽两句。"
            "点一下看板娘可以让她说话")
        look.addRow("", self.chk_mascot_speech)

        # 气泡风格：二次元可爱系配色，点保存即时生效
        self.combo_bubble_style = QComboBox()
        for key, pal in BUBBLE_STYLES.items():
            self.combo_bubble_style.addItem(pal["label"], key)
        cur_style = str(self.config.get("mascot_bubble_style") or "candy")
        sidx = self.combo_bubble_style.findData(cur_style)
        self.combo_bubble_style.setCurrentIndex(max(0, sidx))
        self.combo_bubble_style.setToolTip(
            "看板娘说话的气泡样式：糖果 / 樱花 / 薄荷 / 赛博 / 经典")
        look.addRow("气泡风格", self.combo_bubble_style)

        mascot_row = QHBoxLayout()
        self.edit_mascot = QLineEdit(str(self.config.get("mascot_image") or ""))
        self.edit_mascot.setPlaceholderText(
            f"留空使用内置形象（{default_mascot_path()}）")
        btn_pick = QPushButton("浏览…")
        btn_pick.setFixedWidth(64)
        btn_pick.clicked.connect(self._pick_mascot)
        btn_reset = QPushButton("恢复默认")
        btn_reset.setFixedWidth(78)
        btn_reset.clicked.connect(lambda: self.edit_mascot.clear())
        mascot_row.addWidget(self.edit_mascot, 1)
        mascot_row.addWidget(btn_pick)
        mascot_row.addWidget(btn_reset)
        look.addRow("看板娘图片", mascot_row)

        self.spin_mascot_scale = QSpinBox()
        self.spin_mascot_scale.setRange(50, 200)
        self.spin_mascot_scale.setSingleStep(10)
        self.spin_mascot_scale.setSuffix(" %")
        self.spin_mascot_scale.setValue(
            int(self.config.get("mascot_scale") or 100))
        look.addRow("看板娘大小", self.spin_mascot_scale)

        self.spin_mascot_opacity = QSpinBox()
        self.spin_mascot_opacity.setRange(20, 100)
        self.spin_mascot_opacity.setSingleStep(5)
        self.spin_mascot_opacity.setSuffix(" %")
        self.spin_mascot_opacity.setValue(
            int(self.config.get("mascot_opacity") or 100))
        look.addRow("看板娘不透明度", self.spin_mascot_opacity)

        mascot_flags = QWidget()
        flags_row = QHBoxLayout(mascot_flags)
        flags_row.setContentsMargins(0, 0, 0, 0)
        flags_row.setSpacing(14)
        self.chk_mascot_top = QCheckBox("总在最前")
        self.chk_mascot_top.setChecked(bool(self.config.get("mascot_on_top", True)))
        self.chk_mascot_through = QCheckBox("点击穿透")
        self.chk_mascot_through.setChecked(
            bool(self.config.get("mascot_click_through")))
        flags_row.addWidget(self.chk_mascot_top)
        flags_row.addWidget(self.chk_mascot_through)
        flags_row.addStretch(1)
        look.addRow("", mascot_flags)

        # 自选列表已按用户要求从设置页移除（阶段 8）：
        # 自选的增删 / 排序统一在行情页与搜索页完成，设置页不再重复一份。

        btn_cancel = QPushButton("取消")
        btn_cancel.setMinimumHeight(44)
        btn_cancel.setMinimumWidth(104)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.cancelled.emit)
        btn_save = QPushButton("保存")
        btn_save.setObjectName("popupPrimary")
        btn_save.setMinimumHeight(40)
        btn_save.setMinimumWidth(104)
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.clicked.connect(
            lambda: self.saved.emit(self.get_settings()))
        footer_lay.addStretch(1)
        footer_lay.addWidget(btn_cancel)
        footer_lay.addWidget(btn_save)

    # ---- 卡片容器 ----
    def _card(self, parent_lay, title: str = ""):
        """设置页分组卡片：圆角面板 + 小标题，返回 (卡片布局, 表单布局)。

        手机式设置页的骨架——每一组配置是一张卡，整页竖排滚动，
        不再把所有选项平铺成一张长表单。
        """
        card = QFrame()
        card.setObjectName("settingsCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(14, 12, 14, 13)
        box.setSpacing(10)
        if title:
            lbl = QLabel(title)
            lbl.setObjectName("settingsCardTitle")
            box.addWidget(lbl)
        form = QFormLayout()
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        box.addLayout(form)
        parent_lay.addWidget(card)
        return box, form

    # ---- 内部操作 ----
    def _pick_mascot(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择看板娘图片", "",
            "图片 (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
        if path:
            self.edit_mascot.setText(path)

    # ---- 保存 ----
    def get_settings(self):
        result = {
            "interval": self.spin_interval.value(),
            "source": self.combo_source.currentData() or "",
            "opacity": self.slider_opacity.value(),
            "always_on_top": self.chk_top.isChecked(),
            "frameless": self.chk_frameless.isChecked(),
            "autostart": self.chk_autostart.isChecked(),
            "start_in_tray": self.chk_start_tray.isChecked(),
            "tray_show_price": self.chk_tray_price.isChecked(),
            "price_badge": self.chk_price_badge.isChecked(),
            "price_badge_style": self.combo_badge_style.currentData()
                                 or "full",
            "prefetch_enabled": self.chk_prefetch.isChecked(),
            "prefetch_top": self.spin_prefetch_top.value(),
            "tray_symbol": self.combo_tray.currentText().strip().upper()
                           or "BTC",
            # symbols 不再由设置页管理：保存时不动配置里的自选列表
            # ---- 外观 / 实时 / 看板娘 ----
            "theme": self.combo_theme.currentData() or "binance",
            "app_icon": self.combo_icon.currentData() or "classic",
            "tray_icon_style": self.combo_tray_icon.currentData() or "app",
            "chart_font_scale": self.spin_font.value(),
            "show_currency": self.chk_currency.isChecked(),
            "live_feed": self.chk_live.isChecked(),
            "live_interval_ms": self.spin_live.value(),
            "mascot_enabled": self.chk_mascot.isChecked(),
            "mascot_image": self.edit_mascot.text().strip(),
            "mascot_scale": self.spin_mascot_scale.value(),
            "mascot_opacity": self.spin_mascot_opacity.value(),
            "mascot_on_top": self.chk_mascot_top.isChecked(),
            "mascot_click_through": self.chk_mascot_through.isChecked(),
            "mascot_speech": self.chk_mascot_speech.isChecked(),
            "mascot_bubble_style": self.combo_bubble_style.currentData()
                                   or "candy",
        }
        for key, chk in self.chk_indicators.items():
            result[key] = chk.isChecked()
        return result


# 兼容旧引用（早期回归测试仍 import 这个名字）。它现在就是同一个 QWidget
# 页面，主窗口已不再用 exec() 弹模态窗口。
SettingsDialog = SettingsPage
