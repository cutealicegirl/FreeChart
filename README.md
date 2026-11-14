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
  与「已链上确认但无现货交易对」；地址不存在时直接提示核对，不再一句「搜不到」
- DexScreener 只在可用时补价格与交易对，探活失败后本次运行不再重试，不会卡 8 秒

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
  **图表已并入行情**——点任意一行行情就进图表（图表页顶部「返回列表」或
  点底栏「行情」回来），不再单列一个主入口；顶部标题栏与各按钮点击区按
  触摸尺寸放大（按钮 34×30、设置 38×38）
- 设置页改为可滚动 sheet：三张卡片（行情与窗口 / 外观 / 自选列表）+ 底部固定
  操作条，尺寸跟随主窗口，窄屏不挤
- 排序 / 切市场只重排当前页（不再整窗重排 4 个市场最多 1000 行），重排期间冻结
- **子页切换不残留**：从「全部」切回「自选」时，上一子页的行会被显式隐藏，
  不会以旧坐标叠在新列表上（以前会看到「自己没添加的品种」并连带弹出提示小窗）
- 批量建行时分批（60 行/批）+ 冻结页面重绘 + 临时静音行内提示，
  切「全部」不再连续弹小窗、也不抖动
  重绘，点排序不闪、不抖、不弹窗

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

这条规则很关键——多实例会导致两个常驻价格条叠在同一位置、多个托盘图标各自弹气泡，
看起来就像「疯狂弹窗 + 疯狂抖动」。

> 从旧版本升级后，如果托盘里还留着旧版进程，请先在托盘右键「退出」或结束
> 任务管理器里的所有 `Free Chart.exe`（若从旧快捷方式启动，进程名也可能是
> `CryptoTicker.exe`），再启动新版。

窗口在构造期间用 `WA_DontShowOnScreen` 压制上屏，布局与配置全部应用完才由
`prepare_show()` 一次性显示，因此启动时不会再闪一个 170×63 的透明空壳小窗。

## v21 交互修复

- **图表工具条：悬停一定生效。** 旧版会把「固定展开」写进 `chart_tools_open`，
  重启后工具条一直摊开，鼠标扫过 / 离开看起来完全没反应。现在每次启动都从
  收纳状态开始；`Enter/Leave` 事件负责即时响应，另有 60ms 一次的光标坐标轮询
  兜底——顶层悬浮窗（看板娘 / 气泡）吞掉事件、鼠标先停在工具条上再切到图表页
  等情况也能自动展开，离开约 300ms 自动收纳。点按钮的手动固定只在本次停留有效，
  鼠标一离开即自动解除。
- **看板娘：隐藏后重现会重新开口。** 被 K 线挡住时气泡被收掉且台词被丢弃，
  重现后要等下一次行情播报才可能说话。现在让位期间的最后一句台词会排队，重现后
  优先补说；没有排队台词时说一句带日语假名的「ただいま〜」回来台词。行情播报
  只有在台词真的被接收时才记入去重，不会在隐藏期间被悄悄用掉。
- 顺带修正气泡生命周期：到点自动淡出；淡出时挂起的延迟关闭不会误伤新气泡。
- 新增 `tests/test_release_v21.py` 离线回归（v4–v21 共 18 套全部通过）。

## v22 交互与资料升级

- **行情资料改成悬停弹窗。** 列表上方不再常驻资料卡；鼠标停在哪一行，就在那一行
  旁边浮出一张卡片（右侧优先、空间不够翻到左侧、上下钳制在主窗口内），离开约
  220ms 自动收起。浮层设置 `WA_TransparentForMouseEvents`，不会吞掉行事件。
- **所有弹窗统一规格。** 新增 `ui/popup.py`：圆角面板 / 1px 边框 / 统一投影 /
  44px 标题栏 / 分组卡片 / 主按钮，全部从 `ui.theme` 动态取色，换主题自动跟着变。
  `theme.dialog_qss()` 现在转发到 `popup_qss()`，设置页、详情抽屉、悬停资料卡
  共用一张样式表，不再各写一套。
- **设置改为独立界面。** `SettingsDialog` → `SettingsPage(QWidget)`，作为
  `QStackedWidget` 的一页由底部导航「设置」切换；保存 / 取消都回到进来之前的页面
  （列表页或图表页），不再是模态弹窗。旧名字保留为兼容别名。
- **滚轮缩放以原 K 线为锚点。** 旧版缩小后会把 `pan` 强制改成 0（贴死最右侧）
  或 `-(view-total)/2`（整块居中）。现在只保持锚点那根 K 线的屏幕 x 不变：
  光标在绘图区内就用光标下那根，贴着右侧价格轴时用视口中心那根。仅在视野宽过
  全部历史时加一个下限约束，保证早期 K 线不会被推出屏幕，不强制任何固定位置。
- **跨图表保留缩放与位置。** `view_count` / `pan` 在换品种、换周期、离开图表时
  存入 `chart_view_count` / `chart_view_pan`（节流 1 秒写盘，重启也恢复）；
  后续到达的 K 线数据不再把用户视口自动居中回去。点「最新」才复位。
- **项目背景介绍。** `data/about.py` 离线中文资料库覆盖主流加密资产与常见股票，
  含项目 / 公司 / 产品 / 创始人 / 创立年份 / 简介，未收录品种按市场生成兜底文案。
  悬停弹窗与详情抽屉都新增「项目 · 公司介绍」卡片，断网也能秒开。
