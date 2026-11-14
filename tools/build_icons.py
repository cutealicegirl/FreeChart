# -*- coding: utf-8 -*-
"""一次性生成/增强全部图标资源（开发期运行，运行时只读成品）。

1. 把 assets/coins_src 里的原始币种 logo 统一做成 128x128 高对比圆形徽章：
   裁掉透明边 -> 放大 -> 对比度/不透明度提升 -> 按 logo 明暗自动选
   亮底/暗底 -> 加亮色描边。暗色 logo（XRP/NEAR 等）不再糊在深色背景里。
2. 用 AI 生成的赛博朋克徽标 compositing 出主图标 assets/app_icon.png，
   并导出标准多尺寸 assets/app_icon.ico（BMP 32 位，兼容性最好）。

运行：python tools/build_icons.py
"""
import os
import shutil
import struct
import sys

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QImage, QLinearGradient, QPainter,
                           QPen, QPixmap)
from PySide6.QtWidgets import QApplication

app = QApplication([])

ASSETS = os.path.join(_ROOT, "assets")
SRC_DIR = os.path.join(ASSETS, "coins_src")
OUT_DIR = os.path.join(ASSETS, "coins")
APP_PNG = os.path.join(ASSETS, "app_icon.png")
APP_ICO = os.path.join(ASSETS, "app_icon.ico")
PREVIEW = os.path.join(_ROOT, "preview")
os.makedirs(PREVIEW, exist_ok=True)


# ---------- 通用小工具 ----------
def alpha_bbox(img: QImage, threshold=12):
    """返回非透明内容的包围盒，用于裁掉原始 logo 的大片透明边。"""
    w, h = img.width(), img.height()
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if img.pixelColor(x, y).alpha() >= threshold:
                x0, y0 = min(x0, x), min(y0, y)
                x1, y1 = max(x1, x), max(y1, y)
    if x1 < 0:
        return QRectF(0, 0, w, h)
    pad = max(1, int(min(w, h) * 0.02))
    return QRectF(max(0, x0 - pad), max(0, y0 - pad),
                  min(w, x1 - x0 + 1 + 2 * pad),
                  min(h, y1 - y0 + 1 + 2 * pad))


def mean_lum(img: QImage):
    total, n = 0.0, 0
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            c = img.pixelColor(x, y)
            if c.alpha() > 60:
                total += (c.red() + c.green() + c.blue()) / 3.0
                n += 1
    return total / n if n else 128.0


def dechecker(img: QImage) -> QImage:
    """生成图把「透明」画成了浅灰棋盘格，这里把低饱和高亮像素抠掉。"""
    out = img.convertToFormat(QImage.Format_ARGB32).copy()
    for y in range(out.height()):
        for x in range(out.width()):
            c = out.pixelColor(x, y)
            r, g, b, a = c.red(), c.green(), c.blue(), c.alpha()
            sat = max(r, g, b) - min(r, g, b)
            lum = (r + g + b) / 3.0
            if sat < 20 and lum > 190:
                out.setPixelColor(x, y, QColor(0, 0, 0, 0))
            elif sat < 28 and lum > 150:
                out.setPixelColor(x, y, QColor(r, g, b, int(a * 0.25)))
    return out


def enhance(img: QImage, contrast=1.16) -> QImage:
    """提升对比度并把半透明边缘压实，避免缩到 30px 后发灰发虚。"""
    out = img.convertToFormat(QImage.Format_ARGB32).copy()
    for y in range(out.height()):
        for x in range(out.width()):
            c = out.pixelColor(x, y)
            if c.alpha() < 12:
                out.setPixelColor(x, y, QColor(0, 0, 0, 0))
                continue
            a = min(255, max(205, c.alpha()))
            r = max(0, min(255, int(128 + (c.red() - 128) * contrast)))
            g = max(0, min(255, int(128 + (c.green() - 128) * contrast)))
            b = max(0, min(255, int(128 + (c.blue() - 128) * contrast)))
            out.setPixelColor(x, y, QColor(r, g, b, a))
    return out


# ---------- 1. 品种图标 ----------
TARGET = 256          # 输出分辨率：256px，24~40px 显示时细节充足


def qimg_to_np(img: QImage):
    """QImage -> HxWx4 float32 数组（RGBA，非预乘）。"""
    img = img.convertToFormat(QImage.Format_RGBA8888)
    w, h = img.width(), img.height()
    arr = np.frombuffer(img.constBits(), np.uint8)
    arr = arr.reshape(h, img.bytesPerLine())[:, :w * 4].reshape(h, w, 4)
    return arr.astype(np.float32).copy()


