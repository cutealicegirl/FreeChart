# -*- coding: utf-8 -*-
"""全程序统一的「弹窗」外观。

之前设置窗口、品种详情、悬停资料卡各写了一套 QSS：颜色取自同一份调色板，
但圆角、边框、标题栏、按钮、卡片标题都各不相同，换主题后更显得杂乱。
这里把弹窗的视觉规格收敛成一份：

  - Surface：圆角面板 + 1px 边框 + 统一投影；
  - Head：左侧标题 + 右侧关闭按钮，统一高度与分隔线；
  - Card：内容分组卡片；
  - Button：普通 / 主按钮两套，全程序一致。

所有颜色都从 ui.theme 的**模块属性**动态读取（不 from-import 常量），
因此设置里切换主题后重新 apply 样式即可整体换肤。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect,
                               QHBoxLayout, QLabel, QPushButton, QVBoxLayout)

from ui import theme

POPUP_RADIUS = 14
POPUP_HEAD_H = 44


def _c(name: str, fallback: str = "#1e2329"):
    """动态取当前主题色（换肤后调用方会重新套用样式）。"""
    return getattr(theme, name, fallback)


def popup_qss() -> str:
    """所有弹窗 / 设置页 / 详情抽屉 / 悬停卡共用的基础样式表。"""
    base, panel, inp = _c("C_BG_BASE"), _c("C_BG_PANEL"), _c("C_BG_INPUT")
    hover, border = _c("C_BG_HOVER"), _c("C_BORDER")
    main, sub, dim, accent = (_c("C_TEXT_MAIN"), _c("C_TEXT_SUB"),
                               _c("C_TEXT_DIM"), _c("C_ACCENT"))
    font = theme._base_font(12)
    return (
        # ---- 弹窗底：QDialog / 独立设置页 / 悬浮资料卡表面 ----
        f"QDialog, QWidget#settingsRoot, QFrame#popupSurface {{"
        f" background:{base}; border:1px solid {border};"
        f" border-radius:{POPUP_RADIUS}px; }}"
        f"QWidget#settingsBody {{ background:{base}; }}"
        # ---- 统一标题栏 ----
        f"QFrame#popupHead {{ background:{base};"
        f" border-bottom:1px solid {border};"
        f" border-top-left-radius:{POPUP_RADIUS}px;"
        f" border-top-right-radius:{POPUP_RADIUS}px; }}"
        f"QLabel#popupTitle {{ {theme._base_font(13, True)}"
        f" color:{main}; }}"
        f"QPushButton#popupClose {{ {theme._base_font(15, True)} color:{sub};"
        f" background:transparent; border:none; border-radius:10px; }}"
        f"QPushButton#popupClose:hover {{ color:{main};"
        f" background:{hover}; }}"
        f"QPushButton#popupClose:pressed {{ color:{main};"
        f" background:{border}; }}"
        # ---- 内容分组卡片 ----
        f"QFrame#popupCard, QFrame#settingsCard {{ background:{panel};"
        f" border:1px solid {border}; border-radius:{POPUP_RADIUS}px; }}"
        f"QLabel#popupCardTitle, QLabel#settingsCardTitle {{"
        f" {theme._base_font(12, True)} color:{accent}; padding:0 0 2px 0; }}"
        f"QFrame#popupFooter, QFrame#settingsFooter {{"
        f" background:{panel}; border-top:1px solid {border}; }}"
        # ---- 文本与输入 ----
        f"QLabel {{ {font} color:{sub}; }}"
        f"QLabel#popupNote {{ {theme._base_font(10)} color:{dim}; }}"
        f"QCheckBox {{ {font} color:{sub}; spacing:8px; padding:6px 0; }}"
        f"QSpinBox, QLineEdit, QComboBox {{ {font} background:{inp};"
        f" color:{main}; border:1px solid {border}; border-radius:10px;"
        f" padding:7px 10px; min-height:24px; }}"
        f"QListWidget {{ {theme._base_font(12, numeric=True)}"
        f" background:{inp}; color:{main}; border:1px solid {border};"
        f" border-radius:10px; padding:4px; }}"
        f"QListWidget::item {{ padding:6px 2px; }}"
        # ---- 按钮 ----
        f"QPushButton {{ {font} color:{main}; background:{hover};"
        f" border:1px solid {border}; border-radius:10px;"
        f" padding:8px 14px; }}"
        f"QPushButton:hover {{ border-color:{accent}; color:{accent}; }}"
        f"QPushButton.popupPrimary, QPushButton#popupPrimary {{"
        f" color:{base}; background:{accent};"
        f" border:1px solid {accent}; {theme._base_font(12, True)} }}"
        f"QPushButton.popupPrimary:hover, QPushButton#popupPrimary:hover {{"
        f" color:{base}; background:{accent}; border-color:{main}; }}"
    )


def apply_popup_shadow(widget, blur: int = 26, alpha: int = 110):
    """给浮层加统一投影；offscreen 截图环境跳过，避免软件渲染抖动。"""
    if QApplication.platformName() == "offscreen":
        return None
    try:
        from PySide6.QtGui import QColor
        effect = QGraphicsDropShadowEffect(widget)
        effect.setBlurRadius(blur)
        effect.setOffset(0, 6)
        effect.setColor(QColor(0, 0, 0, alpha))
        widget.setGraphicsEffect(effect)
        return effect
    except Exception:
        return None


def popup_card(title: str = "", parent=None) -> tuple:
    """创建统一卡片：返回 (卡片 frame, 卡片内竖向布局)。"""
    card = QFrame(parent)
    card.setObjectName("popupCard")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(12, 11, 12, 12)
    lay.setSpacing(8)
    if title:
        lbl = QLabel(title, card)
        lbl.setObjectName("popupCardTitle")
        lay.addWidget(lbl)
    return card, lay


def popup_close_button(parent=None) -> QPushButton:
    """统一关闭按钮：加大热区（44x34），悬停有圆形底色，好点也好认。"""
    btn = QPushButton("✕", parent)
    btn.setObjectName("popupClose")
    btn.setFixedSize(44, 34)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setFocusPolicy(Qt.NoFocus)
    btn.setToolTip("关闭")
    return btn


class PopupSurface(QFrame):
    """带统一标题栏与关闭按钮的弹窗外壳。

    既可作为 QDialog 的内容，也可作为主窗口里的浮层；
    `closed` 信号由关闭按钮或外部主动触发，调用方决定是关闭还是隐藏。
    """

    closed = Signal()

    def __init__(self, title: str = "", parent=None, closable: bool = True):
        super().__init__(parent)
        self.setObjectName("popupSurface")
        self.setStyleSheet(popup_qss())
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.head = QFrame(self)
        self.head.setObjectName("popupHead")
        self.head.setFixedHeight(POPUP_HEAD_H)
        hh = QHBoxLayout(self.head)
        hh.setContentsMargins(14, 4, 6, 4)
        hh.setSpacing(8)
        self.lbl_title = QLabel(title, self.head)
        self.lbl_title.setObjectName("popupTitle")
        hh.addWidget(self.lbl_title)
        hh.addStretch(1)
        self.btn_close = popup_close_button(self.head)
        self.btn_close.clicked.connect(self.closed.emit)
        self.btn_close.setVisible(closable)
        hh.addWidget(self.btn_close)
        root.addWidget(self.head)
        self.body = QFrame(self)
        self.body.setObjectName("popupBody")
        self.body.setStyleSheet(
            f"QFrame#popupBody {{ background:{_c('C_BG_BASE')};"
            f" border:none; }}")
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(0, 0, 0, 0)
        self.body_lay.setSpacing(0)
        root.addWidget(self.body, 1)
        apply_popup_shadow(self)

    def set_title(self, text: str):
        self.lbl_title.setText(text)

    def refresh_style(self):
        self.setStyleSheet(popup_qss())
        self.body.setStyleSheet(
            f"QFrame#popupBody {{ background:{_c('C_BG_BASE')};"
            f" border:none; }}")