- 新增 `tests/test_release_v22.py`，并把 v11 / v13 / v19 中关于「强制居中」「资料卡
  常驻列表上方」的旧断言更新为新行为；`tests/qt_exit.py` 统一处理 offscreen 下
  Qt 卸载竞态（v4–v22 共 19 套全部 RC=0）。

## v24 资料卡改右键触发 + 设置页导航修复

- **品种资料卡改为右键菜单选中才弹出。** 悬停不再自动弹出；在行情行上点右键 →
  「ℹ 查看资料」才浮出卡片。卡片可交互、右上角 ✕ 手动关闭；滚动列表、切市场、
  进图表、进设置时自动收起，不会留下悬空卡片。
- **修复设置页里点「行情」无法跳回。** 旧版 `_on_bottom_nav("list")` 只处理了
  图表页分支；从列表页进设置后 `_list_geometry` 为空，点「行情」什么也不发生。
  现在设置页里点「行情」走 `_close_settings_page()` 回到进设置前的页面
  （列表页或图表页）。顺带：已在设置页时重复点「设置」不再重置回退目标。
- 回归稳定化：v19 改为离线注入合成 K 线（真实网络加载偶发超过等待窗口导致
  「图表应已渲染出 K 线区域」随机失败）；v12 补 `qt_exit.finish()` 收尾；
  v19 / v20 的悬停断言更新为右键触发新行为。
- 新增 `tests/test_release_v23.py`、`tools/make_preview_v24.py`（v4–v23 共
  20 套全部 RC=0）。

## v25 工具条独立图层 + 资料弹窗不遮挡可拖动 + 关闭按钮加大

- **图表工具条与 K 线不同图层。** 展开面板不再参与布局：悬浮在 K 线图上方
  （细条正下方、带投影的浮层），展开 / 收纳 / 改窗口大小都不会挤压或重排
  K 线，缩放与平移状态完全不受影响；细条本身仍占一条稳定高度。
- **资料弹窗默认位置不遮挡。** 窄窗口两侧放不下时停靠窗口右下角，不压右键
  点开的那一行、不挡上方页签 / 搜索区；宽窗口优先放行侧面的整块空位。
- **弹窗可拖动。** 按住标题栏即可整体拖动，全程钳制在软件窗口内；
  本次会话记住拖动后的位置，再次「查看资料」沿用。
- **关闭按钮加大。** 统一关闭按钮热区从 30x28 加到 44x34（弹窗 / 详情抽屉 /
  设置页三处一致），悬停有圆形底色。
- 新增 `tests/test_release_v24.py`、`tools/make_preview_v25.py`
  （preview/97–100）；v19 的「展开挤压图表」旧断言更新为独立图层新行为
  （v4–v24 共 21 套全部 RC=0）。

## 任务栏「指定品种价格」小工具修复

- **两个开关解耦。** 旧版 `_sync_badge()` 用 `price_badge AND tray_show_price`
  决定任务栏常驻价格条的显隐，`_refresh_symbols()` 也只在 `tray_show_price`
  为真时把指定品种纳入请求集合。于是托盘右键选一次「不显示价格」
  （`tray_show_price=False`）后，价格条被连带隐藏、指定品种也不再取数，
  一直显示 `-- WAIT` —— 看起来就是「小工具失灵」。现在价格条只受
  `price_badge` 控制；只要价格条或托盘价格任一开启，指定品种都会取数。
- **单轮缺项不再闪回占位符。** 行情按数据源合并，某一组临时失败时返回的
  字典会缺个别代码；旧版整体替换 `_last_tickers` 后直接 `.get()`，价格条
  会瞬间变 `-- WAIT`、下一轮又恢复。现在保留 5 分钟内的上次真实报价，并在
  tooltip 标注「数据来源：上次成功刷新的缓存（非实时）」；缓存过期后老实
  回到等待态，绝不把陈旧价格冒充实时价。
- **托盘菜单勾选同步。** 价格条右键「隐藏」原用 `hide()`（C++ slot，绕过
  Python 重写的 `setVisible`），导致托盘菜单仍显示已勾选，再点一次反而把它
  关掉。改为走 `setVisible`，且只在状态真变化时广播 `visibility_changed`。
- **可指定品种清单共用。** 托盘右键与价格条右键现在共用同一份候选
  （自选 + 当前市场「全部」页前 40 + 当前指定品种），非自选品种也能直接
  指定；补上了构造顺序导致的首次注入缺失（托盘菜单先于价格条创建）。
- **立即刷新不再被吞。** `refresh_now()` 撞上在途请求时旧版直接丢弃，换品种
  要等满一个刷新周期才生效。现在记下 pending，在途结束后补发一次。
- 新增 `tests/test_release_v25.py`（7 组离线断言）；v4–v25 共 22 套回归
  全部 RC=0；`dist/CryptoTicker.exe` 已重新打包。

## 阶段 1：品种详情信息完善（真实数据，不编造）

- **数据来源实测。** CoinLore `/api/tickers/` 提供 `csupply / tsupply /
  msupply / volume24 / rank`；腾讯行情 88 字段快照里 `f[30]` 是交易所行情时间、
  `f[36]` 成交量（手）、`f[37]` 成交额（万元）、`f[38]` 换手率、`f[39]` 市盈率、
  `f[44]/f[45]` 流通/总市值、`f[46]` 市净率。只用已核实含义的字段，不臆测索引。
- **`data/fundamentals.py`：profile v2。** 固定字段 schema，新增流通量 /
  总供应量 / 最大供应量 / 成交量 / 换手率 / 市净率 / 成交额；补齐
  `source / source_url / source_note / updated_ts / updated_text / updated_kind`。
  **「更新时间」不再恒显示「刚刚」**：股票用交易所 f[30] 行情时间，加密用真实
  本地采集时间，并标出口径。
