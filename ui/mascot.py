# -*- coding: utf-8 -*-
"""「看板娘」悬浮形象窗口（独立模块，集成方自行接入）。

用法（集成示例）::

    from ui.mascot import MascotWindow
    mascot = MascotWindow(config)      # config: core.config.Config 实例
    mascot.apply_config()              # 设置保存后再次调用，即时生效

窗口为无边框 / 透明背景 / 工具窗口，可鼠标左键拖动，右键呼出菜单。
不启动线程、不访问网络；QT_QPA_PLATFORM=offscreen 下可安全构造与截图。

配置项（本模块自带默认值，无需 DEFAULTS 里预先登记）::

    mascot_enabled        bool  默认 False   显隐
    mascot_image          str   默认 ""      自定义图片路径；空/文件不存在 -> 内置图
    mascot_scale          int   50..200      默认 100（百分比）
    mascot_opacity        int   20..100      默认 100
    mascot_x / mascot_y   int   默认 -1      -1 = 贴屏幕右下角
    mascot_click_through  bool  默认 False   点击穿透
    mascot_on_top         bool  默认 True    总在最前

注意：开启「点击穿透」后本窗口不再接收任何鼠标事件（含右键菜单），
      需要在设置对话框/托盘等外部入口把它关闭，或修改配置后调用
      apply_config() 恢复。
"""
import os
import random
import sys
import time

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QRect, QRectF,
                            QSize, Qt, QTimer, QVariantAnimation)
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QImageReader,
                           QLinearGradient, QMovie, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QWidget

__all__ = ["MascotWindow", "MascotBubble", "default_mascot_path"]

# 本模块自带的配置默认值（core.config.Config 的 DEFAULTS 不需要包含这些键）
DEFAULTS = {
    "mascot_enabled": False,
    "mascot_image": "",
    "mascot_scale": 100,
    "mascot_opacity": 100,
    "mascot_x": -1,
    "mascot_y": -1,
    "mascot_click_through": False,
    "mascot_on_top": True,
    "mascot_speech": True,
    "mascot_bubble_style": "candy",     # 可选值见 BUBBLE_STYLES
}

_MARGIN = 12                     # 贴右下角时留出的边距（px）
_SCALE_MIN, _SCALE_MAX = 50, 200
_OPACITY_MIN, _OPACITY_MAX = 20, 100
_GIF_EXTS = {".gif"}

# ---------------------------------------------------------------- 台词库
# 占位符：{sym} 品种代码 / {name} 名称 / {pct} 涨跌幅 / {market} 市场名
SPEECH = {
    "greet": [
        "我回来啦～今天也一起盯盘吧！",
        "おかえりなさい、ご主人様～一緒に頑張りましょうね！",
        "主人，行情随时会动，我帮你看着呢。",
        "ただいま戻りました、今日もよろしくお願いします♪",
        "嗯……这次的走势，我有点预感。",
    ],
    "return": [
        "ただいま〜！K線を邪魔しない場所に戻ってきたよ♪",
        "我回来啦～刚才是怕挡住 K 线，先躲了一下！お待たせ〜",
        "お待たせしました、ご主人様～続きを見ましょうね！",
        "K線、ちゃんと見えてる？私はここにいますよ～",
    ],
    "click": [
        "别戳啦，会痒的～",
        "えへへ、くすぐったいです～",
        "在的在的，有什么想看的吗？",
        "なになに？呼んだ？",
        "要不要我帮你翻翻K线？",
        "主人今天心情如何？にゃはは～",
    ],
    "up": [
        "{sym} 涨了 {pct}，看着真舒服～",
        "{sym} が {pct} 上がったよ！やったね～",
        "{sym} 走强了，主人要不要看一眼？",
        "赤い赤い！{sym} {pct}、翼がキラキラしてます✨",
        "红盘！{sym} {pct}，我的翅膀都亮起来了。",
    ],
    "down": [
        "{sym} 跌了 {pct}……别慌，先看看支撑位。",
        "{sym} が {pct} 下がっちゃった……大丈夫、まだ大丈夫！",
        "{sym} 有点弱呢，要不要我陪你盯一会儿？",
        "緑色です……{sym} {pct}、深呼吸してね。",
        "绿了绿了，{sym} {pct}。深呼吸，别追跌。",
    ],
    "big_up": [
        "{sym} 直接拉到 {pct}！这波有点猛。",
        "すごーい！{sym} {pct}、ご主人様の自選が光ってます！",
        "哇——{sym} {pct}，主人你的自选在发光。",
    ],
    "big_down": [
        "{sym} 杀到 {pct}……要不要先离场看看？",
        "{sym} が {pct} も下がってる……逃げるも恥だが役に立つ、です。",
        "{sym} 跌得有点狠（{pct}），我帮你盯着反弹。",
    ],
    "chart": [
        "看 {sym} のチャート？一緒に見ましょう～",
        "{sym} 的K线打开了，注意最近的支撑压力。",
        "{sym} のローソク、綺麗に並んでますね～",
    ],
    "add": [
        "{sym} 加进自选了，我会盯紧它。",
        "{sym} をウォッチリストに入れました、任せてください！",
        "收到，{sym} 已加入观察名单～",
    ],
    "remove": [
        "{sym} 移出自选了，眼不见心不烦。",
        "{sym} をリストから外しました、さようなら～",
        "好，{sym} 先放一边。",
    ],
    "market": [
        "切到{market}了，这边节奏不太一样哦。",
        "{market}に切り替えました、テンポが違いますね～",
        "{market}的品种，主人比较熟吗？",
    ],
    "theme": [
        "换新皮肤啦？这个配色我喜欢。",
        "新しい服ですか？可愛いですね、この配色！",
        "灯光调好了，继续盯盘～",
    ],
    "settings": [
        "要调整什么？我在这儿等着。",
        "設定中ですか？ゆっくりどうぞ、行情は見てますから。",
        "设置慢慢改，行情我先替你看着。",
    ],
    "idle": [
        "盯了好久啦，要不要休息一下眼睛？",
        "ずっと見てましたね、目を休ませてあげてください。",
        "行情安静得像在憋大招……",
        "主人，记得设好止损再离开。損切りは大事です！",
    ],
}

