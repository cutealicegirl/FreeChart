# -*- coding: utf-8 -*-
"""币安风格 K 线图表页：蜡烛 + 成交量 + MACD + MA + BOLL 布林线 + 画线工具。

纯 QPainter 自绘，不引入任何图表库依赖，保持低资源占用。
配色沿用 A 股惯例：红涨绿跌。

交互：
- 滚轮缩放（右端锚定，放大/缩小对称生效）；
- 十字光标、OHLC / 指标数值图例、独立时间轴；
- 指标显隐（MA / EMA / BOLL / VOL / MACD），MA / EMA 天数、BOLL / MACD
  参数可按「全部周期」或「仅当前周期」在指标参数面板里调整；
- 画线（画完自动回光标，可选中后拖端点/整体平移二次调整）。
"""
import math
from datetime import datetime

from PySide6.QtCore import (QEasingCurve, QEvent, QPoint, QPointF, QRect,
                            QRectF, Qt, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetrics, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from core import indicator_params, onchain_history
from data import kline_cache, onchain
from data.klines import (HistoryWorker, KlineWorker, default_interval,
                         intervals_for, refresh_seconds)
from ui.theme import (C_ACCENT, C_BG_BASE, C_BG_HOVER, C_BG_PANEL,
                      C_BLUE, C_BORDER, C_DOWN, C_PURPLE, C_TEAL,
                      C_TEXT_DIM, C_TEXT_MAIN, C_TEXT_SUB, C_UP,
                      icon_btn_qss, label_qss, panel_qss, segment_qss,
                      toggle_qss, tool_qss)
from ui.theme import C_BG_ROW
from ui.indicator_sheet import IndicatorSettingsSheet
from ui.popup import apply_popup_shadow
from ui.ticker_widget import format_price
from ui.units import unit_of, with_unit

C_GRID = "#2b3139"           # 网格
C_AXIS_BG = "#12161e"        # 价格轴 / 时间轴底色
C_CROSS = "#848e9c"          # 十字光标
C_LINE = C_ACCENT            # 画线默认色
C_SELECT = "#ffffff"         # 选中线高亮
# 均线调色板：按用户设定的第 1~4 条线分配，与具体天数解耦
MA_PALETTE = [C_ACCENT, C_PURPLE, C_BLUE, C_TEAL]
EMA_PALETTE = ["#ff9f43", "#e040fb", "#26de81", "#f7d794"]
# 兼容早期回归测试与旧引用：默认四条 MA 的颜色
MA_COLORS = dict(zip((5, 10, 20, 30), MA_PALETTE))
BOLL_BAND = "#4b9cff"
BOLL_MID = C_ACCENT
DIF_COLOR = C_ACCENT
DEA_COLOR = "#e040fb"


# ================= 指标计算（纯函数） =================
def _ema_series(values, n):
    """EMA 序列（与 closes 等长，前段为 None 预热）。"""
    out = [None] * len(values)
    if len(values) < n:
        return out
    k = 2.0 / (n + 1)
    e = sum(values[:n]) / n
    out[n - 1] = e
    for i in range(n, len(values)):
        e = values[i] * k + e * (1 - k)
        out[i] = e
    return out


def ma_series(closes, n):
    """简单移动平均 MA(n)，前 n-1 个为 None。"""
    out = [None] * len(closes)
    s = 0.0
    for i, v in enumerate(closes):
        s += v
        if i >= n:
            s -= closes[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def boll_series(closes, n=20, k=2.0):
    """布林线 BOLL(n,k)：返回 (上轨, 中轨, 下轨)。

    中轨 = MA(n)，上下轨 = 中轨 ± k × 总体标准差（与通达信/币安一致）。
    """
    size = len(closes)
    upper = [None] * size
    mid = [None] * size
    lower = [None] * size
    for i in range(n - 1, size):
        window = closes[i - n + 1:i + 1]
        m = sum(window) / n
        std = math.sqrt(sum((v - m) ** 2 for v in window) / n)
        mid[i] = m
        upper[i] = m + k * std
        lower[i] = m - k * std
    return upper, mid, lower


def macd_series(closes, fast=12, slow=26, signal=9):
    """MACD(12,26,9)：返回 (DIF, DEA, HIST)，hist=2*(DIF-DEA) 国内惯例。"""
    ef = _ema_series(closes, fast)
    es = _ema_series(closes, slow)
    dif = [None if (a is None or b is None) else a - b
           for a, b in zip(ef, es)]
    valid = [(i, v) for i, v in enumerate(dif) if v is not None]
    dea = [None] * len(closes)
    if len(valid) >= signal:
        e9 = _ema_series([v for _, v in valid], signal)
        for j, (i, _) in enumerate(valid):
            dea[i] = e9[j]
    hist = [None if (d is None or e is None) else 2 * (d - e)
            for d, e in zip(dif, dea)]
    return dif, dea, hist


class CandleChart(QWidget):
    """K 线绘制区：主图 + 可选成交量/MACD 副图 + 布林带 + 可编辑画线。"""

    tool_finished = Signal()   # 画线/删除动作完成，请求工具栏回到光标模式
    need_history = Signal()    # 缩到当前数据尽头，请求加载更早历史
    user_view_change = Signal()  # 用户主动放大 / 拖动，退出「全部历史自动贴合」
    view_changed = Signal()    # 缩放 / 平移后记下视口，供跨图表恢复

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)   # 接收 ESC / Delete
        self.candles: list = []
        # 链上合约品种：走「真实报价采样走势 + 链上结构图」绘制分支，
        # 不画不存在的 K 线。None = 普通蜡烛模式。
        self.onchain_view = None
        self._mouse_pos: QPoint | None = None
        self._status = "加载数据中..."
        self._margin_l, self._margin_r = 10, 74
        self._margin_t, self._margin_b = 40, 28

        # 滚轮缩放：可见根数（无固定上限，可一路缩到品种上市首根）
        self._view_count = 90
        self._min_bars = 8
        # _pan：右边缘相对最新一根回看的根数；负值 = 整图右移后的右侧留白。
        # 浮点让拖动严格跟手，图表右端不再被钉死在最新一根。
        self._pan = 0.0
        self._panning = False
        self._pan_start = None
        # 用户是否手动调过视野：调过之后 set_data 不再自动居中覆盖，
        # 否则后台每来一页历史都会把刚缩好的 K 线「弹」回最右侧 / 居中。
        self._view_touched = False
        self.interval = "15m"           # 当前周期（决定时间轴年份格式）
        # 实时最新价（ticker），光标涨跌幅的基准；None 时退回最后一根收盘
        self.last_price = None
        # 价格轴 / 指标数字的字号倍率（设置里可调，默认比旧版大 20%）
        self.font_scale = 1.2
        # 货币单位前缀（$ / ¥ / HK$），由 ChartPanel 按品种设置
        self.unit_prefix = ""
        self.show_currency = True
        # 是否已回溯到品种上市首根。它是一个 property：直接赋值视为
        # 「明确宣称全历史」（兼容旧调用与回归），生产代码一律走
        # set_history_exhausted(flag, trusted=...) / trust_extremes()。
        self.history_exhausted = False
        self.history_capped = False     # 达到用户设定的回溯上限（≠ 上市首根）
        self.history_loading = False
        self.fit_all = False        # 缩到尽头后自动持续回溯并一屏铺满全部历史
        # 最新一根 K 线随实时价平滑伸缩的动画（时长跟随实时轮询间隔）
        self._anim_start = 0.0
        self._anim_target = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(900)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_live_anim)
        # 智能标注各自独立，工具栏各有一个按钮控制
        self.show_trend = False     # 线性回归趋势线
        self.show_res = False       # 压力位 R1/R2
        self.show_sup = False       # 支撑位 S1/S2
        self.show_extremes = True   # ATH / ATL（在对应 K 线处标价格）
        self.show_pivots = True     # 局部高点 LH / 局部低点 LL（同上方式）
        self._heavy = False         # 超长历史：跳过逐根指标与蜡烛绘制
        self._auto_lines = None
        self._extremes = None       # (最高索引, 最高价, 最低索引, 最低价)
        self._extreme_rects = []    # ATH/ATL 标签占位，供局部高低点避让

        # 指标显示开关（可由工具栏切换、由配置持久化）
        self.show_ma = True
        self.show_ema = True
        self.show_boll = True
        self.show_macd = True
        self.show_vol = True

        # 可配置参数：MA / EMA 各 4 条（天数 + 启用 + 颜色），BOLL / MACD
        # 的周期与倍数。set_indicator_params() 会清洗并立即重算缓存。
        self._params = indicator_params.default_params()
        self.ma_lines = []
        self.ema_lines = []
        self.boll_params = dict(indicator_params.DEFAULT_BOLL)
        self.macd_params = dict(indicator_params.DEFAULT_MACD)

        # 指标缓存：仅在数据更新 / 参数变化时计算一次，绘制时只读
        self._ind = {"ma": {}, "ema": {}, "boll": ([], [], []),
                     "macd": ([], [], [])}
        self.set_indicator_params(self._params)

        # 画线工具状态
        self._tool = "none"              # none/trend/hline/del
        self._pending = None             # 趋势线第一个锚点 (ts, price)
        self._lines: list = []           # 已画线：{kind, p1, p2} 或 {kind, price}
        self._selected = None            # 当前选中的线（可拖动调整）
        self._drag = None                # 拖动状态

    @property
    def show_auto(self):
        """兼容旧接口：三个智能开关是否至少开了一个。"""
        return self.show_trend or self.show_res or self.show_sup

    @show_auto.setter
    def show_auto(self, value):
        self.show_trend = self.show_res = self.show_sup = bool(value)

    # ---- 数据 ----
    def set_status(self, text: str):
        self._status = text
        self.update()

    def set_onchain_view(self, data: dict | None):
        """切换到链上真实数据视图；传 None 恢复普通 K 线绘制。"""
        self.onchain_view = data
        self.update()

    # ---- 可配置指标参数 ----
    def set_indicator_params(self, params: dict):
        """应用一组指标参数（天数 / 启用 / 周期），必要时重算并重绘。"""
        clean = indicator_params.normalize(params)
        self._params = clean
        self.ma_lines = [
            {"period": line["period"], "enabled": line["enabled"],
             "color": MA_PALETTE[i]}
            for i, line in enumerate(clean["ma"])]
        self.ema_lines = [
            {"period": line["period"], "enabled": line["enabled"],
             "color": EMA_PALETTE[i]}
            for i, line in enumerate(clean["ema"])]
        self.boll_params = dict(clean["boll"])
        self.macd_params = dict(clean["macd"])
        self._recalc_indicators()
        self.update()

    def macd_title(self) -> str:
        """副图标题跟着 MACD 参数走，避免参数改了标题还是 12,26,9。"""
        m = self.macd_params
        return f"MACD({m['fast']},{m['slow']},{m['signal']})"

    def _recalc_indicators(self):
        """按当前参数与已加载 K 线重算全部指标缓存。"""
        empty = {"ma": {}, "ema": {}, "boll": ([], [], []),
                 "macd": ([], [], [])}
        # 回溯到几万根时，逐根算 MA/EMA/BOLL/MACD 会让每次翻页变成
        # O(n²)，且一屏也画不出十几万根蜡烛：超长历史只保留收盘价趋势。
        if getattr(self, "_heavy", False) or not getattr(self, "candles", None):
            self._ind = empty
            return
        closes = [c.close for c in self.candles]
        ma_p = indicator_params.enabled_periods(self._params, "ma")
        ema_p = indicator_params.enabled_periods(self._params, "ema")
        b = self.boll_params
        m = self.macd_params
        self._ind = {
            "ma": {p: ma_series(closes, p) for p in ma_p},
            "ema": {p: _ema_series(closes, p) for p in ema_p},
            "boll": boll_series(closes, b["period"], b["k"]),
            "macd": macd_series(closes, m["fast"], m["slow"],
                                m["signal"]),
        }

    # 只有日线及以上能回溯到上市首根；分钟线全历史动辄上百万根，
    # 拿到的永远是「一段区间」，区间极值绝不许叫 ATH / ATL。
    FULL_PERIODS = ("1d", "day", "3d", "3day", "1w", "week",
                    "1M", "month", "1y", "1year")

    @property
    def history_exhausted(self) -> bool:
        """是否已停止回溯（不等于「已覆盖全历史」，见 _extremes_trusted）。"""
        return self._history_exhausted

    @history_exhausted.setter
    def history_exhausted(self, value):
        # 直接赋值视为调用方明确宣称「这就是全历史」，兼容旧代码与回归；
        # 生产代码请改用 set_history_exhausted(...) / trust_extremes()。
        self._history_exhausted = bool(value)
        self._extremes_trusted = bool(value)

    def set_history_exhausted(self, flag: bool, trusted=None):
        """设置回溯状态。trusted=False 表示只是停止回溯，极值仍只是区间高低。

        达到回溯上限、分页边界、缓存标记恢复等「假 True」路径都走这里，
        与真正回溯到首根的 trust_extremes() 严格区分。
        """
        self._history_exhausted = bool(flag)
        self._extremes_trusted = (bool(flag) if trusted is None
                                  else bool(flag and trusted))
        if not flag:
            self.history_capped = False

    def trust_extremes(self) -> bool:
        """确认当前 candles 覆盖上市以来全历史，才允许标注 ATH / ATL。"""
        if (str(getattr(self, "interval", "")) not in self.FULL_PERIODS
                or not self.candles):
            self._extremes_trusted = False
            return False
        self._history_exhausted = True
        self._extremes_trusted = True
        return True

    def set_data(self, candles: list):
        self._anim.stop()               # 数据整体换新，旧动画作废
        # 数据一换，旧的全历史资格立即作废：切周期 / 切品种 / 合并缓存 /
        # 回溯分页后，先按「区间极值」处理，直到再次确认覆盖上市首根。
        self._extremes_trusted = False
        self._heavy = len(candles) > 20000
        self.candles = candles
        self._recalc_indicators()
        # 记录已加载历史中的最高/最低及其位置，供主图标注
        if candles:
            hi_i = max(range(len(candles)), key=lambda i: candles[i].high)
            lo_i = min(range(len(candles)), key=lambda i: candles[i].low)
            self._extremes = (hi_i, candles[hi_i].high,
                              lo_i, candles[lo_i].low)
        else:
            self._extremes = None
        # 注意：不要把 _view_count 压到 len(candles)。否则短周期数据加载后
        # 用户此前的缩放级别会被永久压缩，切回长周期时"只能放大不能缩小"。
        self._clamp_pan()
        # 只有「尚未手动调过视野」的初始状态才自动居中；用户滚轮 / 拖动过
        # 之后，后台补历史、切周期、切品种都不得再改他的视口位置。
        if not self._view_touched:
            self._center_when_narrow()
        if self._selected not in self._lines:
            self._selected = None
            self._drag = None
        self.update()

    # ---- 实时价 -> 最新 K 线动画 ----
    def animate_last_price(self, price):
        """实时价更新时，最新一根 K 线的收盘/高低随动画平滑伸缩。

        连续多个 tick 会从「当前动画值」重新起步，视觉上始终连贯：
        上一次动画跑到一半就被新价打断时，从当前显示值继续插值，
        不会回跳，所以每秒一次的外盘价也能呈现出连续爬升/回落。
        """
        if not self.candles or not price or price <= 0:
            return
        last = self.candles[-1]
        start = float(last.close)
        target = float(price)
        if abs(target - start) < 1e-12:
            return
        self._anim.stop()
        self._anim_start, self._anim_target = start, target
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def _on_live_anim(self, frac):
        if not self.candles:
            return
        v = self._anim_start + (self._anim_target - self._anim_start) \
            * float(frac)
        last = self.candles[-1]
        last.close = v
        # 与真实行情一致：会话内高低点只向外扩张
        if v > last.high:
            last.high = v
        if v < last.low:
            last.low = v
        self.update()

    # ---- 视野（缩放 + 平移）----
    def _clamp_pan(self):
        """限制视野：可回看到最早一批，也可继续右移留出空白。"""
        total = len(self.candles)
        max_back = max(0.0, total - self._min_bars)
        max_forward = max(8.0, self._view_count * 0.8)
        self._pan = max(-max_forward, min(max_back, float(self._pan)))

    def _right_edge(self):
        """绘图区右边缘对应的数据索引（可超过 total，表示右侧留白）。"""
        return len(self.candles) - self._pan

    def _center_when_narrow(self):
        """全部已加载 K 线比视野还窄时，整块居中显示。

        月线等短历史品种总根数可能小于默认视野：若按 pan=0 贴右边缘，
        一缩小整块就往右窜、左边全是空白。居中后从屏幕中心对称收缩，
        视觉上稳定，也不会「飘到最右边」。
        """
        total = len(self.candles)
        if total and self._view_count >= total:
            self._pan = -(self._view_count - total) / 2.0
        self._clamp_pan()

    def _visible_range(self):
        """返回当前可见 K 线在完整数据中的 [start, end)。"""
        total = len(self.candles)
        right = self._right_edge()
        end = max(0, min(total, int(math.ceil(right))))
        start = max(0, int(math.floor(right - self._view_count)))
        if start >= end:
            start = max(0, end - 1)
        return start, end

    def reset_view(self):
        """复位：回到最新一根、恢复默认缩放级别（用户主动点「最新」时）。"""
        self._view_count = 90
        self._pan = 0.0
        self._panning = False
        self._pan_start = None
        self.fit_all = False
        self._view_touched = False
        self._center_when_narrow()      # 短历史品种复位后也居中
        self.view_changed.emit()
        self.update()

    # ---- 视口状态：跨品种 / 跨周期 / 重启都保留缩放与位置 ----
    def view_state(self) -> dict:
        return {"view_count": float(self._view_count),
                "pan": float(self._pan)}

    def restore_view(self, state: dict | None):
        """恢复上一次的缩放级别与横向位置。

        标记为「用户视口」，避免随后到达的 K 线数据把位置自动居中回去。
        """
        if not state:
            return
        try:
            vc = float(state.get("view_count") or 0.0)
            pan = float(state.get("pan") or 0.0)
        except (TypeError, ValueError, AttributeError):
            return
        if vc < self._min_bars:
            return
        self._view_count = vc
        self._pan = pan
        self._view_touched = True
        self._clamp_pan()
        self.update()

    # ---- 画线存取 ----
    def get_drawings(self):
        return [dict(line) for line in self._lines]

    def set_drawings(self, lines: list):
        self._lines = [dict(line) for line in lines]
        self._selected = None
        self._drag = None
        self.update()

    def clear_drawings(self):
        self._lines.clear()
        self._selected = None
        self._drag = None
        self._pending = None
        self.update()

    def set_tool(self, tool: str):
        self._tool = tool
        self._pending = None
        self._drag = None
        cursor = Qt.CrossCursor if tool in ("trend", "hline") else \
            Qt.PointingHandCursor if tool == "del" else Qt.ArrowCursor
        self.setCursor(cursor)
        self.update()

    # ---- 几何 ----
    def _bars(self):
        """当前可见的 K 线（整图平移后落在绘图区内的部分）。"""
        start, end = self._visible_range()
        return self.candles[start:end]

    def _geom(self):
        """按当前显示的指标动态分配面板高度（隐藏副图时主图自动占满）。"""
        bars = self._bars()
        n = max(1, len(bars))
        offset, _end = self._visible_range()
        w = max(60.0, self.width() - self._margin_l - self._margin_r)
        full_h = max(60.0, self.height() - self._margin_t - self._margin_b)
        weights = [("price", 0.60)]
        if self.show_vol:
            weights.append(("vol", 0.14))
        if self.show_macd:
            weights.append(("macd", 0.26))
        total = sum(v for _, v in weights) or 1.0
        rects, y = {}, float(self._margin_t)
        for key, wt in weights:
            h = full_h * wt / total
            rects[key] = QRectF(self._margin_l, y, w, h)
            y += h

        # step 只由缩放级别决定；bar_x0 是第 offset 根所在格子的虚拟左边界。
        # 整图右移时 bar_x0 变小，右侧自然留白，不再强制右端对齐最新一根。
        step = w / self._view_count
        bar_x0 = self._margin_l + w - (self._right_edge() - offset) * step

        hi = max((c.high for c in bars), default=1.0)
        lo = min((c.low for c in bars), default=0.0)
        # 主图指标（BOLL / MA）可能超出蜡烛高低点，需一并纳入价格范围
        extra = []
        if self.show_boll:
            up, _mid, dn = self._ind["boll"]
            extra += [v for v in up[offset:offset + n] if v is not None]
            extra += [v for v in dn[offset:offset + n] if v is not None]
        if self.show_ma:
            for series in self._ind["ma"].values():
                extra += [v for v in series[offset:offset + n]
                          if v is not None]
        if self.show_ema:
            for series in self._ind["ema"].values():
                extra += [v for v in series[offset:offset + n]
                          if v is not None]
        if extra:
            hi, lo = max(hi, max(extra)), min(lo, min(extra))
        span = (hi - lo) or hi * 0.01 or 1.0
        hi += span * 0.06
        lo -= span * 0.06
        return {
            "bars": bars, "n": n, "step": step, "offset": offset,
            "x0": self._margin_l, "bar_x0": bar_x0, "w": w, "bottom": y,
            "price": rects["price"],
            "vol": rects.get("vol"), "macd": rects.get("macd"),
            "hi": hi, "lo": lo,
        }

    def candles_global_rect(self) -> QRectF:
        """K 线实际占据的屏幕矩形（全局坐标），给看板娘避让用。

        只算 K 线本身（蜡烛左右边界 + 可见高低点），不含坐标轴留白和副图，
        这样「立绘压在空白处」不会被误判成遮挡。
        """
        try:
            g = self._geom()
        except Exception:
            return QRectF()
        bars = g.get("bars") or []
        if not bars:
            return QRectF()
        hi = max(c.high for c in bars)
        lo = min(c.low for c in bars)
        r = g["price"]
        top = self._y_price(g, hi)
        bottom = self._y_price(g, lo)
        x0 = max(g["x0"], g["bar_x0"])
        x1 = min(g["x0"] + g["w"], g["bar_x0"] + g["n"] * g["step"])
        if x1 <= x0:
            return QRectF()
        rect = QRectF(x0, min(top, bottom), x1 - x0, abs(bottom - top))
        origin = self.mapToGlobal(rect.topLeft().toPoint())
        return QRectF(float(origin.x()), float(origin.y()),
                      rect.width(), rect.height())

    def _y_price(self, g, p):
        """价格 -> 屏幕 y（价格越高越靠上）。"""
        r = g["price"]
        return r.top() + r.height() * (g["hi"] - p) / (g["hi"] - g["lo"])

    def _price_at(self, g, y):
        """屏幕 y -> 价格：_y_price 的严格逆函数。

        这里必须是 hi - (y-top)/H*(hi-lo)。若写成 lo + ... 会把价格轴
        上下颠倒，导致画出的线/拖动方向与鼠标相反。
        """
        r = g["price"]
        return g["hi"] - (g["hi"] - g["lo"]) * (y - r.top()) / r.height()

    def _x_index(self, g, x):
        return max(0, min(g["n"] - 1, int((x - g["bar_x0"]) / g["step"])))

    def _avg_dt(self, bars):
        """可见 K 线的平均时间间隔（秒），用于拖动时的时间外推。"""
        if len(bars) < 2:
            return 1.0
        return max(1.0, (bars[-1].ts - bars[0].ts) / (len(bars) - 1))

    def _ts_x(self, g, ts):
        """时间戳 -> x 坐标；超出可见区时线性外推（线不会被整条丢弃）。"""
        bars = g["bars"]
        if not bars or ts is None:
            return None
        dt = self._avg_dt(bars)
        if ts <= bars[0].ts:
            return g["bar_x0"] + g["step"] * 0.5 - (bars[0].ts - ts) / dt * g["step"]
        for i in range(1, len(bars)):
            if ts <= bars[i].ts:
                frac = (ts - bars[i - 1].ts) / max(1.0, bars[i].ts - bars[i - 1].ts)
                return g["bar_x0"] + g["step"] * (i - 0.5 + frac)
        return (g["bar_x0"] + g["step"] * (len(bars) - 0.5)
                + (ts - bars[-1].ts) / dt * g["step"])

    def _ts_at_x(self, g, x):
        """x 坐标 -> 时间戳（允许面板外推，用于拖动端点）。"""
        bars = g["bars"]
        if not bars:
            return 0.0
        idx = (x - g["bar_x0"]) / g["step"] - 0.5
        dt = self._avg_dt(bars)
        if idx < 0:
            return bars[0].ts + idx * dt
        if idx >= len(bars) - 1:
            return bars[-1].ts + (idx - (len(bars) - 1)) * dt
        i = int(idx)
        frac = idx - i
        return bars[i].ts + frac * max(1.0, bars[i + 1].ts - bars[i].ts)

    # ---- 交互 ----
    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        self._mouse_pos = pos
        g = self._geom() if self.candles else None
        if self._panning and g is not None \
                and (event.buttons() & Qt.LeftButton):
            # 向右拖 -> K 线整体右移 -> 露出更早的历史（_pan 增大）
            start_x, start_pan, step = self._pan_start
            delta = (pos.x() - start_x) / max(1.0, step)
            self._pan = start_pan + delta
            self._clamp_pan()
            self._view_touched = True
            self.view_changed.emit()
            self.update()
            return
        if self._drag is not None and g is not None \
                and (event.buttons() & Qt.LeftButton):
            self._apply_drag(g, pos)
        elif self._tool == "none" and g is not None:
            self.setCursor(Qt.SizeAllCursor if self._hit_test(g, pos)
                           else Qt.ArrowCursor)
        self.update()

    def leaveEvent(self, event):
        self._mouse_pos = None
        if self._drag is None:
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = None
            self._panning = False
            self._pan_start = None
            if self._tool == "none":
                self.setCursor(Qt.ArrowCursor)
            self.update()

    def zoom_by(self, zoom_in: bool):
        """阶段 6：触屏「＋ / −」缩放按钮。

        复用滚轮那套锚点公式（锚点取视口中心），保证触摸缩放也不会被
        强制对齐到最右侧，且缩放状态同样广播给跨图表记忆。
        """
        if not self.candles:
            return
        old = float(self._view_count)
        total = len(self.candles)
        if zoom_in:
            new = max(float(self._min_bars), min(old - 1.0, old * 0.84))
            if new < old:
                self.fit_all = False
                self.user_view_change.emit()
        else:
            vmax = max(180.0, 2.0 * total)
            new = max(old, min(old * 1.22 + 1.0, vmax))
            if not self.history_exhausted and new >= float(total):
                self.need_history.emit()
            if new > float(total):
                self.fit_all = False
        if new != old:
            w = max(60.0, self.width() - self._margin_l - self._margin_r)
            right_px = self._margin_l + w
            mx = (self._margin_l + right_px) / 2.0
            idx = self._right_edge() - (right_px - mx) / (w / old)
            self._pan = total - (idx + (right_px - mx) / (w / new))
            self._view_count = new
            self._view_touched = True
            self.view_changed.emit()
        elif not zoom_in:
            self.need_history.emit()
        if not zoom_in and new >= float(total):
            self._pan = max(float(self._pan), float(total) - new)
        self._clamp_pan()
        self.update()

    def wheelEvent(self, event):
        """滚轮缩放：以「原 K 线位置」为锚点，上滚放大、下滚缩小。

        v22 修复的 bug：旧版缩放后会强制 `pan = 0`（最新一根贴死右边缘）
        或 `pan = -(view-total)/2`（整块居中），所以一缩小 K 线就被硬生生
        对齐到最右侧 / 中间。现在只做一件事——**保持锚点那根 K 线在屏幕
        上的 x 坐标不变**，两侧的蜡烛围绕它对称地展开或收拢，绝不重排。

        锚点：光标落在绘图区内且没紧贴右侧价格轴时，用光标下那根 K 线；
        否则用视口中心那根（鼠标停在右边缘时也不会把整图甩到最右）。
        缩小方向永不把视野压小，越过「全部已加载历史铺满」点时请求回溯。
        """
        delta = event.angleDelta().y()
        if delta == 0 or not self.candles:
            return
        old = float(self._view_count)
        total = len(self.candles)
        zoom_in = delta > 0
        if zoom_in:
            new = max(float(self._min_bars), min(old - 1.0, old * 0.84))
            if new < old:
                self.fit_all = False
                self.user_view_change.emit()
        else:
            vmax = max(180.0, 2.0 * total)
            new = max(old, min(old * 1.22 + 1.0, vmax))
            if not self.history_exhausted and new >= float(total):
                self.need_history.emit()
            if new > float(total):
                self.fit_all = False
        if new != old:
            w = max(60.0, self.width() - self._margin_l - self._margin_r)
            right_px = self._margin_l + w
            mx = float(event.position().x())
            near_axis = right_px - w * 0.12
            if not (self._margin_l <= mx <= near_axis):
                mx = (self._margin_l + right_px) / 2.0
            old_step, new_step = w / old, w / new
            idx_anchor = self._right_edge() - (right_px - mx) / old_step
            # 新右边缘 = 锚点索引 + 锚点到右边缘的「新格子数」
            self._pan = total - (idx_anchor + (right_px - mx) / new_step)
            self._view_count = new
            self._view_touched = True
            self.view_changed.emit()
        elif not zoom_in:
            self.need_history.emit()      # 已在极限，继续请求更早历史
        if not zoom_in and new >= float(total):
            # 视野比全部历史还宽时，锚点可能把早期 K 线推出左边缘（右侧
            # 留白越堆越多）。这里只做下限约束：保证全部已加载历史仍在
            # 屏内，绝不把 pan 强行设成某个固定值（那才是旧的对齐 bug）。
            self._pan = max(float(self._pan), float(total) - new)
        self._clamp_pan()
        event.accept()
        self.update()

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        g = self._geom() if self.candles else None
        if event.button() == Qt.RightButton:
            if self._pending is not None or self._selected is not None:
                self._pending = None
                self._selected = None
                self._drag = None
                self.update()
            return
        if event.button() != Qt.LeftButton or g is None:
            return

        if self._tool == "none":
            # 光标模式下：点在线上 -> 调整线条；点在空白 -> 左右拖动平移
            if not (g["price"].top() <= pos.y() <= g["bottom"]):
                return
            hit = self._hit_test(g, pos)
            self._selected = hit
            if hit is not None:
                self._drag = {
                    "line": hit, "mode": self._handle_at(g, hit, pos),
                    "start": (pos.x(), pos.y()), "orig": dict(hit)}
                self.setCursor(Qt.SizeAllCursor)
            else:
                self._panning = True
                self._pan_start = (pos.x(), self._pan, g["step"])
                self.setCursor(Qt.ClosedHandCursor)
                # 手动平移即退出「全部历史自动贴合」，避免刷新时被拉回全图
                if self.fit_all:
                    self.fit_all = False
                    self.user_view_change.emit()
            self.update()
            return

        if not g["price"].contains(QPointF(pos)):
            return
        price = self._price_at(g, pos.y())
        ts = self._ts_at_x(g, pos.x())
        if self._tool == "hline":
            self._lines.append({"kind": "hline", "price": price})
            self._selected = self._lines[-1]
            self._pending = None
            self.tool_finished.emit()      # 自动回光标，可立即二次调整
            self.update()
        elif self._tool == "trend":
            if self._pending is None:
                self._pending = (ts, price)
            else:
                self._lines.append(
                    {"kind": "trend", "p1": self._pending, "p2": (ts, price)})
                self._selected = self._lines[-1]
                self._pending = None
                self.tool_finished.emit()
            self.update()
        elif self._tool == "del":
            self._delete_near(g, pos)
            self.tool_finished.emit()

    def mouseDoubleClickEvent(self, event):
        """双击线 -> 选中进入光标模式；双击空白 -> 视野复位到最新。"""
        pos = event.position().toPoint()
        g = self._geom() if self.candles else None
        if g is not None:
            self._selected = self._hit_test(g, pos)
            if self._selected is None:
                self.reset_view()
            self.tool_finished.emit()
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._pending = None
            self._selected = None
            self._drag = None
            self._panning = False
            self._pan_start = None
            self.update()
        elif event.key() in (Qt.Key_Delete, Qt.Key_Backspace) \
                and self._selected is not None:
            if self._selected in self._lines:
                self._lines.remove(self._selected)
            self._selected = None
            self._drag = None
            self.update()
        else:
            super().keyPressEvent(event)

    # ---- 画线编辑 ----
    def _apply_drag(self, g, pos):
        """拖动：端点改位置 / 整条平移 / 水平线改价格（用增量，避免跳变）。"""
        d = self._drag
        line, orig, mode = d["line"], d["orig"], d["mode"]
        start_x, start_y = d["start"]
        # 价格增量：屏幕 y 增大 -> 价格减小（与 _y_price 严格互逆）
        dprice = self._price_at(g, pos.y()) - self._price_at(g, start_y)
        # 时间增量：直接用坐标反算，避免不规则时间轴（周末/停牌）产生偏差
        dts = self._ts_at_x(g, pos.x()) - self._ts_at_x(g, start_x)
        if mode == "hline":
            line["price"] = orig["price"] + dprice
        elif mode in ("p1", "p2"):
            line[mode] = (orig[mode][0] + dts, orig[mode][1] + dprice)
        else:  # move：整条线同时平移（保持斜率）
            line["p1"] = (orig["p1"][0] + dts, orig["p1"][1] + dprice)
            line["p2"] = (orig["p2"][0] + dts, orig["p2"][1] + dprice)

    def _hit_test(self, g, pos):
        """返回鼠标附近（8px 容差）最近的一条线。"""
        best, best_d = None, 8.0
        for line in self._lines:
            d = self._line_distance(g, line, pos)
            if d is not None and d < best_d:
                best, best_d = line, d
        return best

    def _handle_at(self, g, line, pos):
        """判断按在线的哪个部位：端点手柄 or 线体（整体平移）。"""
        pts = self._line_points(g, line)
        if pts is None:
            return "move"
        if line["kind"] == "hline":
            return "hline"
        x1, y1, x2, y2 = pts
        if math.hypot(pos.x() - x1, pos.y() - y1) <= 10:
            return "p1"
        if math.hypot(pos.x() - x2, pos.y() - y2) <= 10:
            return "p2"
        return "move"

    def _delete_near(self, g, pos):
        hit = self._hit_test(g, pos)
        if hit is not None:
            self._lines.remove(hit)
            if self._selected is hit:
                self._selected = None
            self.update()

    def _line_points(self, g, line):
        """线 -> (x1,y1,x2,y2)；允许端点超出面板，由 QPainter 自动裁剪。"""
        if line["kind"] == "hline":
            y = self._y_price(g, line["price"])
            return g["x0"], y, g["x0"] + g["w"], y
        x1 = self._ts_x(g, line["p1"][0])
        x2 = self._ts_x(g, line["p2"][0])
        if x1 is None or x2 is None:
            return None
        return x1, self._y_price(g, line["p1"][1]), \
            x2, self._y_price(g, line["p2"][1])

    def _line_distance(self, g, line, pos):
        pts = self._line_points(g, line)
        if pts is None:
            return None
        x1, y1, x2, y2 = pts
        px, py = pos.x(), pos.y()
        dx, dy = x2 - x1, y2 - y1
        if dx == dy == 0:
            return math.hypot(px - x1, py - y1)
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

    # ---- 绘制辅助 ----
    @staticmethod
    def _font(px: int, numeric: bool = False, bold: bool = False) -> QFont:
        font = QFont("IBM Plex Mono" if numeric else "Microsoft YaHei UI")
        font.setPixelSize(px)
        font.setBold(bold)
        return font

    def _axis_scale(self):
        """缩放级别 -> 轴/日期/图例数字的字号系数。

        放大（可见根数少）时略放大到 1.22 倍，缩到整个生命周期时
        缩到 0.82 倍，避免一屏几千根时文字挤成一团。
        """
        v = max(8.0, float(self._view_count))
        return max(0.82, min(1.22,
                             1.0 - math.log10(v / 90.0) * 0.13))

    def _axis_px(self, base=10):
        """轴/标签字号 = 基础字号 × 缩放系数 × 用户字号倍率。"""
        return max(8, int(round(base * self._axis_scale() * self.font_scale)))

    def set_live_speed(self, ms: int):
        """最新 K 线动画时长跟随实时轮询间隔，做到「一直在动」。"""
        self._anim.setDuration(max(220, min(2000, int(ms))))

    def set_font_scale(self, pct: int):
        """图表字号倍率（百分比）：价格轴、指标数值、标注一起放大。"""
        self.font_scale = max(1.0, min(2.0, float(pct) / 100.0))
        # 右侧价格轴按字号同比加宽，否则放大后 "$120,345.67" 会被截断
        self._margin_r = max(78, int(round(66 * self.font_scale + 16)))
        # 顶部两行图例、底部时间轴也按字号撑开，避免文字被裁掉
        self._margin_t = max(40, int(round(self._axis_px(10) * 2.5)))
        self._margin_b = max(28, int(round(self._axis_px(9) * 2.2)))
        self.update()

    def _money(self, text: str) -> str:
        """给价格文本加货币单位（$ / ¥ / HK$）。"""
        if not self.show_currency or not self.unit_prefix or not text:
            return text
        if text.startswith(self.unit_prefix):
            return text
        return self.unit_prefix + text

    def _text(self, painter, x, y, w, h, text, color,
              px=10, numeric=False, bold=False,
              align=Qt.AlignLeft | Qt.AlignVCenter):
        painter.setPen(QColor(color))
        painter.setFont(self._font(px, numeric, bold))
        painter.drawText(QRectF(x, y, w, h), align, text)

    @staticmethod
    def _dim_color(color, factor=170):
        """指标色的暗化版：给「名称」用，与「数值」拉开明度差。"""
        return QColor(color).darker(factor).name()

    def _draw_pair(self, painter, x, y, w, h, name, value,
                   name_color, value_color, px=10,
                   align=Qt.AlignLeft | Qt.AlignVCenter, bold=False):
        """名称与数值分色画在同一行。

        之前 `MA7 67891.23` 是整段字符串用同一个颜色，名称和价格糊在
        一起不好分辨；现在名称用暗色（或指标色的暗化版），数值用语义色 /
        指标本色，一眼就能把两者分开，同时保留数值与图上线条的对应关系。
        """
        fm = QFontMetrics(self._font(px, numeric=True, bold=bold))
        gap = fm.horizontalAdvance(" ")
        nw = fm.horizontalAdvance(name) + gap
        vw = fm.horizontalAdvance(value)
        if align & Qt.AlignHCenter:
            x += max(0.0, (w - nw - vw) / 2.0)
        elif align & Qt.AlignRight:
            x += max(0.0, w - nw - vw)
        self._text(painter, x, y, nw, h, name, name_color, px,
                   numeric=True, bold=bold)
        self._text(painter, x + nw, y, max(vw, w - nw), h, value,
                   value_color, px, numeric=True, bold=bold)

    @staticmethod
    def hover_change(target: float, now: float):
        """当前最新价 -> 光标横坐标处目标价 的倍数 / 涨跌幅。

        目标价在当前价之上：涨幅（UP，红色 C_UP）；
        目标价在当前价之下：当前价到目标价的跌幅（DN，绿色 C_DOWN）。
        全程只用英文缩写与数字，不出现汉字。
        """
        mult = target / now if now > 0 else 1.0
        pct = (mult - 1.0) * 100.0
        up = pct >= 0
        sign = "+" if up else ""
        return {
            "mult": mult, "pct": pct, "up": up,
            "color": C_UP if up else C_DOWN,
            "tag": "UP" if up else "DN",
            "text": f"{'UP' if up else 'DN'} x{mult:.2f} {sign}{pct:.1f}%",
        }

    # ---- 自动分析线：趋势线 / 压力位 / 支撑位 ----
    def _compute_auto(self, bars):
        """基于可见 K 线计算：线性回归趋势线 + 枢轴点聚类支撑压力位。

        超长历史先等距抽样，避免一屏十几万根时每帧做百万级运算。
        """
        stride = max(1, len(bars) // 1500)
        if stride > 1:
            bars = bars[::stride]
        n = len(bars)
        if n < 24:
            return None
        highs = [c.high for c in bars]
        lows = [c.low for c in bars]
        closes = [c.close for c in bars]
        # 趋势线：收盘价最小二乘拟合，锚定在可见区首末两根
        mx = (n - 1) / 2.0
        my = sum(closes) / n
        den = sum((i - mx) ** 2 for i in range(n)) or 1.0
        slope = sum((i - mx) * (closes[i] - my)
                    for i in range(n)) / den
        p0 = my - slope * mx
        p1 = p0 + slope * (n - 1)
        # 枢轴高低点（左右 w 根内最值）
        w = max(3, min(14, n // 40))
        piv_h, piv_l = [], []
        for i in range(w, n - w):
            if highs[i] >= max(highs[i - w:i + w + 1]):
                piv_h.append((highs[i], i))     # 同时记住枢轴所在 K 线
            if lows[i] <= min(lows[i - w:i + w + 1]):
                piv_l.append((lows[i], i))
        span = (max(highs) - min(lows)) or (closes[-1] * 0.01) or 1.0
        tol = span * 0.012

        def levels(pairs):
            """按价位聚类，并返回该价位最具代表性的那根 K 线索引。"""
            groups = []
            for v, i in sorted(pairs):
                if groups and v - groups[-1][-1][0] <= tol:
                    groups[-1].append((v, i))
                else:
                    groups.append([(v, i)])
            scored = []
            for gp in groups:
                price = sum(v for v, _ in gp) / len(gp)
                rep = min(gp, key=lambda it: abs(it[0] - price))[1]
                scored.append({"p": price, "i": rep, "n": len(gp)})
            scored.sort(key=lambda d: -d["n"])  # 触及次数越多越显著
            return scored[:6]

        last = closes[-1]
        res = sorted([d for d in levels(piv_h) if d["p"] > last],
                     key=lambda d: d["p"] - last)[:2]
        sup = sorted([d for d in levels(piv_l) if d["p"] < last],
                     key=lambda d: last - d["p"])[:2]
        # 聚类得到的索引是抽样后的位置，画标注时要映射回真实 K 线
        for d in res + sup:
            age = (n - 1) - d["i"]           # 距最新一根多少根（抽样单位）
            d["age"] = age
            # 近期（末段）且被反复触及的才算「当前仍有效」的支撑压力：
            # 这些用最醒目的实色标出，历史失效的用暗色 + 小点弱化。
            d["recent"] = age <= max(6, int(n * 0.28))
            d["i"] *= stride
        return {"p0": p0, "p1": p1, "slope": slope,
                "res": res, "sup": sup, "stride": stride}

    def _draw_auto(self, painter, g):
        """智能线：趋势 / 压力 / 支撑 分别由三个独立按钮控制。

        不再画贯穿全图的水平线；压力位与支撑位只在「对应的枢轴 K 线」
        处打点并标注价格，趋势线仍保留为斜线。
        """
        if not (self.show_trend or self.show_res or self.show_sup):
            return
        bars = g["bars"]
        a = self._compute_auto(bars)
        if a is None:
            return
        first_x = g["bar_x0"] + g["step"] * 0.5
        last_x = g["bar_x0"] + g["step"] * (len(bars) - 0.5)
        view_x = g["x0"] + g["w"]
        label_right = view_x - 66   # 右侧当前价气泡占位，标签不要压上去
        painter.setBrush(Qt.NoBrush)
        if self.show_trend:
            painter.setPen(QPen(QColor(C_ACCENT), 1.6, Qt.DashLine))
            painter.drawLine(QPointF(first_x, self._y_price(g, a["p0"])),
                             QPointF(last_x, self._y_price(g, a["p1"])))
            self._text(painter, first_x + 4, g["price"].top() + 2, 150, 15,
                       f"TREND {'UP' if a['slope'] >= 0 else 'DN'}",
                       C_ACCENT, self._axis_px(10), numeric=True, bold=True)
        groups = []
        if self.show_res:
            groups.append(("R", a["res"], C_UP))
        if self.show_sup:
            groups.append(("S", a["sup"], C_DOWN))
        for kind, group, color in groups:
            for seq, d in enumerate(group, 1):
                price = d["p"]
                x = g["bar_x0"] + g["step"] * (d["i"] + 0.5)
                y = self._y_price(g, price)
                if not (g["x0"] <= x <= view_x and
                        g["price"].top() - 2 <= y <= g["price"].bottom() + 2):
                    continue
                # 近期有效：最醒目的实色 + 大圆点 + 淡色药丸底；
                # 历史失效：同类色压暗 55%，圆点缩小，只留价格不抢视线。
                live = bool(d.get("recent")) and seq == 1
                if live:
                    dot = 4.8
                    fg = QColor(color)
                    dim = QColor(color)
                    pill = QColor(color)
                    pill.setAlpha(46)
                    px = self._axis_px(11)
                    tw, th = 126, 19
                else:
                    dot = 2.6
                    fg = QColor(color).darker(230)
                    dim = QColor(color).darker(260)
                    pill = None
                    px = self._axis_px(9)
                    tw, th = 112, 15
                painter.setBrush(QColor(color) if live else fg)
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(x, y), dot, dot)
                tx = max(g["x0"] + 2,
                         min(x - tw / 2, label_right - tw - 2))
                ty = y - (th + 6) if kind == "R" else y + 5
                ty = max(g["price"].top() + 2,
                         min(ty, g["price"].bottom() - th - 2))
                if pill is not None:
                    painter.setBrush(pill)
                    painter.drawRoundedRect(QRectF(tx - 3, ty, tw + 6, th),
                                            4, 4)
                self._draw_pair(painter, tx, ty, tw, th,
                                f"{kind}{seq}", self._money(format_price(price)),
                                dim.name(), fg.name(), px,
                                align=Qt.AlignHCenter, bold=True)

    def _draw_extremes(self, painter, g):
        """在对应 K 线处标注 ATH / ATL 价格：无水平线、无右侧轴参考线。

        只有「已回溯到上市首根」时，self._extremes 才是真正的历史最高 /
        最低；历史还没拉全时它只是已加载区间里的极值，即局部高低点。
        之前无论是否回溯完都按 ATH / ATL 画，于是近期的一个小高点被
        标成「历史最高」——这里必须门控，宁可不标也不能标错。

        v37 追加：history_exhausted 只代表「回溯停止」，达到回溯上限、
        分页边界、从缓存恢复标记时也会是 True。必须再要求
        _extremes_trusted（当前 candles 确实覆盖上市首根且周期是日线以上），
        否则用户放大到几根 K 线的小时间范围时，局部高低点又会被冒充 ATH / ATL。
        """
        e = self._extremes
        self._extreme_rects = []
        if not e or not (self.history_exhausted and self._extremes_trusted):
            return
        hi_i, hi_p, lo_i, lo_p = e
        offset, end = self._visible_range()
        view_x = g["x0"] + g["w"]
        label_right = view_x - 66   # 给右侧当前价气泡留位
        for label, idx, price, color, above in (
                ("ATH", hi_i, hi_p, C_UP, True),
                ("ATL", lo_i, lo_p, C_BLUE, False)):
            if not (offset <= idx < end):
                continue    # 对应 K 线不在视野里就不标注
            y = self._y_price(g, price)
            if not (g["price"].top() - 2 <= y <= g["price"].bottom() + 2):
                continue
            x = g["bar_x0"] + g["step"] * (idx - offset + 0.5)
            painter.setBrush(QColor(color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(x, y), 3.6, 3.6)
            th = self._axis_px(9) + 8
            tw = th * 7.0
            tx = max(g["x0"] + 2,
                     min(x - tw / 2, label_right - tw - 2))
            ty = y - th - 4 if above else y + 5
            ty = max(g["price"].top() + 2,
                     min(ty, g["price"].bottom() - th - 2))
            self._extreme_rects.append(QRectF(tx, ty, tw, th))
            self._draw_pair(painter, tx, ty, tw, th,
                            label, self._money(format_price(price)),
                            self._dim_color(color, 150), color,
                            self._axis_px(9),
                            align=Qt.AlignHCenter, bold=True)

    # ---- 局部高低点（LH / LL）----
    def _compute_pivots(self, bars):
        """一屏各只取一个：可见区间的最高价 K 线（LH）与最低价 K 线（LL）。

        不再做 swing 转折点枚举，直接取可见切片的极值所在那根 K 线；
        返回索引相对 bars 切片，绘制时可直接定位。
        """
        if len(bars) < 3:
            return {"h": [], "l": []}
        hi = max(range(len(bars)), key=lambda i: bars[i].high)
        lo = min(range(len(bars)), key=lambda i: bars[i].low)
        return {"h": [(hi, bars[hi].high)], "l": [(lo, bars[lo].low)]}

    def _draw_pivots(self, painter, g):
        """局部高点 LH / 局部低点 LL：一屏各只标一个（可见区间极值）。

        沿用 ATH/ATL 与 R/S 的显示方式：只在对应 K 线的最高/最低价处
        打点，旁边标英文缩写 + 价格，不画贯穿水平线。若史高 ATH /
        史低 ATL 的标注已落在可见区间，对应方向的局部标注让位，
        不在同一根 K 线上重复标价。
        """
        pv = self._compute_pivots(g["bars"])
        if not pv["h"] and not pv["l"]:
            return
        offset, end = self._visible_range()
        e = self._extremes or (None, None, None, None)
        # 只有真实的 ATH / ATL 且在屏内时才让位。history_exhausted 可能
        # 只是「回溯停止」（上限 / 分页边界 / 缓存标记），必须同时要求
        # _extremes_trusted，否则小时间范围里的局部点会被当成史高史低。
        trusted = self.history_exhausted and self._extremes_trusted
        skip_h = (self.show_extremes and trusted
                  and e[0] is not None and offset <= e[0] < end)
        skip_l = (self.show_extremes and trusted
                  and e[2] is not None and offset <= e[2] < end)
        view_x = g["x0"] + g["w"]
        label_right = view_x - 66   # 给右侧当前价气泡留位
        top, bottom = g["price"].top(), g["price"].bottom()
        placed = list(self._extreme_rects) if self.show_extremes else []
        for label, group, color, above, skip in (
                ("LH", pv["h"], C_UP, True, skip_h),
                ("LL", pv["l"], C_DOWN, False, skip_l)):
            if skip:
                continue
            for idx, price in group:
                x = g["bar_x0"] + g["step"] * (idx + 0.5)
                y = self._y_price(g, price)
                if not (g["x0"] <= x <= view_x and
                        top - 2 <= y <= bottom + 2):
                    continue
                tw = (self._axis_px(9) + 8) * 6.4
                th = self._axis_px(9) + 8
                tx = max(g["x0"] + 2,
                         min(x - tw / 2, label_right - tw - 2))
                ty = y - th - 3 if above else y + 5
                ty = max(top + 2, min(ty, bottom - th - 2))
                rect = QRectF(tx, ty, tw, th)
                if any(rect.intersects(r) for r in placed):
                    continue
                placed.append(rect)
                painter.setBrush(QColor(color))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(x, y), 3.0, 3.0)
                self._draw_pair(painter, tx, ty, tw, th,
                                label, self._money(format_price(price)),
                                self._dim_color(color, 150), color,
                                self._axis_px(9),
                                align=Qt.AlignHCenter, bold=True)

    # ---- 绘制 ----
    def _draw_onchain(self, painter):
        """链上真实数据图：采样报价折线 + 持有人 / 流动性池结构条。

        所有点都来自 Rugcheck 真实返回；没有 OHLC、成交量与插值。
        """
        v = self.onchain_view or {}
        series = [p for p in (v.get("series") or [])
                  if isinstance(p, (list, tuple)) and len(p) >= 2]
        holders = v.get("holders") or []
        pools = v.get("pools") or []
        W, H = self.width(), self.height()
        x0, x1 = 12, max(90, W - 78)
        y0 = 58
        y1 = max(y0 + 60, int(H * 0.60))
        painter.fillRect(QRectF(x1, 0, W - x1, H), QColor(C_AXIS_BG))
        self._text(painter, 12, 6, W - 24, 20,
                   "链上真实报价走势 · 非交易所 K 线（无 OHLC / 成交量）",
                   C_TEXT_SUB, 11, bold=True)
        self._text(painter, 12, 27, W - 24, 20,
                   f"来源 {v.get('source') or '链上报价源'} · "
                   f"{len(series)} 个真实采样点 · 本设备采集",
                   C_TEXT_DIM, 10)

        try:
            vals = [float(p[1]) for p in series]
        except (TypeError, ValueError):
            vals = []
        lo, hi = (min(vals), max(vals)) if vals else (0.0, 1.0)
        if hi <= lo:
            d = max(abs(lo) * 0.02, 1e-8)
            hi, lo = lo + d, lo - d
        else:
            d = (hi - lo) * 0.12
            hi, lo = hi + d, lo - d

        painter.setPen(QPen(QColor(C_GRID), 1))
        for i in range(5):
            yy = y0 + (y1 - y0) * i / 4
            painter.drawLine(x0, int(yy), x1, int(yy))
            self._text(painter, x1 + 4, int(yy) - 9, W - x1 - 6, 18,
                       "$" + format_price(hi - (hi - lo) * i / 4),
                       C_TEXT_DIM, 10, numeric=True)

        def px(i):
            return x0 + ((x1 - x0) * i / (len(series) - 1)
                         if len(series) > 1 else (x1 - x0) / 2)

        def py(price):
            return y1 - (price - lo) / (hi - lo) * (y1 - y0)

        if len(vals) >= 2:
            path = QPainterPath()
            for i, price in enumerate(vals):
                if i == 0:
                    path.moveTo(px(i), py(price))
                else:
                    path.lineTo(px(i), py(price))
            painter.setPen(QPen(QColor(C_ACCENT), 2))
            painter.drawPath(path)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(C_ACCENT))
            step = max(1, len(vals) // 80)
            for i in range(0, len(vals), step):
                painter.drawRect(QRectF(px(i) - 1.5, py(vals[i]) - 1.5, 3, 3))
            painter.setBrush(Qt.NoBrush)
            try:
                left = datetime.fromtimestamp(series[0][0]).strftime("%m-%d %H:%M")
                right = datetime.fromtimestamp(series[-1][0]).strftime("%m-%d %H:%M")
            except (OSError, TypeError, ValueError):
                left = right = ""
            self._text(painter, x0, H - 24, 150, 18, left, C_TEXT_DIM, 10)
            self._text(painter, x1 - 150, H - 24, 150, 18, right,
                       C_TEXT_DIM, 10, align=Qt.AlignRight | Qt.AlignVCenter)
        else:
            self._text(painter, x0, (y0 + y1) // 2 - 14, x1 - x0, 28,
                       "已采到 1 个真实价格点 · 行情刷新后自动累积走势"
                       if vals else "等待首个真实链上报价…",
                       C_TEXT_DIM, 11, align=Qt.AlignCenter)
            if vals:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(C_ACCENT))
                painter.drawRect(QRectF(px(0) - 4, py(vals[0]) - 4, 8, 8))
                painter.setBrush(Qt.NoBrush)

        sy = y1 + 22
        bars = []
        if holders:
            title = f"前 {min(6, len(holders))} 大持有地址占比 · 真实链上快照"
            for h in holders[:6]:
                try:
                    pct = float(h.get("pct") or 0)
                except (TypeError, ValueError, AttributeError):
                    pct = 0.0
                bars.append((str(h.get("label") or "#"), pct, f"{pct:.2f}%"))
        elif pools:
            title = (f"流动性池类型分布 · 共 "
                     f"{v.get('market_count') or len(pools)} 个池")
            for p in pools[:6]:
                try:
                    cnt = float(p.get("count") or 0)
                except (TypeError, ValueError, AttributeError):
                    cnt = 0.0
                bars.append((str(p.get("label") or "other"), cnt,
                             str(p.get("count") or 0)))
        self._text(painter, x0, sy, W - 24, 20,
                   title if bars else
                   "链上结构数据暂不可用（数据源未返回持有地址 / 池信息）",
                   C_TEXT_SUB, 11, bold=True)
        if not bars:
            return
        maxv = max((b[1] for b in bars), default=0.0) or 1.0
        row_h = max(16, min(30, (H - sy - 30) // len(bars)))
        bx, bw = x0 + 96, max(40, x1 - x0 - 150)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(C_ACCENT))
        for i, (label, val, text) in enumerate(bars):
            yy = sy + 24 + i * row_h
            self._text(painter, x0, yy, 92, row_h - 2, label[:12],
                       C_TEXT_DIM, 10)
            painter.setOpacity(0.75)
            painter.drawRect(QRectF(bx, yy + 3,
                                    max(2.0, bw * val / maxv),
                                    max(3.0, row_h - 8)))
            painter.setOpacity(1.0)
            self._text(painter, x1 - 72, yy, 72, row_h - 2, text,
                       C_TEXT_MAIN, 10, numeric=True,
                       align=Qt.AlignRight | Qt.AlignVCenter)
        painter.setBrush(Qt.NoBrush)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(C_BG_BASE))

        if self.onchain_view is not None:
            self._draw_onchain(painter)
            painter.end()
            return

        if not self.candles:
            self._text(painter, 0, 0, self.width(), self.height(),
                       self._status, C_TEXT_DIM, 12,
                       align=Qt.AlignCenter)
            painter.end()
            return

        g = self._geom()
        bars = g["bars"]
        # 日线 5 年（约 1800 根）仍然画真实蜡烛，不提前切成简化折线；
        # 只有上万根的全历史才做抽样面积线。
        heavy = self._heavy or len(bars) > 6000
        step = g["step"]
        body_w = max(1.5, min(18.0, step * 0.62))
        offset = g["offset"]
        n = g["n"]
        hover_i = self._hover_index(g)
        view_x = g["x0"] + g["w"]
        axis_bg = QColor(C_AXIS_BG)

        # ---- 右侧价格轴 / 底部时间轴底色 ----
        painter.fillRect(QRectF(view_x, 0, self._margin_r, self.height()),
                         axis_bg)
        painter.fillRect(QRectF(0, g["bottom"], self.width(),
                                self.height() - g["bottom"]), axis_bg)
        painter.setPen(QPen(QColor(C_BORDER), 1))
        painter.drawLine(int(view_x), 0, int(view_x), self.height())
        painter.drawLine(0, int(g["bottom"]), self.width(), int(g["bottom"]))

        # ---- 图例（顶部信息区，不再压在 K 线上）----
        self._draw_legend(painter, g, hover_i, n)

        # ---- 价格网格 + 轴 ----
        painter.setFont(self._font(self._axis_px(10), numeric=True))
        for i in range(5):
            p = g["lo"] + (g["hi"] - g["lo"]) * i / 4
            y = self._y_price(g, p)
            painter.setPen(QPen(QColor(C_GRID), 1, Qt.DotLine))
            painter.drawLine(g["x0"], int(y), int(view_x), int(y))
            self._text(painter, view_x + 6, y - 8, self._margin_r - 8, 16,
                       self._money(format_price(p)), C_TEXT_DIM,
                       self._axis_px(10), numeric=True)

        # ---- 副图分隔线 / 标题 ----
        for key, title in (("vol", "VOL"), ("macd", self.macd_title())):
            r = g.get(key)
            if r is None:
                continue
            painter.setPen(QPen(QColor(C_GRID), 1, Qt.DotLine))
            painter.drawLine(g["x0"], int(r.top()), int(view_x), int(r.top()))
            self._text(painter, g["x0"] + 6, r.top() + 2, 220, 15,
                       title, C_TEXT_DIM, self._axis_px(10))
        if g.get("macd") is not None:
            mr = g["macd"]
            painter.setPen(QPen(QColor(C_GRID), 1, Qt.DotLine))
            painter.drawLine(g["x0"], int(mr.top() + mr.height() / 2),
                             int(view_x), int(mr.top() + mr.height() / 2))

        # ---- 蜡烛 / 全历史密度自适应 ----
        if step < 0.35 or self._heavy:
            # 真正上万根的全历史才切面积折线；日线 5 年仍是真实蜡烛。
            # 自动切换成收盘价面积折线；超长历史等距抽样，
            # 保证十几万根也不会拖慢绘制。
            if bars:
                stride = max(1, len(bars) // 2200)
                idx = list(range(0, len(bars), stride))
                if idx[-1] != len(bars) - 1:
                    idx.append(len(bars) - 1)
                color = QColor(C_UP if bars[-1].close >= bars[0].close
                               else C_DOWN)
                line = QPainterPath()
                fill = QPainterPath()
                first_x = g["bar_x0"] + step * (idx[0] + 0.5)
                last_x = g["bar_x0"] + step * (idx[-1] + 0.5)
                fill.moveTo(first_x, g["price"].bottom())
                for k, i in enumerate(idx):
                    x = g["bar_x0"] + step * (i + 0.5)
                    y = self._y_price(g, bars[i].close)
                    if k == 0:
                        line.moveTo(x, y)
                    else:
                        line.lineTo(x, y)
                    fill.lineTo(x, y)
                fill.lineTo(last_x, g["price"].bottom())
                fill.closeSubpath()
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(color, 1.6))
                painter.drawPath(line)
                painter.fillPath(fill, QColor(color.red(), color.green(),
                                              color.blue(), 38))
        else:
            for i, c in enumerate(bars):
                up = c.close >= c.open
                color = QColor(C_UP if up else C_DOWN)
                x = g["bar_x0"] + step * (i + 0.5)
                painter.setPen(QPen(color, 1))
                painter.drawLine(int(x), int(self._y_price(g, c.high)),
                                 int(x), int(self._y_price(g, c.low)))
                top = self._y_price(g, max(c.open, c.close))
                bottom = self._y_price(g, min(c.open, c.close))
                painter.setBrush(color)
                painter.setPen(Qt.NoPen)
                painter.drawRect(QRectF(x - body_w / 2, top,
                                        body_w, max(1.0, bottom - top)))

        # ---- 自动趋势线 / 压力位 / 支撑位 ----
        if self.show_auto:
            self._draw_auto(painter, g)

        # ---- 历史最高价 / 最低价标注 ----
        if self.show_extremes:
            self._draw_extremes(painter, g)

        # ---- 局部高点 LH / 局部低点 LL（同一方式：只打点标价格）----
        if self.show_pivots:
            self._draw_pivots(painter, g)

        # ---- BOLL 布林带（超长历史跳过逐根绘制）----
        if self.show_boll and not heavy:
            self._draw_boll(painter, g, offset, n)

        # ---- 成交量副图 ----
        vr = g.get("vol")
        if vr is not None:
            vstride = max(1, len(bars) // 1600)
            max_vol = max((c.volume for c in bars), default=0.0) or 1.0
            for i in range(0, len(bars), vstride):
                c = bars[i]
                color = QColor(C_UP if c.close >= c.open else C_DOWN)
                x = g["bar_x0"] + step * (i + 0.5)
                vh = vr.height() * 0.88 * c.volume / max_vol
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                painter.drawRect(QRectF(x - body_w / 2,
                                        vr.bottom() - vh, body_w, vh))
            # 成交量刻度放在副图底部：放顶部会和最下面的价格轴标签撞在一起
            self._text(painter, view_x + 6, vr.bottom() - self._axis_px(9) - 4,
                       self._margin_r - 8, self._axis_px(9) + 4,
                       self._short_vol(max_vol), C_TEXT_DIM,
                       self._axis_px(9), numeric=True)

        # ---- MA / EMA 均线（天数、启用状态由指标参数面板控制）----
        if not heavy:
            if self.show_ma:
                for line in self.ma_lines:
                    if line["enabled"]:
                        self._draw_series_line(
                            painter, g,
                            self._ind["ma"].get(line["period"], []),
                            offset, line["color"])
            if self.show_ema:
                for line in self.ema_lines:
                    if line["enabled"]:
                        self._draw_series_line(
                            painter, g,
                            self._ind["ema"].get(line["period"], []),
                            offset, line["color"], width=1.4)

        # ---- 最新价虚线 + 价格标签 ----
        last = bars[-1]
        y = self._y_price(g, last.close)
        color = QColor(C_UP if last.close >= last.open else C_DOWN)
        painter.setPen(QPen(color, 1, Qt.DashLine))
        painter.drawLine(g["x0"], int(y), int(view_x), int(y))
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        tag = QRectF(view_x + 2, y - self._axis_px(10) * 0.95,
                     self._margin_r - 4, self._axis_px(10) * 1.9)
        painter.drawRect(tag)
        self._text(painter, tag.x(), tag.y(), tag.width(), tag.height(),
                   self._money(format_price(last.close)), "#ffffff",
                   self._axis_px(10), numeric=True,
                   bold=True, align=Qt.AlignCenter)

        # ---- MACD 副图 ----
        mr = g.get("macd")
        if mr is not None and not heavy:
            dif, dea, hist = self._ind["macd"]
            self._draw_macd(painter, g, dif, dea, hist, offset, body_w)
            self._draw_macd_labels(painter, g, dif, dea, hist,
                                   offset, hover_i, n)

        # ---- 画线（选中线加粗 + 端点手柄） ----
        for line in self._lines:
            pts = self._line_points(g, line)
            if pts is None:
                continue
            sel = line is self._selected
            painter.setPen(QPen(QColor(C_SELECT if sel else C_LINE),
                                2.2 if sel else 1.4))
            painter.drawLine(int(pts[0]), int(pts[1]),
                             int(pts[2]), int(pts[3]))
            if sel:
                painter.setBrush(QColor(C_LINE))
                painter.setPen(QPen(QColor(C_SELECT), 1))
                for hx, hy in ((pts[0], pts[1]), (pts[2], pts[3])):
                    if 0 <= hx <= self.width() and 0 <= hy <= self.height():
                        painter.drawRect(QRectF(hx - 4, hy - 4, 8, 8))

        # ---- 趋势线预览 ----
        if self._pending is not None and self._mouse_pos is not None:
            x1 = self._ts_x(g, self._pending[0])
            y1 = self._y_price(g, self._pending[1])
            painter.setPen(QPen(QColor(C_LINE), 1.2, Qt.DashLine))
            painter.drawLine(int(x1), int(y1),
                             self._mouse_pos.x(), self._mouse_pos.y())

        # ---- 十字光标 ----
        if hover_i is not None and self._mouse_pos is not None:
            x = g["bar_x0"] + step * (hover_i + 0.5)
            painter.setPen(QPen(QColor(C_CROSS), 1, Qt.DashLine))
            painter.drawLine(int(x), int(g["price"].top()),
                             int(x), int(g["bottom"]))
            painter.drawLine(g["x0"], self._mouse_pos.y(),
                             int(view_x), self._mouse_pos.y())
            # 只有光标在主图价格区里，y 坐标才对应一个有效价格；
            # 悬停在成交量 / MACD 副图时不要按价格轴外推（会得到负数）
            in_price = (g["price"].top() - 1 <= self._mouse_pos.y()
                        <= g["price"].bottom() + 1)
            cursor_price = (self._price_at(g, self._mouse_pos.y())
                            if in_price else 0.0)
            if in_price:
                py = max(g["price"].top(),
                         min(g["price"].bottom() - 18,
                             self._mouse_pos.y() - 9))
                painter.fillRect(QRectF(view_x + 2, py,
                                        self._margin_r - 4, 18),
                                 QColor(C_BG_HOVER))
                self._text(painter, view_x + 2, py, self._margin_r - 4, 18,
                           format_price(cursor_price),
                           C_TEXT_MAIN, self._axis_px(10), numeric=True,
                           align=Qt.AlignCenter)
            # 跟随光标的浮动标签：光标纵坐标价格 vs 当前市场价。
            # 之前拿「光标处 K 线收盘价」和「最后一根收盘价」比较，
            # 鼠标上下移动时数字不变，和右侧轴显示的价位也对不上。
            if in_price and cursor_price > 0 and self.candles:
                target = cursor_price
                # 基准价优先用实时最新价（ticker），没有则退回最后一根收盘
                now = self.last_price or self.candles[-1].close
                chg = self.hover_change(target, now)
                col = chg["color"]
                bw, bh = 152, 22
                bx = self._mouse_pos.x() + 14
                if bx + bw > view_x:
                    bx = self._mouse_pos.x() - bw - 14
                bx = max(g["x0"] + 2, min(bx, view_x - bw - 2))
                by = self._mouse_pos.y() + 14
                if by + bh > g["bottom"] - 2:
                    by = self._mouse_pos.y() - bh - 14
                by = max(g["price"].top() + 2,
                         min(by, g["bottom"] - bh - 2))
                painter.fillRect(QRectF(bx, by, bw, bh),
                                 QColor(C_BG_PANEL))
                painter.setPen(QPen(QColor(col), 1))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(QRectF(bx, by, bw, bh))
                self._text(painter, bx + 2, by, bw - 4, bh,
                           chg["text"], col,
                           self._axis_px(11), numeric=True, bold=True,
                           align=Qt.AlignCenter)

        # ---- 时间轴（独立区域，标签完整居中，绝不越界）----
        self._draw_time_axis(painter, g, hover_i, view_x)
        painter.end()

    # ---- 各区块绘制 ----
    def _draw_legend(self, painter, g, hover_i, n):
        """顶部两行图例：OHLC 行情 + 指标数值（跟随悬停，默认最新一根）。"""
        idx = g["offset"] + (hover_i if hover_i is not None else n - 1)
        bars = g["bars"]
        c = bars[hover_i if hover_i is not None else n - 1]
        if hover_i is not None and hover_i > 0:
            prev = bars[hover_i - 1]
        else:
            prev = bars[n - 2] if n > 1 else c
        chg = (c.close - prev.close) / prev.close * 100 if prev.close else 0.0
        chg_color = C_UP if chg >= 0 else C_DOWN

        h = max(15, self._axis_px(10) + 5)
        y1, y2 = 1, max(15, self._axis_px(10) + 5) + 4
        x = g["x0"] + 2
        px = self._axis_px(10)
        fm = QFontMetrics(self._font(px, numeric=True, bold=True))

        def seg_w(name, value):
            """按实际字宽排版：字号放大后仍不会把下一段挤掉或截断。"""
            return (fm.horizontalAdvance(name) + fm.horizontalAdvance(value)
                    + max(10, fm.horizontalAdvance("  ")) + 2)

        # 名称统一用暗灰，数值用亮色 / 涨跌色，两者不再同色
        segments = [
            ("", c.time_label, C_TEXT_SUB),
            ("O", self._money(format_price(c.open)), C_TEXT_MAIN),
            ("H", self._money(format_price(c.high)), C_TEXT_MAIN),
            ("L", self._money(format_price(c.low)), C_TEXT_MAIN),
            ("C", self._money(format_price(c.close)), C_TEXT_MAIN),
            ("", f"{chg:+.2f}%", chg_color),
        ]
        limit = self.width() - 300     # 右上角状态提示的起点
        for name, value, color in segments:
            w = seg_w(name, value)
            if x + w > limit:          # 窄窗口下不覆盖状态提示
                break
            if name:
                self._draw_pair(painter, x, y1, w, h, name, value,
                                C_TEXT_DIM, color, px,
                                bold=(color == chg_color))
            else:
                self._text(painter, x, y1, w, h, value, color,
                           px, numeric=True, bold=(color == chg_color))
            x += w

        # 第二行：指标名称（暗化指标色）与指标数值（指标本色）分色
        x = g["x0"] + 2
        parts = []
        if self.show_ma:
            for line in self.ma_lines:
                if not line["enabled"]:
                    continue
                series = self._ind["ma"].get(line["period"], [])
                v = series[idx] if idx < len(series) else None
                parts.append((f"MA{line['period']}",
                              self._money(format_price(v)) if v else "--",
                              line["color"]))
        if self.show_ema:
            for line in self.ema_lines:
                if not line["enabled"]:
                    continue
                series = self._ind["ema"].get(line["period"], [])
                v = series[idx] if idx < len(series) else None
                parts.append((f"EMA{line['period']}",
                              self._money(format_price(v)) if v else "--",
                              line["color"]))
        if self.show_boll:
            up, mid, dn = self._ind["boll"]
            for name, series, color in (("UP", up, BOLL_BAND),
                                        ("MB", mid, BOLL_MID),
                                        ("DN", dn, BOLL_BAND)):
                v = series[idx] if idx < len(series) else None
                parts.append((f"BOLL {name}",
                              self._money(format_price(v)) if v else "--",
                              color))
        for name, value, color in parts:
            w = seg_w(name, value)
            # 状态提示只占第一行，指标行可用整幅宽度；MA+EMA+BOLL 同时
            # 开启时也能尽量多显示，放不下的尾部才省略。
            if x + w > self.width() - 8:
                break
            self._draw_pair(painter, x, y2, w, h, name, value,
                            self._dim_color(color), color, px)
            x += w

        # 右上角：缩放 / 平移状态 + 可视时间区间（明确标出年份）
        total = len(self.candles)
        back = f" · 回看 {int(self._pan)} 根" if self._pan > 0.5 else \
            (f" · 右移 {int(-self._pan)} 根" if self._pan < -0.5 else " · 最新")
        # 未回溯到上市首根 / 只回溯到上限时，明确标注「区间高低」，
        # 避免把小时间范围内的局部高低误读成 ATH / ATL
        if self._extremes_trusted:
            tail = " · 全部历史"
        elif self.history_capped:
            tail = " · 已达回溯上限 · 区间高低"
        else:
            tail = " · 未回溯至首根 · 区间高低"
        info = f"{n}/{total} 根{back}{tail} · 滚轮缩放 / 拖动平移"
        self._text(painter, self.width() - 280, 2, 272, 17, info,
                   C_TEXT_DIM, self._axis_px(10),
                   align=Qt.AlignRight | Qt.AlignVCenter)
        if bars:
            span = f"{self._axis_date(bars[0])} → {self._axis_date(bars[-1])}"
            self._text(painter, self.width() - 280, 20, 272, 15, span,
                       C_TEXT_SUB, self._axis_px(9), numeric=True,
                       align=Qt.AlignRight | Qt.AlignVCenter)

    def _draw_boll(self, painter, g, offset, n):
        """布林带：半透明填充 + 上/中/下三条轨道。"""
        upper, mid, lower = self._ind["boll"]
        pts_u, pts_d = [], []
        for i in range(n):
            idx = offset + i
            u = upper[idx] if idx < len(upper) else None
            d = lower[idx] if idx < len(lower) else None
            if u is None or d is None:
                continue
            x = g["bar_x0"] + g["step"] * (i + 0.5)
            pts_u.append(QPointF(x, self._y_price(g, u)))
            pts_d.append(QPointF(x, self._y_price(g, d)))
        if len(pts_u) > 1:
            path = QPainterPath()
            path.moveTo(pts_u[0])
            for p in pts_u[1:]:
                path.lineTo(p)
            for p in reversed(pts_d):
                path.lineTo(p)
            path.closeSubpath()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(74, 144, 226, 26))
            painter.drawPath(path)
        self._draw_series_line(painter, g, upper, offset, BOLL_BAND)
        self._draw_series_line(painter, g, lower, offset, BOLL_BAND)
        self._draw_series_line(painter, g, mid, offset, BOLL_MID, dashed=True)

    def _draw_series_line(self, painter, g, series, offset, color,
                          dashed=False, width=1.2):
        pen = QPen(QColor(color), width,
                   Qt.DashLine if dashed else Qt.SolidLine)
        painter.setPen(pen)
        prev = None
        for i in range(len(g["bars"])):
            idx = offset + i
            v = series[idx] if idx < len(series) else None
            if v is None:
                prev = None
                continue
            x = g["bar_x0"] + g["step"] * (i + 0.5)
            y = self._y_price(g, v)
            if prev is not None:
                painter.drawLine(int(prev[0]), int(prev[1]), int(x), int(y))
            prev = (x, y)

    def _draw_macd(self, painter, g, dif, dea, hist, offset, body_w):
        mr = g["macd"]
        end = offset + len(g["bars"])
        vals = [v for v in hist[offset:end] if v is not None] + \
               [v for v in dif[offset:end] if v is not None] + \
               [v for v in dea[offset:end] if v is not None]
        if not vals:
            return
        mx = max(max(vals), abs(min(vals))) or 1.0
        half = mr.height() / 2 * 0.88
        zero = mr.top() + mr.height() / 2

        def y_val(v):
            return zero - half * v / mx

        for i in range(len(g["bars"])):
            idx = offset + i
            v = hist[idx] if idx < len(hist) else None
            if v is None:
                continue
            x = g["bar_x0"] + g["step"] * (i + 0.5)
            y = y_val(v)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(C_UP if v >= 0 else C_DOWN))
            painter.drawRect(QRectF(x - body_w / 2, min(y, zero),
                                    body_w, abs(y - zero) or 1.0))
        for series, color in ((dif, DIF_COLOR), (dea, DEA_COLOR)):
            pen = QPen(QColor(color), 1)
            painter.setPen(pen)
            prev = None
            for i in range(len(g["bars"])):
                idx = offset + i
                v = series[idx] if idx < len(series) else None
                if v is None:
                    prev = None
                    continue
                x = g["bar_x0"] + g["step"] * (i + 0.5)
                y = y_val(v)
                if prev is not None:
                    painter.drawLine(int(prev[0]), int(prev[1]),
                                     int(x), int(y))
                prev = (x, y)

    def _draw_macd_labels(self, painter, g, dif, dea, hist,
                          offset, hover_i, n):
        idx = offset + (hover_i if hover_i is not None else n - 1)
        mr = g["macd"]
        px = self._axis_px(9)
        th = px + 6
        # 从标题右侧留足空白，避免与 "MACD(fast,slow,signal)" 挤在一起
        x, y = g["x0"] + 132, mr.top() + 1
        step = 92 * self.font_scale
        for name, series, color in (("DIF", dif, DIF_COLOR),
                                    ("DEA", dea, DEA_COLOR),
                                    ("MACD", hist, C_UP)):
            v = series[idx] if idx < len(series) else None
            self._draw_pair(painter, x, y, step, th, name,
                            f"{v:.3f}" if v is not None else "--",
                            self._dim_color(color), color, px)
            x += step

    def _axis_date(self, candle):
        """时间轴标签：一律带年份，跨年/跨月一眼可辨。"""
        d = datetime.fromtimestamp(candle.ts)
        if self.interval in ("1M", "month"):
            return d.strftime("%Y-%m")
        if self.interval in ("1y", "1year"):
            return d.strftime("%Y")
        return d.strftime("%Y-%m-%d")

    def _axis_full(self, candle):
        """十字光标气泡：分钟线补上具体时刻。"""
        d = datetime.fromtimestamp(candle.ts)
        if self.interval in ("1M", "month", "1y", "1year"):
            return self._axis_date(candle)
        if self.interval in ("1m", "5m", "15m", "30m", "1h", "4h",
                             "m1", "m5", "m15", "m30", "m60"):
            return d.strftime("%Y-%m-%d %H:%M")
        return d.strftime("%Y-%m-%d")

    def _time_axis_labels(self, g, view_x=None):
        """计算时间轴标签矩形：自适应抽稀，保证完整落在控件内。

        返回 [(rect, text, tick_x)]，绘制与回归测试共用同一套几何。
        """
        bars = g["bars"]
        if view_x is None:
            view_x = g["x0"] + g["w"]
        axis_top = g["bottom"] + 1
        axis_h = max(6, self.height() - axis_top - 2)
        # 标签宽度按「实际字形宽度」算：字号放大后日期是 "2026-10-27"，
        # 旧的固定 94px 会把后一个标签压到前一个上面（看起来像日期连成串）。
        px = self._axis_px(9)
        fm = QFontMetrics(self._font(px, numeric=True))
        sample = self._axis_date(bars[-1]) if bars else "2026-01-01"
        label_w = max(48, fm.horizontalAdvance(sample) + 16)
        # 抽稀步长按「每根 K 线实际像素宽」算：否则 260 根挤在 670px 时
        # 两个日期会贴在一起（"2026-10-272026-10-29"）。
        step = max(0.2, float(g.get("step") or 1.0))
        stride = max(1, int(math.ceil(label_w / step)))
        out = []
        last_right = -1e9
        for i in range(0, len(bars), stride):
            x = g["bar_x0"] + g["step"] * (i + 0.5)
            left = max(g["x0"], min(x - label_w / 2, view_x - label_w))
            width = max(20, min(label_w, self.width() - left - 2))
            rect = QRectF(left, axis_top, width, axis_h)
            # 兜底去重：字号放大后实际字宽可能略超估算，宁可少画一个
            # 日期，也不让两个日期贴成 "2026-10-272026-10-29"。
            if rect.left() < last_right - 1:
                continue
            out.append((rect, self._axis_date(bars[i]), x))
            last_right = rect.right()
        return out

    def _draw_time_axis(self, painter, g, hover_i, view_x):
        """独立时间轴：标签带年份、完整居中，不越界不重叠。"""
        bars = g["bars"]
        axis_top = g["bottom"] + 1
        axis_h = max(6, self.height() - axis_top - 2)
        painter.setFont(self._font(self._axis_px(9), numeric=True))
        for rect, text, tick_x in self._time_axis_labels(g, view_x):
            painter.setPen(QPen(QColor(C_GRID), 1))
            painter.drawLine(int(tick_x), int(axis_top),
                             int(tick_x), int(axis_top + 3))
            self._text(painter, rect.x(), rect.y(), rect.width(),
                       rect.height(), text, C_TEXT_DIM, self._axis_px(9),
                       numeric=True, align=Qt.AlignCenter)
        # 十字光标对应的时间气泡（覆盖在标签之上，始终完整显示）
        if hover_i is not None and 0 <= hover_i < len(bars):
            x = g["bar_x0"] + g["step"] * (hover_i + 0.5)
            bw = 138
            left = max(g["x0"], min(x - bw / 2, view_x - bw))
            bw = max(20, min(bw, self.width() - left - 2))
            painter.fillRect(QRectF(left, axis_top + 1, bw, axis_h - 2),
                             QColor(C_BG_HOVER))
            self._text(painter, left, axis_top + 1, bw, axis_h - 2,
                       self._axis_full(bars[hover_i]), C_TEXT_MAIN,
                       self._axis_px(10), numeric=True,
                       align=Qt.AlignCenter)

    @staticmethod
    def _short_vol(v: float) -> str:
        if v >= 1e8:
            return f"{v / 1e8:.1f}亿"
        if v >= 1e4:
            return f"{v / 1e4:.1f}万"
        return f"{v:.0f}"

    def _hover_index(self, g):
        if self._mouse_pos is None or not g["bars"]:
            return None
        if not (g["price"].top() <= self._mouse_pos.y() <= g["bottom"]):
            return None
        return self._x_index(g, self._mouse_pos.x())


