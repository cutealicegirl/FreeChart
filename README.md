# Free Chart

[![Latest Release](https://img.shields.io/github/v/release/cutealicegirl/FreeChart?label=最新版本)](https://github.com/cutealicegirl/FreeChart/releases)
[![Downloads](https://img.shields.io/github/downloads/cutealicegirl/FreeChart/total?label=下载量)](https://github.com/cutealicegirl/FreeChart/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2B%20%7C%20Android%2010%2B-blue)](https://github.com/cutealicegirl/FreeChart)

全市场行情与品种档案 · 自由缩放 K 线（Windows 桌面版 + Android 10+）。
覆盖加密货币 / A股 / 港股 / 美股 / 链上合约，并提供品种发展历程与详情档案。

- 技术栈：Python 3.11+ / PySide6 / requests，图表与控件全部 QPainter 自绘
- 对外显示名与交付文件名统一为 `Free Chart`；内部 ID `CryptoTicker` 仅用于配置、缓存与单实例锁
- 特点：深色金融终端风格、常驻桌面、低资源占用、多数据源自动切换

## 下载

- **Windows 安装包（推荐）**：从 [Releases](https://github.com/cutealicegirl/FreeChart/releases) 下载最新的 `FreeChart-Setup-*.exe`
  —— 双击安装，自动创建「开始菜单 / 桌面」快捷方式并支持卸载。
- **Android 安装包（APK，Android 10+）**：从 [Releases](https://github.com/cutealicegirl/FreeChart/releases) 下载最新的 APK
  —— 自签名（v1 + v2 + v3），安装前请在系统设置中允许「未知来源」安装。
- 源码与发布包均见 [Releases](https://github.com/cutealicegirl/FreeChart/releases)。

> 想从源码自行构建？见下方「打包 / 制作安装包」。

## 主要功能

**行情**
- 四个市场独立分页，「自选 / 全部」二级切换；「全部」页按总市值降序，
  按页懒加载与展示，滚动 / 翻页时才创建行对象，不一次性挂载全部品种
- 红涨绿跌；列表显示最新价 / 涨跌幅 / 当日高低 / 成交额，价格带货币单位
  （加密货币与美股 `$`、A股 `¥`、港股 `HK$`）
- **品种资料卡**（列表上方）：鼠标停在哪一行就显示哪一只（70ms 防抖），
  内容为图标、代码、名称、市场标签、市值排名，以及最新价 / 24h 涨跌 /
  24h 高低 / 振幅 / 成交额 / 总市值 / 流通市值 / 市盈率；市值由
  「股本 × 当前价」实时算出，窗口宽窄自动切换 2 / 3 / 4 列
- 支持代码 / 中文名 / 拼音搜索，以及 EVM / Solana / Tron **链上合约地址**解析
- 任务栏右侧常驻单行价格条（三档信息密度），系统托盘实时价格图标

**窗口与布局**
- 无边框行情窗口可拖动、四边 / 四角拉伸、最大化与全屏展示，`ESC` 退出全屏；
  窄窗口下智能钳制最小尺寸，避免控件被挤坏
- 隐藏到托盘后仍继续刷新行情；只有真正退出时才停止调度器并释放线程资源

**K 线图表**
- 周期：1分 ~ 年K；滚轮缩放可一路缩到品种上市首根，一屏铺开全部历史
- 指标：MA / BOLL / VOL / MACD，趋势线、压力位、支撑位、ATH/ATL、局部高低
  五个开关互相独立，只在对应 K 线处标价格，不画贯穿水平线
- **支撑 / 阻力位只在 4 小时级及以上周期显示**（加密 4h 起，股票日线起）；
  ATH / ATL 必须真正回溯到上市首根后才标注，分页边界、回溯上限、缓存恢复
  等场景只按区间高低处理，不冒充历史极值
- 支撑压力按「近期有效 / 历史失效」分级配色：当前仍有效的用醒目实色 +
  淡色衬底，历史失效的压暗弱化
- **公司行为复权**：已核实的拆股、反向拆股、送转等事件自动前复权，
  成交量同步反向调整以保持成交额守恒；登记库之外的拆股品种，若原始价
  与成交量同步出现可确认的份额比例变化，也会自动前复权；缓存按复权指纹
  失效，避免二次复权；未核实事件只标记、不猜测比例，纯现金分红不伪造复权因子
- 打开图表后按秒级轮询最新价，最新一根 K 线随成交价连续伸缩（可在设置里
  调间隔）；切换周期前会在后台预取其它周期，点过去秒开
- 画线工具（直线 / 水平线 / 删除）、十字光标、光标处价格与当前价涨跌对比
- 头部「ⓘ 详情」按钮：弹出该品种的完整资料抽屉（行情 / 基本面两张卡片，
  含计价货币、数据源、总股本与流通量、市值排名）
- **顶部工具条可收纳**：周期 / 指标 / 画线 / 智能标注默认收成一条 28px 细条，
  鼠标扫过自动展开，离开约 1/3 秒后自动收起，按钮点击可固定展开
- **周期记忆**：每次打开图表自动恢复上一次查看的周期；该品种没有该周期时才回默认值

**链上合约地址解析**
- EVM / Solana / Tron 地址都能认；Solana 走链上直读：SPL Mint 取精度与总量，
  Token-2022 的 TokenMetadata 扩展或 Metaplex 元数据账户取名称 / 代码
- 解析结果显示「链 · 程序 · 名称(代码) · 总量」，并明确区分「币安现货可看 K 线」
  与「已链上确认但无现货交易对」；地址不存在时直接提示核对
- DexScreener 只在可用时补价格与交易对，探活失败后本次运行内不重试，界面不阻塞

**链上标的历史 K 线（v1.5）**
- 链上合约（如 Solana / Pump.fun / DEX 代币）现在支持真实历史 K 线：
  主源 GeckoTerminal DEX OHLCV，备源 CoinGecko onchain，自动解析交易池并缓存
- 支持 1分 / 5分 / 15分 / 30分 / 1时 / 4时 / 日 / 3日 / 周 / 月周期；
  交易池迁移后自动重新解析，历史按时间正序、去重、OHLC 校验后入本地 SQLite
- 双端一致：桌面与 Android 使用同一套周期与数据源口径；本地缓存优先，
  断网时继续显示已存历史，网络恢复后增量补齐
- **绝不伪造数据**：拿不到真实 OHLCV 时明确标注「数据源暂不可用」，
  回退到本设备采集的真实报价走势（非 K 线，无 OHLC / 成交量），不用插值或当前价冒充历史

**外观**
- 6 套全局主题：币安深色 / 午夜蓝 / OLED 纯黑 / 明亮浅色 / 赛博霓虹 / 护眼米黄，
  设置里切换即时生效，无需重启
- 6 套应用图标，切换后自动重写桌面/开始菜单快捷方式图标；托盘图标默认用同一张
  程序图标（右下角红/绿小圆点表示涨跌），也可在设置里改成纯实时价格方块
- 图表价格轴与指标数字字号可调（100%–180%）
- 看板娘：内置 **Remielle Dan** 立绘（透明背景、高 900px），可换任意
  PNG/JPG/WebP/GIF，可调大小、透明度、置顶与点击穿透（右键菜单同样可操作）

**看板娘互动**
- 气泡对话：按行情与操作说不同台词，气泡跟随立绘移动、4.2 秒后淡出；
  台词混着可爱的日语（おかえりなさい、やったね、がんばって等）
- 5 套二次元气泡风格：糖果 / 樱花 / 薄荷 / 赛博 / 经典，设置里一键切换
- 行情播报：自选品种涨跌绝对值 ≥2% 时播报（≥6% 换成加强语气），同品种同方向
  只报一次，75 秒冷却，避免刷屏
- 操作反馈：加/移自选、打开图表、切换市场、换主题、进设置各有一套台词
- 点她一下（按下到松开位移 <5px 判定为单击）也会说话
- 设置里可一键关闭互动气泡，关闭后立绘仍可拖动、仍可换图

**看板娘的显示规则**
- 只在 K 线图表页出现：行情列表页、设置页、最小化状态一律自动收起；
  位置被钳制在主窗口范围内，不会被拖到软件外面挡桌面
- 遮挡 K 线时整个消失：立绘与蜡烛区域一重叠就直接让位（160ms 快速淡出）；
  挪到不重叠的位置再自动淡回来
- 气泡文字测量留足内边距与行高冗余，中日英混排、长句换行都不会裁字

**移动端式布局**
- 底部导航栏「行情 / 设置」，图标 22px、点击区 min-height 48px，单手可达；
  图表并入行情，点任意一行进入图表，顶部「返回列表」或底栏返回
- 顶部标题栏及各按钮点击区按触摸尺寸放大（按钮 34×30、设置 38×38）
- 设置页为可滚动 sheet，卡片式分区，尺寸跟随主窗口，窄屏不挤
- 排序 / 切市场只重排当前页，重排期间冻结页面重绘，流畅不闪烁
- 「自选 / 全部」子页切换干净利落：上一子页的行显式隐藏，列表不残留旧内容
- 批量建行分批进行（60 行/批）+ 冻结重绘 + 临时静音行内提示，切页稳定不抖动

## 环境要求

- Windows 10 / 11，Python 3.11 及以上
- Android 10+（APK 为 WebView 壳 + 本地 H5 资源，不依赖 PySide6 / Qt）

## 安装依赖

```bash
pip install -r requirements.txt
```

> 如果默认源不可用，可使用：
> `pip install -r requirements.txt --index-url https://pypi.org/simple`

## 运行

```bash
python main.py
```

## 打包

桌面端用 PyInstaller 打包为单文件 exe：

```bash
python -m PyInstaller CryptoTicker.spec --noconfirm --clean
```

产物：`dist/Free Chart.exe`（单文件，含图标、字体、品种清单、看板娘素材与
公司行为登记库）。`CryptoTicker.spec` 是内部构建文件名。

### 制作安装包（可安装程序）

仓库提供 Inno Setup 脚本 `installer/FreeChart.iss`，把上面的单文件 exe
封装成标准 Windows 安装包（安装到 `Program Files`、创建快捷方式、自带卸载）：

```bash
# 1) 安装 Inno Setup（仅需一次）：winget install InnoSetup.InnoSetup
# 2) 用脚本编译（需先打包出 dist/Free Chart.exe）：
cd installer
iscc FreeChart.iss
# 或直接双击 installer/build_installer.bat
```

生成的安装包位于 `installer/out/FreeChart-Setup-*.exe`。

### Android 端

Android 端构建与签名见 `android/` 目录说明；交付 APK 位于
`android/dist/Free Chart.apk`。

## 单实例运行

程序同一时刻只允许一个实例：

- 开机自启会在托盘常驻一个实例，之后双击图标不会再开第二个，而是把已有窗口唤到前台；
- 第二个进程检测到已有实例后立即退出（返回码 0）。

## 目录结构

```text
CryptoTicker/
├── main.py                    # 入口（单实例互斥量 + 异常兜底：只写日志，不弹窗）
├── ui/                        # 界面层
│   ├── main_window.py         # 主窗口（按页懒加载 / 排序 / 置顶 / 导航 / 无边框拉伸）
│   ├── chart_view.py          # K 线图表页
│   ├── detail_dialog.py       # 图表页「详情」抽屉（行情 + 基本面 + 档案 + 发展历程）
│   ├── ticker_widget.py       # 行情行控件
│   ├── price_badge.py         # 任务栏常驻价格条
│   ├── theme.py               # 多主题调色板 + QSS
│   ├── icons.py               # 品种图标 / 多套应用图标 / 导航图形
│   ├── mascot.py              # 看板娘悬浮窗 + 气泡
│   ├── popup.py               # 全程序统一弹窗规格
│   ├── info_panel.py          # 悬停资料卡
│   ├── units.py               # 货币单位
│   └── settings_dialog.py     # 设置独立页面
├── data/                      # 数据层
│   ├── api_base.py / binance_api.py / okx_api.py / market_manager.py
│   ├── universe.py            # 各市场「全部」清单（市值降序）
│   ├── contract_search.py     # 链上合约地址解析
│   ├── fundamentals.py        # 市值 / 股本 / 市盈率
│   ├── rank_meta.py           # 排序元数据：真实市值 / 流动性 / 上市年份
│   ├── about.py / timeline.py # 项目与品种资料库
│   ├── history_stats.py       # 历史 K 线统计（标注复权口径）
│   ├── corporate_actions.py / corporate_actions.json
│   ├── corporate_actions_fetch.py
│   └── price_adjustment.py    # 公司行为复权核心
├── core/                      # 核心
│   ├── brand.py               # 品牌常量
│   ├── config.py              # 设置持久化
│   ├── indicators.py          # 跨端一致的 MA/EMA/BOLL/MACD 纯函数
│   ├── thread_cleanup.py      # QThread 安全收尾
│   ├── live_feed.py           # 图表最新价动画
│   ├── shortcut.py            # 快捷方式图标同步
│   └── updater.py             # 刷新调度
├── android/                   # Android 10+ 移植
│   ├── AndroidManifest.xml / build_apk.py / check_installable.py
│   ├── src/                   # Java Bridge + 后台 HTTP
│   ├── assets/www/            # index.html / style.css / app.js / universe.js / about.js
│   ├── tests/                 # Android 离线回归测试
│   └── INSTALL_AND_COMPATIBILITY.md
├── assets/                    # 图标 / 字体 / 看板娘等资源
├── tools/                     # 资源生成与预览脚本（可重复运行）
├── installer/                 # Inno Setup 安装包脚本
├── tests/                     # 桌面端离线回归测试
├── dist/Free Chart.exe        # 桌面交付
├── requirements.txt
└── README.md
```

## 免责声明

本项目仅显示公开行情数据，不提供任何交易功能，不构成投资建议。
