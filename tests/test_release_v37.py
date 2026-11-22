# -*- coding: utf-8 -*-
"""v37 回归：改名 Free Chart + 品种发展历程/档案 + 详情准确性 +
「小时间范围局部高低点不得冒充历史高低点」。

离线运行，不启动任何网络请求（QT_QPA_PLATFORM=offscreen / CT_OFFLINE=1）。
"""
import inspect
import os
import re
import sys
import tempfile
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix="ct_v37_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtGui import QImage, QPainter            # noqa: E402
from PySide6.QtWidgets import QApplication           # noqa: E402

app = QApplication([])

from core import brand                                # noqa: E402
from core.config import Config                        # noqa: E402
from data import about as about_db                    # noqa: E402
from data import fundamentals                        # noqa: E402
from data import history_stats                        # noqa: E402
from data import timeline as tl                       # noqa: E402
from data.klines import Candle                        # noqa: E402
from ui.chart_view import CandleChart, ChartView      # noqa: E402
from ui.detail_dialog import SymbolDetailDialog      # noqa: E402

FAILS, CHECKS = [], [0]


def ok(name, cond, extra=""):
    CHECKS[0] += 1
    print(("PASS " if cond else "FAIL ") + name +
          (("  " + str(extra)) if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


print("=== v37 · 品牌 / 资料库 / 详情准确性 / 图表极值口径 ===\n")

# ---------------- 1. 品牌 ----------------
ok("1. 程序名与内部 ID 全面统一为 Free Chart / FreeChart",
   brand.APP_NAME == "Free Chart" and brand.APP_ID == "FreeChart"
   and "全市场行情" in brand.APP_TITLE)
_mw = open(os.path.join(_ROOT, "ui", "main_window.py"), encoding="utf-8").read()
_pb = open(os.path.join(_ROOT, "ui", "price_badge.py"), encoding="utf-8").read()
_strings = open(os.path.join(_ROOT, "android", "res", "values",
                             "strings.xml"), encoding="utf-8").read()
_index = open(os.path.join(_ROOT, "android", "assets", "www",
                           "index.html"), encoding="utf-8").read()
ok("2. 桌面 / Android 可见文案全部换成新名",
   "brand.APP_TITLE" in _mw and "Free Chart 行情看板" in _mw
   and "brand.BADGE_TOOLTIP" in _pb
   and "<string name=\"app_name\">Free Chart</string>" in _strings
   and "Free Chart" in _index)
# 品牌彻底统一：包名 / 配置目录 / spec / 交付名全部为 FreeChart。
# 旧配置目录由 brand.migrate_legacy_appdata() 在启动时一次性迁移，不丢数据。
ok("3. 包名 / 配置目录 / spec / 交付名全部统一为 FreeChart",
   brand.APP_ID == "FreeChart"
   and "name='Free Chart'" in open(
       os.path.join(_ROOT, "FreeChart.spec"), encoding="utf-8").read()
   and '"FreeChart", "config.json"' in open(
       os.path.join(_ROOT, "core", "config.py"), encoding="utf-8").read()
   and 'package="com.freechart.app"' in open(
       os.path.join(_ROOT, "android", "AndroidManifest.xml"),
       encoding="utf-8").read())

# ---------------- 2. 发展历程资料库 ----------------
st = tl.stats()
ok("4. 发展历程覆盖主流品种且事件量充足",
   st["symbols"] >= 40 and st["events"] >= 150 and st["archive"] >= 20, st)
_date_re = re.compile(r"^\d{4}( 年代|-\d{2}(-\d{2})?)?$")
_bad = [(s, e.get("date")) for s, rows in tl.TIMELINE.items() for e in rows
        if not (_date_re.match(str(e.get("date") or ""))
                and e.get("title") and e.get("src"))]
ok("5. 每条里程碑日期格式规范、标题与来源不为空", not _bad, _bad[:3])
_btc = [e["date"] for e in tl.timeline("BTC")]
ok("6. BTC 时间线含已核验的关键日期且按时间正序",
   "2008-10-31" in _btc and "2009-01-03" in _btc
   and "2024-01-10" in _btc and _btc == sorted(_btc))
_xrp = [e["date"] for e in tl.timeline("XRP")]
ok("7. XRP 案已更新到 2025-08-07 终结（旧资料过时）",
   "2020-12-22" in _xrp and "2025-08-07" in _xrp)
ok("8. 茅台上市日 / 交易所 / 发行价可核对",
   tl.archive("SH:600519").get("listing_date") == "2001-08-27"
   and "上海证券交易所" in tl.archive("SH:600519").get("exchange", "")
   and "31.39" in tl.archive("SH:600519").get("ipo_price", ""))
ok("9. 未收录品种发展历程为空、档案不编造",
   tl.timeline("US:ZZZZ") == [] and tl.archive("US:ZZZZ")["covered"] is False
   and "exchange" in tl.archive("US:ZZZZ"))
ok("10. 档案字段表与来源说明齐备",
   len(tl.ARCHIVE_FIELDS) >= 10 and tl.SOURCE_NOTE and tl.NO_DATA)

# ---------------- 3. about() 准确性修正 ----------------
_a = about_db.about("US:ZZZZ")
ok("11. 未收录品种不再拿通用说明冒充业务 / 特点 / 用途",
   _a["business"] is None and _a["highlights"] is None
   and _a["purpose"] is None and _a["background"] is None)
ok("12. 收录品种挂上发展历程与档案",
   len(about_db.about("BTC")["timeline"]) >= 8
   and about_db.about("BTC")["archive"]["covered"] is True
   and about_db.about("BTC")["timeline_verified_at"] == tl.VERIFIED_AT)
_oc = about_db.about("ONCHAIN:9cRCtestpump")
ok("13. 链上合约不冒充项目背景、发展历程为空",
   _oc["summary"] is None and _oc["timeline"] == []
   and _oc["archive"]["exchange"] == "链上 DEX（合约地址交易）")

# ---------------- 4. 真实字段：成交额单位 / 行情时间 / 市场差异 ----------------
class _Resp:
    def __init__(self, text):
        self.text = text
        self.encoding = "gbk"


def _fields(mkt):
    f = [""] * 60
    f[1], f[3], f[4], f[5] = "测试品种", "100", "99", "100.5"
    f[30] = {"cn": "20261113161455", "hk": "2026/11/13 16:08:22",
             "us": "2026-11-13 16:00:01"}[mkt]
    f[33], f[34], f[36] = "105", "95", "1000"
    f[37] = "5000" if mkt == "cn" else "12251162809.622"
    f[38], f[39], f[43] = "1.2", "20", "3.1"
    f[44], f[45] = "800", "1000"
    f[46] = "6.2" if mkt == "cn" else "TENCENT"
    f[47], f[48], f[49] = "110", "90", "1.3"
    f[51], f[52], f[53] = "100.2", "19", "21"
    if mkt != "cn":
        f[48], f[49] = "653.7", "375.2"      # 52 周高 / 低
    return f


_DB = {fundamentals.tencent_code(s): _fields(m)
       for s, m in (("SH:600519", "cn"), ("HK:00700", "hk"),
                    ("US:NVDA", "us"))}
_orig_get = fundamentals.HTTP.get


def _fake_get(url, timeout=None, **kw):
    code = url.split("q=")[-1]
    return _Resp('v_%s="%s"' % (code, "~".join(_DB.get(code, [""] * 60))))


fundamentals.HTTP.get = _fake_get
try:
    cn = fundamentals._stock_profile("SH:600519", 1.0)
    hk = fundamentals._stock_profile("HK:00700", 1.0)
    us = fundamentals._stock_profile("US:NVDA", 1.0)
finally:
    fundamentals.HTTP.get = _orig_get

ok("14. A 股成交额仍是万元→元换算",
   abs(cn["amount_24h"] - 5000 * 1e4) < 1, cn.get("amount_24h"))
ok("15. 港股 / 美股成交额不再被放大一万倍（v37 修复）",
   abs(hk["amount_24h"] - 12251162809.622) < 1
   and abs(us["amount_24h"] - 12251162809.622) < 1,
   (hk.get("amount_24h"), us.get("amount_24h")))
ok("16. 三种行情时间格式都能解析（港美股不再显示 —）",
   cn["quote_ts"] > 0 and hk["quote_ts"] > 0 and us["quote_ts"] > 0)
ok("17. A 股涨跌停 / 港美股 52 周高低按市场区分，不串用",
   cn.get("limit_up") == 110 and cn.get("week52_high") is None
   and hk.get("week52_high") == 653.7 and hk.get("limit_up") is None
   and us.get("week52_low") == 375.2)
ok("18. 成交量单位按市场标注（手 / 股）",
   "手" in cn["volume_unit"] and "股" in hk["volume_unit"]
   and "股" in us["volume_unit"])
ok("19. PROFILE_FIELDS 覆盖新增真实字段",
   all(k in fundamentals.PROFILE_FIELDS
       for k in ("prev_close", "week52_high", "quote_tz", "exchange")))

# ---------------- 5. 行情里程碑（真实数据计算） ----------------
_m = history_stats.compute(
    [(1, 110, 90, 100), (2, 130, 95, 120), (3, 125, 80, 90)],
    "测试源", "月 K", "区间说明")
ok("20. 区间最高 / 最低 / 涨跌 / 最大回撤计算正确",
   _m["ok"] and _m["high"] == 130 and _m["low"] == 80
   and abs(_m["change_pct"] + 10.0) < 1e-6
   and abs(_m["max_drawdown"] + 25.0) < 1e-6, _m)
ok("21. 样本不足时不产出伪造极值",
   history_stats.compute([(1, 1, 1, 1)], "x", "y")["ok"] is False)

# ---------------- 6. 图表：小时间范围局部高低点不得冒充历史高低 ----------------
def bars(n=60):
    out = []
    for i in range(n):
        p = 100.0 + i * 0.5
        out.append(Candle(ts=1700000000 + i * 86400, time_label="",
                          open=p, high=p + 2, low=p - 2, close=p + 0.2,
                          volume=10))
    return out


c = CandleChart()
c.resize(960, 620)
c.set_data(bars())
c._view_count = len(c.candles)
c._pan = 0.0
c.show_extremes = True
c.show_pivots = True


def render_extremes():
    img = QImage(960, 620, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    c._draw_extremes(p, c._geom())
    p.end()


c.set_history_exhausted(True, trusted=False)   # 达到回溯上限 / 分页边界
render_extremes()
ok("22. 假 True（回溯上限 / 分页边界）不再把局部点画成 ATH/ATL",
   c._extreme_rects == [] and c.history_exhausted is True)
ok("23. 信息栏对非全历史明确标注「区间高低」",
   "区间高低" in inspect.getsource(CandleChart._draw_hud)
   if hasattr(CandleChart, "_draw_hud")
   else "区间高低" in open(os.path.join(_ROOT, "ui", "chart_view.py"),
                          encoding="utf-8").read())

c.history_exhausted = True                     # 明确宣称全历史（兼容旧路径）
render_extremes()
ok("24. 明确确认全历史时仍正常标 ATH / ATL",
   len(c._extreme_rects) == 2, len(c._extreme_rects))

c.set_data(bars(40))                           # 换周期 / 合并缓存 / 回溯分页
render_extremes()
ok("25. 数据一换，全历史资格立即作废（本次 bug 的核心路径）",
   c._extreme_rects == [], c._extreme_rects)
c.interval = "15m"
ok("26. 分钟线 trust_extremes 被拒绝（永远只是区间）",
   c.trust_extremes() is False and c._extremes_trusted is False)
c.interval = "day"
ok("27. 日线且数据齐备时才允许 trust_extremes",
   c.trust_extremes() is True and c._extremes_trusted is True)
small = bars(8)
ok("28. 小时间范围仍标局部高低（LH/LL），但不冒充史高史低",
   (lambda pv: len(pv["h"]) == 1 and len(pv["l"]) == 1)(
       c._compute_pivots(small)))
c.set_history_exhausted(True, trusted=False)
render_extremes()
ok("29. 缩到几根 K 线时 ATH/ATL 依旧不画",
   c._extreme_rects == [])
_psrc = inspect.getsource(CandleChart._draw_pivots)
ok("30. LH/LL 让位逻辑同样要求真实全历史资格",
   "_extremes_trusted" in _psrc and "history_exhausted" in _psrc)

# ---------------- 6b. 空响应不得当成「已回溯到上市首根」 ----------------
# fetch_klines_before 的 exhausted = not candles：限流 / 抖动同样返回空页。
# 一次空响应就 trust_extremes() 会把已加载区间的 LH / LL 冒充成 ATH / ATL。
cv = ChartView(Config())
cv._symbol = "TEST"
cv._interval = "day"
cv.chart.interval = "day"
cv.chart.set_data(bars())
cv.chart.show_extremes = True
cv.chart.set_history_exhausted(False)
cv._on_history("TEST", "day", [], True)
ok("38. 单次空响应（限流 / 抖动）不把区间极值标成 ATH/ATL",
   cv.chart._extremes_trusted is False
   and cv.chart.history_exhausted is False,
   (cv.chart._extremes_trusted, cv.chart.history_exhausted))
cv._on_history("TEST", "day", [], True)
ok("39. 连续两次空响应才确认到头并标 ATH/ATL",
   cv.chart._extremes_trusted is True
   and cv.chart.history_exhausted is True,
   (cv.chart._extremes_trusted, cv.chart.history_exhausted))

cv2 = ChartView(Config())
cv2._symbol = "TEST"
cv2._interval = "15m"
cv2.chart.interval = "15m"
cv2.chart.set_data(bars())
cv2._hist_empty_streak = 1
cv2._on_history("TEST", "15m", [], True)
ok("40. 分钟线即使连续空响应也永不信任 ATH/ATL",
   cv2.chart._extremes_trusted is False)

ok("41. 支撑 / 阻力位仅在 4 小时级及以上周期绘制",
   cv.chart._sr_allowed() is True
   and CandleChart.SR_PERIODS == ("4h", "1d", "3d", "1w", "1M", "1y",
                                  "day", "3day", "week", "month", "1year"))
cv2.chart.interval = "15m"
ok("42. 低时间范围（15m）支撑 / 阻力位被拒绝",
   cv2.chart._sr_allowed() is False)

# ---------------- 7. 详情抽屉新增内容 ----------------
d = SymbolDetailDialog("BTC", "比特币")
_pump = QApplication.processEvents
for _ in range(3):
    _pump()
ok("31. 详情含发展历程 / 档案 / 里程碑 / 交易所快照四组新卡",
   hasattr(d, "_archive_cells") and hasattr(d, "_ms_cells")
   and hasattr(d, "_snap_cells") and hasattr(d, "tl_box"))
ok("32. BTC 发展历程默认渲染 6 条，可展开到全部 11 条",
   d.tl_box_lay.count() == 6 and d.btn_tl_more.isHidden() is False
   and "Free Chart" in d.lbl_verified.text())
d.btn_tl_more.click()
ok("33. 「展开全部」按钮真实展开全部里程碑",
   d.tl_box_lay.count() == len(d._tl_rows) == 11,
   (d.tl_box_lay.count(), len(d._tl_rows)))
ok("34. 发展历程来源与核验日期可追溯",
   tl.VERIFIED_AT in d.lbl_tl_note.text()
   and "来源" in d.lbl_tl_note.text())
ok("35. 档案卡片填入真实字段且不编造",
   d._archive_cells["category"].val.text() not in ("", "—")
   and "— 暂无公开数据" in
   [d._archive_cells[k].val.text() for k in ("exchange",)])
ok("36. 离线下行情里程碑明确留白",
   "—" in d._ms_cells["span"].val.text())
d.close()

_d2 = SymbolDetailDialog("US:ZZZZ", "未收录品种")
for _ in range(2):
    QApplication.processEvents()
ok("37. 未收录品种发展历程显示「暂无」而不是通用说明",
   tl.NO_DATA in _d2.lbl_tl_note.text()
   and _d2.tl_box_lay.count() == 1
   and "未收录" in _d2.lbl_verified.text())
_d2.close()

print(f"\n=== {CHECKS[0] - len(FAILS)}/{CHECKS[0]} 通过 ===")
if FAILS:
    print("失败项：" + "; ".join(FAILS))
sys.path.insert(0, os.path.join(_ROOT, "tests"))
from qt_exit import finish  # noqa: E402
finish(1 if FAILS else 0)