- **不编造。** 流动性、营收、利润、代币分配、解锁计划、协议收入等本程序
  未接入数据源的字段一律为 `None`，界面统一显示「— 暂无公开数据」；离线 /
  断网也只返回「全字段存在但数值为空」的骨架，绝不填 0 或估算值。
- **`data/about.py`：结构化分区。** 增加项目背景 / 业务介绍 / 核心特点 /
  发展前景 / 项目用途；前三项只重组资料库已有事实，发展前景与代币经济学等
  无依据项留空并明确标注；未收录品种照旧有兜底简介。
- **`ui/detail_dialog.py`：层级重构。** 详情抽屉从 3 张卡扩为 6 个分区
  （行情数据 / 市值与估值 / 供应·成交·流动性 / 项目·公司介绍 /
  项目用途·代币经济学 或 公司业务·财务指标 / 数据来源与更新时间），
  加密与股票展示不同字段组；每个数字都能追溯到来源与采集时间。
- **`ui/info_panel.py`**：资料卡补一行来源与更新时间；后台离线兜底不再
  覆盖已经拿到的真实来源。
- 新增 `tests/test_release_v26.py`（6 组断言）；v4–v26 共 23 套回归全部 RC=0；
  `dist/CryptoTicker.exe` 已重新打包。
- 遗留：营收 / 利润 / 代币分配 / 解锁 / 协议收入 / 流动性需要接入财报与链上
  数据源才能真正填值，当前按需求明确标注缺失，等待确认数据源后再补。

## 阶段 0–7 实施报告（问题原因 / 修改文件 / 测试结果 / 遗留问题）

> 严格按阶段顺序推进，每阶段单独编译、回归，再进入下一阶段。
> 桌面端产物 `dist/CryptoTicker.exe`；Android 产物 `android/dist/CryptoTicker.apk`。
> Android 详细安装与兼容性报告见 `android/INSTALL_AND_COMPATIBILITY.md`。

### 阶段 0 · 架构分析

- 现状：`QMainWindow` + `QStackedWidget` + `QScrollArea`；数据链为
  `MarketManager` → Binance / 腾讯 / CoinLore → `RefreshScheduler`（QThread）
  → `_on_fetched()` → 行 / 托盘 / 价格条 / 资料卡。
- 定位到的问题：①「全部」页一次挂载 500 个 `QWidget` 并全量刷新；
  ②切页/排序/force 各自触发请求，无去重；③详情弹窗与资料卡每次重新建控件；
  ④排序只有涨跌幅/价格/成交额，缺真实市值与流动性；⑤「移到顶部」只改内存顺序；
  ⑥图表依附行情页、设置在右上角；⑦交互依赖 hover / 右键 / 40px 控件。
- 修复方案：按需加载 + 请求窗口化 + 快照合并；元数据层；置顶状态持久化；
  三选项卡导航；触摸优先；Android 改用原生 WebView 壳而非 Qt for Android。

### 阶段 1 · 品种详情（已完成，见上节）

- 修改：`data/fundamentals.py`、`data/about.py`、`ui/detail_dialog.py`、
  `ui/info_panel.py`、`tests/test_release_v26.py`。
- 测试：v26 通过，v4–v26 共 23 套回归 RC=0；EXE 重打包。
- 遗留：营收/利润/代币分配/解锁/协议收入无数据源，明确标注「— 暂无公开数据」。

### 阶段 2 · 全部行情加载卡顿与弹窗

- 原因：一次性把全部行塞进布局、每次刷新重绘全表；force/切页/滚动重复触发
  异步任务；详情每次新建对话框与线程；失败反复弹模态窗口。
- 修改：
  - `ui/main_window.py`：`PAGE_SIZE=60 / PREFETCH_ROWS=60 / MAX_REFRESH_SYMBOLS=300 /
    MAX_RETRY=3`；`_fill_rows()` 只挂载首屏，`_refresh_symbols()` 只请求已挂载+预取
    窗口，`_paint_page_rows()` 局部刷新；`_on_fetched()` 合并快照
    （`_last_tickers.update()`）保留缓存价；新增 `_on_retry / _on_list_scroll /
    _load_more_page / _update_load_progress`。
  - `core/updater.py`：120ms `_burst` 合并、`_last_request_key` 去重、
    `_pending_force` 在途补发。
  - `ui/ticker_widget.py`：`StatusPanel.set_progress()` + `retry_requested`，轻量状态条。
  - `ui/detail_dialog.py`：按品种复用最多 3 个非模态抽屉。
  - `ui/info_panel.py`：离线兜底不覆盖已取得的真实来源。
  - `tests/test_release_v27.py` 新增；`tests/test_release_v4.py` 断言改为首屏 60 行。
- 测试：v27 通过，v4–v27 全量 RC=0；EXE 重打包。
- 遗留：首屏外品种的价格在滚动到位后才请求（按需加载的设计取舍）。

### 阶段 3 · 排序体系

- 原因：原排序维度少且缺真实市值/流动性/上市时间；排序会清空筛选条件。
- 修改：`ui/main_window.py` 增加 `SORT_MODES`（14 种）、`SORT_SHORT`、
  `REVERSE_SORT`、`SORT_GROUPS`、`META_SORT_MODES` 与
  `_rank_value / _sort_key / _default_key / _apply_filter / _on_sort_flip /
  _on_sort_menu / _ensure_rank_meta / _on_rank_meta`；新增 `data/rank_meta.py`
  （CoinLore 市值/成交额/排名、腾讯 `f[44]/f[45]/f[38]/f[37]`、内置 `since`
  年份，7 天磁盘缓存，缺失为 `None`）；`tests/test_release_v28.py`。
