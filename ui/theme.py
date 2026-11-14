# -*- coding: utf-8 -*-
"""统一视觉设计 token：多套全局主题、字体、控件 QSS、高对比 Tooltip。

层级：BASE（窗口底） < PANEL（工具条/卡片） < ROW（列表行） < HOVER。
主题切换采用「常量热广播 + 已有样式串换色」两步：
1. set_theme() 更新本模块常量，并把它广播到所有已经 `from ui.theme
   import C_XXX` 的项目模块（否则那些模块里保存的是旧值副本）；
2. recolor_styles() 把窗口里已经生成好的 QSS 字符串按 旧色->新色 替换，
   于是无需重建窗口即可整体换肤；下一次刷新时各处会用新常量重新生成。
"""
import os
import re
import sys

from PySide6.QtWidgets import QApplication

# ================= 全局主题调色板 =================
# 常见类型：币安深色（默认）/ 午夜蓝 / OLED 纯黑 / 明亮 / 赛博霓虹 / 护眼米黄
THEMES = {
    "binance": {
        "bg_base": "#0b0e11", "bg_panel": "#181a20", "bg_row": "#1e2329",
        "bg_hover": "#2b3139", "bg_input": "#12161e",
        "border": "#2b3139", "border_soft": "#242930",
        "text_main": "#eaecef", "text_sub": "#b7bdc6", "text_dim": "#848e9c",
        "up": "#f6465d", "down": "#0ecb81", "accent": "#f0b90b",
        "blue": "#4b9cff", "purple": "#b39ddb", "teal": "#26a69a",
        "grid": "#2b3139", "axis_bg": "#12161e", "cross": "#848e9c",
        "flash_up": "#3a1c24", "flash_down": "#12352a",
        "sel": "#ffffff", "on_dark": True,
    },
    "midnight": {
        "bg_base": "#0a1020", "bg_panel": "#131c31", "bg_row": "#18233c",
        "bg_hover": "#243252", "bg_input": "#0d1526",
        "border": "#2b3b5c", "border_soft": "#22304c",
        "text_main": "#eaf1ff", "text_sub": "#b8c6e0", "text_dim": "#8394b5",
        "up": "#ff5c78", "down": "#25d0a0", "accent": "#5b8cff",
        "blue": "#6aa9ff", "purple": "#b39ddb", "teal": "#26a69a",
        "grid": "#263553", "axis_bg": "#0e1729", "cross": "#8394b5",
        "flash_up": "#3a1d2c", "flash_down": "#123a30",
        "sel": "#ffffff", "on_dark": True,
    },
    "oled": {
        "bg_base": "#000000", "bg_panel": "#0a0a0a", "bg_row": "#111111",
        "bg_hover": "#1c1c1c", "bg_input": "#050505",
        "border": "#2a2a2a", "border_soft": "#1e1e1e",
        "text_main": "#ffffff", "text_sub": "#d0d0d0", "text_dim": "#9a9a9a",
        "up": "#ff3b52", "down": "#00e08a", "accent": "#ffd21e",
        "blue": "#5aa9ff", "purple": "#c39dff", "teal": "#2bd4c0",
        "grid": "#222222", "axis_bg": "#050505", "cross": "#9a9a9a",
        "flash_up": "#2e1016", "flash_down": "#0b2a1e",
        "sel": "#ffffff", "on_dark": True,
    },
    "light": {
        "bg_base": "#f5f7fa", "bg_panel": "#ffffff", "bg_row": "#f0f3f7",
        "bg_hover": "#e4eaf2", "bg_input": "#ffffff",
        "border": "#d6dde8", "border_soft": "#e4e9f0",
        "text_main": "#161b22", "text_sub": "#495666", "text_dim": "#6b7787",
        "up": "#d92b45", "down": "#0a9a62", "accent": "#b8860b",
        "blue": "#2563d9", "purple": "#7c4dbd", "teal": "#11857a",
        "grid": "#dde3ec", "axis_bg": "#eef2f7", "cross": "#6b7787",
        "flash_up": "#fde3e7", "flash_down": "#dcf5ea",
        "sel": "#101820", "on_dark": False,
    },
    "cyber": {
        "bg_base": "#0b0716", "bg_panel": "#171029", "bg_row": "#1e1535",
        "bg_hover": "#2a1d4a", "bg_input": "#100a20",
        "border": "#3a2a63", "border_soft": "#2c2050",
        "text_main": "#f2eaff", "text_sub": "#c8b8e8", "text_dim": "#9a86c4",
        "up": "#ff4d8d", "down": "#22e6c8", "accent": "#00e5ff",
        "blue": "#6f8cff", "purple": "#d17bff", "teal": "#22e6c8",
        "grid": "#332554", "axis_bg": "#120b24", "cross": "#9a86c4",
        "flash_up": "#3b1430", "flash_down": "#0e3733",
        "sel": "#ffffff", "on_dark": True,
    },
    "sepia": {
        "bg_base": "#f6f1e4", "bg_panel": "#fdf9ef", "bg_row": "#f2ead8",
        "bg_hover": "#e8ddc7", "bg_input": "#fffdf7",
        "border": "#d8cbb2", "border_soft": "#e5dac4",
        "text_main": "#33291d", "text_sub": "#5c4c38", "text_dim": "#87755c",
        "up": "#c0392b", "down": "#14835a", "accent": "#b9770e",
        "blue": "#3a6ea5", "purple": "#8055a5", "teal": "#2b7f74",
        "grid": "#ded2bb", "axis_bg": "#f1e9d7", "cross": "#87755c",
        "flash_up": "#f6ddd6", "flash_down": "#d9eee0",
        "sel": "#201910", "on_dark": False,
    },
}

