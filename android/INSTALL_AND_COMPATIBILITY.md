# Free Chart Android 版 · 安装方法与兼容性报告

> 本报告对应 **v38 交付物**：应用名与交付文件名均为 `Free Chart`、
> versionName `1.3.0`、versionCode `7`。
> 所有结论均来自本机实际执行的构建、签名、静态解析、真实接口请求与 WebView 逻辑回归；
> **本机没有连接任何 Android 设备或可用模拟器镜像，因此没有做实机安装 / 启动测试，
> 本报告不声称实机验证通过**。文末给出手机端自测清单。
>
> **命名约定（已按用户要求彻底统一为 Free Chart）**：用户可见名称、交付文件名
> 与全部内部技术标识均已统一 —— 启动器图标名、页面标题、顶栏、桌面窗口/托盘/
> 价格条、`dist/Free Chart.exe`、`android/dist/Free Chart.apk`、PyInstaller
> 产物名、注册表开机自启项名；APK 包名 `com.freechart.app`、
> `%APPDATA%/FreeChart/` 配置与缓存目录、单实例锁名、日志 tag、构建脚本
> `FreeChart.spec` 也全部为 Free Chart。
>
> **升级提示**：包名由旧名改为 `com.freechart.app` 后，Android 系统会把它当作
> 新应用，旧版需先卸载再安装（旧版本地数据不自动迁移，请提前备份）；桌面版
> 启动时会把旧 `%APPDATA%` 目录的数据一次性迁移到 `%APPDATA%/FreeChart/`，
> 自选 / 配置 / 缓存不会因改名丢失。

---

## 一、交付物

| 项目 | 值 |
| --- | --- |
| 文件 | **`android/dist/Free Chart.apk`**（v38 起文件名也改为 Free Chart） |
| 大小 | **1,535,783 字节**（约 1.46 MB，比 1.0.0 大是因为打包了 270 个品种官方 logo） |
| SHA-256 | `31eadd17a8100146a669311c3ab9719c65746b5267f3a7e4a61adfca0e36dc93` |
| 应用标签 | **`Free Chart`**（`aapt2 dump badging` 实测） |
| 包名 | `com.freechart.app`（已随品牌统一改名；旧版需卸载后再装） |
| 版本 | versionName `1.3.0` / **versionCode `7`**（桌面端窗口管理增强（拉伸 / 移动 / 全屏）与「全部」页按页按需加载同步发布；versionName 与桌面端保持一致，仅递增 versionCode） |
| 最低系统 | `minSdkVersion 29`（Android 10） |
| 目标系统 | `targetSdkVersion 34`（Android 14） |
| 屏幕方向 | `portrait`（强制竖屏） |
| 签名 | 自签名 RSA 2048，**v1 回退 + v2 + v3 全部存在**，`apksigner verify` 通过，签名者 1 个 |
| 图标 | 五档密度自适应图标（`mipmap-mdpi` … `xxxhdpi`，K 线造型） |
| 权限 | `INTERNET`、`ACCESS_NETWORK_STATE`（仅网络，无通讯录/定位/存储/电话等敏感权限） |
| 构建链 | `aapt2 compile/link` → `javac --release 8` → `d8 (36.1.0)` → `zipalign` → `apksigner` |

同版桌面交付：**`dist/Free Chart.exe`，55,250,744 字节**，SHA-256
`d8017bba0b40d357818f65617d0d493646944cec0ea0798ba364101e4922d666`；
兼容副本 `dist/FreeChart.exe` 与它字节完全一致（`cmp` 实测）。

签名证书为本地 `android/debug.keystore`（有效期 10000 天）。
**请保留该 keystore**：后续版本必须用同一证书签名，否则手机会提示「应用未安装 / 签名冲突」。
v38 只改了新建 keystore 时的 CN，现有证书未重建，签名与 v37 一致，可正常覆盖升级。

### v38 相对 v37 的主要变化

- **列表顶部自动折叠**：行情页「市场 / 子页 / 搜索框」包进 `.list-head`，
  随 `#list` 上滑收起、下滑展开。用「同方向累计 + 滞回阈值」（上滑 56px 收起、
  下滑 20px 展开、距顶 24px 内强制展开）防抖；`max-height` 写入 JS 实测高度，
  配 `cubic-bezier(.22,.61,.36,1)` 缓动 + 透明度/位移过渡；`.list` 加
  `overflow-anchor:none` 避免 WebView 改 scrollTop 造成回弹。输入框聚焦、
  点顶栏、切回列表、切市场/子页都会强制展开，搜索框始终可达。