- 修复的真实 bug：离线元数据 `None` 覆盖已取得的真实市值（改为逐字段只补真值）；
  测试里误把已收录的 `SH:600519` 当未收录（改用 `US:ZZZZ`）。
- 测试：v28 通过，v4–v28 全量 RC=0；EXE 重打包。
- 遗留：CoinLore 覆盖前 500 名；股票 60 只一批；未收录上市年份的品种排末尾。

### 阶段 4 · 右键「移到顶部」

- 原因：仅改内存列表顺序，刷新/切页后丢失，且被数值排序覆盖。
- 修改：`core/config.py` 新增 `pinned_symbols`（旧配置缺键安全迁移）；
  `ui/main_window.py` 在排序结果前拼接置顶项并新增 `_set_pinned()`；
  `ui/ticker_widget.py` 增加置顶徽章 `set_pinned()`；`tests/test_release_v29.py`。
- 测试：v29 通过（用 `FakeMenu` 替换 `QMenu`，规避 offscreen 下 `exec()` 卡死），
  v4–v29 全量 RC=0；EXE 重打包。
- 遗留：无。

### 阶段 5 · 布局重构

- 原因：图表依附行情页、设置入口在右上角、返回逻辑不统一。
- 修改：`ui/main_window.py`（`BottomNav.ITEMS` 改为 行情/图表/设置，
  `TitleBar` 去掉设置按钮并加 `set_page / btn_back`，新增
  `_on_bottom_nav / _open_chart_tab / _navigate_back / open_settings`）；
  `ui/settings_dialog.py` 改明确「← 返回」（44px）；`tests/test_release_v30.py`；
  同步更新 v17 / v20 / v23 的底栏断言。
- 修复的真实 bug：从设置页点「行情」实际回到图表页时高亮错为「行情」
  （改为按 `stack.currentWidget()` 判断）。
- 测试：v30 通过，v4–v30 全量 RC=0；EXE 重打包。
- 遗留：无。

### 阶段 6 · 移动端优先交互

- 原因：hover / 右键依赖、控件 40px 不适合触摸、图表缺触摸缩放。
- 修改：`ui/main_window.py`（`QScroller` 惯性滚动、`resizeEvent /
  _apply_responsive(width)`、连接 `row.long_pressed`、按钮统一 44px、窄屏收起次要提示）；
  `ui/ticker_widget.py`（`long_pressed` 信号、行内 `⋯` 44×44、500ms 长按、
  `mouseMoveEvent/mouseReleaseEvent` 防滑动误触）；`ui/chart_view.py`
  （`CandleChart.zoom_by()` 复用滚轮锚点公式、`＋/－` 按钮、工具条 44px）；
  `tests/test_release_v31.py`。
- 修复的真实 bug：`line_edit_qss()` 的 `min-height:22px` 让搜索框仍是 40px
  （改 `setFixedHeight(44)`）；测试蜡烛构造缺 `time_label`。
- 测试：v31 通过，v4–v31 共 28 套回归全部 RC=0；EXE 重打包。
- 遗留：桌面右键菜单保留作为兼容路径，触摸为新增路径，未删除既有功能。

### 阶段 7 · Android 移植

- 方案决策：PySide6/Qt 在本机没有 Android Qt 运行时与 CPython wheel，复用会牺牲
  稳定性，故改用「原生 Java WebView + 本地 HTML/CSS/JS + Java 网络/存储桥」，
  不依赖任何桌面运行环境；数据源、字段口径、配置键名与桌面端保持一致。
- 修改文件：`android/AndroidManifest.xml`（minSdk 29 / targetSdk 34 / portrait）、
  `android/res/values/{strings,colors,styles}.xml`（深色启动主题）、
  `android/src/com/cryptoticker/app/MainActivity.java`（`Native.http/get/set/
  copy/paste/finish/version/toast`，后台线程池 HTTP、GBK 解码）、
  `android/build_apk.py`（aapt2→javac→d8→zipalign→apksigner）、
  `android/assets/www/{index.html,style.css,app.js,universe.js,about.js,universe.json}`、
  `android/tests/test_app_logic.js`、`android/INSTALL_AND_COMPATIBILITY.md`。
- 构建问题与修复：34.0.0 的 `d8` 处理匿名内部类 NPE → 改用 36.1.0 `d8.jar`；
  子进程 GBK 输出导致 `UnicodeDecodeError` → `errors="replace"`；
  `apksigner` 主类写错 → 改为 `java -jar apksigner.jar`。
- 测试：`node --check` 通过；`android/tests/test_app_logic.js` 离线 46/46、
  `REAL=1` 真实接口 51/51（Binance / 腾讯 / CoinLore / 两家 K 线全通，
  并覆盖 Canvas 绘制、锚点缩放、逐级返回、配置导入导出）；
  `apksigner verify` v3 通过；`aapt2 dump xmltree` 核对 minSdk/targetSdk/portrait；
  DEX 字符串核对桥方法；桌面端 v4–v31 共 28 套回归 0 失败。
