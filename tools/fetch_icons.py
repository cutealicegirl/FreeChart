# -*- coding: utf-8 -*-
"""开发期补齐缺失的币种官方图标（只写 assets/coins_src，成品由 build_icons 生成）。

数据源：CoinCap 静态图标库 https://assets.coincap.io/assets/icons/{sym}@2x.png
（jsdelivr / raw.githubusercontent / coingecko / coinmarketcap 在本机被网络阻断）

运行：python tools/fetch_icons.py [--limit N]
"""
import concurrent.futures as cf
import json
import os
import sys
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage          # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
SRC = os.path.join(_ROOT, "assets", "coins_src")
os.makedirs(SRC, exist_ok=True)
URL = "https://assets.coincap.io/assets/icons/{}@2x.png"


def have(sym: str) -> bool:
    p = os.path.join(SRC, sym.lower() + ".png")
    return os.path.isfile(p) and os.path.getsize(p) > 800


def fetch(sym: str):
    url = URL.format(sym.lower())
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=12).read()
    except Exception:
        return sym, "miss"
    img = QImage.fromData(data)
    if img.isNull() or img.width() < 32 or img.height() < 32:
        return sym, "bad"
    # 校验不是全透明 / 纯色块
    if img.convertToFormat(QImage.Format_ARGB32).pixelColor(
            img.width() // 2, img.height() // 2).alpha() < 8:
        return sym, "empty"
    with open(os.path.join(SRC, sym.lower() + ".png"), "wb") as f:
        f.write(data)
    return sym, "ok"


def main():
    raw = json.load(open(os.path.join(_ROOT, "data", "top300.json"),
                        encoding="utf-8"))
    syms = [e[0] for e in raw["crypto"]]
    todo = [s for s in syms if not have(s)]
    limit = 0
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if limit:
        todo = todo[:limit]
    print(f"missing={len(todo)}", flush=True)
    got = 0
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for sym, state in ex.map(fetch, todo):
            if state == "ok":
                got += 1
    print(f"downloaded={got} / {len(todo)}  -> assets/coins_src", flush=True)


main()
