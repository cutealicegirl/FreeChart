# -*- coding: utf-8 -*-
"""图标：赛博朋克主 logo、品种原图标、托盘实时价格图标。

- 主图标用 assets/app_icon.png（AI 生成的霓虹徽标 + 程序化暗底描边），
  另导出标准 ICO 供 EXE 文件图标使用；源码运行与 PyInstaller 都兼容。
- 加密货币直接显示 assets/coins/*.png 里的官方原图：256x256、透明背景、
  不再套白色圆底；极暗的 logo 在构建期加了柔和外发光，深色界面上也看得见。
- 所有图标按屏幕设备像素比绘制（125%/150% 缩放不会二次拉伸发虚）。
- 股票用专属字徽：哈希渐变底 + 中文名首字（美股用代码字母），
  每只股票颜色唯一；外圈市场色细环区分 A 股 / 港股 / 美股。
- 托盘图标直接绘制紧凑实时价格（红涨绿跌），保证 16x16 下可读。
"""
import hashlib
import math
import os
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QLinearGradient,
                           QPainter, QPen, QPixmap, QPolygonF)

from ui.theme import (C_ACCENT, C_BG_BASE, C_DOWN, C_TEXT_DIM,
                      C_TEXT_MAIN, C_UP)

MARKET_COLORS = {
    "crypto": "#f7931a",
    "cn": "#f6465d",
    "hk": "#f0b90b",
    "us": "#4b9cff",
}

_PIX_CACHE = {}
_APP_CACHE = {}


def market_of(symbol: str) -> str:
    if symbol.startswith(("SH:", "SZ:")):
        return "cn"
    if symbol.startswith("HK:"):
        return "hk"
    if symbol.startswith("US:"):
        return "us"
    return "crypto"


def display_code(symbol: str) -> str:
    # 链上合约品种代码是 ONCHAIN:<44 位地址>，直接显示会撑破布局；
    # 用短地址兜底（主窗口创建行时会传入真实代币代码覆盖）。
    if isinstance(symbol, str) and symbol.startswith("ONCHAIN:"):
        addr = symbol[len("ONCHAIN:"):]
        return addr[:6] + "…" + addr[-4:] if len(addr) > 14 else addr
    return symbol.split(":")[-1] if ":" in symbol else symbol


def _root() -> str:
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        return bundle
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _asset_dir() -> str:
    return os.path.join(_root(), "assets", "coins")


def _user_icon_dir() -> str:
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "FreeChart", "icons")


def _app_icon_file() -> str:
    return os.path.join(_root(), "assets", "app_icon.png")


def _app_ico_file() -> str:
    return os.path.join(_root(), "assets", "app_icon.ico")


# ================= 多套应用图标（设置里可选） =================
_APP_ICON_SUBDIR = ("assets", "app_icons")
_ACTIVE_ICON = "classic"
# 内置清单（manifest.json 读不到时的兜底，顺序即设置里的顺序）
_ICON_FALLBACK = [
    ("classic", "经典 · 赛博徽标"), ("neon", "霓虹 C"),
    ("candle", "K 线蜡烛"), ("orbit", "轨道芯片"),
    ("wave", "上升波浪"), ("hex", "六边形币"),
]


def app_icon_dir() -> str:
    return os.path.join(_root(), *_APP_ICON_SUBDIR)


def app_icon_keys():
    """[(key, 中文标签)]，读 assets/app_icons/manifest.json。"""
    path = os.path.join(app_icon_dir(), "manifest.json")
    try:
        import json
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        out = []
        for key, meta in raw.items():
            label = ""
            if isinstance(meta, dict):
                label = str(meta.get("label") or "")
            elif isinstance(meta, str):
                label = meta
            if os.path.isfile(os.path.join(app_icon_dir(), f"{key}.ico")):
                out.append((key, label or key))
        if out:
            return out
    except (OSError, ValueError):
        pass
    return list(_ICON_FALLBACK)


def set_app_icon_key(key: str) -> str:
    """切换当前应用图标方案，返回实际生效的 key。"""
    global _ACTIVE_ICON
    valid = {k for k, _ in app_icon_keys()}
    _ACTIVE_ICON = key if key in valid else "classic"
    return _ACTIVE_ICON


def app_icon_key() -> str:
    return _ACTIVE_ICON