- 遗留：**本机 `adb devices` 为空、无 AVD/system-images，未能做实机安装与启动测试**；
  签名证书为本地自签名（升级需保留 keystore）；v1/v2 签名块未生成（minSdk 29
  时 apksigner 只写 v3，覆盖 Android 10+）——**此结论仅对应阶段 7 当时的构建，
  v37 已实测 v1 回退 + v2 + v3 全部存在**；托盘价格条、看板娘、划线指标属桌面专属，
  未移植。详见 `android/INSTALL_AND_COMPATIBILITY.md` 的自测清单。

### 补充 · 链上币种可收藏可看价（无 K 线数据）— v32/v33

- 问题：无图表信息的链上币种（如 Solana pump.fun 新币，币安现货无交易对、无 K 线）
  之前会被判为「无可看 K 线」而拒绝加入自选，用户无法收藏与查看价格。
- 方案：把「能否收藏」与「有没有 K 线」彻底解耦，并找到国内网络可达的真实链上报价源
  **Rugcheck.xyz**（DexScreener / GeckoTerminal / Jupiter / CoinGecko 实测全部超时不可用）。
- 修改文件（桌面端）：新增 `data/onchain.py`（`ON:地址` 符号体系、Rugcheck 报价、
  磁盘缓存与失败退避）；`data/contract_search.py`（合约解析接入链上报价，`onchain` 标记）；
  `ui/main_window.py`（链上品种创建自举行、纳入刷新窗口、行刷新优先用链上报价）；
  `ui/ticker_widget.py`（`update_onchain()`：真实 USD 价、涨跌幅显示「—」、不编造）；
  `ui/chart_view.py`（链上品种明确「链上代币暂无 K 线数据源，仅支持列表行情/详情」，
  不启动秒级 live 轮询）；`data/fundamentals.py` + `data/about.py`（链上详情：真实
  市值/供应量/流动性/持有者 + 来源与时间）；`core/config.py`（配置迁移兼容旧文件）。
- 修改文件（Android 端）：`app.js`（搜索框粘贴合约地址 → Rugcheck 解析代币 →
  「加入自选」；列表行显示代币代码与链上真实报价；图表页显示「链上代币暂无 K 线
  数据源」占位；详情含链上分区）；`universe.js` 不变（链上品种为用户自选，非内置清单）。
- 测试：`tests/test_release_v32.py` 40/40 通过（用真实合约地址
  `9cRC…pump` 全链路验证：可收藏、行显示代币代码、Rugcheck 真实价、无 K 线标注、
  详情真实市值）；桌面端 v4–v32 共 29 套回归 0 失败；Android 回归离线 68/68、
  `REAL=1` 真实接口 75/75；APK 重建（83,128 字节，v3 签名验证通过，含五档应用图标）；
  EXE 重打包为 `dist/CryptoTicker_v33.exe`（原 EXE 被运行中实例占用，未强制关闭）。
- 遗留：Rugcheck 仅覆盖 Solana 及部分 EVM 链，其他链地址会明确提示「链上查不到」，
  不编造价格；链上品种无 24h 涨跌幅数据源，涨跌幅一律显示「—」。

### 补充 · MA/EMA 可设参数 + 手机端功能补齐 — v34 / APK 1.1.0

**桌面端（v34）**

- 新增 `core/indicator_params.py`：MA / EMA 各 4 条线的天数（2–500）与启停、
  BOLL 周期与倍数、MACD 快慢线/信号线参数；支持「全部周期 `*`」与「仅当前周期
  （如 `1h`）」两种作用域，周期只保存与全局不同的字段，改全局会自动传导。
- 新增 `ui/indicator_sheet.py` 悬浮参数面板，图表工具条「⚙ 参数」打开；
  `ui/chart_view.py` 按参数计算 MA/EMA/BOLL/MACD、绘制 EMA 线、图例与副图标题同步，
  切 K 线周期自动换用该周期参数；`ui/settings_dialog.py` 增加 EMA 开关。
- 回归：`tests/test_release_v33.py` 47/47，v25–v32 与搜索冒烟全绿；
  重打包 `dist/CryptoTicker_v34.exe`（55,197,037 字节）。

**Android 端（versionName 1.1.0 / versionCode 2）**

针对「手机端相比 PC 缺失太多」的 5 项反馈逐条补齐：

1. 刷新间隔从 15–120 秒放开到 **5–300 秒**，设置页可输入任意值 + 7 个快捷档。
2. 图表补齐 **MA / EMA（各 4 条、可设天数与启停）/ BOLL 三轨 / MACD 副图 / VOL**，
   带指标参数面板与按周期作用域；Canvas 顶部显示 OHLC 与指标数值图例。
3. 打包 **270 个官方品种 logo**（`android/make_coin_icons.py` 把桌面 256px 原图压成
   64px，共 1.37 MB）；美股走品牌 logo，A股/港股/链上用字徽，图片失败自动回退。
4. K 线 `pan` 允许负值、浮点、左右留白，与桌面 `_clamp_pan` 同规则，
   不再吸附最新一根或拖到头卡住；缩放以视口中心为锚点。
5. 设置页从 3 项扩到 **6 套主题、图表字号、货币单位、图标开关、5 个指标开关、
   默认排序、每页条数、失败重试、实时价轮询与间隔、缓存保留、缓存清理**；
   Windows 专属能力（托盘/任务栏价格条/开机自启/看板娘）明示不移植，不做假开关。

同时同步桌面改动：搜索结果独立页（点击进图表、只有 ＋ 才收藏）、最近 100 条历史、
价格右侧 ⋯ 方框删除（改长按 / 右键菜单）。

