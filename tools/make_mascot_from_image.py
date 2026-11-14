# -*- coding: utf-8 -*-
"""把用户提供的 Remielle Dan 立绘处理成带透明通道的默认看板娘。

原图是白底插画，直接贴到深色窗口上会带一块白方块。这里从四个角做
连通区域填充（flood fill），只把和边缘连通的纯白背景变透明——人物身上
的白色裙装/翅膀不会被误伤，因为它们在空间上和背景不连通。

用法：
    python tools/make_mascot_from_image.py <源图> [输出路径]
"""
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT, "assets", "mascot.png")

# 填充用的哨兵色（正常插画里不会出现这种洋红）
KEY = (255, 0, 255)


def cut_background(src: str, thresh: int = 20) -> Image.Image:
    im = Image.open(src).convert("RGB")
    w, h = im.size
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
             (w // 2, 0), (w // 2, h - 1)]
    for seed in seeds:
        try:
            ImageDraw.floodfill(im, seed, KEY, thresh=thresh)
        except Exception:
            continue
    rgba = im.convert("RGBA")
    px = rgba.load()
    for y in range(h):
        for x in range(w):
            r, g, b, _a = px[x, y]
            if r > 240 and g < 24 and b > 240:
                px[x, y] = (255, 255, 255, 0)
    return rgba


def trim(im: Image.Image, pad: int = 6) -> Image.Image:
    bbox = im.getbbox()
    if not bbox:
        return im
    left, top, right, bottom = bbox
    return im.crop((max(0, left - pad), max(0, top - pad),
                    min(im.width, right + pad), min(im.height, bottom + pad)))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT
    im = cut_background(src)
    im = trim(im)
    # 统一高度，宽度按比例；看板娘展示区高约 420-560，留足细节
    target_h = 900
    if im.height > target_h:
        ratio = target_h / float(im.height)
        im = im.resize((max(1, int(im.width * ratio)), target_h),
                       Image.LANCZOS)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out, "PNG", optimize=True)
    print(f"saved {out}  {im.size[0]}x{im.size[1]}  "
          f"{os.path.getsize(out) / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