def app_icon_ico_path(key: str = "") -> str:
    """指定方案的 ICO 路径；不存在时回退到内置 app_icon.ico。"""
    key = key or _ACTIVE_ICON
    p = os.path.join(app_icon_dir(), f"{key}.ico")
    return p if os.path.isfile(p) else _app_ico_file()


def app_icon_png_path(key: str = "") -> str:
    key = key or _ACTIVE_ICON
    p = os.path.join(app_icon_dir(), f"{key}.png")
    return p if os.path.isfile(p) else _app_icon_file()


def app_icon_pixmap(size: int = 256, key: str = "") -> QPixmap:
    """按方案取一张位图（用于预览、托盘、任务栏重绘）。"""
    path = app_icon_png_path(key)
    pm = QPixmap(path) if os.path.isfile(path) else QPixmap()
    if pm.isNull():
        return app_logo(size)
    return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def icon_file(symbol: str) -> str:
    """返回已存在的图标文件（加密官方图 / 股票真实 logo），没有返回空串。"""
    if market_of(symbol) != "crypto":
        from data import stock_logo          # 延迟导入，避免启动即拉网络栈
        return stock_logo.local_file(symbol)
    name = display_code(symbol).lower() + ".png"
    for d in (_asset_dir(), _user_icon_dir()):
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.path.getsize(p) > 300:
            return p
    return ""


def invalidate_symbol(symbol: str):
    """清掉某品种的像素缓存（真实 logo 落盘后立即生效）。"""
    key = symbol.upper()
    for k in [k for k in _PIX_CACHE if k[0].upper() == key]:
        _PIX_CACHE.pop(k, None)


# ---- 股票名称登记（用于字徽：A股/港股取中文名首字）----
_NAME_MAP = {}
_NAMES_LOADED = False


def register_symbol_name(symbol: str, name: str):
    """登记品种显示名（如「腾讯控股」），字徽立即用上并刷新缓存。"""
    if not symbol or not name:
        return
    global _NAMES_LOADED
    _NAMES_LOADED = True      # 外部已提供名称，无需再读 top300.json
    key = symbol.upper()
    if _NAME_MAP.get(key) == name:
        return
    _NAME_MAP[key] = name
    for k in [k for k in _PIX_CACHE if k[0].upper() == key]:
        _PIX_CACHE.pop(k, None)


def stock_name(symbol: str) -> str:
    """品种中文名：优先运行期登记，其次随包的 top300.json。"""
    key = symbol.upper()
    if key in _NAME_MAP:
        return _NAME_MAP[key]
    global _NAMES_LOADED
    if not _NAMES_LOADED:
        _NAMES_LOADED = True
        try:
            import json
            path = os.path.join(_root(), "data", "top300.json")
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for mkt in ("cn", "hk", "us"):
                for item in data.get(mkt, []):
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        _NAME_MAP.setdefault(
                            str(item[0]).upper(), str(item[1]))
        except Exception:
            pass
    return _NAME_MAP.get(key, "")


def stock_badge(symbol: str, name: str, size: int = 30) -> QPixmap:
    """股票字徽：哈希渐变圆角底 + 中文名首字（美股用代码字母）。

    股票没有可直连的官方 logo 图床（Clearbit/Google favicon 在
    国内网络不可达），改用确定性生成的字徽：每只股票颜色由
    代码哈希唯一决定，一眼可区分；外圈市场色细环标识 A股/港股/美股。
    """
    mkt = market_of(symbol)
    code = display_code(symbol)
    text = ""
    if name:
        name = name.strip()
        if any("\u4e00" <= ch <= "\u9fff" for ch in name):
            text = next(ch for ch in name
                        if "\u4e00" <= ch <= "\u9fff")
    if not text:
        text = code[:4].upper()
    digest = hashlib.md5(symbol.upper().encode("utf-8")).hexdigest()
    hue = int(digest[:4], 16) % 360
    dpr = _dpr()
    px = max(1, int(round(size * dpr)))
    out = QPixmap(px, px)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    inset = px * 0.04
    rect = QRectF(inset, inset, px - 2 * inset, px - 2 * inset)
    radius = px * 0.24
    g = QLinearGradient(0, 0, px, px)
    g.setColorAt(0, QColor.fromHsl(hue, 165, 52))
    g.setColorAt(1, QColor.fromHsl((hue + 42) % 360, 200, 30))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawRoundedRect(rect, radius, radius)
    # 顶部高光，让底色有玻璃质感
    hl = QLinearGradient(0, 0, 0, px * 0.55)
    hl.setColorAt(0, QColor(255, 255, 255, 46))
    hl.setColorAt(1, QColor(255, 255, 255, 0))
    p.setBrush(QBrush(hl))
    p.drawRoundedRect(rect, radius, radius)
    # 市场色细环
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(MARKET_COLORS.get(mkt, C_ACCENT)),
                  max(1.3, px * 0.045)))
    p.drawRoundedRect(rect, radius, radius)
    cn = len(text) == 1 and "\u4e00" <= text <= "\u9fff"
    if cn:
        f = QFont("Microsoft YaHei", weight=QFont.Bold)
        f.setPixelSize(max(6, int(px * 0.5)))
    else:
        f = QFont("IBM Plex Mono SemiBold")
        f.setBold(True)
        f.setPixelSize(max(5, int(px * (0.46 if len(text) <= 2
                                         else 0.38 if len(text) == 3
                                         else 0.30))))
    p.setFont(f)
    p.setPen(QColor("#f4f6fb"))
    p.drawText(rect, Qt.AlignCenter, text)
    p.end()
    out.setDevicePixelRatio(dpr)
    return out


