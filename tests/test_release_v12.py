# -*- coding: utf-8 -*-
"""v12 离线回归：任务栏价格条单行紧凑布局 + ATH/ATL 不再拿局部点冒充
+ 快捷方式图标跟随程序。"""
import glob
import inspect
import os
import shutil
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_v12_")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QLabel

app = QApplication([])

from ui.theme import apply_global
apply_global(app)          # 注册内置 IBM Plex，宽度测量才与真机一致

import core.shortcut as sc
from core.config import Config
from data.klines import Candle
from ui.chart_view import CandleChart
from ui.price_badge import PriceBadge
from data.api_base import Ticker

cfg = Config()


def bars(n=300, peak=150):
    out = []
    for i in range(n):
        high = 105 + i % 9
        low = 95 + i % 5
        if i == peak:
            high = 9999.0            # 这一段里的「局部最高」
        if i == peak + 30:
            low = 1.0                # 这一段里的「局部最低」
        out.append(Candle(ts=1600000000 + i * 86400, time_label=str(i),
                          open=100 + i % 7, high=high, low=low,
                          close=101 + i % 6, volume=1000 + i))
    return out


# ===== 1. 价格条：单行、紧凑、宽度自适应 =====
badge = PriceBadge(cfg)
assert not badge.findChildren(QLabel), "改为纯 QPainter 自绘，不再用 QLabel 堆两行"
src = inspect.getsource(PriceBadge)
assert "QVBoxLayout" not in src and "QHBoxLayout" not in src
assert badge.HEIGHT <= 30, "整条高度必须比旧版 40px 的两行方块更扁"

t = Ticker("BTC", "BTC", 67891.23, 2.35, 70000.0, 66000.0, 1.7e9)
badge.update_ticker(t, "BTC")
assert badge._price_text == "$67,891.23", badge._price_text
assert badge._change_raw == "+2.35%"
assert badge._symbol == "BTC"
w_full = badge._layout()["w"]
assert 90 <= w_full <= badge.W_MAX
assert badge.height() == badge.HEIGHT, "单行高度"
print(f"1. 单行价格条 OK（{w_full}x{badge.HEIGHT}，旧版 158x40）")

# 三档信息密度：完整 > 紧凑 > 极简，宽度逐级收窄
badge._set_style("slim")
w_slim = badge._layout()["w"]
badge._set_style("mini")
w_mini = badge._layout()["w"]
assert w_mini < w_slim < w_full, (w_full, w_slim, w_mini)
assert badge._layout()["show_chg"] is False
assert badge._change_raw == "+2.35%", "切样式不能把行情文本丢掉"
badge._set_style("full")
assert badge._layout()["show_chg"] is True
print(f"2. 三档样式 OK（完整 {w_full} / 紧凑 {w_slim} / 极简 {w_mini}）")

# 长价格（8 位小数）不会撑爆，宽度有上限
badge.update_ticker(
    Ticker("SHIB", "SHIB", 0.00001234, -4.21, 0.000013, 0.000012, 1e8),
    "SHIB")
assert badge._layout()["w"] <= badge.W_MAX
assert badge._price_text.lstrip("$").startswith("0.0000")
assert badge._change_raw.startswith("-")
print("3. 长价格自适应 OK")

# ===== 2. ATH / ATL 只认「回溯到上市首根」后的全历史极值 =====
c = CandleChart()
c.resize(960, 620)
data = bars()
c.set_data(data)
c._view_count = len(data)          # 一屏铺满，ATH/ATL 都在视野里
c._pan = 0.0
c.show_extremes = True
c.show_pivots = True


