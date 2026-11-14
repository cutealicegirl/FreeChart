# -*- coding: utf-8 -*-
"""开发期工具：程序化绘制默认「赛博行情看板娘」立绘 assets/mascot.png。

运行时只读成品，业务代码不依赖本脚本。全部使用 PySide6 的 QPainter，
QT_QPA_PLATFORM=offscreen，无显示器 / 无网络也能重复运行。

做法：先在 3 倍超采样画布上用 220x320 逻辑坐标绘制（渐变、多层发光描边、
径向阴影、高光），再高质量降采样到 220x320，得到干净的抗锯齿透明边缘。

产物：assets/mascot.png —— 220x320 RGBA，背景 alpha=0。

运行：python tools/make_mascot.py
"""
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
# 必须在创建 QApplication 之前设置，保证无 GUI 环境也能跑
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap,
                           QRadialGradient)
from PySide6.QtWidgets import QApplication

app = QApplication([])

# ------------------------------------------------------------------ 常量
W, H = 220, 320              # 最终输出尺寸
SS = 3                       # 超采样倍数
OUT = os.path.join(_ROOT, "assets", "mascot.png")

# 赛博霓虹配色
INK = (12, 16, 40)
CYAN = (0, 229, 255)
PURPLE = (124, 92, 255)
PINK = (255, 64, 196)
MAGENTA = (255, 45, 214)
GREEN = (46, 220, 132)
RED = (255, 86, 104)
SKIN = (255, 228, 220)
SKIN_SH = (246, 180, 192)
WHITE = (238, 246, 255)

HAIR_D = (34, 28, 88)
HAIR_M = (78, 52, 158)
HAIR_L = (142, 100, 246)
HAIR_T = (0, 214, 236)

COAT_D = (16, 22, 58)
COAT_M = (36, 30, 92)
COAT_L = (74, 44, 138)


# ------------------------------------------------------------ 绘制小工具
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


def brush(x):
    return x if isinstance(x, QBrush) else QBrush(x)


def mkpen(paint, w, cap=Qt.RoundCap, join=Qt.RoundJoin):
    """用 QColor / QBrush / QGradient 造圆头圆角笔，规避构造重载歧义。"""
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
    p = QPainterPath()
    p.moveTo(points[0][0], points[0][1])
    for x, y in points[1:]:
        p.lineTo(x, y)
    if close:
        p.closeSubpath()
    return p


def ell(cx, cy, rx, ry):
    p = QPainterPath()
    p.addEllipse(QRectF(cx - rx, cy - ry, 2 * rx, 2 * ry))
    return p


def rr(x, y, w, h, r):
    p = QPainterPath()
    p.addRoundedRect(QRectF(x, y, w, h), r, r)
    return p


def curve(points):
    """[(x,y), (cx1,cy1,cx2,cy2,x,y), ...] -> 贝塞尔路径，首项为起点。"""
    p = QPainterPath()
    p.moveTo(points[0][0], points[0][1])
    for seg in points[1:]:
        p.cubicTo(seg[0], seg[1], seg[2], seg[3], seg[4], seg[5])
    return p


def glow_stroke(p, path, rgb, core_w, grad=None):
    """多层发光描边：逐层收窄的外发光 -> 渐变亮芯 -> 细白高光。"""
    for mul, a in ((4.2, 0.05), (3.0, 0.09), (2.1, 0.17), (1.5, 0.28)):
        p.strokePath(path, mkpen(C(rgb, int(255 * a)), core_w * mul))
    core = QBrush(grad) if grad is not None else C(rgb)
    p.strokePath(path, mkpen(core, core_w))
    p.strokePath(path, mkpen(QColor(255, 255, 255, 70),
                             max(0.8, core_w * 0.20)))


def glow_fill(p, path, fill, rgb, glow_w=9, rim=2.0):
    """发光填充：外发光晕 -> 渐变/纯色实心 -> 亮色细描边。"""
    for mul, a in ((1.0, 0.10), (0.6, 0.22)):
        p.strokePath(path, mkpen(C(rgb, int(255 * a)), glow_w * mul))
    p.fillPath(path, brush(fill))
    p.strokePath(path, mkpen(C(rgb, 220), rim))