- **图表工具条精简**：删除「＋ 放大 / － 缩小」按钮（双指捏合缩放已足够），
  原两行工具合并成一行「⟲ 最新 / ⓘ 详情 / ⚙ 指标」；工具按钮与周期按钮
  视觉高度从 46/44px 收到 36px，并用 `::after` 把实际触摸热区扩回 44px；
  `chart-head` / `chart-note` 间距同步收紧，K 线画布获得更多空间。
  「最新」只复位平移，不改用户调好的缩放倍数。
- **桌面端「全部」页批量弹窗修复**（详见第八节与桌面回归）：根因是 Qt 原生
  tooltip，不是 MessageBox、不是循环渲染、不是重复绑定、也不是接口重复回调。
- **交付文件名统一为 Free Chart**：EXE / APK / 注册表自启项名 / 剪贴板标签 /
  User-Agent 全部同步；桌面 EXE 保留同内容旧名副本以兼容既有快捷方式。

### APK 内容（本轮实测 `zipfile` 列举，共 287 个条目）

```
AndroidManifest.xml            2,664 B
classes.dex                    9,708 B   （Java WebView 壳 + 网络/剪贴板桥，Native.version() = 1.3.0）
resources.arsc                 1,740 B   （深色启动主题 / 应用名 Free Chart / 五档图标）
res/mipmap-*/ic_launcher.png              （5 档，48–192 px K 线图标）
assets/www/index.html         12,088 B   （标题与顶栏为 Free Chart；列表头部包 .list-head；图表工具条合并）
assets/www/style.css          18,183 B   （6 套主题 / 44px 触控 / v37 .timeline / v38 .list-head 折叠与紧凑工具条）
assets/www/app.js            140,362 B   （MA/EMA 参数、MACD、自由平移、发展历程/档案/里程碑、headOnScroll 折叠状态机）
assets/www/coins/*.png       1,368,951 B（270 个官方品种 logo，统一压成 64px）
assets/www/universe.js        28,993 B   （真实离线清单：crypto 200 / cn 100 / hk 200 / us 500）
assets/www/universe.json      66,054 B   （清单原始 JSON，数据溯源用）
assets/www/about.js           51,226 B   （单一资料源导出：45 品种 / 185 事件 / 24 档案 + meta 核验日期）
META-INF/*                              （签名块）
共 287 个条目
```

包内 `app.js` 含 `headOnScroll` / `btnReset` / `milestoneHTML`，已不含
`data-act="zoomin"`；`about.js` 内含 `timeline` / `archive` / `meta`，
`meta.app_name = Free Chart`。

---

## 二、安装方法

### 方式 A：手机直接安装（最常用）

1. 把 `android/dist/Free Chart.apk` 传到手机（微信/QQ/数据线/网盘均可）。
2. 在手机「文件管理」里点击该 APK。
3. 首次安装会提示「未知来源应用」→ 允许当前文件管理器/浏览器的「安装未知应用」权限。
4. 点击「安装」。系统可能提示「该应用来自未知开发者」，选择「仍要安装」。
   **安装器里显示的应用名是 `Free Chart`**。
5. 安装完成点击「打开」，首次进入会请求联网（不需要手动授权，INTERNET 为普通权限）。

### 方式 B：ADB 安装（开发者）

```bat
adb devices
adb install -r "C:\Users\13051\WorkBuddy\2026-11-07-00-14-41\FreeChart\android\dist\Free Chart.apk"
:: 覆盖安装保留数据用 -r；彻底重装先 adb uninstall com.freechart.app
adb shell am start -n com.freechart.app/.MainActivity
```

查看日志：`adb logcat -s AndroidRuntime:W WebView:W FreeChart:V`
（`FreeChart` 是保留的内部日志 tag，不影响用户可见名称。）

### 升级 / 卸载

- 升级：用**同一 keystore** 重新签名后 `adb install -r`，用户自选、置顶、排序、主题、
  搜索历史会保留（`SharedPreferences` 不清除）。v38 → v39(1.3.0) 是 versionCode 6 → 7 的覆盖升级，
  包名与签名证书均未变；文件名变了不影响覆盖安装。
- 卸载：`adb uninstall com.freechart.app` 或系统设置里卸载（在系统里找 `Free Chart`）。

---

