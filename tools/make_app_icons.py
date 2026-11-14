# -*- coding: utf-8 -*-
"""开发期工具：生成 6 套应用图标资源（运行时只读成品，业务代码不依赖本脚本）。

仅写出两个位置：
    tools/make_app_icons.py        （本文件）
    assets/app_icons/*             （全部产物）

绘制完全使用 PySide6 的 QPainter（项目已依赖），设置 QT_QPA_PLATFORM=offscreen，
因此无 GUI / 无显示器环境也能跑；ICO 优先用 Pillow 的 save(sizes=[...]) 生成，
Pillow 缺失时自动回退到纯 QImage + struct 的 32 位 BMP-ICO 写入，保证「可重复运行、
不依赖网络」。Pillow 若可用还会用于内置校验。

运行：python tools/make_app_icons.py

产物：
    <key>.png            256x256 RGBA（圆角方形深色底 + 霓虹描边 + 几何主体，无文字）
    <key>.ico            Windows ICO，含 16/32/48/64/128/256 多尺寸
    classic.png / .ico   从现有 assets/app_icon.png / .ico 复制；png 统一为 256x256
    manifest.json        设置下拉顺序 = 键顺序
    contact_sheet.png    6 款并排预览（带底色 + 小尺寸样张），供人工检查
"""
import json
import math
import os
import shutil
import struct
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
# 必须在导入/创建 QApplication 之前设置，确保 offscreen、无需 GUI
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QImage,
                           QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap, QRadialGradient)
from PySide6.QtWidgets import QApplication

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except Exception:                                    # Pillow 可选
    PILImage = None
    HAS_PIL = False

app = QApplication([])

# ------------------------------------------------------------------ 常量
SIZE = 256
ASSETS = os.path.join(_ROOT, "assets")
OUT_DIR = os.path.join(ASSETS, "app_icons")
ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

# 键顺序 == 设置里下拉顺序
MANIFEST = {
    "classic": {"label": "经典 · 赛博徽标"},
    "neon":    {"label": "霓虹 C"},
    "candle":  {"label": "K 线蜡烛"},
    "orbit":   {"label": "轨道芯片"},
    "wave":    {"label": "上升波浪"},
    "hex":     {"label": "六边形币"},
}

# 每款一套明显不同的配色：深色渐变底 / 霓虹描边 / 发光 / 强调色
THEMES = {
    "neon": dict(                       # 青 -> 紫 -> 品红
        bg=[(10, 14, 38), (8, 9, 26), (26, 10, 48)],
        rim=[(0, 229, 255), (124, 92, 255), (255, 45, 214)],
        glow=(0, 229, 255), accent=(255, 45, 214)),
    "candle": dict(                     # 金黄 + 红绿 K 线
        bg=[(18, 22, 30), (11, 14, 21), (30, 22, 14)],
        rim=[(255, 224, 130), (255, 186, 48), (255, 140, 20)],
        glow=(255, 196, 60), accent=(255, 214, 92)),
    "orbit": dict(                      # 蓝 -> 蓝紫 -> 紫
        bg=[(6, 16, 42), (9, 12, 34), (26, 12, 58)],
        rim=[(58, 160, 255), (106, 91, 255), (162, 75, 255)],
        glow=(90, 140, 255), accent=(150, 110, 255)),
    "wave": dict(                       # 青绿 / 薄荷
        bg=[(4, 26, 25), (5, 32, 30), (6, 44, 34)],
        rim=[(31, 255, 196), (18, 214, 160), (10, 160, 208)],
        glow=(30, 240, 190), accent=(120, 255, 210)),
    "hex": dict(                        # 琥珀 -> 橙 -> 橙红
        bg=[(30, 15, 7), (22, 10, 5), (44, 20, 6)],
        rim=[(255, 176, 32), (255, 122, 0), (255, 61, 0)],
        glow=(255, 150, 20), accent=(255, 200, 60)),
}


# ------------------------------------------------------- 通用绘制小工具
def C(rgb, a=255):
    """(r,g,b)[, alpha] -> QColor。"""
    return QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(a))


def lin(x0, y0, x1, y1, stops):
    g = QLinearGradient(x0, y0, x1, y1)
    for pos, col in stops:
        g.setColorAt(pos, col)
    return g