def star(cx, cy, r, inner=0.32):
    """四尖星光路径。"""
    pts = []
    for k in range(8):
        ang = -math.pi / 2 + k * math.pi / 4
        rad_ = r if k % 2 == 0 else r * inner
        pts.append((cx + rad_ * math.cos(ang),
                    cy + rad_ * math.sin(ang)))
    return poly(pts)


def draw_star(p, cx, cy, r, rgb, alpha=210):
    glow_fill(p, star(cx, cy, r), C(WHITE, alpha), rgb, glow_w=7, rim=0.8)
    p.fillPath(star(cx, cy, r * 0.42), C(WHITE, min(255, alpha + 30)))


def arrow_head(tip, prev, size, half=0.52):
    dx, dy = tip[0] - prev[0], tip[1] - prev[1]
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    bx, by = tip[0] - ux * size, tip[1] - uy * size
    w = size * half
    return poly([tip, (bx + nx * w, by + ny * w),
                 (bx - nx * w, by - ny * w)])


# ------------------------------------------------------------ 各图层
def draw_ground_shadow(p):
    """脚下的软投影（径向渐变，纯半透明内容，不铺满画布）。"""
    sh = ell(110, 300, 56, 9)
    p.fillPath(sh, QBrush(rad(110, 300, 56, [
        (0.0, QColor(4, 6, 20, 120)),
        (0.55, QColor(4, 6, 20, 52)),
        (1.0, QColor(4, 6, 20, 0))])))


def draw_floaties(p):
    """身旁浮动的涨跌箭头 / 迷你 K 线 / 光点。"""
    # --- 左侧：绿色上升折线箭头 ---
    pts = [(20, 196), (32, 178), (41, 186), (56, 150)]
    line = poly(pts, close=False)
    glow_stroke(p, line, GREEN, 3.4,
                lin(20, 196, 56, 150, [(0.0, C(GREEN, 150)), (1.0, C(GREEN))]))
    head = arrow_head(pts[-1], pts[-2], 15, 0.5)
    glow_fill(p, head, C(GREEN, 235), GREEN, glow_w=10, rim=1.2)

    # --- 右侧：红色下降折线箭头 ---
    pts2 = [(198, 112), (205, 130), (212, 125), (216, 148)]
    line2 = poly(pts2, close=False)
    glow_stroke(p, line2, RED, 2.8)
    head2 = arrow_head(pts2[-1], pts2[-2], 12, 0.5)
    glow_fill(p, head2, C(RED, 235), RED, glow_w=8, rim=1.0)

    # --- 迷你浮动 K 线（左上，青色描边小方块 + 蜡烛） ---
    mini = rr(164, 44, 34, 26, 5)
    p.fillPath(mini, C(INK, 205))
    p.strokePath(mini, mkpen(C(CYAN, 150), 1.3))
    for cx, top, bot, col in ((171, 52, 62, GREEN), (179, 48, 58, RED),
                              (187, 50, 64, GREEN), (194, 45, 55, GREEN)):
        p.strokePath(poly([(cx, top - 3), (cx, bot + 3)], False),
                     mkpen(C(col, 220), 1.0))
        p.fillPath(rr(cx - 2.2, top, 4.4, bot - top, 1.0), C(col, 235))

    # --- 散落光点 / 小三角 / 星 ---
    for (x, y, r, col) in ((28, 118, 2.4, CYAN), (190, 176, 2.0, PINK),
                           (176, 96, 1.8, PURPLE), (40, 232, 1.7, GREEN),
                           (150, 32, 1.9, CYAN), (206, 232, 1.6, CYAN)):
        p.fillPath(ell(x, y, r, r), C(col, 190))
    tri = poly([(36, 146), (43, 138), (47, 149)])
    glow_fill(p, tri, C(CYAN, 190), CYAN, glow_w=6, rim=0.8)
    tri2 = poly([(188, 208), (196, 202), (197, 213)])
    glow_fill(p, tri2, C(PINK, 190), PINK, glow_w=6, rim=0.8)
    draw_star(p, 62, 34, 7, CYAN, 190)
    draw_star(p, 158, 258, 5.5, PINK, 180)