def _fallback_logo(size: int, accent: str) -> QPixmap:
    """资源缺失时的程序化兜底：发光 C + 闪电 + 霓虹圆角框。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 64.0
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#0a1020"))
    p.drawRoundedRect(QRectF(0.5 * s, 0.5 * s, 63 * s, 63 * s),
                      15 * s, 15 * s)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor(0, 229, 255))
    g.setColorAt(0.5, QColor(123, 92, 255))
    g.setColorAt(1, QColor(255, 43, 214))
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QBrush(g), 2.4 * s))
    p.drawRoundedRect(QRectF(2 * s, 2 * s, 60 * s, 60 * s),
                      13.5 * s, 13.5 * s)
    p.setPen(QPen(QColor(0, 229, 255), 7 * s, Qt.SolidLine, Qt.RoundCap))
    p.drawArc(QRectF(15 * s, 15 * s, 34 * s, 34 * s), 50 * 16, 260 * 16)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(accent))
    p.drawPolygon(QPolygonF([
        QPointF(35 * s, 18 * s), QPointF(25 * s, 34 * s),
        QPointF(31 * s, 34 * s), QPointF(28 * s, 46 * s),
        QPointF(41 * s, 29 * s), QPointF(34 * s, 29 * s)]))
    p.end()
    return pm


def app_logo(size: int = 64, accent: str = C_ACCENT) -> QPixmap:
    """程序主图标（窗口标题栏 / 托盘 / 品种徽章共用）。"""
    path = _app_icon_file()
    if os.path.isfile(path):
        src = _APP_CACHE.get(path)
        if src is None:
            src = QPixmap(path)
            _APP_CACHE[path] = src
        if not src.isNull():
            return src.scaled(size, size, Qt.IgnoreAspectRatio,
                              Qt.SmoothTransformation)
    return _fallback_logo(size, accent)


def app_icon() -> QIcon:
    """当前方案的应用图标（桌面 / 托盘 / 标题栏统一使用）。"""
    ico = app_icon_ico_path()
    if os.path.isfile(ico):
        return QIcon(ico)          # 多尺寸，任务栏/EXE 都清晰
    return QIcon(app_logo(64))


def _dpr() -> float:
    """当前屏幕的设备像素比：图标按物理像素绘制，125%/150% 下不糊。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        sc = app.primaryScreen()
        if sc is not None:
            try:
                return max(1.0, min(2.0, float(sc.devicePixelRatio() or 1.0)))
            except Exception:
                pass
    return 1.0


