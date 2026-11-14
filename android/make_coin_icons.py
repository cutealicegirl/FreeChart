# -*- coding: utf-8 -*-
"""把桌面 assets/coins 的官方 256px 图标压成移动端 64px PNG。

桌面端用的是各项目官方原图（256×256 RGBA，约 8.6MB）。WebView 里
列表 / 图表头只需要 34~48px，直接把原图塞进 APK 会白白多出 8MB，
因此这里统一转成 64px（高分屏 2× 也够用）再打包，总量约 1.3MB。

用法： python android/make_coin_icons.py
产物： android/assets/www/coins/<code>.png（文件名与桌面一致，全小写）
"""
import glob
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets", "coins")
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "assets", "www", "coins")


def main():
    os.makedirs(DST, exist_ok=True)
    files = sorted(glob.glob(os.path.join(SRC, "*.png")))
    total = 0
    for src in files:
        im = Image.open(src).convert("RGBA")
        if im.size != (64, 64):
            im = im.resize((64, 64), Image.LANCZOS)
        out = os.path.join(DST, os.path.basename(src).lower())
        im.save(out, "PNG", optimize=True)
        total += os.path.getsize(out)
    print("生成 %d 个品种图标，合计 %.2f MB -> %s"
          % (len(files), total / 1024 / 1024, DST))
    return len(files)


if __name__ == "__main__":
    main()
