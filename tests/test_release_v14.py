# -*- coding: utf-8 -*-
"""v14 离线回归：股票真实 logo（本地缓存 / 域名缓存 / 字徽兜底）。"""
import json
import os
import sys
import tempfile

_APPDATA = tempfile.mkdtemp(prefix="ct_v14_")
os.environ["APPDATA"] = _APPDATA
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

app = QApplication([])

from data import stock_logo
from ui.icons import invalidate_symbol, symbol_icon

# ===== 1. 市场识别 / 代码提取 =====
assert stock_logo.market("SH:600519") == "cn"
assert stock_logo.market("SZ:300750") == "cn"
assert stock_logo.market("HK:00700") == "hk"
assert stock_logo.market("US:AAPL") == "us"
assert stock_logo.market("BTC") == ""
assert stock_logo.code_of("HK:00700") == "00700"
print("1. 市场 / 代码识别 OK")

# ===== 2. 没有缓存时 local_file 为空 =====
assert stock_logo.local_file("US:NVDA") == ""
print("2. 未缓存时返回空 OK")

# ===== 3. 手工放一张 logo -> local_file 命中、symbol_icon 用它而不是字徽 =====
pm = QImage(120, 120, QImage.Format_ARGB32)
pm.fill(QColor("#e60012"))
p = QPainter(pm)
p.fillRect(10, 10, 100, 100, QColor("#ffffff"))
p.end()
path = os.path.join(stock_logo.logo_dir(), "nvda.png")
assert pm.save(path, "PNG")
assert stock_logo.local_file("US:NVDA") == path
invalidate_symbol("US:NVDA")
icon = symbol_icon("US:NVDA", 30).toImage()
# 中心应是白色（真 logo），不是字徽的深色渐变底
c = icon.pixelColor(icon.width() // 2, icon.height() // 2)
assert c.lightness() > 180, f"应显示真实 logo, 实际 {c.name()} {c.lightness()}"
print("3. 真实 logo 优先于字徽 OK")

# ===== 4. invalidate_symbol 后能读回新图 =====
invalidate_symbol("US:NVDA")
pm2 = QImage(120, 120, QImage.Format_ARGB32)
pm2.fill(QColor("#0047ab"))
assert pm2.save(path, "PNG")
icon2 = symbol_icon("US:NVDA", 30).toImage()
c2 = icon2.pixelColor(30 // 2, 30 // 2)
assert c2.blue() > c2.red(), f"应换成新图, 实际 {c2.name()}"
print("4. 缓存失效后立即换图 OK")

# ===== 5. 域名缓存：命中 JSON 时不发网络请求 =====
cache = os.path.join(_APPDATA, "FreeChart", "stock_domains.json")
os.makedirs(os.path.dirname(cache), exist_ok=True)
with open(cache, "w", encoding="utf-8") as f:
    json.dump({"HK:00700": "www.tencent.com"}, f)
stock_logo._domains_loaded = False
stock_logo._domains.clear()
assert stock_logo.domain_of("HK:00700") == "www.tencent.com"
print("5. 域名缓存命中 OK（零网络）")

# ===== 6. 未 start 时 request 不建线程、不联网 =====
stock_logo.request("US:AAPL")
stock_logo.request("BTC")
assert stock_logo._worker is None
print("6. request 未启动时不联网 OK")

# ===== 7. 无 logo 的股票仍走字徽（有实底、不为空）=====
invalidate_symbol("US:SPY")
img = symbol_icon("US:SPY", 30).toImage()
n = sum(1 for y in range(0, 30, 2) for x in range(0, 30, 2)
        if img.pixelColor(x, y).alpha() > 10)
assert n > 40
print("7. 无真实 logo 时字徽兜底 OK")

print("\nv14 全部回归测试通过 ✅")