## 三、技术路线与「不依赖桌面运行环境」说明

桌面端基于 PySide6 / Qt + CPython。经评估，本机没有 Android Qt 运行时与可用的
CPython-for-Android wheel，强行用 Qt for Android 会牺牲稳定性，因此**没有复用桌面 UI 代码**。
Android 端采用：

```
原生 Java Activity + WebView（系统组件）
  ├─ 本地 file:///android_asset/www/ 下的 HTML / CSS / JS UI（单列、竖屏、触摸优先）
  └─ Java Bridge "Native"：
       http(url, charset, cb)  后台线程池 HttpURLConnection，绕过 CORS，支持 GBK 解码
       get / set               SharedPreferences 持久化（键名与桌面端 config 对齐）
       copy / paste             系统剪贴板，用于配置导出 / 导入
       version / toast / finish
```

- 无 Python 解释器、无 Qt 库、无第三方 SDK、无 Gradle/NDK 依赖；仅依赖系统 WebView。
- 数据源与桌面端**完全相同**（见第五节），不是占位或模拟数据；发展历程与档案则来自
  同一份离线资料库导出的 `about.js`，完全不联网、不临时抓取。
- 配置迁移：设置页「导入配置（粘贴 JSON）」可直接接受桌面端
  `%APPDATA%/FreeChart/config.json` 里的 `symbols`、`pinned_symbols`、`sort_mode`、
  `sub_tabs`、`interval`、`last_tab`、`theme`、`chart_interval`、`chart_view_*` 等键。

---

## 四、兼容性验证结果（本轮实际执行）

| 验证项 | 方法 | 结果 |
| --- | --- | --- |
| 资源编译 | `aapt2 compile/link` | 通过，`resources.arsc` 含 `AppTheme`、应用名 `Free Chart` |
| Java 编译 | `javac --release 8` | 通过，无 error；`Native.version()` 返回 `1.3.0` |
| DEX 转换 | `d8 --min-api 29` | 通过（`classes.dex` 9,708 B） |
| 4 字节对齐 | `zipalign -p 4` / `zipalign -c -v 4` | 通过 |
| APK 签名 | `apksigner sign` + `verify --verbose` | `Verifies`，**v1 回退 + v2 + v3 均存在**，签名者 1 |
| 清单解析 | `aapt2 dump xmltree --file AndroidManifest.xml` | minSdk=29、targetSdk=34、portrait=1、versionCode=7/1.3.0、package 正确 |
| DEX 桥方法 | `classes.dex` 字符串核对 | 桥方法全部存在 |
| 包内资源 | `zipfile` 列举 | 276 个 www 资源（含 270 个品种 logo）+ dex + arsc 齐全，共 287 条目 |
| 前端语法 | `node --check app.js` / `about.js` | 均通过 |
| 逻辑回归（离线） | `node android/tests/test_app_logic.js` | **68 / 68 通过** |
| v34 功能补齐回归 | `node android/tests/test_app_v34.js` | **61 / 61 通过** |
| v35 批量行情容错回归 | `node android/tests/test_app_v35.js` | **11 / 11 通过** |
| v36 链上图表 / 股票自选回归 | `node android/tests/test_app_v36.js` | **25 / 25 通过** |
| v37 品牌 / 详情 / 发展历程回归 | `node android/tests/test_app_v37.js` | **20 / 20 通过** |
| **v38 列表折叠 / 工具条精简回归** | `node android/tests/test_app_v38.js` | **27 / 27 通过，RC=0**（折叠状态机、防抖阈值、顶部回弹、按钮删除、紧凑样式、触摸缩放保留） |
| 逻辑回归（真实接口） | `REAL=1 node android/tests/test_app_logic.js` | **74 / 75，两次复跑结果一致**：Rugcheck 链上报告或「真实链上价」两项之一偶发「请求超时」 |
| 真实接口连通 | Binance 24hr / 腾讯行情 / CoinLore / Binance K线 / 腾讯 K线 / Rugcheck | **前 5 个稳定返回有效数据**；Rugcheck 偶发超时，属上游波动 |
| 可安装性静态预检 | `python android/check_installable.py` | **17 / 17 通过**（label=`Free Chart`、v1 回退、v2+v3、4 字节对齐、276 个资源引用闭环、app.js 语法） |
| 桌面端回归 | `QT_QPA_PLATFORM=offscreen CT_OFFLINE=1` 跑 `tests/test_release_v4..v38.py` | **34 个脚本，0 失败，RC=0**（含 v38 20/20、v37 37/37、v36 24/24） |
| 桌面 EXE | `python -m PyInstaller FreeChart.spec --noconfirm --clean` | RC=0，`dist/Free Chart.exe` 55,250,744 B，兼容副本字节一致 |