def rad(cx, cy, r, stops):
    g = QRadialGradient(cx, cy, r)
    for pos, col in stops:
        g.setColorAt(pos, col)
    return g


def as_brush(x):
    return x if isinstance(x, QBrush) else QBrush(x)


def mkpen(paint, w, cap=Qt.RoundCap, join=Qt.RoundJoin):
    """用 QColor / QBrush / QGradient 造一支圆头圆角笔，规避构造重载歧义。"""
    pen = QPen()
    if isinstance(paint, QColor):
        pen.setColor(paint)
    elif isinstance(paint, QBrush):
        pen.setBrush(paint)
    else:
        pen.setBrush(QBrush(paint))
    pen.setWidthF(w)
    pen.setCapStyle(cap)
    pen.setJoinStyle(join)
    pen.setStyle(Qt.SolidLine)
    return pen


def poly(points, close=True):
    pth = QPainterPath()
    pth.moveTo(points[0][0], points[0][1])
    for x, y in points[1:]:
        pth.lineTo(x, y)
    if close:
        pth.closeSubpath()
    return pth


def arrow_head(tip, prev, size=26, half=0.55):
    dx, dy = tip[0] - prev[0], tip[1] - prev[1]
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    bx, by = tip[0] - ux * size, tip[1] - uy * size
    w = size * half
    return poly([tip, (bx + nx * w, by + ny * w), (bx - nx * w, by - ny * w)])


def hexpts(cx, cy, r, rot=-90):
    out = []
    for k in range(6):
        a = math.radians(rot + 60 * k)
        out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return out


def neon_stroke(p, path, rgb, core_w, grad=None):
    """多层发光描边：逐层收窄、逐层变亮的外发光 -> 渐变亮芯 -> 细白高光。"""
    for mul, a in ((4.0, 0.05), (3.0, 0.10), (2.1, 0.18), (1.5, 0.30)):
        p.strokePath(path, mkpen(C(rgb, int(255 * a)), core_w * mul))
    core = QBrush(grad) if grad is not None else C(rgb)
    p.strokePath(path, mkpen(core, core_w))
    p.strokePath(path, mkpen(QColor(255, 255, 255, 50), max(1.0, core_w * 0.22)))


def neon_fill(p, path, fill, rgb, glow_w=16):
    """发光填充：外发光描边 -> 渐变实心 -> 亮色细描边。"""
    for mul, a in ((1.0, 0.10), (0.6, 0.22)):
        p.strokePath(path, mkpen(C(rgb, int(255 * a)), glow_w * mul))
    p.fillPath(path, as_brush(fill))
    p.strokePath(path, mkpen(C(rgb, 215), 2.2))


# ------------------------------------------------------------ 通用底板
def draw_base(p, t):
    """深色渐变圆角底 + 多层霓虹描边 + 顶部高光 + 底部内阴影 + 极淡 HUD 点阵。"""
    body = QPainterPath()
    body.addRoundedRect(QRectF(6, 6, 244, 244), 52, 52)

    bg = lin(0, 0, 256, 256, [
        (0.0, C(t["bg"][0])), (0.55, C(t["bg"][1])), (1.0, C(t["bg"][2]))])
    p.fillPath(body, QBrush(bg))

    p.save()
    p.setClipPath(body)
    hi = rad(80, 34, 250, [
        (0.0, C(t["rim"][0], 46)), (0.55, C(t["rim"][1], 12)),
        (1.0, QColor(0, 0, 0, 0))])
    p.fillPath(body, QBrush(hi))
    vg = rad(128, 236, 190, [
        (0.0, QColor(0, 0, 0, 110)), (1.0, QColor(0, 0, 0, 0))])
    p.fillPath(body, QBrush(vg))
    gloss = lin(0, 10, 0, 128, [
        (0.0, QColor(255, 255, 255, 52)), (1.0, QColor(255, 255, 255, 0))])
    p.fillPath(body, QBrush(gloss))
    p.setPen(Qt.NoPen)
    for gx in range(34, 226, 30):
        for gy in range(34, 226, 30):
            p.setBrush(QColor(*t["glow"], 16))
            p.drawEllipse(QPointF(gx, gy), 1.3, 1.3)
    p.restore()

    rim = QPainterPath()
    rim.addRoundedRect(QRectF(9, 9, 238, 238), 48, 48)

    def rg(a):
        return lin(0, 0, 256, 256, [
            (0.0, C(t["rim"][0], a)), (0.5, C(t["rim"][1], a)),
            (1.0, C(t["rim"][2], a))])

    for w, a in ((18, 22), (12, 48), (7, 110), (3.2, 255)):
        p.strokePath(rim, mkpen(QBrush(rg(a)), w))
    inner = QPainterPath()
    inner.addRoundedRect(QRectF(20, 20, 216, 216), 40, 40)
    p.strokePath(inner, mkpen(QColor(255, 255, 255, 22), 1.6))