_BUBBLE_BG = "#151b2e"
_BUBBLE_BORDER = "#3a4a72"
_BUBBLE_TEXT = "#eef3ff"
_BUBBLE_ACCENT = "#f0b90b"
_TAIL_H = 9                      # 气泡尾巴高度

# ---------------------------------------------------------------- 气泡风格
# 每种风格：渐变上下色 / 描边 / 文字 / 点缀色 / 圆角 / 装饰图形
# deco: heart 小爱心 / star 四角星 / dot 圆点 / none
BUBBLE_STYLES = {
    "candy": {
        "label": "糖果（粉紫）",
        "bg1": "#ffe3f3", "bg2": "#e6dcff", "border": "#ffb3da",
        "text": "#4a2c46", "accent": "#ff6fae", "radius": 18,
        "deco": "star",
    },
    "sakura": {
        "label": "樱花（粉白）",
        "bg1": "#fff4f8", "bg2": "#ffe0ec", "border": "#ffc2d8",
        "text": "#5b2d40", "accent": "#ff8fb8", "radius": 18,
        "deco": "heart",
    },
    "mint": {
        "label": "薄荷（青绿）",
        "bg1": "#eafff7", "bg2": "#d5f7ee", "border": "#9fe8d2",
        "text": "#1f4740", "accent": "#2fc39d", "radius": 18,
        "deco": "dot",
    },
    "cyber": {
        "label": "赛博（霓虹）",
        "bg1": "#1a1430", "bg2": "#141a2e", "border": "#59e3ff",
        "text": "#eaf6ff", "accent": "#59e3ff", "radius": 16,
        "deco": "star",
    },
    "classic": {
        "label": "经典（深色）",
        "bg1": "#151b2e", "bg2": "#151b2e", "border": "#3a4a72",
        "text": "#eef3ff", "accent": "#f0b90b", "radius": 13,
        "deco": "none",
    },
}
BUBBLE_STYLE_KEYS = tuple(BUBBLE_STYLES)
DEFAULT_BUBBLE_STYLE = "candy"


