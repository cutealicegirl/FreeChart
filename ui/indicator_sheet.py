# -*- coding: utf-8 -*-
"""「指标参数」浮层：MA / EMA 天数、启停，BOLL / MACD 参数，周期作用域。

与图表工具条一样是独立悬浮图层（不进布局），展开时不会挤压 K 线、
不会改变缩放 / 平移状态。所有输入控件 ≥44px，适合手机手指点按。

周期作用域是本面板的关键：
- 「全部周期」写到 ``*``，所有 K 线周期共用；
- 「仅当前周期」写到 ``15m`` 等周期键，只覆盖该周期，没设置的字段仍
  沿用全局参数。于是「日线用 MA(5,10,20)、1 小时用 MA(20,60)」这类
  需求可以直接在图表上切周期后分别设置。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
                               QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSizePolicy, QSpinBox, QVBoxLayout,
                               QWidget)

from core import indicator_params as ip
from ui.popup import apply_popup_shadow, popup_qss
from ui import theme

MIN_TOUCH = 44
# 与 ui.chart_view 的调色板一致；这里独立定义，避免两模块循环导入。
MA_SWATCH = ["#f0b90b", "#b39ddb", "#4b9cff", "#26a69a"]
EMA_SWATCH = ["#ff9f43", "#e040fb", "#26de81", "#f7d794"]


class IndicatorSettingsSheet(QFrame):
    """悬浮式指标参数面板。"""

    applied = Signal()             # 参数已写入配置并生效
    closed = Signal()

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.setObjectName("popupSurface")
        self.setStyleSheet(popup_qss() + (
            "QDoubleSpinBox { background:%s; color:%s; border:1px solid %s;"
            " border-radius:10px; padding:7px 10px; min-height:24px; }"
            % (theme.C_BG_INPUT, theme.C_TEXT_MAIN, theme.C_BORDER)))
        self._cfg = config
        self._interval_key = ""
        self._interval_label = "当前周期"
        self._scope = ip.SCOPE_ALL
        self._loading = False
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumWidth(320)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 统一标题栏 ----
        head = QFrame()
        head.setObjectName("popupHead")
        head.setFixedHeight(MIN_TOUCH)
        hh = QHBoxLayout(head)
        hh.setContentsMargins(14, 2, 6, 2)
        hh.setSpacing(8)
        title = QLabel("⚙ 指标参数")
        title.setObjectName("popupTitle")
        hh.addWidget(title)
        hh.addStretch(1)
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("popupClose")
        self.btn_close.setFixedSize(MIN_TOUCH, MIN_TOUCH)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.setFocusPolicy(Qt.NoFocus)
        self.btn_close.setToolTip("关闭（不保存未应用的改动）")
        self.btn_close.clicked.connect(self.hide_sheet)
        hh.addWidget(self.btn_close)
        root.addWidget(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(12, 12, 12, 12)
        body_lay.setSpacing(10)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ---- 作用域 ----
        scope_card, scope_form = self._card(body_lay, "参数作用周期")
        self.combo_scope = QComboBox()
        self.combo_scope.setFixedHeight(MIN_TOUCH)
        self.combo_scope.addItem("全部周期（默认）", ip.SCOPE_ALL)
        self.combo_scope.addItem("仅当前周期", "@current")
        self.combo_scope.currentIndexChanged.connect(self._on_scope_changed)
        scope_form.addRow("应用到", self.combo_scope)
        self.lbl_scope_note = QLabel(
            "可为不同 K 线周期分别设天数：切到 1 小时、日线后各设一次，"
            "互不影响；未单独设置的周期沿用「全部周期」。")
        self.lbl_scope_note.setObjectName("popupNote")
        self.lbl_scope_note.setWordWrap(True)
        scope_card.addWidget(self.lbl_scope_note)

        # ---- MA ----
        ma_card, _ = self._card(body_lay, "MA 简单移动平均 · 天数")
        self._ma_rows = self._line_rows(ma_card, "ma")
        self._note(ma_card,
                   "天数按 K 线根数计：日线 MA20 = 20 天，"
                   "1 小时 MA20 = 20 根 1 小时 K 线。未勾选的线不绘制、"
                   "也不参与价格范围计算。")

        # ---- EMA ----
        ema_card, _ = self._card(body_lay, "EMA 指数移动平均 · 天数")
        self._ema_rows = self._line_rows(ema_card, "ema")
        self._note(ema_card,
                   "EMA 对近期价格加权更高，同天数下比 MA 更贴近走势；"
                   "四条线可任意启停，颜色与 MA 区分。")

        # ---- BOLL ----
        boll_card, boll_form = self._card(body_lay, "BOLL 布林线参数")
        self.spin_boll_n = self._spin(2, 200, 20)
        self.spin_boll_n.setToolTip("中轨 MA 的天数 / 标准差窗口")
        boll_form.addRow("周期（天数）", self.spin_boll_n)
        self.spin_boll_k = QDoubleSpinBox()
        self.spin_boll_k.setFixedHeight(MIN_TOUCH)
        self.spin_boll_k.setRange(ip.MIN_K, ip.MAX_K)
        self.spin_boll_k.setSingleStep(0.1)
        self.spin_boll_k.setDecimals(2)
        self.spin_boll_k.setValue(2.0)
        self.spin_boll_k.setToolTip("上下轨 = 中轨 ± K × 标准差")
        boll_form.addRow("标准差倍数 K", self.spin_boll_k)

        # ---- MACD ----
        macd_card, macd_form = self._card(body_lay, "MACD 参数")
        self.spin_macd_fast = self._spin(2, 100, 12)
        macd_form.addRow("快线 EMA", self.spin_macd_fast)
        self.spin_macd_slow = self._spin(3, 200, 26)
        macd_form.addRow("慢线 EMA", self.spin_macd_slow)
        self.spin_macd_signal = self._spin(2, 100, 9)
        macd_form.addRow("信号线 DEA", self.spin_macd_signal)
        self._note(macd_card, "慢线天数必须大于快线；若填反，保存时自动调整。")

        self.btn_reset = QPushButton("恢复本作用范围的默认参数")
        self.btn_reset.setFixedHeight(MIN_TOUCH)
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setFocusPolicy(Qt.NoFocus)
        self.btn_reset.clicked.connect(self._on_reset)
        body_lay.addWidget(self.btn_reset)
        body_lay.addStretch(1)

        # ---- 底部操作栏 ----
        footer = QFrame()
        footer.setObjectName("popupFooter")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(12, 8, 12, 10)
        fl.setSpacing(10)
        fl.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(MIN_TOUCH)
        btn_cancel.setMinimumWidth(92)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setFocusPolicy(Qt.NoFocus)
        btn_cancel.clicked.connect(self.hide_sheet)
        fl.addWidget(btn_cancel)
        self.btn_apply = QPushButton("应用")
        self.btn_apply.setObjectName("popupPrimary")
        self.btn_apply.setFixedHeight(MIN_TOUCH)
        self.btn_apply.setMinimumWidth(104)
        self.btn_apply.setCursor(Qt.PointingHandCursor)
        self.btn_apply.setFocusPolicy(Qt.NoFocus)
        self.btn_apply.setToolTip("保存并立即重算当前图表的所有指标")
        self.btn_apply.clicked.connect(self._on_apply)
        fl.addWidget(self.btn_apply)
        root.addWidget(footer)

        apply_popup_shadow(self)
        self.hide()

    # ---- 小组件 ----
    def _card(self, parent_lay, title: str):
        card = QFrame()
        card.setObjectName("popupCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(12, 10, 12, 11)
        box.setSpacing(7)
        lbl = QLabel(title)
        lbl.setObjectName("popupCardTitle")
        box.addWidget(lbl)
        form = QFormLayout()
        form.setSpacing(7)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        box.addLayout(form)
        parent_lay.addWidget(card)
        return box, form

    @staticmethod
    def _note(parent_lay, text: str):
        lbl = QLabel(text)
        lbl.setObjectName("popupNote")
        lbl.setWordWrap(True)
        lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        parent_lay.addWidget(lbl)

    @staticmethod
    def _spin(lo: int, hi: int, value: int) -> QSpinBox:
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setValue(value)
        sp.setFixedHeight(MIN_TOUCH)
        sp.setToolTip(f"可设 {lo} ~ {hi}")
        return sp

    def _line_rows(self, card, kind: str) -> list:
        palette = MA_SWATCH if kind == "ma" else EMA_SWATCH
        rows = []
        for i in range(ip.MAX_LINES):
            row = QHBoxLayout()
            row.setSpacing(8)
            chk = QCheckBox(f"第 {i + 1} 条")
            chk.setFixedHeight(MIN_TOUCH)
            chk.setMinimumWidth(72)
            row.addWidget(chk)
            swatch = QLabel("")
            swatch.setFixedSize(16, 16)
            swatch.setStyleSheet(
                f"background:{palette[i]}; border-radius:4px; border:none;")
            row.addWidget(swatch)
            row.addStretch(1)
            lbl = QLabel("天数")
            row.addWidget(lbl)
            spin = self._spin(ip.MIN_PERIOD, ip.MAX_PERIOD, 20)
            spin.setFixedWidth(104)
            spin.setEnabled(chk.isChecked())
            chk.toggled.connect(spin.setEnabled)
            row.addWidget(spin)
            card.addLayout(row)
            rows.append((chk, spin))
        return rows

    # ---- 作用域与参数 ----
    def set_interval(self, key: str, label: str = ""):
        """由图表页在切周期时同步，更新「仅当前周期」的显示文字。"""
        self._interval_key = str(key or "")
        self._interval_label = label or self._interval_key or "当前周期"
        self.combo_scope.setItemText(1, f"仅当前周期（{self._interval_label}）")

    def current_scope(self) -> str:
        data = self.combo_scope.currentData()
        if data == "@current":
            return self._interval_key or ip.SCOPE_ALL
        return ip.SCOPE_ALL

    def _load(self):
        self._scope = self.current_scope()
        # 显示「该周期最终生效」的值：周期里没单独设的字段沿用全局，
        # 这样面板上看到的与图上画的永远一致。
        params = ip.params_for(self._cfg, self._scope)
        self._loading = True
        for rows, key in ((self._ma_rows, "ma"), (self._ema_rows, "ema")):
            for i, (chk, spin) in enumerate(rows):
                line = params[key][i]
                chk.setChecked(bool(line["enabled"]))
                spin.setValue(int(line["period"]))
        self.spin_boll_n.setValue(int(params["boll"]["period"]))
        self.spin_boll_k.setValue(float(params["boll"]["k"]))
        self.spin_macd_fast.setValue(int(params["macd"]["fast"]))
        self.spin_macd_slow.setValue(int(params["macd"]["slow"]))
        self.spin_macd_signal.setValue(int(params["macd"]["signal"]))
        self._loading = False

    def _collect(self) -> dict:
        def lines(rows):
            return [{"period": int(spin.value()),
                     "enabled": bool(chk.isChecked())}
                    for chk, spin in rows]
        return ip.normalize({
            "ma": lines(self._ma_rows),
            "ema": lines(self._ema_rows),
            "boll": {"period": int(self.spin_boll_n.value()),
                     "k": float(self.spin_boll_k.value())},
            "macd": {"fast": int(self.spin_macd_fast.value()),
                     "slow": int(self.spin_macd_slow.value()),
                     "signal": int(self.spin_macd_signal.value())},
        })

    def _on_scope_changed(self, _index=0):
        if self._loading:
            return
        # 切换作用域前先把当前编辑静默写回旧作用域，避免用户白填一遍
        old = self._scope
        if old and self.isVisible():
            ip.write_params(self._cfg, old, self._collect())
        self._load()

    def _on_apply(self):
        params = self._collect()
        ip.write_params(self._cfg, self.current_scope(), params)
        self.applied.emit()
        self.hide_sheet()

    def _on_reset(self):
        scope = self.current_scope()
        ip.reset_scope(self._cfg, scope)
        self.applied.emit()
        self._load()

    # ---- 显隐 ----
    def open_sheet(self):
        self._load()
        self.show()
        self.raise_()
        self.setFocus()

    def hide_sheet(self):
        self.hide()
        self.closed.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide_sheet()
            return
        super().keyPressEvent(event)