# ------------------------------------------------------------ 5 款主体
def subject_neon(p, t):
    """赛博霓虹「C」+ 闪电（青紫渐变）。"""
    rect = QRectF(50, 50, 156, 156)
    arc = QPainterPath()
    arc.arcMoveTo(rect, 50)
    arc.arcTo(rect, 50, 260)                  # 50° -> 310°，右侧留缺口形成 C
    cg = lin(40, 40, 216, 216, [
        (0.0, C(t["rim"][0])), (0.5, C(t["rim"][1])), (1.0, C(t["rim"][2]))])
    neon_stroke(p, arc, t["glow"], 22, cg)

    bolt = poly([(152, 50), (96, 140), (126, 140), (104, 206),
                 (170, 112), (140, 112), (162, 50)])
    bg = lin(128, 50, 128, 206, [
        (0.0, C(t["rim"][2])), (1.0, C(t["rim"][0]))])
    neon_fill(p, bolt, QBrush(bg), t["accent"], 22)

    spark = QPainterPath()
    spark.addEllipse(QPointF(198, 152), 5, 5)
    neon_fill(p, spark, QBrush(C(t["accent"])), t["accent"], 8)


def subject_candle(p, t):
    """三根红绿 K 线蜡烛（上升）+ 金黄趋势箭头。"""
    green, red = (46, 220, 132), (255, 86, 104)
    for gy in (78, 128, 178):                 # 极淡行情网格
        g = QPainterPath()
        g.moveTo(34, gy)
        g.lineTo(222, gy)
        p.strokePath(g, mkpen(QColor(255, 255, 255, 18), 1.4))

    candles = [
        (76, 150, 190, 136, 202, red),
        (128, 120, 168, 98, 184, green),
        (180, 84, 140, 64, 156, green),
    ]
    half = 15
    for cx, top, bot, wt, wb, col in candles:
        wick = QPainterPath()
        wick.moveTo(cx, wt)
        wick.lineTo(cx, wb)
        p.strokePath(wick, mkpen(C(col, 230), 3.2))
        body = QPainterPath()
        body.addRoundedRect(QRectF(cx - half, top, 2 * half, bot - top), 4, 4)
        dark = tuple(int(c * 0.55) for c in col)
        grad = lin(cx - half, top, cx + half, bot,
                   [(0.0, C(col)), (1.0, C(dark))])
        neon_fill(p, body, QBrush(grad), col, 14)

    pts = [(46, 202), (104, 152), (136, 168), (198, 76)]
    line = QPainterPath()
    line.moveTo(pts[0][0], pts[0][1])
    for x, y in pts[1:]:
        line.lineTo(x, y)
    ag = lin(46, 202, 198, 76, [
        (0.0, C(t["rim"][2])), (1.0, C(t["rim"][0]))])
    neon_stroke(p, line, t["glow"], 10, ag)
    head = arrow_head(pts[-1], pts[-2], 28, 0.55)
    neon_fill(p, head, QBrush(C(t["accent"])), t["glow"], 10)