class MascotBubble(QWidget):
    """看板娘对话气泡：圆角卡片 + 小尾巴，淡入淡出，自动消失。

    独立顶层工具窗口（不抢焦点、不占任务栏），跟随看板娘位置显示在头顶。
    """

    MAX_W = 300

    def __init__(self, parent=None):
        super().__init__(None)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint |
                            Qt.WindowStaysOnTopHint |
                            Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowTitle("看板娘气泡")
        self._text = ""
        self._anchor = QRect()
        self._text_rect = QRectF()
        self._style = DEFAULT_BUBBLE_STYLE
        self._font = QFont()
        # 圆润一点的字形更贴二次元风格；系统没有就退回雅黑
        try:
            self._font.setFamilies(["HYWenHei-85W", "HarmonyOS Sans SC",
                                    "Microsoft YaHei UI", "PingFang SC"])
        except (AttributeError, TypeError):
            pass
        self._font.setPointSizeF(10.5)
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(170)
        self._fade.valueChanged.connect(
            lambda v: self.setWindowOpacity(max(0.0, min(1.0, float(v)))))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        # 每次 say 递增：淡出过程中挂起的延迟 hide 不能把新气泡一起关掉
        self._hide_token = 0
        self.hide()

    # ---- 风格 ----
    def set_style(self, key: str):
        """切换气泡配色 / 造型（设置里可选，运行中即时生效）。"""
        key = str(key or "").strip().lower()
        if key not in BUBBLE_STYLES or key == self._style:
            return
        self._style = key
        if self.isVisible():
            self.resize(self._measure())
            self._place()
            self.update()

    def style_key(self) -> str:
        return self._style

    @property
    def _palette(self) -> dict:
        return BUBBLE_STYLES.get(self._style, BUBBLE_STYLES[DEFAULT_BUBBLE_STYLE])

    # ---- 对外 ----
    def say(self, text: str, anchor: QRect, ms: int = 4200):
        text = (text or "").strip()
        if not text or not anchor.isValid():
            return
        self._text = text
        self._anchor = QRect(anchor)
        size = self._measure()
        self.resize(size)
        self._place()
        self._timer.stop()
        self._fade.stop()
        self._hide_token += 1       # 作废上一句残留的延迟关闭
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._animate(0.0, 0.97)
        self._timer.start(max(600, int(ms)))   # 到点自动淡出

    def follow(self, anchor: QRect):
        """看板娘被拖动 / 缩放时跟随（没在显示就什么也不做）。"""
        if not self.isVisible():
            return
        self._anchor = QRect(anchor)
        self._place()

    def dismiss(self):
        self._timer.stop()
        self._hide_token += 1
        self._fade.stop()
        if self.isVisible():
            self.hide()

    def is_talking(self) -> bool:
        return self.isVisible()

    # ---- 内部 ----
    def _measure(self) -> QSize:
        fm = QFontMetrics(self._font)
        flags = int(Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter)
        # 上下内边距给足：装饰条 / 高光在顶边，字号带小数（10.5pt）时
        # Qt 的测量与实际绘制会差 1~2px，padding 太小最后一行会被裁掉。
        pad_x, pad_y = 18, 15
        # 先按单行宽度决定气泡多宽（短句不占满整行），再按这个宽度算行数，
        # 否则测量用宽、显示用窄，文字会被挤成多余的一行。
        single = fm.horizontalAdvance(self._text)
        inner = max(96, min(self.MAX_W, single + 4))
        box = fm.boundingRect(QRect(0, 0, inner, 2400), flags, self._text)
        # 高度再留 8px 冗余：日文假名与中英文混排时行高会略有出入，
        # boundingRect 偶尔低估一行，宁可气泡略高也不能切到字。
        w = inner + pad_x * 2
        h = box.height() + pad_y * 2 + 8
        self._text_rect = QRectF(pad_x, pad_y, w - pad_x * 2,
                                 h - pad_y * 2)
        return QSize(w, h + _TAIL_H)

    def _place(self):
        screen = QApplication.primaryScreen()
        avail = QRect(0, 0, 1920, 1080)
        if screen is not None:
            g = screen.availableGeometry()
            if g.isValid() and not g.isEmpty():
                avail = QRect(g)
        x = self._anchor.center().x() - self.width() // 2
        y = self._anchor.top() - self.height() + 8
        if y < avail.top() + 6:                 # 头顶放不下就放到脚下
            y = self._anchor.bottom() - 8
        x = max(avail.left() + 6,
                min(x, avail.right() - self.width() - 6))
        y = max(avail.top() + 6,
                min(y, avail.bottom() - self.height() - 6))
        self.move(x, y)

    def _animate(self, start: float, end: float):
        self._fade.stop()
        self._fade.setStartValue(start)
        self._fade.setEndValue(end)
        self._fade.start()

    def _fade_out(self, immediate: bool = False):
        self._timer.stop()
        if immediate or not self.isVisible():
            self._fade.stop()
            self.hide()
            return
        token = self._hide_token
        self._animate(self.windowOpacity(), 0.0)
        QTimer.singleShot(260, lambda: self._delayed_hide(token))

    def _delayed_hide(self, token: int):
        # 期间若又说了新台词，旧句子的延迟关闭必须作废
        if token == self._hide_token:
            self.hide()

    def paintEvent(self, event):
        pal = self._palette
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        radius = float(pal["radius"])
        body = QRectF(1.0, 1.0, self.width() - 2.0, self.height() - _TAIL_H - 1.0)
        path = QPainterPath()
        path.addRoundedRect(body, radius, radius)
        # 尾巴：贴在底边偏左，指向人物
        tail_x = min(max(18.0, self.width() * 0.32), self.width() - 34.0)
        tail = QPainterPath()
        tail.moveTo(tail_x, body.bottom() - 0.5)
        tail.lineTo(tail_x + 13, body.bottom() + _TAIL_H - 1)
        tail.lineTo(tail_x + 24, body.bottom() - 0.5)
        tail.closeSubpath()
        path = path.united(tail)

        # 外发光：可爱风格带一圈淡淡的光晕
        if self._style != "classic":
            glow = QColor(pal["accent"])
            glow.setAlpha(46)
            p.setPen(QPen(glow, 3.2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

        grad = QLinearGradient(body.topLeft(), body.bottomLeft())
        grad.setColorAt(0.0, QColor(pal["bg1"]))
        grad.setColorAt(1.0, QColor(pal["bg2"]))
        p.setPen(QPen(QColor(pal["border"]), 1.4))
        p.setBrush(QBrush(grad))
        p.drawPath(path)

        # 左上高光（糖果质感）
        if self._style != "classic":
            sheen = QLinearGradient(body.topLeft(), body.center())
            sheen.setColorAt(0.0, QColor(255, 255, 255, 92))
            sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(sheen))
            p.drawPath(path)

        # 左侧强调条（经典风格保留原样）
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal["accent"]))
        if self._style == "classic":
            p.drawRoundedRect(QRectF(body.left() + 1.0, body.top() + 9.0, 2.6,
                                     max(10.0, body.height() - 18.0)), 1.3, 1.3)
        else:
            p.drawRoundedRect(QRectF(body.left() + 13.0, body.top() + 5.4,
                                     16.0, 2.4), 1.2, 1.2)

        self._paint_deco(p, body, pal)

        p.setFont(self._font)
        p.setPen(QColor(pal["text"]))
        p.drawText(self._text_rect,
                   int(Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter),
                   self._text)
        p.end()

    def _paint_deco(self, p: QPainter, body: QRectF, pal: dict):
        """边角小装饰：星星 / 爱心 / 圆点，纯绘制，不占布局。"""
        kind = pal.get("deco") or "none"
        if kind == "none":
            return
        c = QColor(pal["accent"])
        c.setAlpha(150)
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        # 右上角两颗小星星
        self._star(p, body.right() - 13.0, body.top() + 8.0, 4.2)
        self._star(p, body.right() - 25.0, body.top() + 5.6, 2.4)
        if kind == "heart":
            self._heart(p, body.right() - 15.0, body.bottom() - 13.0, 4.2)
        elif kind == "dot":
            for i in range(3):
                p.drawEllipse(
                    QPointF(body.right() - 14.0 - i * 7.0,
                            body.bottom() - 12.0), 1.8, 1.8)
        elif kind == "star":
            self._star(p, body.right() - 15.0, body.bottom() - 13.0, 3.8)

    @staticmethod
    def _star(p: QPainter, cx: float, cy: float, r: float):
        """四角星（二次元常见的那种小闪光）。"""
        path = QPainterPath()
        path.moveTo(cx, cy - r)
        path.quadTo(cx + r * 0.28, cy - r * 0.28, cx + r, cy)
        path.quadTo(cx + r * 0.28, cy + r * 0.28, cx, cy + r)
        path.quadTo(cx - r * 0.28, cy + r * 0.28, cx - r, cy)
        path.quadTo(cx - r * 0.28, cy - r * 0.28, cx, cy - r)
        p.drawPath(path)

    @staticmethod
    def _heart(p: QPainter, cx: float, cy: float, r: float):
        path = QPainterPath()
        path.moveTo(cx, cy + r * 0.9)
        path.cubicTo(cx - r * 1.4, cy - r * 0.35, cx - r * 0.55, cy - r * 1.2,
                     cx, cy - r * 0.35)
        path.cubicTo(cx + r * 0.55, cy - r * 1.2, cx + r * 1.4, cy - r * 0.35,
                     cx, cy + r * 0.9)
        p.drawPath(path)