def np_to_qimg(arr):
    h, w = arr.shape[:2]
    data = np.ascontiguousarray(np.clip(arr, 0, 255).astype(np.uint8))
    img = QImage(data.data, w, h, w * 4, QImage.Format_RGBA8888)
    return img.copy()


def unsharp(arr, amount=0.85):
    """3x3 反锐化掩码：放大后的 logo 恢复边缘锐度。"""
    rgb = arr[..., :3]
    pad = np.pad(rgb, ((1, 1), (1, 1), (0, 0)), mode="edge")
    blur = np.zeros_like(rgb)
    for dy in range(3):
        for dx in range(3):
            blur += pad[dy:dy + rgb.shape[0], dx:dx + rgb.shape[1]]
    blur /= 9.0
    out = rgb + (rgb - blur) * amount
    arr = arr.copy()
    arr[..., :3] = out
    return arr


def solidify(arr, contrast=1.10):
    """提高对比度 + 压实半透明边缘（缩到 24px 时不再发灰）。"""
    a = arr[..., 3]
    rgb = np.clip(128 + (arr[..., :3] - 128) * contrast, 0, 255)
    arr[..., :3] = np.where(a[..., None] > 8, rgb, 0)
    arr[..., 3] = np.where(a < 12, 0, np.clip(a * 1.12 + 26, 205, 255))
    return arr


def halo(arr, color=(232, 240, 255), alpha=135, radius=4):
    """暗色 logo 加柔和外发光：深色界面上看得见，但不是白色圆圈。"""
    a = arr[..., 3:4] / 255.0
    h, w = a.shape[:2]
    pad = np.pad(a, ((radius, radius), (radius, radius), (0, 0)), mode="edge")
    dil = np.zeros_like(a)
    for dy in range(2 * radius + 1):
        for dx in range(2 * radius + 1):
            dil = np.maximum(dil, pad[dy:dy + h, dx:dx + w])
    ha = dil * (alpha / 255.0)
    la = a
    out_a = ha + la * (1 - ha)
    safe = np.maximum(out_a, 1e-6)
    rgb = (np.array(color, np.float32) * ha + arr[..., :3] * la * (1 - ha)) / safe
    out = np.zeros_like(arr)
    out[..., :3] = np.where(out_a > 0.001, rgb, 0)
    out[..., 3] = out_a[..., 0] * 255.0
    return out


def enhance_coins():
    if not os.path.isdir(SRC_DIR):
        # 第一次运行：把当前原始图标备份，之后始终从备份重新生成
        shutil.copytree(OUT_DIR, SRC_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)
    files = sorted(f for f in os.listdir(SRC_DIR) if f.lower().endswith(".png"))
    glow = 0
    for name in files:
        src = QImage(os.path.join(SRC_DIR, name))
        if src.isNull():
            continue
        src = src.convertToFormat(QImage.Format_ARGB32)
        box = alpha_bbox(src)
        cropped = src.copy(int(box.x()), int(box.y()),
                           int(box.width()), int(box.height()))
        # 直接显示原图标：透明背景、无白底圆圈，只保留约 4% 留白
        side = int(TARGET * 0.92)
        logo = cropped.scaled(side, side, Qt.KeepAspectRatio,
                              Qt.SmoothTransformation)
        arr = qimg_to_np(logo)
        lum = float((arr[..., :3][arr[..., 3] > 60]).mean()) \
            if (arr[..., 3] > 60).any() else 128.0
        arr = solidify(arr)
        arr = unsharp(arr, 0.85)
        if lum < 105:               # 深色 logo：加柔和外发光，不糊在深色背景里
            arr = halo(arr)
            glow += 1
        canvas = np.zeros((TARGET, TARGET, 4), np.float32)
        oy = (TARGET - arr.shape[0]) // 2
        ox = (TARGET - arr.shape[1]) // 2
        canvas[oy:oy + arr.shape[0], ox:ox + arr.shape[1]] = arr
        np_to_qimg(canvas).save(os.path.join(OUT_DIR, name), "PNG")
    print(f"coins rebuilt @{TARGET}px, transparent, no disc "
          f"({len(files)} files, glow={glow})", flush=True)