def draw_twintails(p):
    """双马尾（后层）：从头两侧垂下的发束 + 霓虹发圈。"""
    for side in (-1, 1):
        if side < 0:
            top = (58, 76)
            path = curve([
                (58, 76),
                (28, 96, 20, 160, 34, 208),
                (38, 224, 48, 226, 54, 210),
                (40, 176, 46, 120, 70, 92),
            ])
            tail_g = lin(28, 80, 58, 214, [
                (0.0, C(HAIR_D)), (0.5, C(HAIR_M)), (1.0, C(HAIR_T, 235))])
            ring = (56, 84)
        else:
            top = (162, 76)
            path = curve([
                (162, 76),
                (192, 96, 200, 160, 186, 208),
                (182, 224, 172, 226, 166, 210),
                (180, 176, 174, 120, 150, 92),
            ])
            tail_g = lin(192, 80, 162, 214, [
                (0.0, C(HAIR_D)), (0.5, C(HAIR_M)), (1.0, C(HAIR_L))])
            ring = (164, 84)
        glow_fill(p, path, QBrush(tail_g), PURPLE, glow_w=12, rim=2.2)
        # 发束内侧高光
        p.save()
        p.setClipPath(path)
        p.strokePath(curve([top, (top[0] + side * 8, top[1] + 24,
                                 top[0] + side * 12, 160,
                                 top[0] + side * 26, 204)]),
                     mkpen(C(WHITE, 46), 3.0))
        p.restore()
        # 霓虹发圈
        rc = rr(ring[0] - 9, ring[1] - 6, 18, 12, 5)
        glow_fill(p, rc, C(CYAN, 225), CYAN, glow_w=9, rim=1.2)
        p.fillPath(rr(ring[0] - 4, ring[1] - 2.5, 8, 5, 2), C(WHITE, 150))


def draw_legs(p):
    """短腿 + 发光靴子。"""
    leg_g = lin(0, 240, 0, 292, [(0.0, C((28, 32, 72))), (1.0, C((16, 20, 48)))])
    for x in (88, 116):
        leg = rr(x, 238, 16, 52, 7)
        glow_fill(p, leg, QBrush(leg_g), PURPLE, glow_w=7, rim=1.4)
        p.strokePath(poly([(x + 3, 250), (x + 13, 250)], False),
                     mkpen(C(CYAN, 90), 1.2))
        boot = rr(x - 3, 280, 22, 17, 7)
        bg = lin(x - 3, 280, x + 19, 297,
                 [(0.0, C((44, 36, 96))), (1.0, C((18, 22, 58)))])
        glow_fill(p, boot, QBrush(bg), CYAN, glow_w=8, rim=1.6)
        p.strokePath(poly([(x - 2, 293), (x + 18, 293)], False),
                     mkpen(C(CYAN, 220), 2.0))