def _square(src: QPixmap, size: int, dpr: float) -> QPixmap:
    """等比缩放到 size×size 的透明方块，并按物理像素标记。"""
    px = max(1, int(round(size * dpr)))
    scaled = src.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    out = QPixmap(px, px)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.drawPixmap((px - scaled.width()) // 2,
                 (px - scaled.height()) // 2, scaled)
    p.end()
    out.setDevicePixelRatio(dpr)
    return out


def symbol_color(symbol: str) -> QColor:
    key = market_of(symbol)
    if key != "crypto":
        return QColor(MARKET_COLORS[key])
    digest = hashlib.md5(symbol.encode("utf-8")).hexdigest()
    hue = int(digest[:2], 16) % 360
    return QColor.fromHsl(hue, 130, 92)


def project_badge(symbol: str, size: int = 30) -> QPixmap:
    """股票 / 无官方 logo 的品种：直接用项目原图标，不再套白色圆底。

    主图标本身是深色圆角底 + 霓虹描边，在深色列表里足够醒目；
    只在外圈加一圈市场色细环用于区分 A 股 / 港股 / 美股。
    """
    key = market_of(symbol)
    color = MARKET_COLORS.get(key, C_ACCENT)
    dpr = _dpr()
    px = max(1, int(round(size * dpr)))
    out = QPixmap(px, px)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    inset = px * 0.055
    logo = app_logo(max(32, px)).scaled(
        int(px - 2 * inset), int(px - 2 * inset),
        Qt.KeepAspectRatio, Qt.SmoothTransformation)
    p.drawPixmap(int(inset), int(inset), logo)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(color), max(1.4, px * 0.055)))
    r = inset * 0.5
    p.drawRoundedRect(QRectF(inset * 0.5, inset * 0.5,
                             px - inset, px - inset),
                      px * 0.22, px * 0.22)
    p.end()
    out.setDevicePixelRatio(dpr)
    return out


def _stock_square(src: QPixmap, size: int, dpr: float) -> QPixmap:
    """股票真实 logo：等比缩放居中，并按明暗自动垫对比底。

    - logo 自带满幅底色（腾讯蓝方块、阿里橙方块）：直接铺满，不加底；
    - 透明底深色 logo（茅台红蓝标、CATL 深蓝字）：垫淡白底，避免看不见；
    - 透明底浅色/白色 logo（如白字标）：垫深色底，避免糊成一块白斑。
    """
    px = max(1, int(round(size * dpr)))
    out = QPixmap(px, px)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    probe = src.scaled(8, 8, Qt.IgnoreAspectRatio,
                       Qt.SmoothTransformation).toImage()
    opaque, lum = 0, 0.0
    for y in range(probe.height()):
        for x in range(probe.width()):
            c = probe.pixelColor(x, y)
            if c.alpha() > 40:
                opaque += 1
                lum += c.lightness()
    coverage = opaque / max(1, probe.width() * probe.height())
    mean = lum / max(1, opaque)
    if coverage < 0.55:
        # 透明底 logo：垫一层对比色圆角底，深色/白色都清晰
        plate = (QColor(255, 255, 255, 40) if mean < 150
                 else QColor(8, 10, 14, 170))
        p.setPen(Qt.NoPen)
        p.setBrush(plate)
        p.drawRoundedRect(QRectF(0, 0, px, px), px * 0.24, px * 0.24)
        inner = int(px * 0.76)
        scaled = src.scaled(inner, inner, Qt.KeepAspectRatio,
                            Qt.SmoothTransformation)
    else:
        scaled = src.scaled(px, px, Qt.KeepAspectRatio,
                            Qt.SmoothTransformation)
    p.drawPixmap((px - scaled.width()) // 2,
                 (px - scaled.height()) // 2, scaled)
    p.end()
    out.setDevicePixelRatio(dpr)
    return out


def symbol_icon(symbol: str, size: int = 30) -> QPixmap:
    """品种图标：加密货币官方原图；股票真实公司 logo；缺失才用字徽/项目徽章。"""
    dpr = _dpr()
    key = (symbol, size, dpr)
    cached = _PIX_CACHE.get(key)
    if cached is not None:
        return cached
    path = icon_file(symbol)
    if path:
        src = QPixmap(path)
        if not src.isNull():
            pm = (_square(src, size, dpr)
                  if market_of(symbol) == "crypto"
                  else _stock_square(src, size, dpr))
            _PIX_CACHE[key] = pm
            return pm
    if market_of(symbol) != "crypto":
        # 股票：每只一个专属字徽（中文名首字 / 美股代码字母）
        pm = stock_badge(symbol, stock_name(symbol), size)
    else:
        pm = project_badge(symbol, size)
    _PIX_CACHE[key] = pm
    return pm


def compact_price(price: float) -> str:
    """托盘图标上的紧凑价格：67.9k / 1.24 / 0.0832。"""
    if price <= 0:
        return "--"
    if price >= 1_000_000:
        return f"{price / 1_000_000:.2f}M"
    if price >= 10_000:
        return f"{price / 1000:.1f}k"
    if price >= 1000:
        return f"{price:,.0f}"
    if price >= 1:
        return f"{price:.2f}"
    if price >= 0.01:
        return f"{price:.4f}"
    return f"{price:.6f}"


def tray_price_icon(symbol: str, price: float, change: float,
                    size: int = 64) -> QIcon:
    """托盘图标 = 选定品种的实时紧凑价格（红涨绿跌）。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    up = change >= 0
    accent = QColor(C_UP if up else C_DOWN)
    p.setBrush(QColor(C_BG_BASE))
    p.setPen(QPen(accent, max(2, size / 20)))
    p.drawRoundedRect(QRectF(1, 1, size - 2, size - 2),
                      size * 0.16, size * 0.16)
    txt = compact_price(price)
    scale = {1: 0.50, 2: 0.50, 3: 0.46, 4: 0.40, 5: 0.34,
             6: 0.29, 7: 0.25}.get(len(txt), 0.22)
    f = QFont("IBM Plex Mono SemiBold", max(8, int(size * scale)))
    f.setBold(True)
    p.setFont(f)
    p.setPen(accent)
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, txt)
    p.setBrush(accent)
    p.setPen(Qt.NoPen)
    cx, cy, w = size / 2, size * 0.13, size * 0.09
    if up:
        tri = QPolygonF([QPointF(cx, cy - w / 2),
                         QPointF(cx - w, cy + w / 2),
                         QPointF(cx + w, cy + w / 2)])
    else:
        tri = QPolygonF([QPointF(cx, cy + w / 2),
                         QPointF(cx - w, cy - w / 2),
                         QPointF(cx + w, cy - w / 2)])
    p.drawPolygon(tri)
    p.end()
    return QIcon(pm)


def nav_glyph(kind: str, size: int = 22, color: str = "#f0b90b") -> QPixmap:
    """底部导航图标（自绘，不依赖字体里的特殊符号）。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), max(1.6, size / 13))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    s = float(size)
    if kind == "list":
        for i in range(3):
            y = s * (0.28 + i * 0.22)
            p.drawLine(QPointF(s * 0.20, y), QPointF(s * 0.80, y))
    elif kind == "chart":
        p.drawPolyline(QPolygonF([
            QPointF(s * 0.18, s * 0.72), QPointF(s * 0.40, s * 0.46),
            QPointF(s * 0.58, s * 0.60), QPointF(s * 0.82, s * 0.28)]))
    elif kind == "gear":
        p.drawEllipse(QPointF(s / 2, s / 2), s * 0.25, s * 0.25)
        for deg in range(0, 360, 45):
            rad = math.radians(deg)
            p.drawLine(
                QPointF(s / 2 + math.cos(rad) * s * 0.31,
                        s / 2 + math.sin(rad) * s * 0.31),
                QPointF(s / 2 + math.cos(rad) * s * 0.41,
                        s / 2 + math.sin(rad) * s * 0.41))
    p.end()
    return pm