THEME_LABELS = {
    "binance": "币安深色（默认）",
    "midnight": "午夜蓝",
    "oled": "OLED 纯黑 · 高对比",
    "light": "明亮浅色",
    "cyber": "赛博霓虹",
    "sepia": "护眼米黄",
}
DEFAULT_THEME = "binance"

# 模块常量 -> 调色板字段（切换主题时按这张表同步）
_PALETTE_FIELDS = {
    "C_BG_BASE": "bg_base", "C_BG_PANEL": "bg_panel",
    "C_BG_ROW": "bg_row", "C_BG_HOVER": "bg_hover",
    "C_BG_INPUT": "bg_input", "C_BORDER": "border",
    "C_BORDER_SOFT": "border_soft", "C_TEXT_MAIN": "text_main",
    "C_TEXT_SUB": "text_sub", "C_TEXT_DIM": "text_dim",
    "C_UP": "up", "C_DOWN": "down", "C_ACCENT": "accent",
    "C_BLUE": "blue", "C_PURPLE": "purple", "C_TEAL": "teal",
    "C_OK": "down", "C_GRID": "grid", "C_AXIS_BG": "axis_bg",
    "C_CROSS": "cross", "C_FLASH_UP": "flash_up",
    "C_FLASH_DOWN": "flash_down", "C_LINE": "accent",
    "C_SELECT": "sel",
}

CURRENT_THEME = DEFAULT_THEME


def _p():
    return THEMES.get(CURRENT_THEME, THEMES[DEFAULT_THEME])


def current_theme() -> str:
    return CURRENT_THEME


def theme_names():
    return list(THEMES)


def is_dark_theme() -> bool:
    return bool(_p().get("on_dark", True))


def _initial(name):
    return THEMES[name]


_P0 = _initial(DEFAULT_THEME)

# ---- 当前主题的模块级常量（各处 from ui.theme import C_XXX 依赖它们）----
C_BG_BASE = _P0["bg_base"]
C_BG_PANEL = _P0["bg_panel"]
C_BG_ROW = _P0["bg_row"]
C_BG_HOVER = _P0["bg_hover"]
C_BG_INPUT = _P0["bg_input"]
C_BORDER = _P0["border"]
C_BORDER_SOFT = _P0["border_soft"]
C_TEXT_MAIN = _P0["text_main"]
C_TEXT_SUB = _P0["text_sub"]
C_TEXT_DIM = _P0["text_dim"]
C_UP = _P0["up"]
C_DOWN = _P0["down"]
C_ACCENT = _P0["accent"]
C_BLUE = _P0["blue"]
C_PURPLE = _P0["purple"]
C_TEAL = _P0["teal"]
C_OK = _P0["down"]