- 回归：`android/tests/test_app_v34.js` 61/61、既有 `test_app_logic.js` 68/68、
  `REAL=1` 真实接口 75/75、`check_installable.py` 17/17；
  APK 1,519,399 字节，v1/v2/v3 签名与 4 字节对齐验证通过，
  SHA-256 `ab839047c2126ff3f9eb7e1c4405176d97ea13576af589f9f445444ec56ce739`。
- 仍未完成：**真机安装 / 启动测试**（本机无 Android 设备或可用模拟器镜像），
  静态预检不等于实机安装通过，清单见 `android/INSTALL_AND_COMPATIBILITY.md` 第七节。

### v35：修复「加密货币行情打开直接没数据」

- **根因**：币安 `/api/v3/ticker/24hr?symbols=[...]` 是「全有或全无」接口，
  数组里只要有一个无效交易对就整批返回 HTTP 400。用户配置里收藏了链上合约品种
  `ONCHAIN:<addr>`，旧版把它拼成 `<addr>USDT` 一起发出，导致同批 100 个币种
  全部取不到价 —— 表现为加密页整页空白（股票走腾讯源，所以仍有数据）。
  另发现桌面快捷方式一直指向 `dist/CryptoTicker.exe`（11-13 旧包），而非最新交付包。
- **根治**：`data/binance_api.py` 先按合法基础代码过滤（链上/股票/带冒号代码绝不进请求），
  遇到 `400 Invalid symbol` 时二分拆批重试，只丢弃真正无效的一个并缓存；
  非 400 的错误仍交给上层切换数据源，不在故障时放大请求量。
  `data/market_manager.py` 分组时也排除链上品种，`fetch_quote` 不再拼非法 URL。
  `data/onchain.py` 新增 `ensure_meta()`：老配置只有 `symbols` 里的 ONCHAIN 项、
  缺 `onchain_symbols` 时自动补最小元数据并落盘（短地址 + 真实链名，不编造价格）。
- **手机端同步**：`app.js` 新增 `binanceBatch()`，整批失败时按 1/4 逐级拆分重试，
  单个下架币不再让 100 个品种一起空白。
- **交付**：桌面 `dist/CryptoTicker.exe`（快捷方式所指）已替换为 v35，旧包备份为
  `dist/CryptoTicker_legacy_20261113.exe`，另存 `dist/CryptoTicker_v35.exe`（55,200,463 B）；
  Android `1.1.1 / versionCode 3`，APK 1,519,399 B，
  SHA-256 `e3ae076748d46d3bc11cd1340245aaffd067873c37dd6365dc4da01ffb31f1bb`。
  **替换磁盘文件不影响已运行的旧进程，需完全退出程序（含托盘）后重新打开。**
- **回归**：`tests/test_release_v35.py` 20/20、`android/tests/test_app_v35.js` 11/11；
  桌面 v25–v33 + 搜索冒烟、Android v34 61/61 与既有 68/68、`check_installable.py` 17/17 全绿；
  真实配置实测取回 18 个加密 + 18 个股票行情，数据源 `Binance + 腾讯股票`，无错误。

### v36：链上币真实图表 + 手机端股票市场自选修复

- **链上币图表**：DexScreener / GeckoTerminal / CoinGecko / pump.fun 的 K 线接口
  在本机全部超时，唯一可直连的 Rugcheck 报告也不提供 OHLC 历史。因此不画假蜡烛，
  改成两类**真实数据**图表：
  ① 本设备每次刷新采到的 Rugcheck 真实 `(时间, 价格)` 连成的报价走势折线
     （`core/onchain_history.py` / 手机端 `ct_oc_hist`，最多 720 点，20 秒同价去重）；
  ② 当前报告里的前十大持有地址占比、流动性池类型分布横向条形图。
  图表明确标注「非交易所 K 线 · 无 OHLC / 成交量 · 本设备采集」，采样点不足时
  显示采集进度而不是空白。真实报告实测解析出 10 个持有人、6 类池、518 个池。
  两端同步：桌面 `CandleChart._draw_onchain()`、手机端 `drawOnchainChart()`。
  另外把链上品种的实时轮询从 900ms 改为 60 秒节流，避免打爆 Rugcheck。
- **手机端股票市场点不了自选**：`baseList()` 里「自选为空就静默切回全部」的逻辑
  让用户点「自选」后被立刻弹回「全部」。已删除该回落，空自选改为显示引导卡片
  （一键跳全部）；`watchList()` 不再要求品种在离线清单里，导入配置的 ETF /
  新上市股票也能正常进自选。
- **回归**：`tests/test_release_v36.py` 24/24、`android/tests/test_app_v36.js` 25/25；
  v32 与 `test_app_logic.js` 中检查旧「暂无 K 线」文案的断言已按新行为更新，
  桌面 12 套回归 0 失败，Android 68/68、61/61、11/11、25/25、`REAL=1` 75/75，
  安装预检 17/17，真实 Rugcheck 报告字段解析通过。
- **交付**：桌面 `dist/CryptoTicker.exe` 替换为 v36（另存 `dist/CryptoTicker_v36.exe`）；
  Android `1.1.2 / versionCode 4`，APK 1,523,495 字节，
  SHA-256 `632b99050ad379e0806a2b02e6fb61c7fa0322e9c6a2e84e9c224172bbac2876`。

## v37：更名 Free Chart + 品种发展历程 + 详情准确性 + 图表极值口径修复