def subject_orbit(p, t):
    """两条交叉环绕轨道 + 中心芯片方块（蓝紫）。"""
    for ang, col in ((30, t["rim"][0]), (-30, t["rim"][2])):
        p.save()
        p.translate(128, 128)
        p.rotate(ang)
        p.translate(-128, -128)
        ell = QPainterPath()
        ell.addEllipse(QRectF(28, 86, 200, 84))
        eg = lin(28, 86, 228, 170, [
            (0.0, C(col)), (1.0, C(t["rim"][1]))])
        neon_stroke(p, ell, t["glow"], 6, eg)
        p.restore()

    for (x, y), col in (((204, 84), t["rim"][0]), ((52, 172), t["rim"][2])):
        dot = QPainterPath()
        dot.addEllipse(QPointF(x, y), 9, 9)
        neon_fill(p, dot, QBrush(C(col)), t["glow"], 12)

    # 芯片引脚（在方块之后画，向上/下/左/右外伸）
    for w, a in ((7, 70), (3.2, 230)):
        pn = mkpen(C(t["rim"][0], a), w)
        for off in (-24, 0, 24):
            segs = [((128 + off, 86), (128 + off, 74)),
                    ((128 + off, 170), (128 + off, 182)),
                    ((86, 128 + off), (74, 128 + off)),
                    ((170, 128 + off), (182, 128 + off))]
            for (x0, y0), (x1, y1) in segs:
                line = QPainterPath()
                line.moveTo(x0, y0)
                line.lineTo(x1, y1)
                p.strokePath(line, pn)

    chip = QPainterPath()
    chip.addRoundedRect(QRectF(86, 86, 84, 84), 12, 12)
    cg = lin(86, 86, 170, 170, [
        (0.0, C(t["rim"][0])), (1.0, C(t["rim"][2]))])
    neon_fill(p, chip, QBrush(cg), t["glow"], 18)

    inner = QPainterPath()
    inner.addRoundedRect(QRectF(102, 102, 52, 52), 8, 8)
    p.fillPath(inner, QBrush(C((10, 14, 38))))
    p.strokePath(inner, mkpen(C(t["rim"][0], 130), 1.6))
    core = QPainterPath()
    core.addRoundedRect(QRectF(118, 118, 20, 20), 4, 4)
    neon_fill(p, core, QBrush(C(t["accent"])), t["glow"], 8)


def subject_wave(p, t):
    """上升波浪折线 + 圆点（青绿）。"""
    pts = [(38, 194), (82, 152), (114, 170), (154, 112), (186, 128), (216, 64)]
    area = QPainterPath()
    area.moveTo(pts[0][0], 214)
    for x, y in pts:
        area.lineTo(x, y)
    area.lineTo(pts[-1][0], 214)
    area.closeSubpath()
    ag = lin(0, 64, 0, 214, [
        (0.0, C(t["rim"][0], 78)), (1.0, C(t["rim"][0], 0))])
    p.fillPath(area, QBrush(ag))

    base = QPainterPath()
    base.moveTo(30, 208)
    base.lineTo(226, 208)
    p.strokePath(base, mkpen(QColor(255, 255, 255, 26), 1.6))

    line = QPainterPath()
    line.moveTo(pts[0][0], pts[0][1])
    for x, y in pts[1:]:
        line.lineTo(x, y)
    lg = lin(38, 194, 216, 64, [
        (0.0, C(t["rim"][2])), (1.0, C(t["rim"][0]))])
    neon_stroke(p, line, t["glow"], 11, lg)
    head = arrow_head(pts[-1], pts[-2], 28, 0.55)
    neon_fill(p, head, QBrush(C(t["accent"])), t["glow"], 10)

    for x, y in pts[1:-1]:
        dot = QPainterPath()
        dot.addEllipse(QPointF(x, y), 7.5, 7.5)
        neon_fill(p, dot, QBrush(C(t["accent"])), t["glow"], 10)
    p.setPen(Qt.NoPen)
    for x, y in pts[1:-1]:                     # 节点白色高光点
        p.setBrush(QColor(255, 255, 255, 170))
        p.drawEllipse(QPointF(x - 1.8, y - 1.8), 2.2, 2.2)


def subject_hex(p, t):
    """六边形币 + 内嵌菱形（橙金），带切面与内阴影。"""
    outer = hexpts(128, 128, 88)
    og = lin(58, 40, 198, 216, [
        (0.0, C(t["rim"][0])), (0.5, C(t["rim"][1])), (1.0, C(t["rim"][2]))])
    neon_fill(p, poly(outer), QBrush(og), t["glow"], 22)

    inner = hexpts(128, 128, 70)
    ig = lin(70, 58, 186, 198, [
        (0.0, C((74, 34, 10))), (1.0, C((28, 12, 4)))])
    p.fillPath(poly(inner), QBrush(ig))
    p.strokePath(poly(inner), mkpen(C(t["accent"], 130), 2.2))
    facet = poly([inner[0], inner[1], (128, 128), inner[5]])
    p.fillPath(facet, QBrush(C(t["rim"][0], 46)))

    diamond = poly([(128, 82), (158, 128), (128, 174), (98, 128)])
    dg = lin(128, 82, 128, 174, [
        (0.0, C((255, 240, 160))), (1.0, C(t["rim"][1]))])
    neon_fill(p, diamond, QBrush(dg), t["accent"], 16)
    tri = [
        ([(128, 82), (98, 128), (128, 128)], (255, 255, 255, 60)),
        ([(128, 82), (158, 128), (128, 128)], (255, 255, 255, 18)),
        ([(158, 128), (128, 174), (128, 128)], (0, 0, 0, 60)),
        ([(128, 174), (98, 128), (128, 128)], (0, 0, 0, 30)),
    ]
    for points, (r, g, b, a) in tri:
        p.fillPath(poly(points), QBrush(QColor(r, g, b, a)))
    p.strokePath(diamond, mkpen(C(t["accent"], 220), 2.4))