# ---------- 2. 程序主图标 ----------
def find_emblem():
    candidates = [f for f in os.listdir(ASSETS)
                  if f.startswith("A_premium_app_icon") and f.endswith(".png")]
    if not candidates:
        return None
    return os.path.join(ASSETS, sorted(candidates)[-1])


def compose_app(size: int) -> QPixmap:
    """深色圆角底 + 霓虹渐变描边 + 生成的赛博朋克徽标。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 64.0

    bg = QLinearGradient(0, 0, size, size)
    bg.setColorAt(0, QColor("#111c33"))
    bg.setColorAt(0.55, QColor("#0a1020"))
    bg.setColorAt(1, QColor("#1a0f2b"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(bg))
    p.drawRoundedRect(QRectF(0.5 * s, 0.5 * s, 63 * s, 63 * s),
                      15 * s, 15 * s)

    rim = QLinearGradient(0, 0, size, size)
    rim.setColorAt(0, QColor(0, 229, 255))
    rim.setColorAt(0.5, QColor(123, 92, 255))
    rim.setColorAt(1, QColor(255, 43, 214))
    for width, alpha in ((6.5, 46), (3.6, 110), (1.8, 255)):
        g = QLinearGradient(0, 0, size, size)
        for stop, rgb in ((0, (0, 229, 255)),
                          (0.5, (123, 92, 255)), (1, (255, 43, 214))):
            g.setColorAt(stop, QColor(*rgb, alpha))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QBrush(g), width * s, Qt.SolidLine,
                      Qt.RoundCap, Qt.RoundJoin))
        p.drawRoundedRect(QRectF(2 * s, 2 * s, 60 * s, 60 * s),
                          13.5 * s, 13.5 * s)

    emblem_path = find_emblem()
    if emblem_path:
        src = dechecker(QImage(emblem_path))
        box = alpha_bbox(src)
        cropped = src.copy(int(box.x()), int(box.y()),
                           int(box.width()), int(box.height()))
        em = cropped.scaled(int(60 * s), int(60 * s), Qt.KeepAspectRatio,
                            Qt.SmoothTransformation)
        p.drawPixmap(int((size - em.width()) / 2),
                     int((size - em.height()) / 2),
                     QPixmap.fromImage(em))
    else:
        # 资源缺失时的极简兜底：发光 C + 闪电
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 229, 255), 7 * s, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(QRectF(15 * s, 15 * s, 34 * s, 34 * s),
                  50 * 16, 260 * 16)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ff2bd6"))
        p.drawPolygon([QPointF(35 * s, 18 * s), QPointF(25 * s, 34 * s),
                       QPointF(31 * s, 34 * s), QPointF(28 * s, 46 * s),
                       QPointF(41 * s, 29 * s), QPointF(34 * s, 29 * s)])
    p.end()
    return pm


def write_ico(sizes=(16, 24, 32, 48, 64, 128, 256)):
    """手写 BMP(32bit BGRA) 格式 ICO，PyInstaller / Windows 均兼容。"""
    blobs, entries = [], []
    offset = 6 + 16 * len(sizes)
    for size in sizes:
        img = compose_app(size).toImage().convertToFormat(QImage.Format_ARGB32)
        w, h = img.width(), img.height()
        bpr = img.bytesPerLine()
        raw = bytes(img.constBits())[:bpr * h]
        rows = [raw[r * bpr:(r + 1) * bpr] for r in range(h)]
        xor = b"".join(reversed(rows))          # BMP 自下而上
        mask_row = ((w + 31) // 32) * 4
        and_mask = b"\x00" * (mask_row * h)
        header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0,
                             len(xor) + len(and_mask), 0, 0, 0, 0)
        blob = header + xor + and_mask
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256,
                                   0, 0, 1, 32, len(blob), offset))
        offset += len(blob)
        blobs.append(blob)
    with open(APP_ICO, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(sizes)))
        f.write(b"".join(entries))
        f.write(b"".join(blobs))
    print("ico written:", APP_ICO, os.path.getsize(APP_ICO), "bytes",
          flush=True)


def build_app():
    compose_app(512).save(APP_PNG, "PNG")
    compose_app(256).save(os.path.join(PREVIEW, "5_app_icon.png"), "PNG")
    compose_app(64).save(os.path.join(PREVIEW, "6_app_icon_64.png"), "PNG")
    compose_app(16).save(os.path.join(PREVIEW, "7_app_icon_16.png"), "PNG")
    write_ico()
    print("app_icon.png written", flush=True)


enhance_coins()
build_app()
print("DONE", flush=True)