- **更名**：旧名 `CryptoTicker` 只说了「加密行情」，与实际功能（A股 / 港股 /
  美股 / 加密 / 链上合约 + 自由缩放 K 线 + 品种档案）不符。用户定为
  **Free Chart**，副标「全市场行情 · 品种档案」，主打图表缩放与平移自由度。
  `core/brand.py` 统一所有可见文案：窗口标题、顶栏、托盘通知、任务栏价格条、
  HTML 标题 / 顶栏、Android `app_name`。**EXE 文件名、`%APPDATA%` 目录、
  单实例锁、注册表键名、APK 包名一律不改**，避免旧快捷方式失效和升级丢数据。
- **品种发展历程（新增）**：`data/timeline.py` 收录 45 个品种、185 条里程碑、
  24 份档案（行业 / 交易所 / 上市日 / 发行价 / 总部 / 官网 / 共识机制 / 供应上限）。
  资料由 AI 依据公开资料整理，关键日期联网核验：上交所公司概况（茅台
  2001-08-27）、港交所上市资料（腾讯 2004-06-16、阿里 2019-11-26、美团
  2018-09-20）、中证 / 深交所（宁德 2018-06-11、比亚迪 2011-06-30）、
  Nasdaq / 公司 IR（美股 7 只 IPO 日）、SEC 执法公告
  （XRP 案 2025-08-07 双方撤回上诉终结）、项目官方升级记录
  （BTC 白皮书 / 减半、ETH Frontier / Merge / Dencun）。
  日期按可信粒度写（年 / 月 / 日），每条带来源标签，全库标注核验日期
  2026-11-14；未收录品种返回空时间线 + 明确留白，不套用通用说明。
  `tools/export_profile_db.py` 把同一份库导出成 `android/assets/www/about.js`，
  手机端不再手工维护第二份，避免两边日期不一致。
- **详情升级**：桌面新增「交易所快照 · 真实字段」「品种档案」「发展历程 · 里程碑」
  「行情里程碑 · 真实历史数据」四组卡片；发展历程默认 6 条、可一键展开全部。
  手机端 `detailHTML()` 追加 ⑦⑧⑨ 三个分区（原 ①–⑥ 不变），新增
  `.timeline` 时间线样式。行情里程碑由真实月 K / 链上本机报价采样计算
  （区间首末、区间最高最低及日期、区间涨跌、最大回撤、样本根数），
  **一律叫「区间」并写明统计起点**，绝不等同于上市以来全历史。
- **准确性修正（实测腾讯快照）**：
  1. 港股 / 美股 f[37] 成交额本币已是「元 / 美元」，旧版一律按 A 股「万元」
     ×1e4，数值放大一万倍 —— 按市场区分单位；
  2. f[30] 行情时间三种真实格式（`20261113161455` / `2026/11/13 16:08:22` /
     `2026-11-13 16:00:01`），旧版只认第一种，港美股时间一直显示「—」；
  3. A 股 f[47]/f[48] 是涨停 / 跌停价，港美股 f[48]/f[49] 是 52 周高 / 低，
     旧代码可能串用；成交量单位也按「手 / 股」区分；
  4. 资料库未收录的品种不再把「市场通用说明」塞进主营业务 / 核心特点 /
     项目用途冒充该品种资料；
  5. XRP 介绍更新为 SEC 案 2025-08-07 已终结（原描述停留在诉讼中）。
- **图表 bug 修复（用户反馈：小时间范围把局部高低点当成历史高低点）**：
  `_draw_extremes()` 原来只看 `history_exhausted` 布尔值，但达到用户设定的
  回溯上限、分页边界「无更早数据」、从缓存恢复 exhausted 标记时它也会是
  True，于是当前这一小段数据的极值被画成 ATH / ATL。现在引入
  `_extremes_trusted`：**必须与当前 candles 绑定且经 `trust_extremes()` 确认
  （日线以上 + 确实回溯到上市首根）**，任何 `set_data()` 换数据立即作废；
  分钟线永不宣称全历史。LH / LL 让位逻辑、图表右上角状态
  （「区间高低」）同步改口径。v12 的旧门控回归保持通过。
- **老断言对齐**：`test_release_v17.py` 设置页卡片数（v30 已按需求删除自选列表，
  现为 2 张）、`test_release_v4.py` 搜索面板可见性（v31 已改为独立结果页）
  两处历史断言改为当前产品行为，不是放宽检查。
- **回归**：桌面 `tests/test_release_v37.py` 37/37；桌面 v4–v37 全量
  **33 个回归脚本 0 失败，RC=0**（v34 为手机端专属，无桌面脚本）；
  手机端 `test_app_v37.js` 20/20，连同既有 4 套 JS 回归
  （68/68、61/61、11/11、25/25）全部通过；`REAL=1` 联网回归本轮 74/75
  （Rugcheck 上游偶发超时，其余 5 个真实接口正常，详见
  `android/INSTALL_AND_COMPATIBILITY.md`）；
  APK 静态预检 17/17（应用标签 `Free Chart`、v1 回退 + v2 + v3 签名）；
  EXE 归档 PYZ 内含 `data.timeline` / `data.history_stats` / `core.brand`。
- **交付**：桌面 `dist/CryptoTicker.exe`（55,247,416 字节，快捷方式所指路径不变）；
  Android `1.2.0 / versionCode 5`，`android/dist/CryptoTicker.apk`
  1,535,783 字节，SHA-256
  `0e4dff642cf0b48ac8164edcaaf5a33f7b0a8225d1cdcf67556d4756e2175e50`，
  v1/v2/v3 签名与 4 字节对齐通过。真机 `adb install -r` 仍未执行（无设备）。