def draw_coat(p):
    """霓虹外套主体：渐变 + 发光边 + V 领 + 拉链 + 发光条纹 + 胸章。"""
    body = QPainterPath()
    body.moveTo(110, 178)                       # V 领尖
    body.lineTo(80, 158)                        # 左肩
    body.cubicTo(64, 164, 62, 196, 64, 246)
    body.quadTo(110, 258, 156, 246)
    body.cubicTo(158, 196, 156, 164, 140, 158)
    body.lineTo(110, 178)
    body.closeSubpath()

    coat_g = lin(64, 158, 156, 250, [
        (0.0, C(COAT_L)), (0.42, C(COAT_M)), (1.0, C(COAT_D))])
    glow_fill(p, body, QBrush(coat_g), CYAN, glow_w=15, rim=2.4)

    # 外套上的紫色内阴影 / 立体高光（裁剪在衣身内）
    p.save()
    p.setClipPath(body)
    p.fillPath(body, QBrush(rad(88, 172, 120, [
        (0.0, C(PURPLE, 60)), (1.0, QColor(0, 0, 0, 0))])))
    gloss = lin(64, 158, 150, 246, [
        (0.0, C(WHITE, 34)), (0.5, C(WHITE, 6)), (1.0, C(WHITE, 0))])
    p.fillPath(body, QBrush(gloss))
    # 下摆内阴影
    p.fillPath(rr(60, 232, 100, 26, 8), QBrush(
        lin(0, 232, 0, 258, [(0.0, QColor(0, 0, 0, 0)),
                             (1.0, QColor(0, 0, 0, 80))])))
    p.restore()

    # V 领内搭
    collar = poly([(96, 158), (124, 158), (110, 184)])
    glow_fill(p, collar, C((226, 238, 255), 235), CYAN, glow_w=7, rim=1.2)
    # 领口下的小领结（品红发光）
    tie = poly([(110, 180), (102, 172), (101, 188), (110, 196),
                (119, 188), (118, 172)])
    glow_fill(p, tie, C(PINK, 235), PINK, glow_w=8, rim=1.0)
    p.fillPath(ell(110, 182, 2.4, 2.4), C(WHITE, 220))

    # 拉链
    p.strokePath(poly([(110, 196), (110, 246)], False),
                 mkpen(C(CYAN, 200), 2.2))
    p.strokePath(poly([(110, 196), (110, 246)], False),
                 mkpen(C(WHITE, 110), 0.8))
    p.fillPath(rr(107.5, 212, 5, 8, 2), C(CYAN, 230))

    # 肩部 / 袖口发光条纹
    for x0, y0, x1, y1 in ((82, 168, 76, 200), (138, 168, 144, 200)):
        p.strokePath(poly([(x0, y0), (x1, y1)], False),
                     mkpen(C(CYAN, 165), 2.4))
    hem = poly([(66, 244), (110, 253), (154, 244)], False)
    glow_stroke(p, hem, CYAN, 2.2)

    # 左胸 K 线徽章
    badge = ell(88, 190, 12, 12)
    p.fillPath(badge, C(INK, 235))
    p.strokePath(badge, mkpen(C(PURPLE, 220), 1.6))
    for cx, top, bot, col in ((83, 186, 193, GREEN), (88, 183, 190, RED),
                              (93, 185, 195, GREEN)):
        p.strokePath(poly([(cx, top - 2), (cx, bot + 2)], False),
                     mkpen(C(col, 220), 0.9))
        p.fillPath(rr(cx - 1.4, top, 2.8, bot - top, 0.8), C(col, 235))


def draw_arms(p):
    """双臂：左臂自然下垂，右臂前伸托平板。"""
    sleeve = lin(0, 164, 0, 220, [(0.0, C(COAT_L)), (1.0, C(COAT_M))])
    # 左臂
    left = curve([(80, 164), (66, 172, 62, 196, 66, 216)])
    glow_stroke(p, left, PURPLE, 13, QBrush(sleeve))
    cuff = rr(60, 210, 13, 8, 4)
    glow_fill(p, cuff, C(CYAN, 220), CYAN, glow_w=7, rim=1.0)
    p.fillPath(ell(67, 223, 7.5, 7), C(SKIN))
    p.fillPath(ell(64.5, 220.5, 3, 2.2), C(WHITE, 120))

    # 右臂（弯向平板）
    right = curve([(140, 164), (152, 172, 152, 186, 160, 194)])
    glow_stroke(p, right, PURPLE, 13, QBrush(sleeve))
    cuff2 = rr(155, 190, 13, 8, 4)
    glow_fill(p, cuff2, C(CYAN, 220), CYAN, glow_w=7, rim=1.0)
    p.fillPath(ell(164, 202, 7.5, 7), C(SKIN))


