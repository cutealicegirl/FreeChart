# -*- coding: utf-8 -*-
"""离屏生成界面预览图（不启动网络线程，不写真实配置）。"""
import math
import os
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_preview_")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QPoint
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

app = QApplication([])
for f in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc"):
    if os.path.exists(f):
        QFontDatabase.addApplicationFont(f)

from core.config import Config
from data.api_base import Ticker
from data.klines import Candle
from data.universe import all_of, names
from ui.chart_view import ChartView
from ui.main_window import MainWindow

OUT = os.path.join(_ROOT, "preview")
os.makedirs(OUT, exist_ok=True)


def ticker(sym, price, chg):
    return Ticker(sym, sym, price, chg, price * 1.03,
                  price * 0.97, price * 1.7e6)


def candles(n=420):
    out, price = [], 42000.0
    for i in range(n):
        wave = math.sin(i / 9.0) * 620 + math.cos(i / 3.5) * 180
        drift = i * 46
        o = price
        c = 42000.0 + drift + wave
        out.append(Candle(ts=1600000000 + i * 86400,
                          time_label=f"{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
                          open=o, high=max(o, c) + 260,
                          low=min(o, c) - 260, close=c,
                          volume=800 + (i % 17) * 90))
        price = c
    return out


cfg = Config()
w = MainWindow(cfg)
w.scheduler.stop()
w.scheduler.refresh_now = lambda: None
w.apply_window_settings(save=False)

prices = {"BTC": 67891.23, "ETH": 3210.55, "SOL": 178.42,
          "BNB": 612.8, "XRP": 2.31, "DOGE": 0.1834,
          "ZEC": 54.27, "NEAR": 4.82, "ARB": 0.9231,
          "RENDER": 7.44, "HYPE": 31.6, "LINK": 18.72}
tickers = {s: ticker(s, p, 2.35 if i % 2 else -1.28)
           for i, (s, p) in enumerate(prices.items())}
w._on_fetched(tickers, "Binance", 1794155000)
w.resize(420, 640)
w.show()
QApplication.processEvents()
w.grab().save(os.path.join(OUT, "1_watchlist.png"))
print("saved watchlist", flush=True)

w._switch_sub("all")
QApplication.processEvents()
for s in all_of("crypto")[:16]:
    t = ticker(s, 100.0 / (1 + list(all_of("crypto")).index(s) * 0.1),
               1.2)
    w.all_rows["crypto"][s].update_ticker(t)
QApplication.processEvents()
w.grab().save(os.path.join(OUT, "2_all300.png"))
print("saved all300", flush=True)

cv = ChartView(cfg)
cv._symbol, cv._interval = "BTC", "1d"
cv.lbl_symbol.setText("BTC")
cv.lbl_name.setText("Bitcoin · 日K")
cv.lbl_market.setText("加密货币")
cv.lbl_price.setText("67,891.23")
cv.lbl_change.setText("+2.35%")
cv.chart.interval = "1d"
cv.chart.set_data(candles())
cv.chart.show_auto = True      # 趋势线 / 压力位 / 支撑位 三个开关一起打开
cv.chart.show_extremes = True
cv.chart.show_pivots = True    # 局部高点 LH / 局部低点 LL
for _b in cv._smart_buttons.values():
    _b.setChecked(True)
cv.chart._view_count = 200
cv.chart._mouse_pos = QPoint(520, 250)
cv.resize(1020, 690)
cv.show()
QApplication.processEvents()
cv.grab().save(os.path.join(OUT, "3_chart.png"))
print("saved chart", flush=True)

# 全历史一屏（面积折线 + 压力支撑 + 史高史低 + 光标倍数）
from PySide6.QtCore import QPoint
cv.chart._view_count = len(cv.chart.candles)
cv.chart._pan = 0.0
cv.chart._mouse_pos = QPoint(620, 300)
cv.chart.update()
QApplication.processEvents()
cv.grab().save(os.path.join(OUT, "4_chart_allhistory.png"))
print("saved chart allhistory", flush=True)

# 任务栏右侧常驻实时价格：模拟「通知区左侧已被网速小工具占用」的避让效果
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from ui.price_badge import PriceBadge

badge = PriceBadge(cfg)
badge.update_ticker(ticker("BTC", 67891.23, 2.35), "BTC")
badge.show()
QApplication.processEvents()
shot = badge.grab()
bar_h = max(48, shot.height() + 6)
other_w = 168                      # 旁边那款网速/内存小工具的宽度
tray_w = 232                       # 托盘图标 + 时钟
apps_w = 3 * 44 + 12
bar = QPixmap(apps_w + 16 + shot.width() + 8 + other_w + 10 + tray_w, bar_h)
bar.fill(QColor("#1c1c1c"))
p = QPainter(bar)
p.setPen(Qt.NoPen)
# 左侧：几个运行中的程序按钮
p.setBrush(QColor("#2b2b2b"))
for i in range(3):
    p.drawRoundedRect(QRectF(12 + i * 44, bar_h / 2 - 15, 36, 30), 4, 4)
# 我们的价格条：紧挨着别人小工具的左侧，留 8px 间隙（不重叠）
badge_x = apps_w + 16
p.drawPixmap(int(badge_x), int((bar_h - shot.height()) / 2), shot)
# 别的程序小工具（网速/内存），我们主动避让它
other_x = badge_x + shot.width() + 8
p.setBrush(QColor("#232323"))
p.drawRect(QRectF(other_x, 2, other_w, bar_h - 4))
p.setPen(QColor("#8a8f98"))
p.setFont(QFont("Consolas", 9))
p.drawText(QRectF(other_x, 0, other_w, bar_h), Qt.AlignCenter,
           "↓1.2M  ↑320K\nMEM 42%")
# 右侧：托盘图标 + 时钟
p.setPen(Qt.NoPen)
p.setBrush(QColor("#3a3a3a"))
for i in range(5):
    p.drawRoundedRect(QRectF(other_x + other_w + 14 + i * 26,
                             bar_h / 2 - 8, 18, 16), 3, 3)
p.setPen(QColor("#d8d8d8"))
p.setFont(QFont("Consolas", 9))
p.drawText(QRectF(bar.width() - 76, 0, 66, bar_h),
           Qt.AlignVCenter | Qt.AlignLeft, "12:38\n11/09")
p.end()
bar.save(os.path.join(OUT, "8_taskbar_price.png"))
print("saved taskbar price", flush=True)
print("DONE", flush=True)