- **文档同步**：`android/INSTALL_AND_COMPATIBILITY.md` 已从 v36 更新到 v37 ——
  应用名 `Free Chart`、`1.2.0 / versionCode 5`、实测大小与 SHA、APK 内 287 个条目清单、
  详情 9 分区与离线资料库口径、17 项静态预检、桌面 33 套 / 手机端 5 套回归结果、
  Rugcheck 联网超时说明，以及补充发展历程 / 区间高低点的手机端自测清单。

### v38 · 列表折叠 / 图表精简 / 桌面弹窗修复 / 文件名统一 — 2026-11-14

- **手机端列表顶部自动折叠**（用户：「选项卡搜索框太占空间，应随上滑下滑自动隐藏/展现，
  动画要流畅自然」）：`index.html` 把 `#markets` / `#subs` / `.toolbar` 包进
  `#listHead.list-head`；`app.js` 新增 `headOnScroll()` 状态机——同方向累计位移
  上滑 56px 收起、下滑 20px 展开、距顶 24px 内强制展开，方向变化即清零，
  惯性滚动与手抖不会来回切换；`setHeadHidden()` 写 JS **实测高度**的
  `max-height`（不用 auto，才有平滑过渡），配 `.28s cubic-bezier(.22,.61,.36,1)`
  + opacity / translateY，`style.css` 给 `.list` 加 `overflow-anchor:none` 防回弹。
  输入框聚焦、点顶栏、切回列表、切市场/子页均强制展开，搜索框始终可达。
- **图表页工具条精简**（用户：「不要放大缩小按钮，触摸缩放就够；其余按钮缩小、
  布局合理安排」）：删除 `＋ 放大 / － 缩小`，双指捏合 `zoomBy()` 保留；原两行工具
  合并成一行「⟲ 最新 / ⓘ 详情 / ⚙ 指标」，视觉高度 46→36px、周期按钮 44→36px，
  用 `::after` 把触摸热区补回 44px；`chart-head` / `chart-note` 间距收紧，
  画布更大。「最新」只复位平移，不改用户调好的缩放倍数。
- **桌面「全部」页批量弹窗修复**（用户要求排查循环渲染 / 事件重复绑定 / 接口重复回调）：
  三项怀疑**均不成立**——`core/updater.py` 的 120ms burst + 在途去重已挡住重复请求，
  行信号只在创建时连一次，`_relayout_page` 有顺序短路。真正根因是 **Qt 原生
  `QToolTip`（QTipLabel 顶层小窗）**：分批建行时光标下的子 QLabel 反复
  `show/hide/重设 tooltip`，Qt 连发 `QEvent.ToolTip`，而旧版把过滤写在父行
  `TickerWidget.event()` —— 事件在子 QLabel 处就被 `QWidget::event()` 消费，
  父行根本收不到；再加全局 bool 在多市场并行建行时被先结束的链提前打开。
  修复：`ui/ticker_widget.py` 改为**应用级 `installEventFilter` + 引用计数**
  （`ToolTipGuard` / `begin_tooltip_hold` / `end_tooltip_hold`），
  `ui/main_window.py` 用 `_release_fill()` 单一收尾路径 + `try/finally`，
  删掉每链各自的 700ms 定时器，行信号改 `Qt.UniqueConnection`。
  注意 PySide6 的 `eventFilter` 覆写**不能调 `super().eventFilter()`**（会递归回自身），
  已直接 `return False`。
- **程序名彻底统一**（用户：「名字怎么还没改？Free chart」）：上轮只改了界面可见名，
  保留了文件名。本轮把 `CryptoTicker.spec` 的 `name` 改为 `Free Chart`、
  输出 `dist/Free Chart.exe`、APK 输出 `android/dist/Free Chart.apk`、
  `check_installable.py` 路径、`core/autostart.py` 注册表自启项名（并清理旧值）、
  Java 剪贴板标签 / User-Agent 全部同步。仍**不能改**的是包名
  `com.cryptoticker.app`、`%APPDATA%/CryptoTicker/`、单实例锁，否则升级丢数据；
  `dist/CryptoTicker.exe` 保留为字节完全相同的兼容副本，旧快捷方式不失效。
  `core/shortcut.py` 的新旧名都能识别。
- **回归**：新增 `android/tests/test_app_v38.js` **27/27**、
  `tests/test_release_v38.py` **20/20**（含「对子 QLabel 发 ToolTip 不弹窗」
  「全过程无新增顶层窗口」「多链引用计数」「链异常可恢复」「其它弹窗源计数为 0」）；
  桌面 v4–v38 全量 **34 个脚本 0 失败**、手机端 **6 套 JS 全绿**；
  `v37` 中「EXE 名必须保持 CryptoTicker」的历史断言已按新命名对齐。
  APK 静态预检 17/17。`REAL=1` 联网回归仍为 74/75（Rugcheck 偶发超时，非回归）。
- **交付**：`dist/Free Chart.exe` 55,250,744 字节，SHA-256
  `d8017bba0b40d357818f65617d0d493646944cec0ea0798ba364101e4922d666`；
  `android/dist/Free Chart.apk` 1,535,783 字节，`versionCode 6 / 1.2.0`，SHA-256
  `31eadd17a8100146a669311c3ab9719c65746b5267f3a7e4a61adfca0e36dc93`。
  `android/INSTALL_AND_COMPATIBILITY.md` 已同步到 v38。真机 `adb install -r`
  与折叠动画手感仍未测（无设备 / 模拟器）。

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
├── dist/Free Chart.exe    # 唯一桌面交付（v38 / Free Chart）；旧名兼容副本已移除
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