def tray_app_icon(change: float = 0.0, size: int = 64,
                  key: str = "") -> QIcon:
    """托盘图标 = 当前程序图标，右下角叠一个红/绿涨跌点。

    口径跟桌面 / 任务栏图标完全一致（同一个 app_icons 方案），只在角上
    加一个小圆点表示方向，避免托盘里出现一套「长得不像本程序」的图标。
    """
    base = app_icon_pixmap(size, key)
    if base.isNull() or base.width() != size:
        canvas = QPixmap(size, size)
        canvas.fill(Qt.transparent)
        if not base.isNull():
            scaled = base.scaled(size, size, Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation)
            x = (size - scaled.width()) // 2
            y = (size - scaled.height()) // 2
            p = QPainter(canvas)
            p.drawPixmap(x, y, scaled)
            p.end()
        base = canvas
    pm = QPixmap(base)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    accent = QColor(C_UP if change >= 0 else C_DOWN)
    d = size * 0.38
    r = QRectF(size - d - size * 0.02, size - d - size * 0.02, d, d)
    p.setPen(QPen(QColor(C_BG_BASE), max(1.5, size * 0.055)))
    p.setBrush(accent)
    p.drawEllipse(r)
    p.end()
    return QIcon(pm)


def search_glyph(size: int = 18, color: str = "#f0b90b") -> QPixmap:
    """搜索框放大镜（自绘，避免依赖字体里的特殊符号）。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(color), max(1.4, size / 11)))
    p.setBrush(Qt.NoBrush)
    r = size * 0.30
    p.drawEllipse(QPointF(size * 0.42, size * 0.42), r, r)
    p.drawLine(QPointF(size * 0.65, size * 0.65),
               QPointF(size * 0.90, size * 0.90))
    p.end()
    return pm