# ---- 字体（IBM Plex = 币安 BinancePlex 同源）----
FONT_UI = '"Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif'
FONT_UI_BOLD = '"Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif'
FONT_NUM = '"IBM Plex Mono", "Consolas", monospace'
FONT_NUM_BOLD = ('"IBM Plex Mono SemiBold", "IBM Plex Mono", '
                 '"Consolas", monospace')

_FONT_FILES = (
    "IBMPlexSans-Regular.ttf",
    "IBMPlexSans-SemiBold.ttf",
    "IBMPlexMono-Regular.ttf",
    "IBMPlexMono-SemiBold.ttf",
)


def _font_path(name: str) -> str:
    """兼容源码运行与 PyInstaller 单文件打包。"""
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        p = os.path.join(bundle, "assets", "fonts", name)
        if os.path.exists(p):
            return p
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "assets", "fonts", name)


def install_fonts() -> bool:
    """把内置 IBM Plex 字体注册进 Qt 字体库，返回是否至少成功一个。"""
    from PySide6.QtGui import QFontDatabase
    ok = False
    for name in _FONT_FILES:
        try:
            if QFontDatabase.addApplicationFont(_font_path(name)) >= 0:
                ok = True
        except Exception:
            pass
    return ok


def _base_font(size=11, bold=False, numeric=False):
    if numeric:
        family = FONT_NUM_BOLD if bold else FONT_NUM
    else:
        family = FONT_UI
    weight = "font-weight:600;" if bold else ""
    return f"font-family:{family}; font-size:{size}px; {weight}"


# ================= 主题切换 =================
def _derived(p):
    """由主题派生的图表/行内常量，广播到各 UI 模块。"""
    return {
        "MA_COLORS": {5: p["accent"], 10: p["purple"],
                      20: p["blue"], 30: p["teal"]},
        "BOLL_BAND": p["blue"], "BOLL_MID": p["accent"],
        "DIF_COLOR": p["accent"], "DEA_COLOR": p["purple"],
    }


def _broadcast(values: dict):
    """把新常量写进所有已导入的项目模块，覆盖 `from import` 的旧值副本。"""
    for name, mod in list(sys.modules.items()):
        if not (name.startswith(("ui.", "core.", "data.")) or name == "main"):
            continue
        d = getattr(mod, "__dict__", None)
        if not d:
            continue
        for key, val in values.items():
            if key in d and isinstance(d[key], (str, dict)):
                d[key] = val


def set_theme(name: str, app=None) -> str:
    """切换全局主题并立即热更新所有模块常量；返回实际生效的主题名。"""
    global CURRENT_THEME
    name = name if name in THEMES else DEFAULT_THEME
    old = dict(THEMES.get(CURRENT_THEME, _P0))
    p = THEMES[name]
    values = {const: p[field] for const, field in _PALETTE_FIELDS.items()}
    values.update(_derived(p))
    for key, val in values.items():
        globals()[key] = val
    CURRENT_THEME = name
    _broadcast(values)
    if app is not None:
        apply_global(app)
    return name, old, p


_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}")


def recolor_styles(root, old_palette: dict, new_palette: dict):
    """把窗口里已生成的 QSS 按「旧色 -> 新色」整体换色，无需重建控件。"""
    mapping = {}
    for field, new in new_palette.items():
        old = old_palette.get(field)
        if isinstance(old, str) and isinstance(new, str) \
                and old.lower() != new.lower():
            mapping[old.lower()] = new
    if not mapping:
        return
    # 补上 rgb()/rgba() 形式的硬编码红绿（行内涨跌底色）
    def swap(text):
        return _HEX_RE.sub(lambda m: mapping.get(m.group(0).lower(),
                                                 m.group(0)), text)
    from PySide6.QtWidgets import QWidget
    widgets = [root] + list(root.findChildren(QWidget)) if root else []
    for w in widgets:
        try:
            s = w.styleSheet()
            if s:
                ns = swap(s)
                if ns != s:
                    w.setStyleSheet(ns)
        except (RuntimeError, AttributeError):
            pass