def render_extremes():
    img = QImage(960, 620, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    c._draw_extremes(p, c._geom())
    p.end()


c.history_exhausted = False
render_extremes()
assert c._extreme_rects == [], "历史没回溯完时，局部高低点绝不能标成 ATH/ATL"

c.history_exhausted = True
render_extremes()
assert len(c._extreme_rects) == 2, "回溯完成后 ATH 与 ATL 各标一个"
assert c._extremes[1] == 9999.0

# 让位逻辑也必须以「真实 ATH/ATL」为前提
psrc = inspect.getsource(CandleChart._draw_pivots)
assert "history_exhausted" in psrc
esrc = inspect.getsource(CandleChart._draw_extremes)
assert "history_exhausted" in esrc
print("4. ATH/ATL 门控 OK（未回溯不算史高史低，局部点不再冒充）")

# 日线打开 ATH/ATL 会后台补齐历史（分钟线不自动拉，避免百万根）
assert hasattr(c, "_FULL_HISTORY_INTERVALS") is False  # 在 ChartView 上
import ui.chart_view as cv_mod
assert hasattr(cv_mod.ChartView, "_ensure_extremes_history")
assert "1d" in cv_mod.ChartView._FULL_HISTORY_INTERVALS
assert "15m" not in cv_mod.ChartView._FULL_HISTORY_INTERVALS
print("5. ATH/ATL 历史补齐策略 OK")

# ===== 4. 光标处价格 vs 当前市场价：随鼠标上下位置实时变化 =====
hc = CandleChart()
hc.resize(960, 620)
hc.set_data(bars())
hc._view_count = len(hc.candles)
hc._pan = 0.0
hc.last_price = 100.0            # 当前市场价
g = hc._geom()
mid_x = g["x0"] + g["w"] * 0.5

seen = {}


def hover_text(price_wanted):
    y = hc._y_price(g, price_wanted)
    hc._mouse_pos = QPointF(mid_x, y)
    texts = []
    orig = hc._text

    def spy(painter, x, y0, w, h, text, *a, **k):
        texts.append(text)
        return orig(painter, x, y0, w, h, text, *a, **k)

    hc._text = spy
    try:
        hc.grab()
    finally:
        del hc._text
    return [t for t in texts if isinstance(t, str)
            and t.startswith(("UP", "DN"))]


up = hover_text(120.0)           # 光标价高于现价 = 涨幅
dn = hover_text(80.0)            # 低于现价 = 跌幅
assert up and up[0].startswith("UP"), up
assert dn and dn[0].startswith("DN"), dn
assert "+20" in up[0], f"120 vs 100 应为 +20%，实际 {up[0]}"
assert "-20" in dn[0], f"80 vs 100 应为 -20%，实际 {dn[0]}"
assert up[0] != dn[0], "鼠标上下移动必须改变涨跌幅"

# 同一横坐标、不同纵坐标 -> 数值不同（旧实现按 K 线收盘价算，纵移不变）
assert up[0] != dn[0]
# 副图（成交量）里不按价格轴外推，不显示涨跌标签
vy = g["vol"].top() + g["vol"].height() * 0.5 if "vol" in g else None
if vy is not None:
    hc._mouse_pos = QPointF(mid_x, vy)
    texts = []
    orig = hc._text

    def spy2(painter, x, y0, w, h, text, *a, **k):
        texts.append(text)
        return orig(painter, x, y0, w, h, text, *a, **k)

    hc._text = spy2
    try:
        hc.grab()
    finally:
        del hc._text
    assert not [t for t in texts if isinstance(t, str)
                and t.startswith(("UP", "DN"))], "副图不该出现价格涨跌标签"
print("6. 光标价格涨跌幅 OK（随纵坐标变化，基准为实时价）")

# ===== 5. 快捷方式图标跟随 =====
ico_asset = sc.icon_asset()
assert os.path.isfile(ico_asset) and os.path.getsize(ico_asset) > 10000
ico = sc.sync_icon_file()
assert ico and os.path.isfile(ico)
assert os.path.basename(ico).startswith("app_") and ico.endswith(".ico")
assert os.path.getsize(ico) == os.path.getsize(ico_asset)
assert sc.sync_icon_file() == ico, "同一份 ICO 必须落到同一个哈希文件名"

exe = os.path.join(_ROOT, "dist", "Free Chart.exe")
assert sc._is_ours(exe, exe, "x.lnk")
assert sc._is_ours(r"C:\somewhere\FreeChart.exe", exe, "x.lnk")
assert not sc._is_ours(r"C:\Windows\notepad.exe", exe, "x.lnk")

# 有真实快捷方式时，在副本上验证「只改图标、不改目标」
srcs = glob.glob(os.path.join(os.path.expanduser("~"), "Desktop",
                              "FreeChart*.lnk"))
if srcs:
    tmp = os.path.join(tempfile.mkdtemp(prefix="ct_lnk_"), "copy.lnk")
    shutil.copyfile(srcs[0], tmp)          # copy2 会带 ACL，普通复制即可
    target_before = sc.target_of(tmp)
    with sc.ShellLink() as link:
        assert link.load(tmp)
        link.set_icon(ico, 0)
        assert link.save(tmp)
    got_icon, idx = sc.current_icon_of(tmp)
    assert idx == 0 and os.path.normcase(got_icon) == os.path.normcase(ico)
    assert sc.target_of(tmp) == target_before, "改图标不得动快捷方式目标"
    print("7. 快捷方式图标重写 OK（target 保持不变）")
else:
    print("6. 快捷方式图标重写 SKIP（无桌面快捷方式样本）")

# ===== 4. 托盘菜单提供手动修复入口 =====
from ui.main_window import MainWindow
w = MainWindow(cfg)
w.scheduler.stop()
labels = [a.text() for a in w.tray_menu.actions()]
assert "修复快捷方式图标" in labels
w.quit_app()
print("8. 托盘「修复快捷方式图标」入口 OK")

print("\nv12 全部回归测试通过 ✅")
from qt_exit import finish       # 跳过 offscreen 的 Qt 卸载竞态
finish()