SUBJECTS = {
    "neon": subject_neon,
    "candle": subject_candle,
    "orbit": subject_orbit,
    "wave": subject_wave,
    "hex": subject_hex,
}


# ------------------------------------------------------------ ICO 写出
def write_ico_pil(png_path, ico_path):
    im = PILImage.open(png_path).convert("RGBA")
    im.save(ico_path, format="ICO", sizes=ICO_SIZES)
    im.close()


def write_ico_qt(master, ico_path):
    """Pillow 缺失时的回退：纯 QImage + struct 写 32 位 BMP-ICO（Windows 兼容）。"""
    blobs, entries = [], []
    offset = 6 + 16 * len(ICO_SIZES)
    for w, h in ICO_SIZES:
        img = master.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation) \
                    .convertToFormat(QImage.Format_ARGB32)
        bpr = img.bytesPerLine()
        raw = bytes(img.constBits())[:bpr * h]
        rows = [raw[r * bpr:(r + 1) * bpr] for r in range(h)]
        xor = b"".join(reversed(rows))            # BMP 自下而上
        mask_row = ((w + 31) // 32) * 4
        and_mask = b"\x00" * (mask_row * h)
        header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0,
                             len(xor) + len(and_mask), 0, 0, 0, 0)
        blob = header + xor + and_mask
        entries.append(struct.pack("<BBBBHHII", w % 256, h % 256,
                                   0, 0, 1, 32, len(blob), offset))
        offset += len(blob)
        blobs.append(blob)
    with open(ico_path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(ICO_SIZES)))
        f.write(b"".join(entries))
        f.write(b"".join(blobs))


def write_ico(png_path, master, ico_path):
    if HAS_PIL:
        try:
            write_ico_pil(png_path, ico_path)
            return "PIL"
        except Exception as exc:                 # 不中断，走回退
            print("  ! PIL ICO 失败，回退 QImage：", exc, flush=True)
    write_ico_qt(master, ico_path)
    return "QImage"


def ico_sizes(path):
    """不依赖 PIL，直接解析 ICO 目录项得到尺寸列表。"""
    with open(path, "rb") as f:
        _, _, count = struct.unpack("<HHH", f.read(6))
        sizes = []
        for _ in range(count):
            e = f.read(16)
            sizes.append((e[0] or 256, e[1] or 256))
    return sizes