> **联网回归的诚实说明**：`REAL=1` 两次均为 74/75，失败项在「Rugcheck 链上报告」
> 与「真实链上价可解析」之间交替，是该上游响应不稳定而非产品逻辑退化。
> 68 项离线逻辑、5 个其他真实接口、桌面 34 套与手机端 6 套离线回归均全绿。
> 产品内对该接口已有失败退避 / 最多 3 次自动重试 / 轻量「重试」按钮 /
> 缓存快照回退，不会弹模态窗口或编造价格。

### 已验证的兼容性设计点

- **Android 10+**：minSdk 29；签名 v3 自 Android 9（API 28）起受支持，另有 v2 与 v1 回退。
- **多分辨率 / 屏幕比例**：flex + `viewport-fit=cover`、`env(safe-area-inset-*)`，
  Canvas 按 `devicePixelRatio` 重设位图；`@media (min-width: 600px)` 时主容器限宽居中。
- **竖屏**：Manifest `screenOrientation="portrait"` + `configChanges` 声明方向/密度变化。
- **深色启动**：`AppTheme` 的 `windowBackground` 与 CSS 深色主题一致，冷启动不闪白屏。
- **触摸优先**：可点区域 ≥44px（v38 工具按钮视觉 36px + `::after` 隐形热区补到 44px）；
  点击进图表、长按 500ms 出行操作、滑动加载下一页、图表单指平移 / 双指缩放；
  菜单兼容系统右键，无 `:hover` 依赖。
- **v38 顶部折叠**：折叠只改 `max-height` / `opacity` / `transform`，不重建 DOM；
  `.list` 关闭滚动锚定；滚动事件里只做算术，状态翻转才写一次样式；
  方向累计有滞回阈值，惯性滚动与手抖不会来回切换。
- **发展历程可离线阅读**：45 个品种 / 185 条事件随 APK 内置，默认 6 条、可展开全部；
  每条带日期与来源标签，未收录品种明确留白，不套用市场通用说明。
- **网络与启动优化**：首屏只挂载并请求 60 行；120ms 请求合并 + 同 key 3 秒去重；
  断网显示上次真实快照并标注「缓存」；失败退避、最多 3 次自动重试，之后只显示轻量
  「重试」按钮，不弹模态窗口；HTTP 全在 Java 后台线程池执行。

---

## 五、数据源与「不编造数据」约束

| 用途 | 接口 | 实测 |
| --- | --- | --- |
| 加密货币行情 | `https://data-api.binance.vision/api/v3/ticker/24hr?symbols=[...]` | HTTP 200，真实价格/涨跌幅/成交额 |
| 股票行情 / 市值 / 换手 / PE / PB | `https://qt.gtimg.cn/q=...`（GBK） | HTTP 200，88 字段；A 股成交额万元已换算为元，港股/美股本已是元/美元不再乘 1e4 |
| 加密市值 / 供应量 / 排名 | `https://api.coinlore.net/api/tickers/` | HTTP 200 |
| 加密 K 线 | `https://data-api.binance.vision/api/v3/klines` | HTTP 200 |
| A股 / 港股 K 线 | `web.ifzq.gtimg.cn/.../(hk)fqkline/get` | HTTP 200，`qfqday` |
| 美股 K 线 | `stock.finance.sina.com.cn/usstock/api/...` | 桌面端同款接口 |
| 链上合约报价 | `https://api.rugcheck.xyz/v1/tokens/{addr}/report` | HTTP 200 时返回真实 USD 价/流动性/持有者/供应量；本轮偶发超时 |
| **品种发展历程 / 档案（离线）** | `data/timeline.py` → `tools/export_profile_db.py` → `assets/www/about.js` | 45 品种 / 185 事件 / 24 档案，核验日期 2026-11-14 |

- 详情页 **9 个分区**：① 行情数据 ② 市值与估值 ③ 供应·成交·流动性
  ④ 项目用途/代币经济学 或 公司业务/财务 ⑤ 项目公司介绍 ⑥ 数据来源与更新时间
  ⑦ 发展历程 · 里程碑 ⑧ 品种档案 ⑨ 行情里程碑 · 真实历史数据。