# ================= 全局样式 =================
def tooltip_qss() -> str:
    """高对比提示框：近黑底 + 纯白字 + 强调色描边。

    Qt 在 Windows 上默认 QToolTip 用系统亮色底 + 系统文字色，配合本程序
    的深色 QPalette 会出现「浅灰字压浅灰底」几乎看不见。这里不再依赖
    主题的 panel 色（它偏灰、和中灰文字对比只有 3:1 左右），直接锁死
    最深底色 + 纯白文字，对比度 > 15:1；浅色主题反过来用白底近黑字。
    """
    dark = is_dark_theme()
    bg = "#07080a" if dark else "#ffffff"
    fg = "#ffffff" if dark else "#0d1117"
    return (f"QToolTip {{ background:{bg}; color:{fg};"
            f" border:2px solid {C_ACCENT}; border-radius:7px;"
            f" padding:7px 10px; font-family:{FONT_UI}; font-size:12px;"
            f" font-weight:600; }}")


def global_qss() -> str:
    """应用级 QSS：只放全局性的 tooltip / 菜单，局部样式仍由各控件负责。"""
    return tooltip_qss() + "\n" + menu_qss()


# ---- 容器 ----
def panel_qss(radius=6, bg=None, border=None) -> str:
    bg = bg or C_BG_PANEL
    border = border or C_BORDER
    return (f"QFrame {{ background:{bg}; border:1px solid {border};"
            f" border-radius:{radius}px; }}")


def separator_qss() -> str:
    return f"QFrame {{ background:{C_BORDER}; border:none; }}"


# ---- 按钮 ----
def tab_qss(active: bool, color=None) -> str:
    """市场页签：激活用该市场专属色实底 + 深色文字，对比度最高且各市场可区分。

    min-height 按触摸目标给到 38（加 margin 后实际 46），移植手机端不用重调。
    """
    color = color or C_ACCENT
    if active:
        return (f"QPushButton {{ {_base_font(13, True)} color:{C_BG_BASE};"
                f" background:{color}; border:1px solid {color};"
                f" border-radius:10px; padding:9px 17px; min-height:22px;"
                f" margin:4px 3px; }}"
                f"QPushButton:hover {{ background:{color};"
                f" color:{C_TEXT_MAIN}; }}")
    return (f"QPushButton {{ {_base_font(12, True)} color:{C_TEXT_SUB};"
            f" background:{C_BG_PANEL}; border:1px solid {C_BORDER};"
            f" border-radius:10px; padding:9px 17px; min-height:22px;"
            f" margin:4px 3px; }}"
            f"QPushButton:hover {{ color:{C_TEXT_MAIN};"
            f" border-color:{color}; background:{C_BG_HOVER}; }}")


def sort_btn_qss() -> str:
    """排序循环按钮：黄色描边，单击即切换下一种排序。"""
    return (f"QPushButton {{ {_base_font(11, True)} color:{C_ACCENT};"
            f" background:{C_BG_INPUT}; border:1px solid {C_ACCENT};"
            f" border-radius:4px; padding:4px 9px; }}"
            f"QPushButton:hover {{ background:{C_BG_HOVER};"
            f" color:{C_TEXT_MAIN}; }}"
            f"QPushButton:pressed {{ background:{C_ACCENT};"
            f" color:{C_BG_BASE}; }}")