def draw_tablet(p):
    """手里的小平板：霓虹边框 + 红绿 K 线 + 发光趋势箭头。"""
    p.save()
    p.translate(174, 204)
    p.rotate(-9)
    # 外框
    frame = rr(-33, -27, 66, 54, 8)
    fg = lin(-33, -27, 33, 27, [
        (0.0, C((48, 40, 108))), (0.55, C((22, 26, 66))),
        (1.0, C((12, 16, 44)))])
    glow_fill(p, frame, QBrush(fg), CYAN, glow_w=12, rim=2.2)
    # 屏幕
    screen = rr(-28, -22, 56, 40, 4)
    p.fillPath(screen, QBrush(lin(-28, -22, 28, 18, [
        (0.0, C((10, 18, 38))), (1.0, C((6, 10, 26)))])))
    p.strokePath(screen, mkpen(C(CYAN, 110), 1.0))
    p.save()
    p.setClipPath(screen)
    # 极淡网格
    for gy in (-12, 0, 12):
        p.strokePath(poly([(-28, gy), (28, gy)], False),
                     mkpen(C(WHITE, 20), 0.7))
    # K 线蜡烛（含影线）
    candles = [(-20, -8, 8, -14, 13, RED),
               (-9, -2, 12, -8, 16, GREEN),
               (2, -12, 4, -17, 8, GREEN),
               (13, -16, -1, -20, 3, GREEN),
               (23, -10, -6, -13, 0, RED)]
    for cx, top, bot, wt, wb, col in candles:
        p.strokePath(poly([(cx, wt), (cx, wb)], False), mkpen(C(col, 230), 1.3))
        body = rr(cx - 3, top, 6, bot - top, 1.5)
        dark = tuple(int(c * 0.55) for c in col)
        p.fillPath(body, QBrush(lin(cx - 3, top, cx + 3, bot,
                                    [(0.0, C(col)), (1.0, C(dark))])))
        p.strokePath(body, mkpen(C(col, 255), 0.7))
    # 发光上升趋势线
    trend = poly([(-24, 14), (-10, 6), (2, 9), (16, -8), (26, -16)], False)
    glow_stroke(p, trend, CYAN, 1.6,
                lin(-24, 14, 26, -16, [(0.0, C(CYAN, 90)), (1.0, C(CYAN))]))
    p.restore()
    # 顶部指示灯 + 底部品牌条
    p.fillPath(ell(0, -24, 1.6, 1.6), C(CYAN, 230))
    p.fillPath(rr(-9, 22, 18, 2, 1), C(PURPLE, 200))
    # 四角高光
    for (x, y) in ((-29, -23), (25, -23), (-29, 15), (25, 15)):
        p.fillPath(ell(x, y, 1.2, 1.2), C(WHITE, 170))
    p.restore()

    # 平板旁边的悬浮星与光晕
    draw_star(p, 206, 168, 5, CYAN, 200)


def draw_head_back(p):
    """后发（比脸大一圈的椭圆）+ 边缘发光。"""
    hair = ell(110, 96, 57, 53)
    hg = lin(54, 44, 166, 148, [
        (0.0, C(HAIR_L)), (0.42, C(HAIR_M)), (1.0, C(HAIR_D))])
    glow_fill(p, hair, QBrush(hg), PURPLE, glow_w=16, rim=2.4)
    # 头发内部高光弧
    p.save()
    p.setClipPath(hair)
    p.fillPath(ell(88, 66, 34, 22), QBrush(
        rad(88, 62, 40, [(0.0, C(WHITE, 46)), (1.0, QColor(0, 0, 0, 0))])))
    # 发梢偏青
    p.fillPath(ell(110, 140, 56, 16), QBrush(
        lin(0, 128, 0, 152, [(0.0, C(HAIR_T, 0)), (1.0, C(HAIR_T, 80))])))
    p.restore()
    # 头后飘出的几缕呆毛
    for pts, col in (([(110, 44), (116, 30), (108, 36)], PURPLE),
                     ([(96, 46), (88, 32), (98, 40)], CYAN)):
        glow_stroke(p, poly(pts, False), col, 2.2)