- **接口未返回的字段一律显示「— 暂无公开数据」**，不填 0、不估算、不倒推、
  不拿市场通用说明冒充具体品种资料。
- **发展历程日期按可信粒度记录**（年 / 月 / 日 / 年代），不硬补精确日期；
  每条带来源标签，全库标注核验日期。
- **行情里程碑一律叫「区间」**：由真实月 K 线或链上本机真实报价采样计算，
  写明统计起点与样本根数，绝不冒充上市以来全历史。桌面图表同理：只有真正
  回溯到上市首根且为日线以上周期才允许标 ATH/ATL，其余一律 LH/LL「区间高低」。
- 腾讯快照字段按市场区分：A 股 `f[47]/f[48]` 为涨停/跌停价、成交量单位「手」；
  港股/美股 `f[48]/f[49]` 为 52 周高/低、成交量单位「股」；行情时间 `f[30]` 支持三种真实格式。

---

## 六、桌面端功能对照

| 功能 | 桌面端 | Android 端 |
| --- | --- | --- |
| 四个市场 + 自选/全部子页 | ✅ | ✅ |
| 14 种排序（含升降序、自定义、默认） | ✅ | ✅ |
| 搜索筛选且排序后保持 | ✅ | ✅ |
| 置顶 / 取消置顶，跨页面与刷新保留 | ✅ | ✅ |
| 按需加载 / 滚动分页 / 请求去重 | ✅ | ✅ |
| **顶部选项卡 / 搜索框随滚动折叠** | ❌ 桌面顶部为固定标题栏，无此需求 | ✅ v38 `.list-head` 上滑收起、下滑展开 |
| **图表工具条精简（无 ＋/－ 缩放按钮）** | ✅ 桌面用滚轮缩放 | ✅ v38 一行三枚紧凑按钮，双指捏合缩放 |
| 详情 9 分区（含发展历程 / 档案 / 里程碑） | ✅ | ✅ |
| 品种发展历程离线资料库（45 品种 / 185 事件 / 24 档案） | ✅ | ✅ 共用同一份导出的 `about.js` |
| 交易所快照真实字段（成交额单位 / 行情时间 / 涨跌停 / 52 周高低） | ✅ | ✅ |
| 用户可见品牌与交付文件名 `Free Chart` | ✅ 窗口 / 顶栏 / 托盘 / EXE 名 / 自启项名 | ✅ 启动器 / 页面标题 / APK 名 |
| K 线多周期 / 锚点缩放 / 视口记忆 / 自由平移 | ✅ | ✅ Canvas，触摸缩放 |
| ATH/ATL 与区间 LH/LL 口径分离 | ✅ `_extremes_trusted` 门控 | ✅ 里程碑写明「区间」与统计起点 |
| 底部导航 / 主题 6 套 / 刷新间隔 5–300 秒 | ✅ | ✅ |
| 配置导出导入（可吃桌面 config.json） | 配置文件 | ✅ 剪贴板 + 文本框 |
| 链上合约币种收藏 / 查看价格 / 真实采样走势 | ✅ | ✅（不画假蜡烛） |
| 股票市场「自选」子页 / 搜索结果独立页 + 最近 100 条历史 | ✅ | ✅ |
| 品种官方 logo / 图标 | ✅ | ✅ APK 内置 270 个 64px 图标 |
| MA / EMA 可设参数 / BOLL / MACD / VOL | ✅ | ✅ |
| 托盘价格条 / 任务栏小工具 / 开机自启 / 看板娘 | ✅ | ❌ Windows 专属，设置页已明示 |

---

## 七、未完成的实机测试（诚实说明）

本机环境检查结果：

```
adb devices        → 已启动 daemon，设备列表为空
AVD / system-images → 未安装，无可用模拟器镜像
```

因此**以下项目没有在本机完成，不能声称通过**：

1. 真机 / 模拟器上的 `adb install` 与首次冷启动耗时；
2. 各品牌 ROM 的 WebView 版本差异、`file://` 本地资源加载与 JS 桥行为；
3. 真实蜂窝网络 / 弱网 / 飞行模式下的失败重试与缓存回退体验；
4. 刘海屏、挖孔屏、折叠屏、`safe-area-inset` 与系统手势导航的实际表现；
5. 长时间后台/切前台后的内存占用与电池消耗；
6. **v38 折叠动画在真实惯性滑动 / 高刷新率屏幕上的手感**（离线回归只验证状态机与样式，
   动画流畅度需真机目视确认）。