def segment_qss(active: bool, color=None, pad_x=14) -> str:
    """紧凑型分段按钮（周期、指标开关、自选/全部）。

    pad_x 可调：周期有 11 个按钮，默认 14px 内边距在窄窗口下会把按钮
    压到比文字还窄，Qt 直接裁掉文字（看起来是一排空框），所以要能收窄。
    """
    color = color or C_ACCENT
    bg = C_BG_HOVER if active else "transparent"
    fg = color if active else C_TEXT_SUB
    border = f"1px solid {color}" if active else f"1px solid {C_BORDER}"
    return (f"QPushButton {{ {_base_font(12, active)} color:{fg};"
            f" background:{bg}; border:{border}; border-radius:8px;"
            f" padding:6px {pad_x}px; min-height:22px; }}"
            f"QPushButton:hover {{ color:{C_TEXT_MAIN};"
            f" background:{C_BG_HOVER}; }}")


def toggle_qss(color=None) -> str:
    color = color or C_ACCENT
    return (f"QPushButton {{ {_base_font(11)} color:{C_TEXT_DIM};"
            f" background:transparent; border:1px solid {C_BORDER};"
            f" border-radius:4px; padding:3px 10px; }}"
            f"QPushButton:checked {{ color:{color};"
            f" border-color:{color}; background:{C_BG_HOVER}; }}"
            f"QPushButton:hover {{ color:{C_TEXT_MAIN}; }}")


def tool_qss(color=None) -> str:
    color = color or C_ACCENT
    return (f"QPushButton {{ {_base_font(11)} color:{C_TEXT_SUB};"
            f" background:transparent; border:1px solid transparent;"
            f" border-radius:4px; padding:3px 9px; }}"
            f"QPushButton:checked {{ color:{color};"
            f" background:{C_BG_HOVER}; border-color:{color}; }}"
            f"QPushButton:hover {{ color:{C_TEXT_MAIN};"
            f" background:{C_BG_HOVER}; }}")


def icon_btn_qss(size=13, danger=False) -> str:
    hover = C_UP if danger else C_BG_HOVER
    return (f"QPushButton {{ {_base_font(size)} color:{C_TEXT_SUB};"
            f" background:transparent; border:1px solid {C_BORDER};"
            f" border-radius:4px; }}"
            f"QPushButton:hover {{ color:{C_TEXT_MAIN if danger else C_ACCENT};"
            f" background:{hover}; border-color:{C_ACCENT}; }}")


def bottom_nav_qss() -> str:
    """手机式底部导航栏：图标在上文字在下，选中态用主题色。

    触摸目标按 Material 的最小 48dp 设计，整栏 60px，方便以后搬到手机端。
    """
    return (f"#bottomNav {{ background:{C_BG_PANEL};"
            f" border-top:1px solid {C_BORDER}; }}"
            f"#bottomNav QToolButton {{ {_base_font(11, True)} color:{C_TEXT_DIM};"
            f" background:transparent; border:none; border-radius:8px;"
            f" padding:4px 2px 2px 2px; min-height:48px; }}"
            f"#bottomNav QToolButton:hover {{ background:{C_BG_HOVER};"
            f" color:{C_TEXT_MAIN}; }}"
            f"#bottomNav QToolButton:checked {{ color:{C_ACCENT};"
            f" background:{C_BG_HOVER}; }}")


def mini_btn_qss(active=False, color=None) -> str:
    """行内小按钮：加入 / 移除自选。"""
    color = color or C_ACCENT
    fg = C_BG_BASE if active else color
    bg = color if active else "transparent"
    return (f"QPushButton {{ {_base_font(11, True)} color:{fg};"
            f" background:{bg}; border:1px solid {color};"
            f" border-radius:4px; padding:2px 8px; }}"
            f"QPushButton:hover {{ background:{C_BG_HOVER};"
            f" color:{color}; }}")


def label_qss(size=11, color=None, bold=False, numeric=False) -> str:
    color = color or C_TEXT_DIM
    return f"QLabel {{ {_base_font(size, bold, numeric)} color:{color};" \
           f" background:transparent; border:none; }}"


def badge_qss(fg: str, bg: str, size=10) -> str:
    return (f"QLabel {{ {_base_font(size, True, True)} color:{fg};"
            f" background:{bg}; border-radius:4px; padding:1px 6px; }}")