def draw_face(p):
    """脸 + 大眼睛 + 眉 + 腮红 + 嘴。"""
    face = ell(110, 103, 44, 39)
    fg = lin(66, 66, 154, 142, [
        (0.0, C(WHITE, 255)), (0.35, C(SKIN)), (1.0, C(SKIN_SH))])
    glow_fill(p, face, QBrush(fg), PINK, glow_w=8, rim=1.6)
    p.save()
    p.setClipPath(face)
    # 额头高光
    p.fillPath(ell(96, 82, 22, 9), QBrush(
        rad(96, 80, 26, [(0.0, C(WHITE, 90)), (1.0, QColor(0, 0, 0, 0))])))
    # 下巴阴影
    p.fillPath(ell(110, 140, 34, 9), QBrush(
        rad(110, 140, 34, [(0.0, C(SKIN_SH, 90)), (1.0, QColor(0, 0, 0, 0))])))
    p.restore()

    # 眉
    for pts in ([(80, 88), (88, 84), (99, 87)],
                [(121, 87), (132, 84), (140, 88)]):
        p.strokePath(poly(pts, False), mkpen(C((74, 52, 108), 220), 2.2))

    # 大眼睛
    for ecx in (90, 130):
        eye = ell(ecx, 106, 11.5, 14.5)
        p.fillPath(eye, C(WHITE))
        p.strokePath(eye, mkpen(C((60, 42, 96), 235), 1.8))
        # 上眼睑加粗（睫毛感）
        lid = poly([(ecx - 11, 101), (ecx - 7, 95),
                    (ecx, 93.5), (ecx + 7, 95), (ecx + 11, 101)], False)
        glow_stroke(p, lid, PURPLE, 2.6)
        # 虹膜（青紫渐变）
        iris = ell(ecx, 108, 8, 10.5)
        ig = lin(ecx - 8, 98, ecx + 8, 118, [
            (0.0, C(CYAN)), (0.5, C(PURPLE)), (1.0, C(PINK))])
        p.save()
        p.setClipPath(eye)
        p.fillPath(iris, QBrush(ig))
        # 瞳孔 + 下部深晕
        p.fillPath(ell(ecx, 108, 4, 6.5), C((26, 20, 62)))
        p.fillPath(ell(ecx, 116, 8, 4), QBrush(
            rad(ecx, 116, 9, [(0.0, C(WHITE, 0)), (1.0, C((24, 18, 64), 150))])))
        # 高光
        p.fillPath(ell(ecx - 3.2, 102.5, 3.1, 3.8), C(WHITE, 240))
        p.fillPath(ell(ecx + 3.4, 111.5, 1.6, 2.0), C(WHITE, 200))
        p.restore()
        # 眼睛底部亮线
        p.strokePath(poly([(ecx - 7, 117), (ecx + 7, 117)], False),
                     mkpen(C(WHITE, 130), 1.0))

    # 腮红
    for cx in (75, 145):
        p.fillPath(ell(cx, 122, 9, 5), QBrush(
            rad(cx, 122, 10, [(0.0, C(PINK, 120)), (1.0, C(PINK, 0))])))
        for dx in (-4, 0, 4):
            p.strokePath(poly([(cx + dx - 1, 121), (cx + dx + 1, 123)], False),
                         mkpen(C((255, 120, 180), 150), 1.0))

    # 小嘴（微笑）
    mouth = curve([(103, 130), (107, 135, 113, 135, 117, 130)])
    p.strokePath(mouth, mkpen(C((196, 84, 122), 235), 2.0))
    p.fillPath(ell(110, 133.5, 2.2, 1.2), C((255, 130, 165), 200))
    # 鼻尖
    p.fillPath(ell(110, 122, 1.6, 1.2), C(SKIN_SH, 200))