_IMAGE_FILTER = (
    "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;"
    "GIF 动图 (*.gif);;所有文件 (*)"
)

_MENU_QSS = (
    "QMenu{background:#141a2e;color:#e8f0ff;border:1px solid #2a3a66;"
    "border-radius:6px;padding:4px;}"
    "QMenu::item{padding:5px 22px;border-radius:4px;}"
    "QMenu::item:selected{background:#24345c;}"
    "QMenu::separator{height:1px;background:#2a3a66;margin:4px 6px;}"
)


# ------------------------------------------------------------------ 模块级
def default_mascot_path() -> str:
    """返回内置 assets/mascot.png 的绝对路径。

    兼容两种运行方式：
    - 源码运行：以本文件所在目录（ui/）为基准取 ../assets/mascot.png；
    - PyInstaller 单文件：资源被解包到 sys._MEIPASS，优先取那里的副本。
    文件缺失时仍返回一个稳定路径，由 set_image() 再做占位兜底。
    """
    rel = os.path.join("assets", "mascot.png")
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = os.path.join(meipass, rel)
        if os.path.isfile(candidate):
            return candidate
    return os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", rel))


def _as_bool(value, fallback: bool) -> bool:
    """容错布尔转换（兼容 JSON 里可能写成的字符串/数字）。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off", ""):
            return False
    return fallback


def _as_int(value, fallback: int, lo: int, hi: int) -> int:
    """容错整数转换并钳制到 [lo, hi]。"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(lo, min(hi, n))