def chip_qss(color: str, size=10) -> str:
    """市场 / 类型标签。"""
    return (f"QLabel {{ {_base_font(size, True)} color:{color};"
            f" border:1px solid {color}; border-radius:3px;"
            f" padding:0px 5px; background:transparent; }}")


# ---- 输入 / 下拉 ----
def line_edit_qss() -> str:
    return (f"QLineEdit {{ {_base_font(12)} background:{C_BG_INPUT};"
            f" color:{C_TEXT_MAIN}; border:1px solid {C_BORDER};"
            f" border-radius:10px; padding:8px 12px; min-height:22px; }}"
            f"QLineEdit:focus {{ border-color:{C_ACCENT}; }}")


def combo_qss() -> str:
    return (f"QComboBox {{ {_base_font(11)} background:{C_BG_INPUT};"
            f" color:{C_TEXT_MAIN}; border:1px solid {C_BORDER};"
            f" border-radius:4px; padding:4px 8px; }}"
            f"QComboBox:hover {{ border-color:{C_ACCENT}; }}"
            f"QComboBox::drop-down {{ border:none; width:16px; }}"
            f"QComboBox QAbstractItemView {{ background:{C_BG_PANEL};"
            f" color:{C_TEXT_MAIN}; border:1px solid {C_BORDER};"
            f" selection-background-color:{C_BG_HOVER}; }}")


def scroll_qss() -> str:
    return (f"QScrollArea {{ background:transparent; border:none; }}"
            f"QScrollBar:vertical {{ background:transparent; width:7px;"
            f" margin:2px; }}"
            f"QScrollBar::handle:vertical {{ background:{C_BORDER};"
            f" border-radius:3px; min-height:28px; }}"
            f"QScrollBar::handle:vertical:hover {{ background:{C_TEXT_DIM}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical"
            f" {{ height:0; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical"
            f" {{ background:transparent; }}")


def menu_qss() -> str:
    return (f"QMenu {{ {_base_font(12)} background:{C_BG_PANEL};"
            f" color:{C_TEXT_MAIN}; border:1px solid {C_BORDER};"
            f" border-radius:6px; padding:5px; }}"
            f"QMenu::item {{ padding:6px 22px; border-radius:4px; }}"
            f"QMenu::item:selected {{ background:{C_BG_HOVER};"
            f" color:{C_ACCENT}; }}"
            f"QMenu::separator {{ height:1px; background:{C_BORDER};"
            f" margin:4px 6px; }}")


def dialog_qss() -> str:
    """所有弹窗共用一份规格（见 ui.popup）；换主题时会自动跟着变。"""
    from ui.popup import popup_qss      # 局部导入，避免 theme <-> popup 循环
    return popup_qss()


def apply_global(app: QApplication):
    """注册字体、设置全局调色板与高对比 Tooltip 样式。"""
    from PySide6.QtGui import QColor, QFont, QPalette
    install_fonts()
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(C_BG_BASE))
    palette.setColor(QPalette.WindowText, QColor(C_TEXT_MAIN))
    palette.setColor(QPalette.Base, QColor(C_BG_INPUT))
    palette.setColor(QPalette.Text, QColor(C_TEXT_MAIN))
    palette.setColor(QPalette.Button, QColor(C_BG_PANEL))
    palette.setColor(QPalette.ButtonText, QColor(C_TEXT_MAIN))
    # 显式锁定 tooltip 底色/文字色：Windows 默认浅底浅字在深色主题下几乎不可读
    dark = is_dark_theme()
    palette.setColor(QPalette.ToolTipBase,
                     QColor("#07080a" if dark else "#ffffff"))
    palette.setColor(QPalette.ToolTipText,
                     QColor("#ffffff" if dark else "#0d1117"))
    palette.setColor(QPalette.Highlight, QColor(C_ACCENT))
    palette.setColor(QPalette.HighlightedText,
                     QColor("#0b0e11" if dark else "#ffffff"))
    app.setPalette(palette)
    font = QFont("Microsoft YaHei UI", 9)
    font.setHintingPreference(QFont.PreferDefaultHinting)
    app.setFont(font)
    app.setStyleSheet(global_qss())