def draw_bangs(p):
    """刘海：M 形分缕 + 中间一缕长刘海 + 发光发丝。"""
    bangs = QPainterPath()
    bangs.moveTo(66, 96)
    bangs.cubicTo(64, 70, 78, 52, 100, 52)
    bangs.cubicTo(108, 52, 112, 58, 110, 68)
    bangs.cubicTo(118, 56, 132, 52, 146, 56)
    bangs.cubicTo(158, 60, 158, 78, 154, 96)
    bangs.cubicTo(146, 82, 138, 78, 130, 82)
    bangs.cubicTo(124, 86, 122, 92, 120, 98)
    bangs.cubicTo(116, 86, 110, 78, 104, 84)
    bangs.cubicTo(98, 90, 96, 94, 94, 100)
    bangs.cubicTo(88, 84, 78, 84, 66, 96)
    bangs.closeSubpath()
    bg = lin(66, 52, 154, 100, [
        (0.0, C(HAIR_L)), (0.45, C(HAIR_M)), (1.0, C(HAIR_D))])
    glow_fill(p, bangs, QBrush(bg), PURPLE, glow_w=12, rim=2.0)
    # 发丝高光
    for pts in ([(88, 62), (82, 76), (80, 88)],
                [(110, 60), (110, 74), (108, 88)],
                [(136, 62), (140, 76), (142, 88)]):
        p.strokePath(poly(pts, False), mkpen(C(CYAN, 90), 1.8))
    # 中间那缕长刘海的青色发梢
    p.strokePath(poly([(104, 84), (100, 94), (94, 100)], False),
                 mkpen(C(HAIR_T, 170), 2.0))


def draw_headphones(p):
    """猫耳耳机：猫耳三角 + 发光头梁 + 双侧耳罩。"""
    # 头梁（在头发之上）
    beam = QPainterPath()
    beam.moveTo(56, 92)
    beam.cubicTo(54, 42, 84, 26, 110, 26)
    beam.cubicTo(136, 26, 166, 42, 164, 92)
    glow_stroke(p, beam, CYAN, 6.0,
                lin(56, 26, 164, 92, [(0.0, C(CYAN)), (0.5, C(PURPLE)),
                                      (1.0, C(PINK))]))
    # 猫耳（左 / 右）
    for side in (-1, 1):
        if side < 0:
            outer = poly([(44, 48), (40, 18), (72, 40)])
            inner = poly([(48, 45), (46, 27), (66, 41)])
        else:
            outer = poly([(176, 48), (180, 18), (148, 40)])
            inner = poly([(172, 45), (174, 27), (154, 41)])
        eg = lin(40, 18, 72, 48, [(0.0, C(PINK)), (1.0, C(PURPLE))]) \
            if side < 0 else lin(148, 40, 180, 18,
                                 [(0.0, C(PURPLE)), (1.0, C(PINK))])
        glow_fill(p, outer, QBrush(eg), PINK, glow_w=10, rim=1.8)
        p.fillPath(inner, C((255, 158, 210), 235))
        p.fillPath(inner, QBrush(
            rad(56 if side < 0 else 164, 36, 20,
                [(0.0, C(WHITE, 90)), (1.0, QColor(0, 0, 0, 0))])))

    # 双侧耳罩
    for side in (-1, 1):
        cx = 56 if side < 0 else 164
        shell = ell(cx, 98, 15, 19)
        sg = lin(cx - 15, 80, cx + 15, 116, [
            (0.0, C((70, 52, 142))), (0.5, C((28, 26, 74))),
            (1.0, C((16, 18, 50)))])
        glow_fill(p, shell, QBrush(sg), CYAN, glow_w=11, rim=2.0)
        # 内圈发光环
        p.strokePath(ell(cx, 98, 9.5, 13), mkpen(C(CYAN, 220), 2.2))
        p.strokePath(ell(cx, 98, 6, 9), mkpen(C(PURPLE, 170), 1.4))
        # 中心小 K 线 / 心形指示
        p.fillPath(ell(cx, 98, 3.2, 3.2), C(PINK, 235))
        # 外壳高光
        p.fillPath(ell(cx - 6, 88, 4, 7), C(WHITE, 70))
    # 头梁上的小指示灯
    p.fillPath(ell(110, 27, 2.6, 2.6), C(WHITE, 235))
    p.fillPath(ell(110, 27, 5.5, 5.5), QBrush(
        rad(110, 27, 6, [(0.0, C(CYAN, 140)), (1.0, QColor(0, 0, 0, 0))])))


