# Free Chart

[![Latest Release](https://img.shields.io/github/v/release/cutealicegirl/FreeChart?label=最新版本)](https://github.com/cutealicegirl/FreeChart/releases)
[![Downloads](https://img.shields.io/github/downloads/cutealicegirl/FreeChart/total?label=下载量)](https://github.com/cutealicegirl/FreeChart/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2B%20%7C%20Android%2010%2B-blue)](https://github.com/cutealicegirl/FreeChart)

全市场行情与品种档案 · 自由缩放 K 线（Windows 桌面版 + Android 10+）。
覆盖加密货币 / A股 / 港股 / 美股 / 链上合约，并提供品种发展历程与详情档案。
用户可见名称与交付文件名统一为 `Free Chart`（EXE / APK / 启动器 / 自启项名）。
仅保留不可见的技术 ID `CryptoTicker`：APK 包名、配置与缓存目录、单实例锁名，
用于兼容覆盖升级。

- 技术栈：Python 3.11+ / PySide6 / requests，图表与控件全部 QPainter 自绘
- 特点：深色金融终端风格、常驻桌面、低资源占用、多数据源自动切换

## 下载

- **Windows 安装包（推荐）**：[FreeChart-Setup-1.0.0.exe](https://github.com/cutealicegirl/FreeChart/releases/download/v1.0.0/FreeChart-Setup-1.0.0.exe)
  —— 双击安装，自动创建「开始菜单 / 桌面」快捷方式并支持卸载。
- **Android 安装包（APK，Android 10+）**：[FreeChart-Android-1.2.0.apk](https://github.com/cutealicegirl/FreeChart/releases/download/v1.0.0/FreeChart-Android-1.2.0.apk)
  —— 本地自签名（v1+v2+v3 签名），安装前请在系统设置中允许「未知来源」安装。
- 历史版本与源码见 [Releases](https://github.com/cutealicegirl/FreeChart/releases)。

> 想从源码自行构建？见下方「打包 / 制作安装包」。

## 主要功能

**行情**
- 四个市场独立分页，「自选 / 全部」二级切换；「全部」页按总市值降序：
  加密货币 200、美股 500、A股 100、港股 200
- 红涨绿跌；列表显示最新价 / 涨跌幅 / 当日高低 / 成交额，价格带货币单位
  （加密货币与美股 `$`、A股 `¥`、港股 `HK$`）
- **品种资料卡**（列表上方）：鼠标停在**哪一行**就显示**哪一只**（70ms 防抖，
  扫过列表时不会乱跳）；全部页默认显示榜首。内容为图标、代码、名称、市场标签、
  市值排名，以及最新价 / 24h 涨跌 / 24h 高低 / 振幅 / 成交额 / 总市值 /
  流通市值 / 市盈率。市值由「股本 × 当前价」实时算出，跟着行情一起动；
  窗口宽窄自动切 2 / 3 / 4 列
- 支持代码 / 中文名 / 拼音搜索，以及 EVM / Solana / Tron **链上合约地址**解析
- 任务栏右侧常驻单行价格条（三档信息密度），系统托盘实时价格图标

**K 线图表**
- 周期：1分 ~ 年K；滚轮缩放可一路缩到品种上市首根，一屏铺开全部历史
- 指标：MA / BOLL / VOL / MACD，趋势线、压力位、支撑位、ATH/ATL、局部高低
  五个开关互相独立，只在对应 K 线处标价格，不画贯穿水平线
- **支撑 / 阻力位只在 4 小时级及以上周期显示**（低时间范围噪音大，不显示）；
  ATH / ATL 需回溯到上市首根后才标注，未回溯完时极值只按区间高低处理
- 支撑压力按「近期有效 / 历史失效」分级配色：当前仍有效的用醒目实色 +
  淡色衬底，历史失效的压暗弱化
- 打开图表后按秒级轮询最新价，最新一根 K 线随成交价连续伸缩（可在设置里
  调间隔）；切换周期前会在后台预取其它周期，点过去秒开
- 画线工具（直线 / 水平线 / 删除）、十字光标、光标处价格与当前价涨跌对比
- 头部「ⓘ 详情」按钮：弹出该品种的完整资料抽屉（行情 / 基本面两张卡片，
  含计价货币、数据源、总股本与流通量、市值排名）
- **顶部工具条可收纳**：周期 / 指标 / 画线 / 智能标注默认收成一条 28px 细条
  （只剩切换按钮 + 当前周期 + 最新 / 全部历史），把 100+px 高度全让给 K 线；
  **鼠标扫过细条自动展开，离开约 1/3 秒后自动收起**，按钮点击=固定展开
- **周期记忆**：每次打开图表自动恢复上一次查看的周期（该品种没有这个周期时
  才回默认，如股票没有 15 分线）

**链上合约地址解析**
- EVM / Solana / Tron 地址都能认；Solana 走**链上直读**：SPL Mint 取精度与总量，
  Token-2022 的 TokenMetadata 扩展或 Metaplex 元数据账户取名称 / 代码
- 解析结果显示「链 · 程序 · 名称(代码) · 总量」，并明确区分「币安现货可看 K 线」
  与「已链上确认但无现货交易对」；地址不存在时直接提示核对
- DexScreener 只在可用时补价格与交易对，探活失败后本次运行内不重试，界面不阻塞

**外观**
- 6 套全局主题：币安深色 / 午夜蓝 / OLED 纯黑 / 明亮浅色 / 赛博霓虹 / 护眼米黄，
  设置里切换即时生效，无需重启
- 6 套应用图标，切换后自动重写桌面/开始菜单快捷方式图标；托盘图标默认用同一张
  程序图标（右下角一个红/绿小圆点表示涨跌），也可在设置里改成纯实时价格方块
- 图表价格轴与指标数字字号可调（100%–180%）
- 看板娘：内置 **Remielle Dan** 立绘（透明背景、高 900px），可换任意
  PNG/JPG/WebP/GIF，可调大小、透明度、置顶与点击穿透（右键菜单同样可操作）

**看板娘互动**
- 气泡对话：按行情与操作说不同台词，气泡跟随立绘移动、4.2 秒后淡出；
  **台词混着可爱的日语**（おかえりなさい、やったね、がんばって等）
- **5 套二次元气泡风格**：糖果（粉紫渐变）/ 樱花（粉白 + 小爱心）/ 薄荷
  （青绿 + 圆点）/ 赛博（霓虹青边）/ 经典（深色金条），带圆角、外发光与
  星星装饰，设置里「气泡风格」一键切换
- 行情播报：自选品种涨跌绝对值 ≥2% 时播报（≥6% 换成加强语气），同品种同方向
  只报一次，75 秒冷却，避免刷屏
- 操作反馈：加/移自选、打开图表、切换市场、换主题、进设置各有一套台词
- 点她一下（按下到松开位移 <5px 判定为单击）也会说话
- 设置里可一键关闭互动气泡，关闭后立绘仍可拖动、仍可换图

**看板娘的显示规则**
- **只在 K 线图表页出现**：行情列表页、设置页、最小化状态一律自动收起；
  位置被钳制在主窗口范围内，不会被拖到软件外面挡桌面
- **遮挡 K 线时整个消失**：立绘与 K 线（蜡烛区域）一重叠就直接让位（160ms
  快速淡出），把完整的 K 线还给你；挪到不重叠的位置再自动淡回来
- 气泡文字测量留足内边距与行高冗余，中日英混排、长句换行都不会裁字

**手机式布局（为移植手机预留）**
- 底部导航栏「行情 / 设置」，图标 22px、点击区 min-height 48px，单手可达；
  **图表并入行情**——点任意一行行情进入图表（图表页顶部「返回列表」或
  点底栏「行情」返回）；顶部标题栏与各按钮点击区按触摸尺寸放大
  （按钮 34×30、设置 38×38）
- 设置页为可滚动 sheet：三张卡片（行情与窗口 / 外观 / 自选列表）+ 底部固定
  操作条，尺寸跟随主窗口，窄屏不挤
- 排序 / 切市场只重排当前页，重排期间冻结页面重绘，流畅不闪烁
- 「自选 / 全部」子页切换干净利落：上一子页的行显式隐藏，列表不残留旧内容
- 批量建行分批进行（60 行/批）+ 冻结重绘 + 临时静音行内提示，切页稳定不抖动

## 环境要求

- Windows 10 / 11
- Python 3.11 及以上

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

桌面端（Windows）用 PyInstaller 打包为单文件 exe：

```bash
python -m PyInstaller CryptoTicker.spec --noconfirm --clean
```

产物：`dist/Free Chart.exe`（单文件，含图标、字体、品种清单、看板娘素材）。
构建脚本文件名 `CryptoTicker.spec` 属开发内部文件，沿用旧名以免破坏既有命令。

> 注：应用内部 ID 仍为 `CryptoTicker`（数据目录 `%APPDATA%/CryptoTicker`、
> 进程单实例锁），这是为兼容历史版本升级而保留的；对外显示名统一为 Free Chart。

### 制作安装包（可安装程序）

仓库提供了 Inno Setup 脚本 `installer/FreeChart.iss`，把上面的单文件 exe
封装成标准 Windows 安装包（安装到 `Program Files`、创建「开始菜单 / 桌面」
快捷方式、自带卸载）：

```bash
# 1) 安装 Inno Setup（仅需一次）：winget install InnoSetup.InnoSetup
# 2) 用脚本编译（需先打包出 dist/Free Chart.exe）：
cd installer
iscc FreeChart.iss
# 或直接双击 installer/build_installer.bat
```

生成的安装包位于 `installer/out/FreeChart-Setup-<版本>.exe`。

### Android 端

Android 端为 WebView 壳 + 本地 H5 资源，构建与签名见 `android/` 目录说明。

## 单实例运行

程序同一时刻只允许一个实例：

- 开机自启会在托盘常驻一个实例，之后双击图标**不会**再开第二个，而是把已有窗口唤到前台；
- 第二个进程检测到已有实例后立即退出（返回码 0）。

## 目录结构

```
CryptoTicker/
├── main.py                # 入口（单实例互斥量 + 异常兜底：只写日志，不弹窗）
├── ui/                    # 界面层
│   ├── main_window.py     # 主窗口（按需加载 / 14 种排序 / 置顶 / 三选项卡导航 / 响应式）
│   ├── chart_view.py      # K 线图表页
│   ├── ticker_widget.py   # 行情行控件
│   ├── price_badge.py     # 任务栏常驻价格条
│   ├── theme.py           # 多主题调色板 + QSS
│   ├── icons.py           # 品种图标 / 多套应用图标 / 导航图形
│   ├── mascot.py          # 看板娘悬浮窗 + 气泡（MascotBubble）
│   ├── popup.py           # 全程序统一弹窗规格（表面 / 标题栏 / 卡片 / 按钮）
│   ├── info_panel.py      # 行情行右键「查看资料」弹出的品种资料弹窗（含项目介绍）
│   ├── detail_dialog.py   # 图表页「详情」抽屉（行情 + 基本面 + 档案 + 发展历程 + 里程碑）
│   ├── units.py           # 货币单位
│   └── settings_dialog.py # 设置独立页面（QStackedWidget 的一页）
├── data/                  # 数据层（适配器架构）
│   ├── api_base.py        # 行情适配器基类
│   ├── binance_api.py     # Binance 适配器
│   ├── okx_api.py         # OKX 适配器
│   ├── market_manager.py  # 数据源管理/自动切换/单品种实时报价
│   ├── universe.py        # 各市场「全部」清单（市值降序）
│   ├── contract_search.py # 链上合约地址解析（Solana 直读 RPC）
│   ├── fundamentals.py    # 市值 / 股本 / 市盈率（profile v2 + 磁盘缓存）
│   ├── rank_meta.py       # 排序元数据：真实市值 / 流动性 / 上市年份（7 天缓存）
│   ├── about.py           # 项目 / 公司 / 产品 / 创始人离线中文资料库
│   ├── timeline.py        # 发展历程 45 品种 / 185 里程碑 + 品种档案（核验 2026-11-14）
│   └── history_stats.py   # 由真实历史 K 线算「区间」里程碑（不冒充全历史）
├── core/                  # 核心
│   ├── brand.py           # 统一品牌常量（Free Chart，内部 ID 保持兼容）
│   ├── config.py          # 设置持久化
│   ├── live_feed.py       # 秒级实时价（图表最新 K 线动画）
│   ├── shortcut.py        # 快捷方式图标同步
│   └── updater.py         # 刷新调度
├── assets/                # 图标 / 字体 / 看板娘等资源
├── tools/                 # 资源生成与预览脚本（可重复运行）
│   ├── export_profile_db.py       # Python 资料库 → Android about.js（单一数据源）
│   ├── make_mascot_from_image.py  # 立绘抠图（四角 floodfill 去白底）
│   ├── make_preview_v19.py        # 资料卡 / 工具条收纳 / 看板娘预览图
│   ├── make_preview_v20.py        # 悬停资料卡 / 详情抽屉 / 气泡风格预览图
│   ├── make_preview_v21.py        # 看板娘显示规则 / 遮挡隐藏 / 日文气泡预览图
│   ├── make_preview_v22.py        # 工具条悬停收纳 / 看板娘重现说话预览图
│   ├── make_preview_v24.py        # 右键资料弹窗 / 设置页导航修复预览图
│   └── make_preview_v25.py        # 工具条独立图层 / 弹窗拖动 / 关闭按钮预览图
├── tests/                 # 桌面端离线回归 v4–v38（含 qt_exit.py 退出助手）
├── dist/Free Chart.exe    # 唯一桌面交付（Free Chart）
├── dist/archive/          # 历史版本备份（CryptoTicker_v33–v36 / legacy_20261113）
├── android/              # Android 10+ 移植（原生 WebView 壳，不依赖 PySide6/Qt）
│   ├── AndroidManifest.xml       # minSdk 29 / targetSdk 34 / 强制竖屏
│   ├── build_apk.py              # aapt2→javac→d8→zipalign→apksigner 手工构建链
│   ├── check_installable.py      # APK 可安装性静态预检（签名/对齐/图标/桥方法）
│   ├── debug.keystore            # 自签名证书（覆盖升级必须沿用）
│   ├── res/values/               # 应用名 Free Chart / 深色启动主题
│   ├── res/mipmap-*/             # 五档密度 K 线应用图标
│   ├── src/com/cryptoticker/app/MainActivity.java  # Java Bridge + 后台 HTTP
│   ├── assets/www/               # index.html / style.css / app.js / universe.js / about.js
│   ├── make_coin_icons.py        # 桌面官方 logo → 移动端 64px 资源（270 个）
│   ├── assets/www/coins/         # 打包进 APK 的品种 logo
│   ├── tests/test_app_logic.js   # DOM/Bridge 模拟层回归（离线 + REAL=1 真实接口）
│   ├── tests/test_app_v34.js     # v34 手机端功能补齐回归（61 项）
│   ├── tests/test_app_v35.js     # v35 批量行情容错回归（11 项）
│   ├── tests/test_app_v36.js     # v36 股票自选 + 链上真实图表（25 项）
│   ├── tests/test_app_v37.js     # v37 品牌 / 发展历程 / 档案 / 里程碑（20 项）
│   ├── tests/test_app_v38.js     # v38 列表折叠 / 图表工具条（27 项）
│   ├── INSTALL_AND_COMPATIBILITY.md  # 安装方法 + 兼容性报告 + 手机自测清单
│   └── dist/Free Chart.apk       # 最终可安装 APK（v38 / v1+v2+v3 签名）
├── requirements.txt
└── README.md
```

## 免责声明

本项目仅显示公开行情数据，不提供任何交易功能，不构成投资建议。
