# -*- coding: utf-8 -*-
"""v19 回归：品种资料卡 / 看板娘显示场景与遮挡透明度 / 图表工具条收纳 /
Solana 合约地址链上解析。

覆盖：
1. 资料卡：代码 / 名称 / 市场 / 排名 / 市值，价格涨跌跟着行情走，窄屏 2 列宽屏 4 列；
2. 市值按「股本 × 当前价」随价格缩放（不是抓取时的死数）；
3. 看板娘：竖屏（高 > 宽）隐藏，横屏大窗显示，切回竖屏又收起；
4. 看板娘与 K 线重叠度越高越透明，离开重叠恢复，且不透到看不见；
5. 图表工具条默认收起（不占 K 线高度）、展开放开、状态写进配置；
6. base58 / ed25519 曲线判定 / Metaplex PDA 派生正确（真实链上地址校验）；
7. Token-2022 扩展元数据（名称/代码/URI）解析；
8. 合约地址格式识别与「链上查不到」的兜底返回。

全部离线（临时 APPDATA + offscreen，不发起网络请求）。
"""
import os
import struct
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="ct_v19_")
os.environ["APPDATA"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from core.config import Config
from data import contract_search as cs
from data.api_base import Ticker
from ui.chart_view import ChartView
from ui.info_panel import SymbolInfoPanel, format_cap
from ui.main_window import MainWindow

# v23 起离线注入合成 K 线：真实网络加载偶发超过 0.8s 的等待窗口，
# 会让「图表应已渲染出 K 线区域」随机失败。本测试的焦点是看板娘遮挡、
# 工具条几何与地址解析，不依赖真实行情数据。
import ui.chart_view as _cv
from data.klines import Candle as _Candle


def _synth_candles(n=300):
    return [_Candle(ts=1600000000 + i * 86400, time_label=str(i),
                    open=100 + i % 7, high=105 + i % 9, low=95 + i % 5,
                    close=101 + i % 6, volume=1000 + i) for i in range(n)]


_cv.ChartView._load = lambda self: None
_cv.ChartView._ensure_extremes_history = lambda self: None
_cv.ChartView._prefetch_intervals = lambda self: None
_cv.kline_cache.is_fresh = lambda *a, **k: True
_cv.kline_cache.load = lambda *a, **k: []

app = QApplication([])


def pump(seconds=0.05):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


# ================= 1. 资料卡字段与自适应列数 =================
panel = SymbolInfoPanel()
panel.resize(520, 110)
panel.set_symbol("BTC", "Bitcoin")
panel.set_profile({"cap": 1.4e12, "float_cap": 1.4e12, "pe": None,
                   "rank": 1, "shares": 19.7e6})
t = Ticker(symbol="BTC", name="Bitcoin", last_price=70000.0, change_pct=2.35,
           high_24h=71500.0, low_24h=68500.0, quote_volume_24h=1.23e10)
panel.update_ticker(t)
pump(0.02)

assert panel.lbl_code.text() == "BTC", panel.lbl_code.text()
assert "Bitcoin" in panel.lbl_name.text()
assert panel.lbl_market.text() == "加密", panel.lbl_market.text()
assert panel.lbl_rank.text() == "市值 #1", panel.lbl_rank.text()
assert panel.lbl_change.text().startswith("▲"), panel.lbl_change.text()
assert panel._cells["high"].val.text().startswith("$"), panel._cells["high"].val.text()
assert panel._cells["amp"].val.text() == "4.38%", panel._cells["amp"].val.text()
assert panel._cells["cap"].val.text() == "1.38万亿", panel._cells["cap"].val.text()
assert panel._cells["pe"].isHidden(), "加密品种不应显示市盈率"
assert panel._cells["rank"].val.text() == "#1"
print("1. 资料卡代码/名称/市场/排名/市值/振幅 OK")

assert panel._cols == 4, f"520 宽应 4 列，实际 {panel._cols}"
panel.show()                      # 隐藏状态下 Qt 不派发 resizeEvent
pump(0.05)
for target in (300, 420, 560, 760):
    panel.resize(target, 110)
    pump(0.05)
    # 面板有最小宽度，窄窗会被系统钳制——按「真实宽度」判断该有几列
    expect = 2 if panel.width() < 340 else (3 if panel.width() < 500 else 4)
    assert panel._cols == expect, \
        f"{panel.width()} 宽应 {expect} 列，实际 {panel._cols}"
panel.hide()
print("2. 列数自适应（2 / 3 / 4 列）OK")

# 市值随价格缩放：股本 1e7、抓取价 100 -> 现价 200 时市值翻倍
panel2 = SymbolInfoPanel()
panel2.resize(460, 110)
panel2.set_symbol("ETH", "Ethereum")
panel2._profile = {"shares": 1e7, "px0": 100.0, "cap": 1e9,
                   "float_cap": 1e9, "pe": None, "rank": 2}
panel2.update_ticker(Ticker(symbol="ETH", last_price=200.0, change_pct=0.0))
pump(0.02)
assert panel2._cells["cap"].val.text() == "20.00亿", panel2._cells["cap"].val.text()
print("3. 市值 = 股本 × 当前价（随行情缩放）OK")

assert format_cap(0) == "—" and format_cap(1.5e12) == "1.50万亿"
assert format_cap(3.7e11) == "3,700亿"
print("4. 市值单位格式（万亿 / 亿 / 万 / —）OK")

# ================= 2. 主窗口集成 =================
cfg = Config()
cfg.set("mascot_enabled", True)
cfg.set("mascot_speech", True)
w = MainWindow(cfg)
w.resize(480, 820)          # 竖屏
w.prepare_show()
pump(0.15)

assert w.info_panel is not None
assert w.info_panel._symbol in ("BTC", "ETH"), w.info_panel._symbol
assert w.info_panel not in w._list_controls, \
    "v22：资料改成悬停浮层，不再常驻列表上方"
assert w.info_panel.parentWidget() is not None, \
    "浮层必须挂在主窗口内，不能变成独立的顶层窗口"
assert not w.info_panel.isVisible(), "没有鼠标悬停时资料浮层不应显示"
print("5. 资料改为悬停浮层（不占布局 / 默认隐藏）OK")

# ================= 3. 看板娘只在图表页显示 =================
m = w.mascot
assert m is not None
pump(0.1)
assert not m.isVisible(), "行情列表页不应显示看板娘"

w.resize(1280, 800)         # 横屏大窗但仍在列表页
pump(0.3)
w._sync_mascot_visibility()
pump(0.1)
assert not m.isVisible(), "列表页（即使横屏大窗）也不应显示看板娘"

sym = next(iter(w.rows))
w._open_chart(sym)          # 进入 K 线页
w.chart_view.chart.set_data(_synth_candles())   # 离线注入，不等网络
pump(0.8)
assert m.isVisible(), "进入图表页应显示看板娘"

w._leave_chart()            # 回到列表页
pump(0.5)
assert not m.isVisible(), "离开图表页应立即收起看板娘"
print("6. 看板娘：只在 K 线页显示 OK")

# ================= 4. 遮挡 K 线时完全消失 / 离开重现 =================
w._open_chart(sym)
w.chart_view.chart.set_data(_synth_candles())   # 离线注入，不等网络
pump(0.8)
assert m.isVisible(), "图表页看板娘应显示"
base = m.windowOpacity()
assert 0.95 <= base <= 1.0, base

# 把立绘挪进 K 线绘制区域，让 400ms 重叠轮询自己算出「被压住」
rect = w.chart_view.candles_global_rect().toRect()
assert not rect.isEmpty(), "图表应已渲染出 K 线区域"
m.move(rect.center().x() - m.width() // 2, rect.top() + 10)
for _ in range(40):          # 等至少两轮轮询（400ms 周期）
    pump(0.03)
assert not m.isVisible(), f"压住 K 线应完全消失（opacity={m.windowOpacity()}）"

m.move(rect.right() + m.width() + 40, rect.top())   # 挪出 K 线区域
for _ in range(40):
    pump(0.03)
assert m.isVisible(), "离开重叠区应重新出现"
assert abs(m.windowOpacity() - base) < 0.06, m.windowOpacity()
print(f"7. 看板娘：遮挡完全消失 / 离开重现（opacity {base:.2f}→0→恢复）OK")

# 主窗口侧：图表可见时把重叠度算出来（这里用矩形直接验证换算逻辑）
w._enter_chart_layout()
pump(0.05)
assert w._mascot_timer.isActive(), "图表页应开启重叠度轮询"
w._leave_chart_layout()
pump(0.05)
assert not w._mascot_timer.isActive(), "离开图表页应停止轮询"
assert not m.isVisible(), "回到列表页看板娘应收起"
print("8. 图表页开启 / 离开时停止重叠度轮询 OK")

# ================= 5. 图表工具条收纳 =================
cv = ChartView(Config())
cv.resize(1000, 700)
cv.show()
pump(0.1)
assert not cv.tools_panel.isVisible(), "工具条默认应收起"
collapsed_h = cv.chart.height()
cv.btn_tools.setChecked(True)
pump(0.1)
opened_h = cv.chart.height()
assert cv.tools_panel.isVisible(), "展开后工具条应可见"
# v24 起：工具面板是独立图层（悬浮在图表上方），展开 / 收纳
# 都不得改变 K 线图的高度 —— 图表区完全不被挤压重排。
assert opened_h == collapsed_h, \
    f"展开工具面板不得挤压 K 线：{collapsed_h}->{opened_h}"
assert cv.tools_panel.geometry().intersects(
    cv.chart.parentWidget().geometry()), "面板应悬浮覆盖在图表上方"
assert Config().get("chart_tools_open") is True, "展开状态应写进配置"
cv.btn_tools.setChecked(False)
pump(0.1)
assert not cv.tools_panel.isVisible()
assert cv.chart.height() == collapsed_h
assert "周期" in cv.btn_tools.text()
print("9. 图表工具条收纳（独立图层，展开/收纳不动 K 线）OK")

# ================= 6. Solana 地址解析基础件 =================
addr = "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump"
assert cs.is_contract(addr), "44 位 base58 应识别为合约地址"
assert cs._b58encode(cs.b58decode(addr)) == addr, "base58 编解码需可逆"
assert cs._is_on_curve(cs.b58decode(addr)), "真实公钥应在曲线上"

# Metaplex 元数据 PDA：wSOL 的元数据账户（链上真实存在，owner = metaqbxx）
program = cs.b58decode(cs._METAPLEX)
pda = cs._find_pda([b"metadata", program,
                    cs.b58decode("So11111111111111111111111111111111111111112")],
                   program)
assert cs._b58encode(pda) == "6dM4TqWyWJsbx7obrdLcviBkTafD5E8av61zfU6jq57X", \
    cs._b58encode(pda)
print("10. base58 可逆 / 曲线判定 / Metaplex PDA 派生 OK")

# Token-2022：构造一段扩展数据，验证名称/代码/URI 解析
def _s(text):
    raw = text.encode("utf-8")
    return struct.pack("<I", len(raw)) + raw

ext = b"\x00" * 32 + b"\x11" * 32 + _s("The Black Bull") + _s("ANSEM") + _s("https://x.io/a")
tlv = struct.pack("<HH", 19, len(ext)) + ext
account = b"\x00" * 165 + b"\x01" + tlv
name, symbol, uri = cs._token2022_meta(account)
assert (name, symbol, uri) == ("The Black Bull", "ANSEM", "https://x.io/a"), \
    (name, symbol, uri)
print("11. Token-2022 扩展元数据解析 OK")

# 链上查不到时的兜底（不发网络请求：monkeypatch 掉 RPC 与 DEX）
cs._rpc_call = lambda *a, **k: None
cs._dex_pairs = lambda q: []
cs._SOL_CACHE.clear()
bad = cs.resolve("9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGabc")
assert bad and bad["exists"] is False and bad["symbol"] == ""
assert cs.resolve("0xnot-a-real-address") is None
print("12. 链上查不到 / 非法地址的兜底返回 OK")

# ================= 收尾 =================
try:
    w.live.shutdown()       # 测试里进过图表页，秒级实时价线程要收掉
except Exception:
    pass
w.scheduler.stop()
if getattr(w, "mascot", None) is not None:
    try:
        if w.mascot._fade is not None:
            w.mascot._fade.stop()
        w.mascot._bubble.dismiss()
        w.mascot.hide()
    except RuntimeError:
        pass
w.close()
cv.close()
pump(0.05)
from qt_exit import finish           # 跳过 offscreen 的 Qt 卸载竞态
print("\nv19 全部回归测试通过 ✅")
finish()