def draw_final_sparkles(p):
    """收尾：整体高光星点。"""
    draw_star(p, 70, 58, 5, WHITE, 210)
    draw_star(p, 152, 132, 4, CYAN, 190)
    draw_star(p, 92, 276, 4.5, PINK, 180)


# ------------------------------------------------------------ 主流程
def render() -> QPixmap:
    """在超采样画布上绘制，再降采样到 220x320 透明 PNG。"""
    canvas = QPixmap(W * SS, H * SS)
    canvas.fill(Qt.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    p.scale(SS, SS)

    draw_ground_shadow(p)
    draw_floaties(p)
    draw_twintails(p)
    draw_legs(p)
    draw_coat(p)
    draw_arms(p)
    draw_tablet(p)
    draw_head_back(p)
    draw_face(p)
    draw_bangs(p)
    draw_headphones(p)
    draw_final_sparkles(p)

    p.end()
    return canvas.scaled(W, H, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def verify(path: str) -> bool:
    """校验尺寸 / alpha 通道 / 边缘透明 / 内容非空。"""
    img = QImage(path)
    ok = True
    size_ok = (not img.isNull()) and img.width() == W and img.height() == H
    alpha_ok = (not img.isNull()) and img.hasAlphaChannel()
    corners = [(0, 0), (W - 1, 0), (0, H - 1), (W - 1, H - 1)]
    edge_ok = all(img.pixelColor(x, y).alpha() == 0 for x, y in corners)

    transparent = 0
    opaque = 0
    if size_ok:
        for y in range(H):
            for x in range(W):
                a = img.pixelColor(x, y).alpha()
                if a == 0:
                    transparent += 1
                elif a > 200:
                    opaque += 1
    total = W * H
    bg_ok = transparent > total * 0.35          # 大面积背景确实全透明
    content_ok = opaque > total * 0.06           # 且确有实心内容
    ok = bool(size_ok and alpha_ok and edge_ok and bg_ok and content_ok)

    print("  [%s] 尺寸 %dx%d（期望 %dx%d）"
          % ("OK" if size_ok else "FAIL", img.width(), img.height(), W, H))
    print("  [%s] 含 alpha 通道: %s" % ("OK" if alpha_ok else "FAIL", alpha_ok))
    print("  [%s] 四角 alpha=0（边缘干净）" % ("OK" if edge_ok else "FAIL"))
    print("  [%s] 全透明像素占比 %.1f%% / 不透明像素占比 %.1f%%"
          % ("OK" if (bg_ok and content_ok) else "FAIL",
             100.0 * transparent / total, 100.0 * opaque / total))

    # Pillow 可选二次校验
    try:
        from PIL import Image as PILImage
        with PILImage.open(path) as im:
            p_ok = im.size == (W, H) and im.mode == "RGBA"
            p_corner = all(im.getpixel(pt)[3] == 0 for pt in
                           [(0, 0), (W - 1, 0), (0, H - 1), (W - 1, H - 1)])
            print("  [%s] Pillow 复核: %s %s, 四角 alpha=%s"
                  % ("OK" if (p_ok and p_corner) else "FAIL",
                     im.size, im.mode, p_corner))
            if not (p_ok and p_corner):
                ok = False
    except ImportError:
        print("  [--] Pillow 未安装，跳过二次校验（不影响结果）")

    print("  => %s" % ("全部通过" if ok else "存在问题"))
    return ok


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    pm = render()
    if not pm.save(OUT, "PNG"):
        raise RuntimeError("写出失败：" + OUT)
    print("已生成:", OUT, "(%d bytes)" % os.path.getsize(OUT))
    print("校验:")
    return verify(OUT)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