class ChartView(QWidget):
    """完整图表页：信息头 + 周期 / 指标 / 画线 分区工具栏 + K 线图。"""

    back_requested = Signal()
    detail_requested = Signal()        # 图表页「详情」：主窗口弹品种资料详情

    TOOLS = [("光标", "none"), ("直线", "trend"),
             ("水平线", "hline"), ("删除", "del")]
    # 主图指标 / 副图指标分组，便于分区排版
    MAIN_INDICATORS = [("MA", "show_ma"), ("EMA", "show_ema"),
                       ("BOLL", "show_boll")]
    SUB_INDICATORS = [("VOL", "show_vol"), ("MACD", "show_macd")]
    INDICATORS = MAIN_INDICATORS + SUB_INDICATORS

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C_BG_BASE};")
        self._cfg = config
        self._symbol = ""
        self._interval = ""
        self._worker: KlineWorker | None = None
        self._hist_worker: HistoryWorker | None = None
        self._show_all = False
        self._last_ticker = None
        self._drawings: dict = {}

        self.chart = CandleChart()
        # 周期切换预加载线程（打开图表后把其它周期悄悄落盘，切过去秒开）
        self._prefetch_threads = []
        self.apply_appearance()
        self._apply_indicator_params()
        for _label, key in self.INDICATORS:
            setattr(self.chart, key,
                    bool(self._cfg.get(key)) if self._cfg else True)
        # 智能标注：趋势 / 压力 / 支撑 / ATH-ATL / 局部高低 各自独立持久化
        for key, default in (("show_trend", False), ("show_res", False),
                             ("show_sup", False), ("show_extremes", True),
                             ("show_pivots", True)):
            setattr(self.chart, key,
                    bool(self._cfg.get(key, default)) if self._cfg
                    else default)
        self.chart.tool_finished.connect(lambda: self._set_tool("none"))
        self.chart.need_history.connect(self._on_need_history)
        self.chart.user_view_change.connect(self._on_user_view_change)
        # ---- 跨图表视口状态 ----
        # 进入新图表（换品种 / 换周期）时恢复上一次的缩放级别与横向位置；
        # 滚轮或拖动变化后节流 1 秒写回配置，重启程序也保留。
        self._view_state = None
        self._view_save_timer = QTimer(self)
        self._view_save_timer.setSingleShot(True)
        self._view_save_timer.setInterval(1000)
        self._view_save_timer.timeout.connect(self._remember_view)
        self.chart.view_changed.connect(self._on_view_changed)
        if self._cfg is not None:
            try:
                vc = float(self._cfg.get("chart_view_count") or 0.0)
                if vc >= self.chart._min_bars:
                    self._view_state = {
                        "view_count": vc,
                        "pan": float(self._cfg.get("chart_view_pan") or 0.0)}
            except (TypeError, ValueError, AttributeError):
                self._view_state = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(7)

        # ---- 信息头 ----
        header = QFrame()
        header.setStyleSheet(panel_qss())
        head = QHBoxLayout(header)
        head.setContentsMargins(10, 8, 14, 8)
        head.setSpacing(10)
        self.btn_back = QPushButton("返回列表")
        self.btn_back.setFixedHeight(44)
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.setStyleSheet(icon_btn_qss(12))
        self.btn_back.clicked.connect(self._on_back)
        head.addWidget(self.btn_back)

        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"QFrame {{ background:{C_BORDER}; }}")
        head.addWidget(sep)

        info = QVBoxLayout()
        info.setSpacing(0)
        line1 = QHBoxLayout()
        line1.setSpacing(6)
        self.lbl_symbol = QLabel("--")
        self.lbl_symbol.setStyleSheet(
            f"color:{C_TEXT_MAIN}; font-size:16px; font-weight:700;"
            f" font-family:'IBM Plex Mono SemiBold', 'Consolas', monospace;")
        line1.addWidget(self.lbl_symbol)
        self.lbl_market = QLabel("")
        self.lbl_market.setStyleSheet(
            f"color:{C_ACCENT}; font-size:10px; border:1px solid {C_ACCENT};"
            f" border-radius:4px; padding:0px 5px;")
        line1.addWidget(self.lbl_market)
        line1.addStretch(1)
        info.addLayout(line1)
        self.lbl_name = QLabel("")
        self.lbl_name.setStyleSheet(label_qss(11, C_TEXT_DIM))
        info.addWidget(self.lbl_name)
        head.addLayout(info, 1)

        quote = QVBoxLayout()
        quote.setSpacing(0)
        quote.setAlignment(Qt.AlignRight)
        self.lbl_price = QLabel("--")
        self.lbl_price.setAlignment(Qt.AlignRight)
        self.lbl_price.setStyleSheet(
            f"color:{C_TEXT_MAIN}; font-size:19px; font-weight:700;"
            f" font-family:'IBM Plex Mono SemiBold', 'Consolas', monospace;")
        self.lbl_change = QLabel("--")
        self.lbl_change.setAlignment(Qt.AlignRight)
        self.lbl_change.setStyleSheet(label_qss(12, C_TEXT_DIM, True, True))
        quote.addWidget(self.lbl_price)
        quote.addWidget(self.lbl_change)
        head.addLayout(quote)

        # ---- 详情：当前品种的完整资料（市值 / 市盈率 / 高低 / 成交额…）----
        self.btn_detail = QPushButton("ⓘ 详情")
        self.btn_detail.setFixedHeight(44)
        self.btn_detail.setCursor(Qt.PointingHandCursor)
        self.btn_detail.setFocusPolicy(Qt.NoFocus)
        self.btn_detail.setToolTip("查看该品种的完整资料：市值、市盈率、"
                                   "24h 高低、振幅、成交额等")
        self.btn_detail.setStyleSheet(tool_qss(C_ACCENT))
        self.btn_detail.clicked.connect(self.detail_requested.emit)
        head.addWidget(self.btn_detail)
        layout.addWidget(header)

        # ---- 工具栏：两行分区 ----
        toolbar = QFrame()
        toolbar.setStyleSheet(panel_qss())
        tb = QVBoxLayout(toolbar)
        tb.setContentsMargins(10, 5, 10, 5)
        tb.setSpacing(4)

        row1 = QHBoxLayout()
        row1.setSpacing(4)
        row1.addWidget(self._caption("周期"))
        self.intervals_bar = QHBoxLayout()
        self.intervals_bar.setSpacing(2)
        self._interval_buttons = {}
        row1.addLayout(self.intervals_bar)
        # 周期 11 个按钮独占一行：和主图/副图挤在一起时按钮会被压到比文字
        # 还窄，Qt 直接裁掉文字（看起来是一排空框），所以分组挪到下一行。
        row1.addStretch(1)
        tb.addLayout(row1)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"QFrame {{ background:{C_BORDER}; }}")
        tb.addWidget(line)

        row_ind = QHBoxLayout()
        row_ind.setSpacing(3)
        row_ind.addWidget(self._caption("主图"))
        self._indicator_buttons = {}
        self._main_bar = QHBoxLayout()
        self._main_bar.setSpacing(3)
        for label, key in self.MAIN_INDICATORS:
            self._main_bar.addWidget(self._make_indicator(label, key))
        row_ind.addLayout(self._main_bar)
        row_ind.addSpacing(8)
        row_ind.addWidget(self._vsep())
        row_ind.addSpacing(8)
        row_ind.addWidget(self._caption("副图"))
        self._sub_bar = QHBoxLayout()
        self._sub_bar.setSpacing(3)
        for label, key in self.SUB_INDICATORS:
            self._sub_bar.addWidget(self._make_indicator(label, key))
        row_ind.addLayout(self._sub_bar)
        row_ind.addSpacing(8)
        row_ind.addWidget(self._vsep())
        row_ind.addSpacing(8)
        # 指标参数：MA / EMA 天数与启停、BOLL / MACD 参数、按周期分别设置
        self.btn_indicator_settings = QPushButton("⚙ 参数")
        self.btn_indicator_settings.setFixedHeight(44)
        self.btn_indicator_settings.setMinimumWidth(88)
        self.btn_indicator_settings.setCursor(Qt.PointingHandCursor)
        self.btn_indicator_settings.setFocusPolicy(Qt.NoFocus)
        self.btn_indicator_settings.setToolTip(
            "设置 MA / EMA 均线天数、启停与周期作用范围，"
            "以及 BOLL / MACD 参数")
        self.btn_indicator_settings.setStyleSheet(tool_qss(C_ACCENT))
        self.btn_indicator_settings.clicked.connect(
            self._open_indicator_sheet)
        row_ind.addWidget(self.btn_indicator_settings)
        row_ind.addStretch(1)
        tb.addLayout(row_ind)

        row2 = QHBoxLayout()
        row2.setSpacing(3)
        row2.addWidget(self._caption("画线"))
        self._tool_buttons = {}
        for label, key in self.TOOLS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setToolTip({
                "none": "选中线条后可拖动端点/整条线调整，Delete 删除，ESC 取消",
                "trend": "点两次画直线（画完自动回光标）",
                "hline": "单击画水平线（画完自动回光标）",
                "del": "点击线条删除",
            }[key])
            btn.setStyleSheet(tool_qss())
            btn.clicked.connect(lambda checked=False, k=key:
                                self._set_tool(k))
            row2.addWidget(btn)
            self._tool_buttons[key] = btn
        btn_clear = QPushButton("清空")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setFocusPolicy(Qt.NoFocus)
        btn_clear.setToolTip("清空当前标的的全部画线")
        btn_clear.setStyleSheet(tool_qss(C_UP))
        btn_clear.clicked.connect(self.chart.clear_drawings)
        row2.addWidget(btn_clear)
        btn_reset = QPushButton("最新")
        btn_reset.setCursor(Qt.PointingHandCursor)
        btn_reset.setFocusPolicy(Qt.NoFocus)
        btn_reset.setToolTip("视野复位：回到最新一根并恢复默认缩放")
        btn_reset.setStyleSheet(tool_qss(C_BLUE))
        btn_reset.clicked.connect(self._on_reset_view)
        row2.addWidget(btn_reset)
        btn_history = QPushButton("全部历史")
        btn_history.setCursor(Qt.PointingHandCursor)
        btn_history.setFocusPolicy(Qt.NoFocus)
        btn_history.setToolTip(
            "一屏铺开该品种整个生命周期，并自动回溯到上市首根 K 线")
        btn_history.setStyleSheet(tool_qss(C_ACCENT))
        btn_history.clicked.connect(self._show_all_history)
        row2.addWidget(btn_history)

        row2.addStretch(1)
        hint = QLabel("滚轮缩放(可缩到全部历史) · 左键拖动整图平移"
                      " · Delete 删除 · 双击空白复位")
        hint.setStyleSheet(label_qss(10, C_TEXT_DIM))
        row2.addWidget(hint)
        tb.addLayout(row2)

        # ---- 第三行：趋势 / 压力 / 支撑 / ATH-ATL / 局部高低 各自独立 ----
        row3 = QHBoxLayout()
        row3.setSpacing(3)
        row3.addWidget(self._caption("智能"))
        self._smart_buttons = {}
        for label, key, tip, accent in (
                ("趋势线", "show_trend",
                 "收盘价线性回归趋势线（TREND UP / DN）", C_ACCENT),
                ("压力位", "show_res",
                 "枢轴高点聚类压力位 R1/R2，在对应 K 线处标价格", C_UP),
                ("支撑位", "show_sup",
                 "枢轴低点聚类支撑位 S1/S2，在对应 K 线处标价格", C_DOWN),
                ("ATH / ATL", "show_extremes",
                 "史高 ATH / 史低 ATL，在对应 K 线处标价格；\n"
                 "需回溯到上市首根后才显示（未回溯完时极值只是局部点）",
                 C_BLUE),
                ("局部高低", "show_pivots",
                 "一屏各只标一个：可见区间最高 LH / 最低 LL；"
                 "真实史高史低在屏内时让位给 ATH/ATL", C_PURPLE)):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(getattr(self.chart, key))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setToolTip(tip)
            btn.setStyleSheet(tool_qss(accent))
            btn.clicked.connect(lambda checked=False, k=key:
                                self._toggle_smart(k, checked))
            row3.addWidget(btn)
            self._smart_buttons[key] = btn
        row3.addStretch(1)
        smart_hint = QLabel("开关互不干扰 · 只在对应 K 线处标价格，不画水平线")
        smart_hint.setStyleSheet(label_qss(10, C_TEXT_DIM))
        row3.addWidget(smart_hint)
        tb.addLayout(row3)

        # ---- 工具条收纳：默认只留一条 28px 的细条，不占空间、不挡 K 线 ----
        self.tools_head = QFrame()
        self.tools_head.setObjectName("toolsHead")
        self.tools_head.setStyleSheet(
            f"#toolsHead {{ background:{C_BG_PANEL}; border:1px solid {C_BORDER};"
            f" border-radius:8px; }}")
        hh = QHBoxLayout(self.tools_head)
        hh.setContentsMargins(8, 3, 8, 3)
        hh.setSpacing(8)
        self.btn_tools = QPushButton("⚙ 周期 · 指标 · 画线")
        self.btn_tools.setCheckable(True)
        self.btn_tools.setFixedHeight(44)
        self.btn_tools.setCursor(Qt.PointingHandCursor)
        self.btn_tools.setFocusPolicy(Qt.NoFocus)
        self.btn_tools.setToolTip("展开 / 收起周期、指标、画线与智能标注工具条")
        self.btn_tools.setStyleSheet(tool_qss(C_ACCENT))
        self.btn_tools.toggled.connect(self._toggle_tools)
        hh.addWidget(self.btn_tools)
        self.lbl_interval_now = QLabel("--")
        self.lbl_interval_now.setStyleSheet(label_qss(10, C_TEXT_SUB, True, True))
        hh.addWidget(self.lbl_interval_now)
        # 阶段 6：触屏缩放按钮（手机没有滚轮），44×40 触控目标
        self.btn_zoom_in = QPushButton("＋")
        self.btn_zoom_in.setFixedSize(44, 44)
        self.btn_zoom_in.setCursor(Qt.PointingHandCursor)
        self.btn_zoom_in.setFocusPolicy(Qt.NoFocus)
        self.btn_zoom_in.setToolTip("放大 K 线（以视口中心为锚点）")
        self.btn_zoom_in.setStyleSheet(tool_qss(C_ACCENT))
        self.btn_zoom_in.clicked.connect(lambda: self.chart.zoom_by(True))
        hh.addWidget(self.btn_zoom_in)
        self.btn_zoom_out = QPushButton("－")
        self.btn_zoom_out.setFixedSize(44, 44)
        self.btn_zoom_out.setCursor(Qt.PointingHandCursor)
        self.btn_zoom_out.setFocusPolicy(Qt.NoFocus)
        self.btn_zoom_out.setToolTip("缩小 K 线（必要时自动请求更早历史）")
        self.btn_zoom_out.setStyleSheet(tool_qss(C_ACCENT))
        self.btn_zoom_out.clicked.connect(lambda: self.chart.zoom_by(False))
        hh.addWidget(self.btn_zoom_out)
        hh.addStretch(1)
        self.btn_quick_latest = QPushButton("最新")
        self.btn_quick_latest.setFixedHeight(44)
        self.btn_quick_latest.setCursor(Qt.PointingHandCursor)
        self.btn_quick_latest.setFocusPolicy(Qt.NoFocus)
        self.btn_quick_latest.setToolTip("视野复位：回到最新一根并恢复默认缩放")
        self.btn_quick_latest.setStyleSheet(tool_qss(C_BLUE))
        self.btn_quick_latest.clicked.connect(self._on_reset_view)
        hh.addWidget(self.btn_quick_latest)
        self.btn_quick_history = QPushButton("全部历史")
        self.btn_quick_history.setFixedHeight(44)
        self.btn_quick_history.setCursor(Qt.PointingHandCursor)
        self.btn_quick_history.setFocusPolicy(Qt.NoFocus)
        self.btn_quick_history.setToolTip("一屏铺开该品种整个生命周期")
        self.btn_quick_history.setStyleSheet(tool_qss(C_ACCENT))
        self.btn_quick_history.clicked.connect(self._show_all_history)
        hh.addWidget(self.btn_quick_history)
        layout.addWidget(self.tools_head)

        self.tools_panel = toolbar
        # ---- 悬停自动展开 / 离开自动收纳 ----
        # 鼠标扫过细条（或停在展开面板上）立即展开；离开两块区域
        # 约 300ms 后自动收起。按钮点击 = 手动固定展开（只在本次停留有效）。
        self._tools_pinned = False
        self._tools_hovered = False
        self._tools_leave_timer = QTimer(self)
        self._tools_leave_timer.setSingleShot(True)
        self._tools_leave_timer.setInterval(300)
        self._tools_leave_timer.timeout.connect(self._on_tools_leave_timeout)
        # 坐标轮询兜底：顶层悬浮窗（看板娘 / 气泡）、快速划过、以及
        # 鼠标已经在工具条上才切换到图表页等情况，都会吞掉 Enter 事件，
        # 只看事件时表现为「鼠标移上去完全没反应」。这里按真实光标坐标
        # 60ms 校对一次，事件通道仍负责即时响应。
        self._tools_hover_timer = QTimer(self)
        self._tools_hover_timer.setInterval(60)
        self._tools_hover_timer.timeout.connect(self._poll_tools_hover)
        for hover_widget in (self.tools_head, self.tools_panel):
            hover_widget.installEventFilter(self)
        # 旧版会把「固定展开」写进配置，重启后工具条一直摊开，
        # 悬停 / 离开看起来就彻底失效。统一从收纳状态开始。
        if self._cfg is not None:
            try:
                if self._cfg.get("chart_tools_open", False):
                    self._cfg.set("chart_tools_open", False)
                    self._cfg.save()
            except (AttributeError, OSError, TypeError):
                pass
        self.btn_tools.blockSignals(True)
        self.btn_tools.setChecked(False)
        self.btn_tools.blockSignals(False)
        self._tools_panel_shown = False
        self.tools_panel.setVisible(False)
        self._sync_tools_button()
        # 工具面板与 K 线不同图层：不加入布局、悬浮在图表上方。
        # 展开 / 收纳只改自己的可见性，图表区大小不变，
        # K 线不会被挤压重排（缩放 / 平移状态也完全不受影响）。
        self.tools_panel.setParent(self)
        self.tools_panel.raise_()
        apply_popup_shadow(self.tools_panel)

        # ---- 指标参数浮层：同样是独立图层，展开不挤压 K 线 ----
        self.indicator_sheet = IndicatorSettingsSheet(self._cfg, self)
        self.indicator_sheet.applied.connect(self._apply_indicator_params)
        self.indicator_sheet.hide()
        self._apply_indicator_params()   # 此时才有 sheet，同步一次周期标签

        # ---- 图表区 ----
        chart_frame = QFrame()
        chart_frame.setStyleSheet(panel_qss(6, C_BG_BASE))
        cf = QVBoxLayout(chart_frame)
        cf.setContentsMargins(1, 1, 1, 1)
        cf.addWidget(self.chart, 1)
        layout.addWidget(chart_frame, 1)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(label_qss(11, C_UP))
        self.lbl_error.hide()
        layout.addWidget(self.lbl_error)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._load)
        # 历史回溯「泵」：全览模式下持续分页，直到数据源确实没有更早 K 线。
        # 定时器比 loaded 信号里递归更稳，不会被「worker 仍未结束」掐断。
        self._hist_timer = QTimer(self)
        self._hist_timer.setInterval(160)
        self._hist_timer.timeout.connect(self._load_history)

    # ---- 小组件 ----
    @staticmethod
    def _caption(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(label_qss(10, C_TEXT_DIM, True))
        lbl.setFixedWidth(30)
        return lbl

    @staticmethod
    def _vsep() -> QFrame:
        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"QFrame {{ background:{C_BORDER}; }}")
        return sep

    # ---- 工具条收纳 ----
    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, "_tools_hover_timer"):
            self._tools_hover_timer.start()
        self._position_tools()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_tools()

    def _position_tools(self):
        """工具面板独立图层：对齐细条正下方悬浮，宽度铺满、高度自适应。

        因为不参与布局，必须在显示 / 窗口尺寸变化时手动摆位。
        """
        if not hasattr(self, "tools_panel"):
            return
        margin = 8
        head_geo = self.tools_head.geometry()
        y = head_geo.bottom() + 3 if head_geo.height() > 0 else 44
        w = max(320, self.width() - 2 * margin)
        h = max(1, self.tools_panel.sizeHint().height())
        self.tools_panel.resize(w, h)
        self.tools_panel.move(margin, y)
        self.tools_panel.raise_()
        if hasattr(self, "indicator_sheet"):
            sw = min(440, max(320, self.width() - 16))
            sh = min(620, max(320, self.height() - 16))
            self.indicator_sheet.resize(sw, sh)
            self.indicator_sheet.move((self.width() - sw) // 2,
                                      max(8, (self.height() - sh) // 2))
            if self.indicator_sheet.isVisible():
                self.indicator_sheet.raise_()

    def hideEvent(self, event):
        if hasattr(self, "indicator_sheet") and \
                self.indicator_sheet.isVisible():
            self.indicator_sheet.hide()
        if hasattr(self, "_tools_hover_timer"):
            self._tools_hover_timer.stop()
            self._tools_leave_timer.stop()
            self._tools_hovered = False
            # 离开图表页时清掉手动固定，避免下次进来卡在展开状态
            if self._tools_pinned:
                self._set_tools_pinned(False)
            self._apply_tools_visible()
            self._sync_tools_button()
        super().hideEvent(event)

    def eventFilter(self, obj, event):
        """细条 / 展开面板的悬停事件：扫过展开，离开延迟收纳。"""
        if obj in (self.tools_head, self.tools_panel):
            if event.type() == QEvent.Enter:
                self._set_tools_hover(True)
            elif event.type() == QEvent.Leave:
                self._set_tools_hover(False)
        return super().eventFilter(obj, event)

    def _set_tools_hover(self, hovered: bool):
        if hovered:
            self._tools_leave_timer.stop()
            if not self._tools_hovered:
                self._tools_hovered = True
                self._apply_tools_visible()
                self._sync_tools_button()
        else:
            self._tools_hovered = False
            # 缝隙 / 两块区域间穿行时不立刻收，交给延迟确认
            if not self._tools_leave_timer.isActive():
                self._tools_leave_timer.start()

    def _poll_tools_hover(self):
        """按真实光标坐标兜底：顶层悬浮窗吞掉 Enter 时也能自动展开。"""
        if not self.isVisible() or not self.tools_head.isVisible():
            return
        pos = QCursor.pos()
        inside = False
        for hw in (self.tools_head, self.tools_panel):
            if not hw.isVisible():
                continue
            r = QRect(hw.mapToGlobal(QPoint(0, 0)), hw.size())
            if r.adjusted(-4, -4, 4, 4).contains(pos):
                inside = True
                break
        if inside:
            if not self._tools_hovered:
                self._set_tools_hover(True)
            elif self._tools_leave_timer.isActive():
                self._tools_leave_timer.stop()
        elif self._tools_hovered:
            self._set_tools_hover(False)

    def _on_tools_leave_timeout(self):
        if self._tools_hovered:
            return
        # 到点再确认一次鼠标真的不在两块区域内（快速划回时别收）
        for hover_widget in (self.tools_head, self.tools_panel):
            if hover_widget.isVisible() and hover_widget.underMouse():
                self._set_tools_hover(True)
                return
        # 鼠标确实离开了：手动固定也随这次离开放开，保证「移开即收纳」
        if self._tools_pinned:
            self._set_tools_pinned(False)
        self._apply_tools_visible()
        self._sync_tools_button()

    def _apply_tools_visible(self):
        """面板可见 = 用户固定展开 或 鼠标正停在工具条上。

        用显式标志判断而不是 isVisible()：图表页在 QStackedWidget 里
        没轮到它时 isVisible() 恒为 False，会导致「想收起却没真正收」。
        """
        if not hasattr(self, "tools_panel"):
            return
        want = bool(self._tools_pinned or self._tools_hovered)
        if getattr(self, "_tools_panel_shown", None) == want:
            return
        self._tools_panel_shown = want
        self.tools_panel.setVisible(want)
        if want:
            self._position_tools()      # 悬浮层：显示时确保摆位正确

    def _sync_tools_button(self):
        """按钮文字随固定 / 悬停状态变化。"""
        if not hasattr(self, "btn_tools"):
            return
        if self._tools_pinned:
            text = "📌 工具条已固定"
        elif self._tools_hovered:
            text = "⚙ 工具条已展开"
        else:
            text = "⚙ 周期 · 指标 · 画线"
        self.btn_tools.setText(text)
        self.btn_tools.setToolTip(
            "鼠标移到这一行会自动展开，移开自动收纳；"
            "点一下可临时固定展开，鼠标离开后自动解除")

    def _set_tools_pinned(self, pinned: bool):
        self._tools_pinned = bool(pinned)
        if hasattr(self, "btn_tools"):
            self.btn_tools.blockSignals(True)
            self.btn_tools.setChecked(self._tools_pinned)
            self.btn_tools.blockSignals(False)
        if self._cfg is not None:
            try:
                self._cfg.set("chart_tools_open", self._tools_pinned)
                self._cfg.save()
            except (AttributeError, OSError, TypeError):
                pass

    def _toggle_tools(self, checked: bool):
        self._set_tools_pinned(bool(checked))
        self._apply_tools_visible()
        self._sync_tools_button()

    def _make_indicator(self, label: str, key: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setChecked(getattr(self.chart, key))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setStyleSheet(toggle_qss())
        btn.clicked.connect(lambda checked=False, k=key:
                            self._toggle_indicator(k))
        self._indicator_buttons[key] = btn
        return btn

    # ---- 指标参数（天数 / 周期作用域）----
    def _apply_indicator_params(self):
        """从配置读取「当前周期最终生效」的参数并应用到 K 线。

        切周期、设置页保存、参数面板应用后都会走这里；图表已有 K 线时
        立即按新天数重算，不需要重新联网拉数据。
        """
        params = indicator_params.params_for(self._cfg, self._interval)
        self.chart.set_indicator_params(params)
        if hasattr(self, "indicator_sheet"):
            try:
                labels = dict((k, lb) for lb, k in
                              intervals_for(self._symbol))
            except Exception:
                labels = {}
            self.indicator_sheet.set_interval(
                self._interval, labels.get(self._interval, self._interval))
        self.chart.update()

    def _open_indicator_sheet(self):
        self._apply_indicator_params()
        self.indicator_sheet.open_sheet()
        self._position_tools()

    # ---- 指标开关 ----
    def _toggle_indicator(self, key: str):
        val = self._indicator_buttons[key].isChecked()
        setattr(self.chart, key, val)
        if self._cfg:
            self._cfg.set(key, val)
            self._cfg.save()
        self.chart.update()

    def sync_indicators(self):
        """设置对话框保存后，把配置同步到图表与工具栏按钮。"""
        if not self._cfg:
            return
        for _label, key in self.INDICATORS:
            val = bool(self._cfg.get(key))
            setattr(self.chart, key, val)
            self._indicator_buttons[key].setChecked(val)
        self._apply_indicator_params()
        self.chart.update()

    # ---- 打开/关闭 ----
    def candles_global_rect(self):
        """K 线实际占据的屏幕矩形（全局坐标）；给看板娘算遮挡比例用。"""
        try:
            return self.chart.candles_global_rect()
        except Exception:
            return QRectF()

    def apply_appearance(self):
        """应用外观设置：字号倍率 / 货币单位 / 最新 K 线动画速度。"""
        cfg = self._cfg
        scale = int((cfg.get("chart_font_scale") if cfg else 0) or 120)
        self.chart.set_font_scale(scale)
        self.chart.show_currency = bool(
            cfg.get("show_currency", True)) if cfg else True
        ms = int((cfg.get("live_interval_ms") if cfg else 0) or 900)
        self.chart.set_live_speed(ms)
        self.chart.unit_prefix = unit_of(self._symbol) if self._symbol else ""
        self.update()

    def _prefetch_intervals(self):
        """打开图表后，把该品种其它周期的 K 线在后台悄悄写入本地缓存。

        目的：切换周期时先命中缓存立即出图，再后台校验，消除"点一下卡一下"
        的停顿感。只补本地没有/过期的周期，已有数据零请求。
        """
        if not self._symbol or self._cfg is None:
            return
        if getattr(self, "_no_kline", False):
            return
        if not bool(self._cfg.get("prefetch_enabled", True)):
            return
        try:
            keys = [k for _, k in intervals_for(self._symbol)]
        except Exception:
            return
        queue = [(self._symbol, k) for k in keys
                 if k != self._interval and not kline_cache.is_fresh(
                     self._symbol, k)]
        if not queue:
            return
        try:
            from data.prefetch import PrefetchWorker
            worker = PrefetchWorker(self._cfg, self, ttl=None, gap_ms=140,
                                    delay_s=0, queue=queue)
        except Exception:
            return
        self._prefetch_threads.append(worker)

        def _done(*_a):
            try:
                worker.deleteLater()
            except RuntimeError:
                pass
            if worker in self._prefetch_threads:
                self._prefetch_threads.remove(worker)

        worker.finished.connect(_done)
        worker.start()

    def _on_view_changed(self):
        """用户滚轮 / 拖动后立刻记住视口，节流写盘。"""
        self._view_state = self.chart.view_state()
        self._view_save_timer.start()

    def _remember_view(self):
        """把当前缩放级别与位置持久化（重启仍保留）。

        还没打开过任何图表时不要写：否则启动阶段的默认 90 根会把配置里
        上次保存的缩放状态冲掉。
        """
        if not self._symbol:
            return
        state = self.chart.view_state()
        self._view_state = state
        if self._cfg is None:
            return
        try:
            self._cfg.set("chart_view_count", state["view_count"])
            self._cfg.set("chart_view_pan", state["pan"])
            self._cfg.save()
        except (AttributeError, OSError, TypeError):
            pass

    def _on_reset_view(self):
        """用户主动点「最新」才复位，并同步更新记住的视口。"""
        self.chart.reset_view()
        self._remember_view()

    def open(self, symbol: str, name: str = "", ticker=None):
        if self._symbol:
            self._drawings[self._symbol] = self.chart.get_drawings()
            # 换品种前先接住上一个图表的缩放与位置
            self._view_state = self.chart.view_state()
        self._symbol = symbol
        # 链上合约品种没有交易所 K 线：不请求、不轮询，但保留价格与资料
        self._no_kline = onchain.is_onchain(symbol)
        # 从链上页切回普通品种时恢复蜡烛绘制
        self.chart.set_onchain_view(None)
        self._onchain_code = ""
        # 货币单位跟着品种走（$ / ¥ / HK$）
        self.chart.unit_prefix = unit_of(symbol)
        self.chart.show_currency = bool(
            self._cfg.get("show_currency", True)) if self._cfg else True
        self.lbl_symbol.setText(
            onchain.short_address(onchain.address_of(symbol))
            if self._no_kline else symbol.split(":")[-1])
        self.lbl_name.setText(name or "实时行情 · K 线图表")
        self.lbl_market.setText(self._market_tag(symbol))
        self.lbl_price.setText("--")
        self.lbl_change.setText("--")
        self.chart.last_price = None      # 换品种：先清基准价，避免沿用上一个品种
        self._last_ticker = ticker
        if ticker is not None:
            self._update_ticker(ticker)
        self._set_tool("none")
        self.chart.set_drawings(self._drawings.get(symbol, []))
        self._stop_history_pump()
        # 不在换品种时复位：恢复上一次图表的缩放级别与横向位置
        self.chart.restore_view(self._view_state)
        self.chart.set_history_exhausted(False)
        self._show_all = False
        self._build_interval_bar()
        if self._no_kline:
            # 没有交易所 K 线：切到「真实报价采样走势 + 链上结构图」分支，
            # 不发必然失败的 K 线请求，也不画假蜡烛；价格、资料、收藏照常。
            self.chart.set_data([])
            self.chart.set_onchain_view({
                "series": onchain_history.series(symbol),
                "holders": [], "pools": [], "source": onchain.SOURCE,
            })
            self.chart.set_status("链上真实报价走势 · 非交易所 K 线")
            self._refresh_timer.stop()
            self.lbl_name.setText(name or "链上合约品种 · 真实报价走势")
            self.lbl_market.setText("链上合约")
            self.lbl_price.setText("--")
            self.lbl_change.setText("—")
            self.lbl_change.setStyleSheet(label_qss(12, C_TEXT_DIM, True, True))
            self.lbl_error.hide()
            return
        if not intervals_for(symbol):
            self.chart.set_data([])
            self.chart.set_status("该市场暂无K线数据源，仅支持列表行情")
            self._refresh_timer.stop()
            return
        # 恢复上一次查看的周期；该品种没有这个周期（如股票没有 15m）才回默认
        self._set_interval(self._remembered_interval(symbol))
        # 首屏出来后再预热其它周期，避免和首屏请求抢带宽
        QTimer.singleShot(1500, self._prefetch_intervals)

    @staticmethod
    def _market_tag(symbol: str) -> str:
        if symbol.startswith(("SH:", "SZ:")):
            return "A股"
        if symbol.startswith("HK:"):
            return "港股"
        if symbol.startswith("US:"):
            return "美股"
        return "加密货币"

    def close_chart(self):
        if self._symbol:
            self._drawings[self._symbol] = self.chart.get_drawings()
        self._remember_view()      # 离开图表时记下缩放与位置
        self._refresh_timer.stop()
        self._stop_history_pump()

    def update_ticker(self, ticker):
        if self.isVisible() and ticker is not None \
                and ticker.symbol == self._symbol \
                and not getattr(self, "_no_kline", False):
            self._update_ticker(ticker)

    def show_onchain(self, symbol: str, meta: dict, q: dict):
        """链上合约品种：代币代码 + 真实链上价 + 来源，不画不存在的 K 线。"""
        if symbol != self._symbol:
            return
        meta = meta or {}
        code = (meta.get("code") or "").upper() or \
            onchain.short_address(onchain.address_of(symbol))
        self._onchain_code = code
        self.lbl_symbol.setText(code)
        self.lbl_name.setText(meta.get("name") or code)
        self.lbl_market.setText(meta.get("chain") or "链上合约")
        self.update_onchain(q)

    def update_onchain(self, q: dict):
        """只展示真实链上 USD 报价；没有 24h 涨跌幅就显示「—」，不编造。"""
        if not getattr(self, "_no_kline", False):
            return
        q = q or {}
        # 真实采样走势 + 链上结构数据（持有地址占比 / 池类型分布）
        self.chart.set_onchain_view({
            "series": q.get("series") or onchain_history.series(self._symbol),
            "holders": q.get("top_holders") or [],
            "pools": q.get("pool_types") or [],
            "market_count": q.get("market_count"),
            "source": q.get("source") or onchain.SOURCE,
        })
        p = q.get("price")
        ts = q.get("ts")
        when = (datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                if ts else "—")
        src = q.get("source") or "链上报价源"
        liq = q.get("liquidity")
        tip = [f"来源：{src}", f"取数时间：{when}",
               f"链上流动性：${liq:,.0f}" if liq is not None
               else "链上流动性：—",
               "无交易所 K 线；图表为本设备采集的真实报价走势",
               "无 24h 涨跌幅数据（数据源不提供）"]
        if p is None or p <= 0:
            self.lbl_price.setText("--")
            self.lbl_change.setText("—")
            self.lbl_change.setStyleSheet(
                label_qss(12, C_TEXT_DIM, True, True))
            self.lbl_price.setToolTip("\n".join(tip) + "\n暂无公开链上报价")
            return
        self.lbl_price.setText("$" + format_price(float(p)))
        self.lbl_price.setStyleSheet(
            f"color:{C_TEXT_MAIN}; font-size:19px; font-weight:700;"
            f" font-family:'IBM Plex Mono SemiBold', 'Consolas', monospace;")
        self.lbl_change.setText("—")
        self.lbl_change.setStyleSheet(label_qss(12, C_TEXT_DIM, True, True))
        self.lbl_price.setToolTip("\n".join(tip))

    def on_live(self, symbol, price, change_pct):
        """秒级实时价（LiveFeed）：驱动最新 K 线连续伸缩 + 头部价格跳动。"""
        if symbol != self._symbol or not price:
            return
        t = self._last_ticker
        if t is not None and getattr(t, "symbol", "") == symbol:
            try:
                t.last_price = float(price)
                t.change_pct = float(change_pct or 0.0)
            except (TypeError, ValueError):
                return
            self._update_ticker(t)
        else:
            self.chart.last_price = float(price)
            self.chart.animate_last_price(float(price))

    def stop_prefetch(self):
        """退出前收尾周期预加载线程，避免 QThread 析构崩溃。"""
        for worker in list(self._prefetch_threads):
            try:
                worker.requestInterruption()
            except RuntimeError:
                pass
        for worker in list(self._prefetch_threads):
            try:
                worker.wait(3000)
            except RuntimeError:
                pass
        self._prefetch_threads.clear()

    def _update_ticker(self, t):
        # 光标涨跌幅要用「当前市场价」做基准，不能用最后一根 K 线收盘价
        self.chart.last_price = t.last_price
        # 最新 K 线随实时价平滑伸缩（涨 -> 蜡烛拔高，跌 -> 蜡烛缩短）
        self.chart.animate_last_price(t.last_price)
        color = C_UP if t.change_pct >= 0 else C_DOWN
        sign = "+" if t.change_pct >= 0 else ""
        price_text = with_unit(format_price(t.last_price), t.symbol,
                               self.chart.show_currency)
        self.lbl_price.setText(price_text)
        self.lbl_change.setText(f"{sign}{t.change_pct:.2f}%")
        self.lbl_change.setStyleSheet(label_qss(12, color, True, True))
        self.lbl_price.setStyleSheet(
            f"color:{color}; font-size:19px; font-weight:700;"
            f" font-family:'IBM Plex Mono SemiBold', 'Consolas', monospace;")

    # ---- 画图工具 ----
    def _set_tool(self, key: str):
        self.chart.set_tool(key)
        for k, btn in self._tool_buttons.items():
            btn.setChecked(k == key)

    def _toggle_smart(self, key: str, checked: bool):
        """五个智能标注开关各自独立切换，并持久化到配置。"""
        setattr(self.chart, key, bool(checked))
        if self._cfg:
            self._cfg.set(key, bool(checked))
            self._cfg.save()
        if key == "show_extremes" and checked:
            # 刚打开 ATH/ATL：后台把日线及以上回溯到上市首根，
            # 极值才配叫「历史最高/最低」，否则暂时不画（见 _draw_extremes）
            self._ensure_extremes_history()
        self.chart.update()

    def _toggle_auto(self, checked):
        """兼容旧接口：一次性打开/关闭趋势、压力、支撑三项。"""
        self.chart.show_auto = bool(checked)
        for key in ("show_trend", "show_res", "show_sup"):
            self._smart_buttons[key].setChecked(bool(checked))
        self.chart.update()

    def _toggle_extremes(self, checked):
        """兼容旧接口：显示/隐藏 ATH / ATL 标注。"""
        self.chart.show_extremes = bool(checked)
        self.chart.update()

    def sync_smart_buttons(self):
        """配置被外部修改后，把五个开关同步回按钮。"""
        for key, btn in self._smart_buttons.items():
            if self._cfg:
                val = bool(self._cfg.get(
                    key, key in ("show_extremes", "show_pivots")))
                setattr(self.chart, key, val)
            btn.setChecked(getattr(self.chart, key))
        self.chart.update()

    # ---- 周期切换 ----
    @staticmethod
    def _interval_qss(active: bool) -> str:
        """周期按钮专用样式：11 个按钮挤一行，内边距收到 6px 才不裁字。"""
        return segment_qss(active, pad_x=6)

    def _build_interval_bar(self):
        while self.intervals_bar.count():
            item = self.intervals_bar.takeAt(0)
            if item.widget():
                # 只从布局里移除还不够：deleteLater 要等事件循环，这期间旧
                # 按钮仍是工具条的子控件，会和新按钮叠在一起（看起来像被
                # 挤成竖条的空按钮）。先藏起来并断开父子关系。
                w = item.widget()
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self._interval_buttons.clear()
        if getattr(self, "_no_kline", False):
            return     # 链上币种没有 K 线周期，别造一排点了没反应的按钮
        for label, key in intervals_for(self._symbol):
            btn = QPushButton(label)
            btn.setCheckable(True)
            # 固定高度：选中态多 2px 边框会让个别按钮比同行矮/高一截
            btn.setFixedHeight(26)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setStyleSheet(self._interval_qss(False))
            btn.clicked.connect(
                lambda checked=False, k=key: self._set_interval(k))
            self.intervals_bar.addWidget(btn)
            self._interval_buttons[key] = btn

    def _remembered_interval(self, symbol: str) -> str:
        """上一次使用的周期；没存过 / 该品种不支持时回默认。"""
        fallback = default_interval(symbol)
        if self._cfg is None:
            return fallback
        try:
            saved = str(self._cfg.get("chart_interval") or "").strip()
        except Exception:
            return fallback
        if saved and saved in [k for _, k in intervals_for(symbol)]:
            return saved
        return fallback

    def _set_interval(self, key: str):
        self._interval = key
        self.chart.interval = key
        # 不同 K 线周期可以有不同的均线天数，切周期立即换用对应参数
        self._apply_indicator_params()
        # 记住这次选的周期，下次打开图表直接恢复
        if self._cfg is not None:
            try:
                self._cfg.set("chart_interval", key)
                self._cfg.save()
            except (AttributeError, OSError, TypeError):
                pass
        self._stop_history_pump()
        self.chart.set_history_exhausted(False)
        # 切周期同样保留视口，不再把用户刚缩好的 K 线拉回默认 90 根
        self.chart.restore_view(self._view_state or self.chart.view_state())
        self._show_all = False
        for k, btn in self._interval_buttons.items():
            checked = k == key
            btn.setChecked(checked)
            btn.setStyleSheet(self._interval_qss(checked))
        if hasattr(self, "lbl_interval_now"):
            labels = dict((k, lb) for lb, k in intervals_for(self._symbol))
            self.lbl_interval_now.setText(labels.get(key, key))
        self._refresh_timer.start(refresh_seconds(key) * 1000)
        # 有本地历史就先秒开，不等网络；随后 _load() 只做新鲜度校验
        cached = kline_cache.load(self._symbol, key)
        if cached:
            self.chart.set_data(cached)
            # 缓存里的 exhausted 标记也可能来自「达到上限」这类非全历史
            # 路径，必须经 trust_extremes() 复核周期与数据后才准标 ATH/ATL
            cached_all = bool(kline_cache.is_exhausted(self._symbol, key))
            self.chart.set_history_exhausted(cached_all, trusted=False)
            if cached_all:
                self.chart.trust_extremes()
            self.chart.set_status(
                f"本地缓存 {len(cached):,} 根 · 校验更新中")
            self.lbl_error.hide()
        self._load()
        # 日线及以上：ATH/ATL 需要完整历史才准，后台静默补齐
        self._ensure_extremes_history()

    # ---- 数据加载（后台线程）----
    def _load(self):
        if not self._symbol or getattr(self, "_no_kline", False):
            return     # 链上合约品种：没有 K 线，不发无效请求
        # 缓存新鲜期内完全不发 K 线请求：每次浏览都是本地秒开
        if kline_cache.is_fresh(self._symbol, self._interval):
            return
        if self._worker is not None:
            try:
                if self._worker.isRunning():
                    return
            except RuntimeError:
                self._worker = None
        self._worker = KlineWorker(self._symbol, self._interval, self)
        self._worker.loaded.connect(self._on_loaded)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_loaded(self, symbol, interval, candles):
        if symbol != self._symbol or interval != self._interval:
            return
        self.chart.interval = interval
        # API 只返回最近窗口，必须与本地已缓存的更早历史合并，
        # 不能把用户回溯出来的整段历史冲掉。
        merged = {c.ts: c for c in kline_cache.load(symbol, interval)}
        for c in candles:
            merged[c.ts] = c
        self.chart.set_data([merged[t] for t in sorted(merged)])
        kline_cache.save(symbol, interval, candles)
        self.chart.history_loading = False
        self.lbl_error.hide()
        if self._show_all and not self.chart.history_exhausted:
            self._load_history()
        else:
            self._ensure_extremes_history()

    def _on_failed(self, symbol, interval, msg):
        if symbol != self._symbol or interval != self._interval:
            return
        if not self.chart.candles:
            self.chart.set_status("K线加载失败，等待自动重试...")
        self.lbl_error.setText(f"K线数据异常：{msg}")
        self.lbl_error.show()

    # ---- 历史回溯（滚轮缩到整个生命周期）----
    def _fit_all_view(self):
        """把已加载的全部 K 线一次铺满一屏（左端对齐，右端无空白）。"""
        self.chart._pan = 0.0
        self.chart._view_count = max(1, len(self.chart.candles))
        self.chart.fit_all = True
        self.chart._clamp_pan()

    def _start_history_pump(self):
        """进入「无限缩小」模式：开启持续回溯，并立刻拉第一页。

        只有当前视野还没越过「全部铺满」点时才保持自动贴合；
        用户已主动缩小到总根数以外（半屏居中极限方向）时不再回拉。
        """
        self._show_all = True
        if self.chart._view_count > len(self.chart.candles):
            self.chart.fit_all = False
        else:
            self.chart.fit_all = True
        if self.chart.history_exhausted or not self.chart.candles:
            return
        if not self._hist_timer.isActive():
            self._hist_timer.start()
        self._load_history()

    # 需要完整历史才能算准 ATH/ATL 的周期；分钟线全历史动辄上百万根，
    # 不自动拉，用户缩到尽头时仍会按需回溯
    _FULL_HISTORY_INTERVALS = ("1d", "day", "3d", "3day", "1w", "week",
                               "1M", "month", "1y", "1year")

    def _ensure_extremes_history(self):
        """后台静默回溯到上市首根，保证 ATH / ATL 是真正的历史极值。

        与 _start_history_pump 的区别：不设 fit_all，不把视野拉回全图，
        只让数据一点点变多，图表保持用户当前的缩放位置。
        """
        if not self.chart.show_extremes:
            return
        if self._interval not in self._FULL_HISTORY_INTERVALS:
            return
        if self.chart.history_exhausted or not self.chart.candles:
            return
        if not self._hist_timer.isActive():
            self._hist_timer.start()
        self._load_history()

    def _on_need_history(self):
        """滚轮缩到已加载数据尽头 -> 继续往更早的生命周期回溯。"""
        self._start_history_pump()

    def _on_user_view_change(self):
        """用户主动放大 / 拖动：退出「全部历史」模式，别再把视野拉回全图。"""
        self._show_all = False
        self.chart.fit_all = False
        self._stop_history_pump()

    def _stop_history_pump(self):
        self._hist_timer.stop()

    def _load_history(self):
        """分页加载更早 K 线；max_history=0 时不限根数，直到上市首根。

        用定时器驱动而不是在 loaded 里递归：worker 的 loaded 信号会早于
        QThread.finished，旧的「单次重试」逻辑一旦遇到 worker 仍在运行就会
        把整条回溯链掐断，这正是缩小到一半就不动的原因。
        """
        if self.chart.history_exhausted:
            self._stop_history_pump()
            return
        if not self._symbol or not self.chart.candles:
            return
        if self._hist_worker is not None:
            try:
                if self._hist_worker.isRunning():
                    return      # 定时器下一拍继续，链路不会断
            except RuntimeError:
                pass
            self._hist_worker = None
        cap = int(self._cfg.get("max_history") or 0) if self._cfg else 0
        if cap > 0 and len(self.chart.candles) >= cap:
            # 用户设定的回溯上限 ≠ 上市首根：这里只是「一段区间」，
            # 绝不能把它的极值当成 ATH / ATL（v37 修复的误标来源之一）
            self.chart.set_history_exhausted(False)
            self.chart.history_capped = True
            self._stop_history_pump()
            self._fit_all_view()
            self.chart.set_status(
                f"已达设定的回溯上限 {cap:,} 根 · 图上高低仅为该区间极值")
            return
        # 本地已有更早一页就直接吃缓存，零网络请求
        local = kline_cache.take_before(
            self._symbol, self._interval, self.chart.candles[0].ts, 1000)
        if local:
            self._on_history(self._symbol, self._interval, local, False)
            return
        self.chart.history_loading = True
        self.chart.set_status(
            f"正在回溯更早历史… 已加载 {len(self.chart.candles):,} 根")
        worker = HistoryWorker(self._symbol, self._interval,
                               self.chart.candles[0].ts, self)
        worker.loaded.connect(self._on_history)
        worker.failed.connect(self._on_history_failed)
        worker.finished.connect(worker.deleteLater)
        self._hist_worker = worker
        worker.start()

    def _on_history(self, symbol, interval, candles, exhausted):
        if symbol != self._symbol or interval != self._interval:
            return
        self.chart.history_loading = False
        # 视野已越过「全部铺满」点（往半屏居中极限缩）时不回拉，
        # 否则后台每来一页数据都会把用户刚缩小好的视野弹回全图
        auto_fit = ((self._show_all or self.chart.fit_all)
                    and self.chart._view_count <= len(self.chart.candles))
        if candles:
            seen = {c.ts for c in self.chart.candles}
            older = [c for c in candles if c.ts not in seen]
            if not older:
                # 有返回但没有一根更早 -> 确实到头，避免无限空转
                self.chart.set_history_exhausted(True, trusted=False)
                self.chart.trust_extremes()
            else:
                merged = sorted(older + self.chart.candles,
                                key=lambda c: c.ts)
                self.chart.set_data(merged)
                kline_cache.save(symbol, interval, older)
                if auto_fit:
                    self._fit_all_view()
        else:
            self.chart.set_history_exhausted(True, trusted=False)
            self.chart.trust_extremes()
        if exhausted:
            self.chart.trust_extremes()
        if self.chart._extremes_trusted:
            kline_cache.save(symbol, interval, [], exhausted=True)
            self._stop_history_pump()
            if auto_fit:
                self._fit_all_view()
            self.chart.set_status(
                f"已回溯到上市首根 · 共 {len(self.chart.candles):,} 根")
        else:
            # 分钟线 / 上限截断：回溯到此为止，但这一段只是「区间」，
            # 图上极值只能叫 LH / LL，不许冒充 ATH / ATL
            self.chart.set_history_exhausted(True, trusted=False)
            self._stop_history_pump()
            self.chart.set_status(
                f"已到本次回溯边界 · 共 {len(self.chart.candles):,} 根 · "
                "图上高低仅为该区间极值")
        self.chart.update()

    def _on_history_failed(self, symbol, interval, msg):
        if symbol != self._symbol or interval != self._interval:
            return
        self.chart.history_loading = False
        # 网络抖动不永久判死刑：停泵但保持可重试，滚轮继续缩小即可续上
        self._stop_history_pump()
        self.chart.set_status(f"历史加载暂停：{msg}（继续缩小可重试）")
        self.chart.update()

    def _show_all_history(self):
        """一键铺开全部已加载 K 线，并持续自动回溯到上市首根。"""
        if not self.chart.candles:
            return
        self._fit_all_view()
        self._start_history_pump()
        self.chart.update()

    def _on_back(self):
        self.close_chart()
        self.back_requested.emit()