# ------------------------------------------------------------ 经典复制
def copy_classic():
    src_png = os.path.join(ASSETS, "app_icon.png")
    src_ico = os.path.join(ASSETS, "app_icon.ico")
    dst_png = os.path.join(OUT_DIR, "classic.png")
    dst_ico = os.path.join(OUT_DIR, "classic.ico")
    for src in (src_png, src_ico):
        if not os.path.exists(src):
            raise FileNotFoundError("缺少经典图标源文件：" + src)
    qi = QImage(src_png)
    if qi.isNull():
        raise RuntimeError("无法读取 " + src_png)
    qi = qi.convertToFormat(QImage.Format_ARGB32)
    # 源图为 512x512；整套资源统一为 256x256（内容一致，仅高质量缩放）
    if qi.width() != 256 or qi.height() != 256:
        qi = qi.scaled(256, 256, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    if not qi.save(dst_png, "PNG"):
        raise RuntimeError("写出失败 " + dst_png)
    shutil.copyfile(src_ico, dst_ico)          # ICO 本身已含多尺寸，逐字节复制
    print("  classic: 复制完成（png 归一化为 256x256）", flush=True)


# ------------------------------------------------------------ manifest
def write_manifest():
    path = os.path.join(OUT_DIR, "manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(MANIFEST, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("  manifest.json: 写入", len(MANIFEST), "款", flush=True)


# ------------------------------------------------------------ 拼图预览
def _label_font():
    fam = "Segoe UI"
    fp = os.path.join(ASSETS, "fonts", "IBMPlexSans-SemiBold.ttf")
    if os.path.exists(fp):
        fid = QFontDatabase.addApplicationFont(fp)
        if fid >= 0:
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                fam = families[0]
    f = QFont(fam)
    f.setBold(True)
    return f


def make_contact_sheet():
    keys = list(MANIFEST.keys())
    margin, header_h, cell_w, cell_h = 26, 54, 250, 344
    W = margin * 2 + cell_w * len(keys)
    H = margin + header_h + cell_h + margin
    pm = QPixmap(W, H)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)

    bg = lin(0, 0, W, H, [(0.0, C((14, 18, 28))), (1.0, C((8, 10, 18)))])
    p.fillRect(QRectF(0, 0, W, H), QBrush(bg))

    font = _label_font()
    f = QFont(font)
    f.setPointSize(20)
    p.setFont(f)
    p.setPen(QColor(235, 242, 255))
    p.drawText(QRectF(margin, 8, W - 2 * margin, 34),
               Qt.AlignLeft | Qt.AlignVCenter, "APP ICON PACK  /  6 VARIANTS")
    f2 = QFont(font)
    f2.setPointSize(10)
    f2.setBold(False)
    p.setFont(f2)
    p.setPen(QColor(140, 160, 190))
    p.drawText(QRectF(margin, 34, W - 2 * margin, 20),
               Qt.AlignLeft | Qt.AlignVCenter,
               "256x256 RGBA  |  ICO 16/32/48/64/128/256  |  glyphs contain no text")

    y0 = margin + header_h
    for i, k in enumerate(keys):
        cx = margin + i * cell_w
        qi = QImage(os.path.join(OUT_DIR, k + ".png"))
        panel = QPainterPath()
        panel.addRoundedRect(QRectF(cx + 6, y0 + 4, cell_w - 12, cell_h - 8), 16, 16)
        p.fillPath(panel, QBrush(QColor(255, 255, 255, 8)))
        p.strokePath(panel, mkpen(QColor(255, 255, 255, 18), 1.2))

        # 大图：棋盘底衬托透明圆角
        ix, iy, isz = cx + 30, y0 + 16, 190
        p.save()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(ix, iy, isz, isz), 12, 12)
        p.setClipPath(clip)
        for r in range(0, isz, 16):
            for c in range(0, isz, 16):
                dark = ((r // 16 + c // 16) % 2) == 0
                p.fillRect(QRectF(ix + c, iy + r, 16, 16),
                           QBrush(C((38, 42, 54)) if dark else C((26, 29, 38))))
        p.drawImage(QRectF(ix, iy, isz, isz), qi)
        p.restore()

        t = THEMES.get(k)
        acc = t["glow"] if t else (150, 170, 210)
        bar = QPainterPath()
        bar.addRoundedRect(QRectF(cx + 30, y0 + 216, 40, 5), 2.5, 2.5)
        p.fillPath(bar, QBrush(C(acc)))
        f3 = QFont(font)
        f3.setPointSize(15)
        p.setFont(f3)
        p.setPen(QColor(240, 246, 255))
        p.drawText(QRectF(cx + 30, y0 + 226, cell_w - 60, 24),
                   Qt.AlignLeft | Qt.AlignVCenter, k)

        # 小尺寸样张：验证 16/32/48 下主体是否仍可辨认
        sy = y0 + 256
        strip = QPainterPath()
        strip.addRoundedRect(QRectF(cx + 24, sy, cell_w - 48, 72), 10, 10)
        p.fillPath(strip, QBrush(QColor(0, 0, 0, 90)))
        p.strokePath(strip, mkpen(QColor(255, 255, 255, 14), 1.0))
        f4 = QFont(font)
        f4.setPointSize(9)
        f4.setBold(False)
        p.setFont(f4)
        for s, sx in ((48, cx + 40), (32, cx + 106), (16, cx + 164)):
            p.drawImage(QRectF(sx, sy + 50 - s, s, s), qi)
            p.setPen(QColor(170, 190, 215))
            p.drawText(QRectF(sx, sy + 52, s + 18, 16),
                       Qt.AlignLeft | Qt.AlignVCenter, str(s))

    p.end()
    out = os.path.join(OUT_DIR, "contact_sheet.png")
    pm.save(out, "PNG")
    print("  contact_sheet.png:", W, "x", H, flush=True)


# ------------------------------------------------------------ 校验
def verify():
    print("\n" + "=" * 60)
    print("验证 / VERIFY")
    print("=" * 60)
    keys = list(MANIFEST.keys())
    required = set(ICO_SIZES)
    problems = []
    for k in keys:
        png = os.path.join(OUT_DIR, k + ".png")
        ico = os.path.join(OUT_DIR, k + ".ico")
        qi = QImage(png)
        png_ok = (not qi.isNull()) and qi.width() == 256 and qi.height() == 256
        pil_png = ""
        if HAS_PIL:
            with PILImage.open(png) as im:
                pil_png = "%dx%d %s" % (im.size[0], im.size[1], im.mode)
                if im.size != (256, 256):
                    png_ok = False
        sizes = ico_sizes(ico) if os.path.exists(ico) else []
        ico_ok = required.issubset(set(sizes))
        pil_ico = ""
        if HAS_PIL:
            with PILImage.open(ico) as im:
                ps = set(im.ico.sizes())
                pil_ico = "PIL=%s" % ",".join("%d" % s[0] for s in sorted(ps))
                if not required.issubset(ps):
                    ico_ok = False
        flag = "OK  " if (png_ok and ico_ok) else "FAIL"
        print("  [%s] %-8s PNG %dx%d %-12s | ICO %d sizes %s | %s"
              % (flag, k, qi.width(), qi.height(), pil_png,
                 len(sizes), sorted(sizes), pil_ico), flush=True)
        if not png_ok:
            problems.append(k + ".png 不是 256x256")
        if not ico_ok:
            problems.append(k + ".ico 缺少所需尺寸")

    mp = os.path.join(OUT_DIR, "manifest.json")
    with open(mp, encoding="utf-8") as f:
        data = json.load(f)
    order_ok = list(data.keys()) == keys
    labels_ok = all(isinstance(v, dict) and isinstance(v.get("label"), str)
                    and v["label"] for v in data.values())
    print("  [%s] manifest.json 合法 JSON | 键顺序=%s | labels=%s"
          % ("OK  " if order_ok and labels_ok else "FAIL",
             list(data.keys()), labels_ok), flush=True)
    if not order_ok:
        problems.append("manifest 键顺序不符")
    if not labels_ok:
        problems.append("manifest label 异常")

    cs = os.path.join(OUT_DIR, "contact_sheet.png")
    cs_ok = os.path.exists(cs) and os.path.getsize(cs) > 0
    print("  [%s] contact_sheet.png %s"
          % ("OK  " if cs_ok else "FAIL",
             str(os.path.getsize(cs)) + " bytes" if cs_ok else "缺失"), flush=True)
    if not cs_ok:
        problems.append("contact_sheet.png 缺失")

    print("-" * 60)
    if problems:
        print("结果：存在问题 -> " + "; ".join(problems), flush=True)
    else:
        print("结果：全部通过（6 PNG / 6 ICO / manifest / 拼图）", flush=True)
    print("=" * 60 + "\n")
    return not problems


# ------------------------------------------------------------ 主流程
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("输出目录：", OUT_DIR, flush=True)
    print("Pillow：", "可用" if HAS_PIL else "缺失（使用 QImage 回退写 ICO）", flush=True)

    copy_classic()
    for key, fn in SUBJECTS.items():
        t = THEMES[key]
        pm = QPixmap(SIZE, SIZE)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        draw_base(p, t)
        fn(p, t)
        p.end()
        png_path = os.path.join(OUT_DIR, key + ".png")
        ico_path = os.path.join(OUT_DIR, key + ".ico")
        if not pm.save(png_path, "PNG"):
            raise RuntimeError("写出失败 " + png_path)
        method = write_ico(png_path, pm.toImage(), ico_path)
        print("  %-7s %s.png + %s.ico (ICO via %s)"
              % (key, key, key, method), flush=True)

    write_manifest()
    make_contact_sheet()
    return verify()


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