# ------------------------------------------------------------------ 窗口
class MascotWindow(QWidget):
    """可自定义图片的悬浮看板娘窗口。"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config          # duck typing: get / set / save

        # 当前生效的配置值（apply_config 会覆盖）
        self._enabled = False
        self._image_path = ""
        self._scale = DEFAULTS["mascot_scale"]
        self._opacity = DEFAULTS["mascot_opacity"]
        self._x = DEFAULTS["mascot_x"]
        self._y = DEFAULTS["mascot_y"]
        self._click_through = False
        self._on_top = True

        # 图片资源状态
        self._pixmap = QPixmap()      # 静态图（或 GIF 的兜底首帧）
        self._movie = None            # QMovie（GIF）
        self._src_size = QSize()      # 图片原始逻辑尺寸
        self._loaded_path = ""        # 已加载的解析后路径，避免反复重启 GIF
        self._flags_applied = None    # 上次设置的窗口标志

        self._drag_offset = None      # 拖动时鼠标相对窗口左上角的偏移

        self._bubble = MascotBubble()
        self._speech_on = True
        self._bubble_style = DEFAULT_BUBBLE_STYLE
        self._last_say = 0.0          # 上次说话时间（节流用）
        self._last_market = None      # 上次行情播报的（品种, 方向）
        # 被 K 线挡住期间没来得及说的台词，重现时补上
        self._pending_line = ""
        self._pending_at = 0.0
        self._last_greet = 0.0        # 重现问候节流，避免反复横跳刷屏
        self._reappear_reason = "return"
        self._reappear_timer = QTimer(self)
        self._reappear_timer.setSingleShot(True)
        self._reappear_timer.setInterval(280)
        self._reappear_timer.timeout.connect(self._announce_reappear)

        # 场景开关：主窗口通知当前是否允许显示（现在只有图表页允许）
        self._scene_ok = True
        # 与 K 线重叠时整个让位（True = 立绘完全藏起来，把 K 线还给你）
        self._hidden_by_overlap = False
        self._overlap = 0.0
        self._fade = None             # 透明度过渡动画
        # 主窗口的可用区域：立绘钳制在里面，不会跑出软件窗口
        self._host_rect = QRect()

        self.setWindowTitle("看板娘")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(False)
        self.apply_config()

    # ---------------------------------------------------------- 配置读取
    def _cfg(self, key):
        """读一个配置键；缺失/异常时回退到本模块默认值。"""
        default = DEFAULTS[key]
        try:
            value = self.config.get(key, default)
        except Exception:
            value = default
        return default if value is None else value

    def apply_config(self):
        """重新读取配置并应用全部状态；可在运行中反复调用即时生效。"""
        self._enabled = _as_bool(self._cfg("mascot_enabled"), False)
        self._speech_on = _as_bool(self._cfg("mascot_speech"), True)
        style = str(self._cfg("mascot_bubble_style") or DEFAULT_BUBBLE_STYLE)
        self._bubble_style = (style if style in BUBBLE_STYLES
                              else DEFAULT_BUBBLE_STYLE)
        self._bubble.set_style(self._bubble_style)
        self._image_path = str(self._cfg("mascot_image") or "")
        self._scale = _as_int(self._cfg("mascot_scale"),
                              DEFAULTS["mascot_scale"],
                              _SCALE_MIN, _SCALE_MAX)
        self._opacity = _as_int(self._cfg("mascot_opacity"),
                                DEFAULTS["mascot_opacity"],
                                _OPACITY_MIN, _OPACITY_MAX)
        self._x = _as_int(self._cfg("mascot_x"), -1, -100000, 100000)
        self._y = _as_int(self._cfg("mascot_y"), -1, -100000, 100000)
        self._click_through = _as_bool(
            self._cfg("mascot_click_through"), False)
        self._on_top = _as_bool(self._cfg("mascot_on_top"), True)

        # ---- 窗口标志：仅在真正变化时重设（setWindowFlags 会隐藏窗口）----
        flags = Qt.Tool | Qt.FramelessWindowHint
        if self._on_top:
            flags |= Qt.WindowStaysOnTopHint
        if flags != self._flags_applied:
            self.setWindowFlags(flags)
            self._flags_applied = flags
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents,
                          self._click_through)
        self._apply_opacity()

        # ---- 图片：路径没变就不重新加载，避免 GIF 被反复重启/闪烁 ----
        if self._loaded_path != self._resolve_path(self._image_path):
            self.set_image(self._image_path)
        else:
            self._apply_geometry()      # scale 变化也要重算尺寸/位置

        # ---- 显隐 ----
        self._sync_visible()

    # ---------------------------------------------------------- 显隐 / 透明度
    def _sync_visible(self):
        """只有「开启 + 场景允许 + 没有被 K 线压住」时才真正显示。"""
        if self._enabled and self._scene_ok and not self._hidden_by_overlap:
            self.show()
            self.raise_()
            self._apply_opacity()
        else:
            self._bubble.dismiss()
            self._reappear_timer.stop()
            self.hide()

    def set_scene_visible(self, visible: bool):
        """主窗口通知：现在是否允许露出看板娘（只有 K 线页允许）。"""
        visible = bool(visible)
        if visible == self._scene_ok:
            return
        was_visible = self.isVisible()
        self._scene_ok = visible
        self._sync_visible()
        if visible and not was_visible:
            self._schedule_reappear("greet")

    def is_scene_active(self) -> bool:
        return bool(self._scene_ok and self._enabled)

    def set_host_rect(self, rect):
        """主窗口告知自己的范围：立绘被钳制在内，不会跑出软件窗口。"""
        if rect is None or not rect.isValid() or rect.isEmpty():
            self._host_rect = QRect()
            return
        self._host_rect = QRect(rect)

    def _clamp_into_host(self, x: int, y: int):
        """把左上角坐标钳进主窗口；主窗口未知时原样返回。"""
        if self._host_rect.isEmpty():
            return x, y
        x = min(max(x, self._host_rect.left()),
                self._host_rect.right() - self.width())
        y = min(max(y, self._host_rect.top()),
                self._host_rect.bottom() - self.height())
        return x, y

    def set_overlap(self, ratio: float):
        """立绘与 K 线重叠时整个让位：压住 K 线就完全消失，离开后重新出现。

        之前按重叠比例线性降不透明度，但压到一半时立绘半透明地叠在
        K 线上，两边都看不清。现在只要重叠超过 6% 就把立绘整个藏起来
        （160ms 快速淡出），不再重叠时再淡回来。
        """
        try:
            ratio = max(0.0, min(1.0, float(ratio)))
        except (TypeError, ValueError):
            ratio = 0.0
        hidden = ratio >= 0.06
        self._overlap = ratio
        if hidden == self._hidden_by_overlap:
            return
        self._hidden_by_overlap = hidden
        if hidden:
            self._reappear_timer.stop()
            self._fade_to(0.0, 160, then=self._hide_for_overlap)
        else:
            self._sync_visible()          # 重新 show + 淡回原不透明度
            self._schedule_reappear("return")

    def _hide_for_overlap(self):
        self._bubble.dismiss()
        self.hide()

    def _schedule_reappear(self, reason: str):
        """重新露面后补一句台词；延时等几何 / 显隐状态稳定。"""
        if not self._enabled or not self._speech_on or not self._scene_ok:
            return
        self._reappear_reason = reason
        self._reappear_timer.stop()
        self._reappear_timer.start()

    def _announce_reappear(self):
        """隐藏→重现时开口：优先补说让位期间攒下的台词，否则打招呼。"""
        if (not self.isVisible() or self._hidden_by_overlap
                or not self._enabled or not self._speech_on):
            return
        now = time.time()
        line = ""
        if self._pending_line and now - self._pending_at < 90.0:
            line = self._pending_line
        self._pending_line = ""
        self._pending_at = 0.0
        # 刚进图表页往往已经在说「打开 K 线」那句，别抢话覆盖它
        if self._bubble.is_talking():
            return
        if not line:
            if now - self._last_greet < 8.0:
                return
            pool = SPEECH.get(self._reappear_reason) or SPEECH["greet"]
            line = random.choice(pool)
        if self.say(line, 4600):
            self._last_greet = now

    def _target_opacity(self) -> float:
        return self._opacity / 100.0

    def _fade_to(self, target: float, ms: int, then=None):
        if self._fade is not None:
            self._fade.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(float(self.windowOpacity()))
        anim.setEndValue(float(max(0.0, min(1.0, target))))
        anim.setDuration(max(1, int(ms)))
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.valueChanged.connect(
            lambda v: self.setWindowOpacity(max(0.0, min(1.0, float(v)))))
        if then is not None:
            anim.finished.connect(then)
        anim.finished.connect(self._fade_done)
        self._fade = anim
        anim.start()

    def _apply_opacity(self, animate: bool = False):
        target = self._target_opacity()
        if not animate:
            if self._fade is not None:
                self._fade.stop()
                self._fade = None
            self.setWindowOpacity(target)
            return
        self._fade_to(target, 220)

    def _fade_done(self):
        self._fade = None

    # ---------------------------------------------------------- 说话
    def say(self, text: str, ms: int = 4200) -> bool:
        """冒一个气泡。看板娘没开、或关掉了互动台词，就什么也不做。

        被 K 线挡住而暂时让位时，台词会先排队，重现时补说（返回 True
        表示这一句已被接收，行情播报不会反复触发同一句）。
        """
        if not self._enabled or not self._speech_on or not text:
            return False
        if self._hidden_by_overlap or not self.isVisible():
            # 只补「K 线遮挡」这种临时隐藏；列表页 / 设置页的台词直接
            # 丢弃，免得下次进图表冒出一句已经过时的行情。
            if self._scene_ok and self._hidden_by_overlap:
                self._pending_line = text
                self._pending_at = time.time()
                self._last_say = self._pending_at
                return True
            return False
        self._bubble.say(text, self.frameGeometry(), ms)
        self._last_say = time.time()
        return True

    def react(self, kind: str, **fields) -> str:
        """按事件挑一句台词说出来；返回说出口的那句（没说返回空串）。"""
        pool = SPEECH.get(kind) or []
        if not pool:
            return ""
        line = random.choice(pool)
        if fields:
            try:
                line = line.format(**fields)
            except (KeyError, IndexError, ValueError):
                pass
        return line if self.say(line) else ""

    def react_market(self, symbol: str, change_pct: float,
                     name: str = "", cooldown: float = 75.0) -> str:
        """行情触发：涨跌够大且方向和上次不同才说话，避免刷屏。"""
        if not self._enabled or not self._speech_on:
            return ""
        if abs(change_pct) < 2.0:
            return ""
        if time.time() - self._last_say < cooldown:
            return ""
        direction = "up" if change_pct >= 0 else "down"
        big = abs(change_pct) >= 6.0
        key = (symbol, direction, big)
        if key == self._last_market:
            return ""
        kind = ("big_up" if direction == "up" else "big_down") if big \
            else direction
        line = self.react(kind, sym=symbol, name=name or symbol,
                          pct=f"{change_pct:+.2f}%")
        # 只有台词真的被接收（说出口或排队）才算播报过；否则隐藏期间
        # 会把这一句悄悄「用掉」，重现后同方向就再也不开口了。
        if line:
            self._last_market = key
        return line

    # ---------------------------------------------------------- 图片加载
    @staticmethod
    def _resolve_path(image_path) -> str:
        """空路径 / 不存在的文件 -> 内置默认形象。"""
        path = str(image_path or "").strip()
        if path and os.path.isfile(path):
            return path
        return default_mascot_path()

    def _stop_movie(self):
        """停止并释放旧的 QMovie（不启动任何线程）。"""
        movie = self._movie
        self._movie = None
        if movie is None:
            return
        try:
            movie.stop()
        except RuntimeError:
            pass
        movie.deleteLater()

    def _load_source(self, path):
        """加载一个图片文件 -> (QPixmap, QMovie|None, QSize)；失败返回 None。

        GIF 用 QMovie 播放（自动循环）；其余静态格式用 QPixmap。
        """
        if not path or not os.path.isfile(path):
            return None

        try:
            reader = QImageReader(path)
            reader.setDecideFormatFromContent(True)
            size = reader.size()
        except Exception:
            size = QSize()

        ext = os.path.splitext(path)[1].lower()
        if ext in _GIF_EXTS:
            try:
                movie = QMovie(path)
                movie.setParent(self)
                if movie.isValid():
                    if not (size.isValid() and not size.isEmpty()):
                        size = movie.frameRect().size()
                    if not (size.isValid() and not size.isEmpty()):
                        size = QSize(220, 320)
                    return QPixmap(), movie, size
                movie.setParent(None)
                movie.deleteLater()
            except Exception:
                pass
            return None

        pixmap = QPixmap(path)
        if pixmap.isNull():
            return None
        if not (size.isValid() and not size.isEmpty()):
            size = pixmap.size()
        return pixmap, None, size

    @staticmethod
    def _placeholder_source():
        """内置图也缺失时的内存占位（保证 set_image 永不崩、尺寸有效）。"""
        w, h = 220, 320
        pm = QPixmap(w, h)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        g = QLinearGradient(0, 60, w, 260)
        g.setColorAt(0.0, QColor(0, 229, 255))
        g.setColorAt(1.0, QColor(255, 45, 214))
        p.setPen(QPen(QBrush(g), 7))
        p.setBrush(QColor(18, 24, 58, 210))
        p.drawRoundedRect(QRectF(20, 60, w - 40, h - 120), 26, 26)
        for cx, top, bot, col in ((80, 130, 180, QColor(255, 86, 104)),
                                  (110, 110, 160, QColor(46, 220, 132)),
                                  (140, 95, 145, QColor(46, 220, 132))):
            p.setPen(QPen(col, 3))
            p.drawLine(int(cx), int(top - 12), int(cx), int(bot + 12))
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(cx - 9, top, 18, bot - top), 3, 3)
        p.end()
        return pm, None, QSize(w, h)

    def set_image(self, path):
        """设置形象图片。

        支持 PNG/JPG/WebP/BMP 静态图与 GIF 动图；等比缩放保持透明。
        path 为空字符串或文件不存在时回退内置默认形象；内置图也读不到时
        使用内存占位图（不会抛异常）。
        """
        self._stop_movie()
        resolved = self._resolve_path(path)
        loaded = self._load_source(resolved)
        if loaded is None and resolved != default_mascot_path():
            resolved = default_mascot_path()
            loaded = self._load_source(resolved)
        if loaded is None:
            loaded = self._placeholder_source()
            resolved = "<placeholder>"

        self._pixmap, movie, self._src_size = loaded
        self._movie = movie
        self._loaded_path = resolved

        if movie is not None:
            movie.frameChanged.connect(self._on_frame_changed)
            movie.finished.connect(self._on_movie_finished)
            movie.start()

        self._apply_geometry()
        self.update()

    # ---------------------------------------------------------- 几何
    @staticmethod
    def _screen_geometry() -> QRect:
        """主屏可用区域；offscreen / 无 QScreen 时给一个安全兜底。"""
        screen = QApplication.primaryScreen()
        if screen is None:
            screens = QApplication.screens()
            screen = screens[0] if screens else None
        if screen is not None:
            g = screen.availableGeometry()
            if g.isValid() and not g.isEmpty():
                return QRect(g)
        return QRect(0, 0, 1920, 1080)

    def _apply_geometry(self):
        """窗口尺寸 = 图片原始比例 × scale，等比且最大不超过屏幕 1/3。"""
        src = self._src_size
        if not src.isValid() or src.isEmpty():
            src = QSize(220, 320)
        ratio = self._scale / 100.0
        w = max(1, int(round(src.width() * ratio)))
        h = max(1, int(round(src.height() * ratio)))

        avail = self._screen_geometry()
        max_w = max(1, int(avail.width() / 3))
        max_h = max(1, int(avail.height() / 3))
        if w > max_w or h > max_h:
            k = min(max_w / w, max_h / h)
            w = max(1, int(w * k))
            h = max(1, int(h * k))
        self.resize(w, h)

        if self._x < 0 or self._y < 0:
            nx = avail.x() + avail.width() - w - _MARGIN
            ny = avail.y() + avail.height() - h - _MARGIN
        else:
            nx, ny = self._x, self._y
        # 主窗口给了范围就钳进去：立绘不出软件窗口（只在 K 线页出现）
        nx, ny = self._clamp_into_host(nx, ny)
        self.move(nx, ny)
        self._bubble.follow(self.frameGeometry())

    # ---------------------------------------------------------- 绘制
    def _current_pixmap(self) -> QPixmap:
        if self._movie is not None:
            pm = self._movie.currentPixmap()
            if not pm.isNull():
                return pm
        return self._pixmap

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        pm = self._current_pixmap()
        if not pm.isNull():
            # 窗口本身已按图片比例计算，这里再保持等比居中绘制，抗锯齿
            scaled = pm.scaled(self.size(), Qt.KeepAspectRatio,
                               Qt.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
        p.end()

    def _on_frame_changed(self, _frame):
        """GIF 帧更新时刷新画面。"""
        if self.sender() is self._movie:
            self.update()

    def _on_movie_finished(self):
        """GIF 未声明无限循环时，播完自动重头播放，保证「自动循环」。"""
        movie = self.sender()
        if movie is not None and movie is self._movie:
            movie.start()

    # ---------------------------------------------------------- 拖动
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._click_through:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self._press_at = event.globalPosition().toPoint()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._drag_offset is not None and not self._click_through
                and (event.buttons() & Qt.LeftButton)):
            pos = event.globalPosition().toPoint() - self._drag_offset
            # 拖动也钳在主窗口里，不会把立绘拖到软件外面
            x, y = self._clamp_into_host(pos.x(), pos.y())
            self.move(x, y)
            self._bubble.follow(self.frameGeometry())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            # 松手把位置写回配置并落盘
            self.config.set("mascot_x", self.x())
            self.config.set("mascot_y", self.y())
            self.config.save()
            self._bubble.follow(self.frameGeometry())
            # 没怎么移动 = 单击 -> 说句话
            press = getattr(self, "_press_at", None)
            if press is not None and \
                    (event.globalPosition().toPoint() - press).manhattanLength() < 5:
                self.react("click")
            self._press_at = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # ---------------------------------------------------------- 右键菜单
    def contextMenuEvent(self, event):
        if self._click_through:
            return                  # 穿透时本窗口收不到鼠标事件（兜底）
        menu = QMenu(self)
        menu.setStyleSheet(_MENU_QSS)

        act_change = menu.addAction("更换图片…")
        menu.addSeparator()
        act_bigger = menu.addAction("放大 +10%（当前 %d%%）" % self._scale)
        act_smaller = menu.addAction("缩小 -10%（当前 %d%%）" % self._scale)
        menu.addSeparator()
        act_op_up = menu.addAction(
            "不透明度 +10（当前 %d%%）" % self._opacity)
        act_op_dn = menu.addAction(
            "不透明度 -10（当前 %d%%）" % self._opacity)
        menu.addSeparator()
        act_through = menu.addAction("点击穿透")
        act_through.setCheckable(True)
        act_through.setChecked(self._click_through)
        menu.addSeparator()
        act_default = menu.addAction("恢复默认图片")
        act_hide = menu.addAction("隐藏")

        action = menu.exec(event.globalPos())
        if action is None:
            return
        if action is act_change:
            self._choose_image()
        elif action is act_bigger:
            self._write("mascot_scale",
                        min(_SCALE_MAX, self._scale + 10))
        elif action is act_smaller:
            self._write("mascot_scale",
                        max(_SCALE_MIN, self._scale - 10))
        elif action is act_op_up:
            self._write("mascot_opacity",
                        min(_OPACITY_MAX, self._opacity + 10))
        elif action is act_op_dn:
            self._write("mascot_opacity",
                        max(_OPACITY_MIN, self._opacity - 10))
        elif action is act_through:
            self._write("mascot_click_through", not self._click_through)
        elif action is act_default:
            self._write("mascot_image", "")
        elif action is act_hide:
            self.hide()             # 临时隐藏，不改写启用开关

    def _write(self, key, value):
        """写配置 -> 落盘 -> 重新应用（即时生效）。"""
        self.config.set(key, value)
        self.config.save()
        self.apply_config()

    def _choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择看板娘图片", "", _IMAGE_FILTER, "",
            QFileDialog.DontUseNativeDialog)   # 非原生：无 GUI 环境也不卡死
        if path:
            self._write("mascot_image", path)