静态预检 17/17 只能说明 APK 可被 PackageManager 解析，**不等于实机安装通过**。

### 拿到手机后的自测清单（建议按序）

1. `adb install -r` 成功且桌面出现「**Free Chart**」图标；从 v37 覆盖升级时自选不丢；
2. 冷启动 2 秒内出现行情列表，状态栏显示「已更新 · Binance / 腾讯行情」；
3. 切「全部」→ 首屏 60 行流畅，滚动到底自动追加，无连续弹窗/白屏；
4. **上滑列表**：市场 / 子页 / 搜索框平滑收起、内容顶上来不跳位；**下滑一点**立即展开；
   快速来回小幅滑动不应来回抖；滚回顶部时必定展开；
5. **进图表页**：不再有「＋ 放大 / － 缩小」按钮，只有一行「最新 / 详情 / 指标」小按钮；
   双指捏合能缩放，单指能左右自由平移，点「最新」回到最右但不改变缩放倍数；
6. 切换周期能出真实蜡烛，双指缩放以当前位置为中心（不跳到最右）；
7. 详情 **9 个分区**齐全，缺失项显示「— 暂无公开数据」；
8. **BTC / 贵州茅台 / 腾讯** 的详情：发展历程有日期与来源标签、可展开全部；
   档案有真实字段；行情里程碑写明「区间」与统计起点；未收录品种显示「资料库未收录」；
9. **桌面端小时间范围**：图表右上角应显示「区间高低」，局部极值只标 LH/LL；
10. 开飞行模式刷新 → 显示上次真实快照并带「缓存」标记 +「重试」按钮，不反复弹窗；
11. 设置页改主题/刷新间隔 → 杀进程重启仍保留；导出 JSON 后导入能恢复自选与置顶；
12. 系统返回键：详情 → 图表/设置 → 行情 → 退出，逐级回退不出错。

---

## 八、遗留问题

- **签名证书为本地自签名**：未上架应用商店；换机器重新构建会产生不同证书，需保留
  `android/debug.keystore` 才能覆盖升级。
- **Rugcheck 上游偶发超时**：`REAL=1` 两次均 74/75，失败项在 Rugcheck 报告与真实链上价
  之间交替；其余 5 个真实接口与全部离线回归稳定通过。产品内已有退避重试与缓存回退，
  链上品种取不到数据时显示「— 暂无公开数据」，不编造价格或假 K 线。
- **v38 桌面批量弹窗根因（已修复，结论留档）**：不是循环渲染、不是事件重复绑定、
  也不是接口重复回调（`core/updater.py` 的 120ms burst + 在途去重已挡住）。
  真正来源是 Qt 原生 `QToolTip` / `QTipLabel`：分批建行时鼠标下的子 QLabel 反复
  `show/hide/重设 tooltip`，Qt 连发 `QEvent.ToolTip`。旧版把过滤写在父行
  `TickerWidget.event()`，但事件在子 QLabel 处就被 `QWidget::event()` 消费，
  父行根本收不到；加上全局 bool 在多市场并行建行时被先结束的链提前打开、
  链异常还会永久卡住。现改为**应用级 `installEventFilter` + 引用计数 +
  链收尾 `try/finally` 释放**，并给行信号加 `Qt.UniqueConnection` 作防御。
  桌面 `tests/test_release_v38.py` 20/20 覆盖：子控件 tooltip 拦截、无新增顶层窗口、
  多链计数、异常恢复、其它弹窗源未被触发。
- **元数据覆盖度**：CoinLore 前 500 名覆盖绝大多数加密清单；股票市值依赖腾讯批量
  行情（单次最多 300 只）。未取到的品种排末尾，属预期行为。
- **发展历程资料库覆盖度**：45 品种有里程碑、24 品种有档案，核验日期 2026-11-14；
  扩充时应更新 `data/timeline.py` 后重跑 `tools/export_profile_db.py` 并重建 APK，
  避免两端漂移。
- **腾讯行情 GBK 解码**由 Java 桥完成；上游若改 UTF-8 需同步调整 `charset`。
- **美股分钟线依赖新浪接口**，偶发 JSONP 包裹已做兼容；上游变更需同步 `parseSinaRows()`。
- **桌面端托盘价格条、看板娘、划线指标**未移植，属桌面专属功能。
