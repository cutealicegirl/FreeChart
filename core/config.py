# -*- coding: utf-8 -*-
"""配置持久化（JSON）。

保存路径：%APPDATA%/CryptoTicker/config.json
程序意外关闭后下次启动也能恢复全部设置。
"""
import json
import os
from typing import Any, Dict

# 默认监控币种（自定义排序的初始顺序）
DEFAULT_SYMBOLS = [
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "HYPE", "ENA",
    "TAO", "ZEC", "ONDO", "PUMP", "NEAR", "ARB", "RENDER", "FIL", "AR",
]

# 默认配置
DEFAULTS: Dict[str, Any] = {
    "symbols": DEFAULT_SYMBOLS,   # 自选币列表（顺序即显示顺序）
    # 阶段 4：用户自定义的置顶品种（按置顶先后排列）。独立于 symbols 顺序，
    # 且优先于市值 / 涨跌幅等所有排序规则；旧配置缺该键时为空，安全迁移。
    "pinned_symbols": [],
    # 搜索历史：最多保留最近 100 条，最新在前；旧配置缺键为空列表，安全迁移。
    "search_history": [],
    # 链上合约品种元数据：{ "ONCHAIN:<address>": {address,code,name,chain,...} }。
    # 这类币种没有 K 线，但可收藏、可看真实链上报价；元数据落盘保证重启后
    # 自选行仍能显示代币代码与名称。旧配置缺该键时为空字典，安全迁移。
    "onchain_symbols": {},
    "interval": 15,               # 刷新间隔（秒）
    "source": "",                 # 首选数据源名（空 = 自动）
    "always_on_top": False,       # 窗口置顶
    "frameless": True,            # 无边框模式
    "opacity": 100,               # 不透明度（1-100）
    "x": -1,                      # 窗口位置 x（-1 = 居中）
    "y": -1,                      # 窗口位置 y
    "w": 380,                     # 窗口宽
    "h": 560,                     # 窗口高
    "autostart": False,           # 开机启动
    "sort_mode": "custom",        # 排序方式: custom/change_desc/change_asc/
                                  #          price_desc/amount_desc
    "chart_tools_open": False,    # 图表页顶部工具条是否固定展开（悬停也会自动展开）
    "chart_interval": "",         # 上次查看图表使用的周期（打开图表时恢复）
    "chart_view_count": 0.0,      # 上次 K 线缩放级别（0 = 用默认 90 根）
    "chart_view_pan": 0.0,        # 上次 K 线横向位置（相对最新一根的偏移）
    "last_tab": "crypto",         # 上次所在市场页（crypto/cn/hk/us）
    "show_ma": True,              # 图表页显示 MA 均线
    "show_ema": True,             # 图表页显示 EMA 指数均线（与 MA 同为可配置）
    # MA / EMA 天数、BOLL / MACD 参数。空字典 = 使用内置默认；
    # "*" 为所有周期通用，也可写 "1h" 等周期键单独覆盖（详见
    # core.indicator_params）。旧配置缺键时安全回落到默认参数。
    "indicator_params": {},
    "show_boll": True,            # 图表页显示 BOLL 布林线（默认 20,2）
    "show_macd": True,            # 图表页显示 MACD 副图
    "show_vol": True,             # 图表页显示成交量副图
    "start_in_tray": True,        # 开机自启时自动隐藏到右下角托盘
    "tray_symbol": "BTC",         # 托盘显示的自定义品种
    "tray_show_price": True,      # 托盘图标上显示该品种价格
    "tray_icon_style": "app",     # 托盘图标：app=跟随程序图标 / price=价格方块
    "sub_tabs": {                 # 每个市场当前的子页：watch=自选 / all=全部
        "crypto": "watch", "cn": "watch", "hk": "watch", "us": "watch",
    },
    "max_history": 0,             # 回溯上限根数；0 = 不限，一路回溯到上市首根
    # 图表智能标注：五个开关各自独立，互不捆绑
    "show_trend": False,          # 线性回归趋势线
    "show_res": False,            # 压力位 R1/R2
    "show_sup": False,            # 支撑位 S1/S2
    "show_extremes": True,        # ATH / ATL 标注
    "show_pivots": True,          # 局部高点 LH / 局部低点 LL
    # 任务栏右侧常驻实时价格（贴合任务栏，非悬浮卡片）
    "price_badge": True,
    "price_badge_x": -1,          # 旧版拖动坐标，现由任务栏定位，保留兼容
    "price_badge_y": -1,
    "price_badge_shift": 0,       # 手动左移像素（避开其它任务栏小工具）
    "price_badge_style": "full",  # 任务栏价格条信息密度：full/slim/mini
    # 主流品种 K 线历史后台预缓存（落盘到 %APPDATA%/CryptoTicker/klines.sqlite3）
    "prefetch_enabled": True,     # 启动后后台预热，之后浏览直接读本地
    "prefetch_top": 40,           # 每个市场预取前 N 个主流品种（0 = 只取自选）
    "prefetch_delay": 20,         # 启动后延迟秒数，避开实时行情刷新
    "prefetch_gap": 350,          # 相邻请求间隔毫秒，避免打爆 API
    "prefetch_ttl": 21600,        # 预缓存新鲜期（秒，默认 6 小时）
    # ---- 外观 ----
    "theme": "binance",           # 全局主题：binance/midnight/oled/light/cyber/sepia
    "app_icon": "classic",        # 桌面 + 托盘图标方案（assets/app_icons）
    "chart_font_scale": 120,      # 图表价格轴 / 指标数字字号百分比（100-160）
    "show_currency": True,        # 价格前显示货币单位（$ / ¥ / HK$）
    # ---- 实时行情（图表最新 K 线连续动画）----
    "live_feed": True,            # 打开图表时按秒级轮询最新价，K 线连续伸缩
    "live_interval_ms": 900,      # 实时轮询间隔（毫秒，400-3000）
    # ---- 看板娘 ----
    "mascot_enabled": False,      # 是否显示看板娘
    "mascot_image": "",           # 自定义图片路径（空 = 内置形象）
    "mascot_scale": 100,          # 尺寸百分比（50-200）
    "mascot_opacity": 100,        # 不透明度（20-100）
    "mascot_x": -1,               # 窗口位置（-1 = 贴屏幕右下角）
    "mascot_y": -1,
    "mascot_click_through": False,  # 点击穿透
    "mascot_on_top": True,        # 总在最前
    "mascot_speech": True,        # 互动气泡：按行情 / 操作说话
    "mascot_bubble_style": "candy",  # 气泡风格 candy/sakura/mint/cyber/classic
}


def config_path() -> str:
    """配置文件完整路径。"""
    appdata = os.getenv("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "CryptoTicker", "config.json")


class Config:
    """读写 JSON 配置；文件缺失/损坏时自动回退到默认值。"""

    def __init__(self):
        self._data = dict(DEFAULTS)
        self.load()

    def load(self):
        """加载配置，异常时静默使用默认值（程序不能因配置损坏崩溃）。"""
        try:
            with open(config_path(), "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                for k, v in DEFAULTS.items():
                    if k in saved:
                        self._data[k] = saved[k]
        except (OSError, ValueError):
            pass  # 文件不存在或 JSON 损坏 -> 使用默认配置

    def save(self):
        """保存配置到磁盘。"""
        path = config_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass  # 保存失败不崩溃（如磁盘只读）

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any):
        self._data[key] = value
