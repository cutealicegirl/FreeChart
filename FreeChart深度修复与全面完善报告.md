# FreeChart 深度修复与全面完善报告

- 项目：`FreeChart`（对外品牌 Free Chart），仓库 `https://github.com/cutealicegirl/FreeChart`
- 工作分支：`fix/deep-review-20261115`（独立分支，**全程未提交、未推送、未创建 PR、未改仓库设置**，等待审查授权）
- 基线提交：`0fa352c chore(android): 版本同步至 1.3.0 / versionCode 7`
- 报告日期：2026-11-16
- 执行环境：Windows 11 / Python 3.13.12 / PySide6 6.12.0 / Node 22 / JDK 21 / Android SDK build-tools 34+36
- 数据环境说明：腾讯 K 线接口本环境返回 501、Yahoo Finance 403、Binance 直连超时；东财分红送配 API、新浪美股接口可达。所有"真实数据验证"均标注实际使用的数据源；无法联网验证的项目明确标 NOT RUN / BLOCKED，不编造数据。

---

## 1. 修复总览

本轮在既有深度修复基础上，完成了四类最高优先级核心问题的修复、全部行情页增量渲染、缓存与指标一致性、公司行为复权底层机制，以及本轮新补齐的双端一致性与回归测试。**所有改动都经过"先读完整上下文 → 确认问题真实存在 → 局部修复 → 实测验证 → 全量回归"流程**。

### 已实际完成的修复（12 项）

| # | 修复项 | 优先级 | 状态 |
|---|---|---|---|
| 1 | Android K 线异步请求竞态（chartLoadSeq 序号守卫）| 最高 | ✅ 已修复 + 专项测试 |
| 2 | Windows Alt+F4 隐藏托盘后刷新停止（调度器生命周期）| 最高 | ✅ 已修复 + 专项测试 |
| 3 | QThread 退出资源释放（统一 safe_stop_thread）| 最高 | ✅ 已修复 + 专项测试 |
| 4 | 市值排序元数据失败无法重试（IDLE/LOADING/SUCCESS/FAILED 状态机）| 最高 | ✅ 已修复 + 专项测试 |
| 5 | Android 列表 innerHTML 全量替换（rAF 合帧 + 增量补丁 + 标签解耦）| 第二 | ✅ 已修复 + 专项测试 |
| 6 | 行情时间戳单调性（旧快照不得覆盖新快照）| 第三 | ✅ 已修复 + 专项测试 |
| 7 | Python/JS 指标公式一致性（共用黄金数据集）| 第四 | ✅ 确认公式一致 + 标准化测试 |
| 8 | 公司行为/复权底层机制（拆股/反向拆股/分红送配/代币迁移）| 用户新增专项 | ✅ 已建立通用引擎 + 真实数据验证 |
| 9 | 缓存 schema 版本化 + 复权指纹失效 | 第三/复权 | ✅ 已修复 + 测试 |
| 10 | 跨端导入键名不一致（onchain_symbols ↔ onchain）| 第六 | ✅ 已修复 + 测试 |
| 11 | 双端 K 线周期集合不一致（crypto 缺 30m/3d/1y、US 缺分钟线、CN 缺 m1）| 第六 | ✅ 已对齐 + 专项测试 |
| 12 | 桌面美股 m1 请求映射错误（键名写成 1m 导致取成 5 分钟）| 第六（新发现）| ✅ 已修复 + 测试 |

### 经检查确认不存在 / 属既有设计取舍的项

- **Python 与 JavaScript 的 MA/EMA/BOLL/MACD 公式**：逐项比对确认一致（EMA 前 n 根 SMA 初始化、BOLL 总体标准差 ddof=0、MACD 柱体 ×2），实际用同一黄金数据集双端跑出相同结果，无需改公式。
- **桌面端 findChildren() 滥用**：仅存在于布局重排时的一次性可见性校正（每轮 O(n) 但次数可控），不存在每帧高频遍历；1000 品种实测重排 8ms 量级，未构成瓶颈。
- **重复定时器/重复信号注册**：`RefreshScheduler` 已用 `_running` 幂等保护，测试确认多次 `start()` 不产生叠加定时器。
- **桌面行情请求乱序**：桌面刷新是严格单在途（同一时刻仅一个 FetchWorker），不存在 K 线竞态；竞态风险仅在 Android 多并发路径，已按序号守卫修复。

---

## 2. 已修复问题

### 2.1 Android K 线异步请求竞态

- **原因**：`loadChart()` 的 Promise 回调不校验请求是否仍是当前请求，连续切换品种/周期时旧请求晚返回会覆盖 `CANDLES` 并重绘当前图表；链上请求 `refreshOnchain()` 同样会误触发重绘；`finally` 可能关闭新请求的 loading。
- **修改文件**：`android/assets/www/app.js`
- **具体位置**：全局 `chartLoadSeq` / `chartLoadIsCurrent()`；`loadChart()`（递增 seq、捕获 sym/iv 快照、`.then`/`.catch` 双重校验）；`refreshOnchain()`（捕获 `chartSeqAtStart`，旧请求只写行情不重绘）
- **方案**：递增序号 + (序号,品种,周期) 三元组快照校验；成功/失败回调均校验；旧请求不得修改当前 `CANDLES`/标题/loading/错误提示。不依赖 AbortController（网络层无此能力），纯靠序号保证正确性。
- **行为变化**：连续快速切换 10 品种并倒序触发回调，最终图表数据始终属于当前选中的品种和周期。

### 2.2 Windows 隐藏托盘后刷新停止

- **原因**：旧 `closeEvent()` 在判断是否真正退出前就停掉 scheduler，隐藏到托盘后定时器未恢复。
- **修改文件**：`ui/main_window.py`、`core/updater.py`
- **具体位置**：`closeEvent()`（仅 `_force_quit` 时 `scheduler.stop()`，否则 `event.ignore(); self.hide()` 且调度器继续运行）；`reveal()`/`toggle_visible()`（恢复时 `scheduler.start()`）；`RefreshScheduler.start()`（新增幂等恢复）、`stop()`、`_tick()`（`_running=False` 直接返回）
- **方案**：严格区分"隐藏"与"退出"，调度器提供完整 start/stop 生命周期，幂等防重复启动/重复注册，`_tick()` 忽略 stop 后的残留触发。
- **行为变化**：启动→刷新→Alt+F4 隐藏→托盘恢复→连续两个周期持续刷新→再隐藏→恢复→正常退出，全程无停止、无重复请求；退出时无残留任务。

### 2.3 QThread 退出与资源释放

- **原因**：线程 `wait()` 超时后提前清空引用，而线程仍在网络请求中，父对象析构时 Qt fail-fast 报 `QThread: Destroyed while thread is still running` 并 abort。
- **修改文件**：新增 `core/thread_cleanup.py`；修改 `core/live_feed.py`、`data/prefetch.py`、`ui/chart_view.py`、`ui/main_window.py`
- **具体位置**：`safe_stop_thread()`（请求中断→有上限等待→复查 isRunning→仍在运行则 `setParent(None)` + 加入 `_ORPHAN_THREADS` 强引用保活，已结束则 `deleteLater()`）；`LiveFeed.shutdown()`、`PrefetchWorker.stop()`（返回清理是否干净）、`chart_view.shutdown_threads()`、`main_window.stop_prefetch()`/`quit_app()`
- **方案**：统一收尾范式，绝不无限延长 wait；duck-typed worker 用 `getattr` 兼容；信号断开容错。
- **行为变化**：模拟 1.2s 不可中断请求 + 200ms 等待上限，线程超时后成功脱离对象树并保活，无崩溃/警告。

### 2.4 市值排序元数据失败重试

- **原因**：请求开始就把 `_rank_ready[key]=True`，失败/离线空数据后永久阻止重试。
- **修改文件**：`ui/main_window.py`（`ui/main_window.py:1470-1568`）
- **具体位置**：`_rank_state`/`_rank_seq`/`_rank_fail`/`_rank_next_at`（每市场独立）；`_rank_data_valid()`；`_ensure_rank_meta()`；`_on_rank_meta()`
- **方案**：IDLE→LOADING→SUCCESS/FAILED 状态机；只有数据含真实数值（cap/turnover/listed_year 任一非空）才 SUCCESS；FAILED 按 5/10/20…秒指数退避（上限 120s）重试；每市场请求带序号防旧结果覆盖新结果；用"请求所属市场"重排防切页错配；离线 None 不覆盖已有真值；兼容旧式直接调用契约（test_release_v28）。
- **行为变化**：断网→排序失败→恢复网络→再次排序能重新取到真实元数据，不再永久停留缺失态。

### 2.5 Android 列表增量渲染与合帧

- **原因**：`renderList()` 每次行情刷新都整体 `innerHTML=` 替换，市场/子页按钮每轮重建；已定义的 `scheduleRender()`（rAF 合帧）从未被调用。
- **修改文件**：`android/assets/www/app.js`
- **方案**：`scheduleRender()` 接线到 `refreshTickers`/`refreshOnchain`/`loadMore` 热路径；`renderList(opts)` 增加 `skipTabs`，合帧刷新不重建标签；可见行集合/顺序不变时只补丁变化行的 `.info`/`.right`，结构不符时回退整体替换；用户同步交互（点击排序/切市场）保留原行为以维持既有测试契约。
- **行为变化**：连续刷新不再整体重建 DOM，图标节点得以保留，标签按钮不再重复重建。

### 2.6 行情时间戳单调性

- **原因**：Android 图表/列表/链上三类请求并发写 `TICKERS`，旧请求晚返回可能覆盖新快照。
- **修改文件**：`android/assets/www/app.js`
- **具体位置**：`_quoteIsStale()` 守卫；`applyTickers()` 与链上批量写回路径（1871 行附近）
- **方案**：仅当新旧时间戳都有效且入站时间戳严格更旧时拒绝；无效时间戳不拦截，保证兼容。
- **行为变化**：旧快照（ts=1000）写入后 New（ts=2000）仍为最新，再灌入更旧快照被拒。

### 2.7 公司行为 / 复权底层机制（用户新增专项）

- **原因**：项目此前是"半复权"状态——A股/港股日线靠腾讯 `qfq` 单参数兜底（且只调价不调量），美股新浪接口与所有分钟线返回未复权原始价，缓存无复权维度、无公司行为主数据。
- **真实数据证据**（新浪美股日线实测）：AAPL 2020-08-31 499.23→129.04（≈1/4，288% 假跳空）；TSLA 2022 1拆3（201%）；NVDA 2024 1拆10（893%）；AMZN 2022 1拆20（1861%）。复权后假跳空分别降至 3.3%/0.3%/0.7%/2.0%。
- **修改文件**：新增 `data/corporate_actions.py`（事件模型）、`data/corporate_actions.json`（已核实登记库）、`data/price_adjustment.py`（复权数学核心）、`data/corporate_actions_fetch.py`（东财分红送配抓取）；修改 `data/klines.py`、`data/kline_cache.py`、`data/history_stats.py`、`android/assets/www/app.js`、`FreeChart.spec`
- **方案要点**：
  - 区分原始/前复权价，事件带 ex-date、ratio、来源、confidence；
  - **经验门控**：仅当观测跳空≈拆股比例才认定未复权，已复权数据自动跳过 → 从根上防二次复权；
  - 价格 ÷ 因子、成交量 × 因子，成交额守恒；
  - qfq 路径只补成交量口径（价已复权）；
  - 缓存 schema v2 + 复权事件指纹，旧缓存强制失效，DB 迁移兼容；
  - 纯现金分红因缺可信 prev_close 只标记不猜测；不插值、不删异常 K 线。
- **行为变化**：拆股前后价格正确衔接、量纲一致，指标/统计基于复权价重算，双端口径统一。

### 2.8 跨端配置键名不一致（本轮新发现）

- **原因**：Android 有"导入桌面 config.json"功能，但白名单键是 `onchain`，桌面导出键是 `onchain_symbols`——链上收藏的代币代码/名称在跨端导入时静默丢失。
- **修改文件**：`android/assets/www/app.js`
- **具体位置**：新增 `normalizeImportedConfig()`，在 CFG 初始化读取与 `importConfig()` 两处调用
- **方案**：导入时若 `onchain_symbols` 存在而 `onchain` 缺失则回填，只在新键缺失时回填保证幂等，保留两端原生键。
- **行为变化**：粘贴桌面 config.json 可正确恢复链上品种元数据。

### 2.9 双端 K 线周期集合不一致（本轮新增）

- **原因**：Android crypto 缺 `30m`/`3d`/`1y`，US 缺全部分钟线，CN 缺 `m1`；数据层其实已具备能力，只是 UI 周期表未暴露。
- **修改文件**：`android/assets/www/app.js`、`data/klines.py`
- **方案**：Android `CRYPTO_INTERVALS` 补齐 30m/3d/1y、`US_MINUTES` 补齐 m1/m5/m15/m30/m60、`CN_MINUTES` 补 m1；`intervalsFor()` 按 us 返回分钟线+日线以上，港股维持仅日线以上；Android 年K 走 1M 月线本地聚合（与桌面一致，不透传 Binance 不支持的 1y）；修正桌面 `_US_SINA_TYPE` 键名 `1m`→补 `m1`（原选 1 分实际取 5 分数据）。
- **行为变化**：四市场周期集合双端完全一致（7 项断言全部通过）。

---

## 3. 性能优化结果

**全部为 offscreen 环境实测（1000 个模拟品种，无真实网络/图标 IO），未测量项明确标注，绝不编造。**

| 指标 | 实测值 | 说明 |
|---|---|---|
| 首屏加载耗时 | 698.6 ms | 构造含 1000 品种的主窗口并建首屏行 |
| 首屏创建行对象数 | 60 | = PAGE_SIZE，按页懒创建生效 |
| 首屏布局挂载行数 | 60 | 未一次性预建 1000 行 |
| 滚到末页耗时 | 5831 ms | 翻 16 页（每页 +60） |
| 末页累计行对象数 | 1000 | 见下方"已知限制" |
| 末页布局挂载行数 | 1000 | 见下方"已知限制" |
| 100 次连续重排耗时 | 834 ms（平均 8.34 ms/次）| 刷新路径不重建行对象 |
| 刷新后行对象数 | 1000 → 1000 | ✓ 无累积 |
| 全量倒序排序耗时 | 105 ms | 1000 行重排 |
| 运行中 QThread 残留 | 0 | 退出无泄漏 |

**已知限制（如实报告，未擅自重构）**：桌面"全部"页是"按页加载 + 累积挂载"架构，`_page_limit` 单调增长，浏览到末页后 1000 行都会挂在布局中（不是视口虚拟化）。这符合"加载更多"的产品语义，且刷新不会额外累积对象、重排耗时可接受（8ms 级）；但严格意义上不满足"视口外行不占 UI 对象"的虚拟列表目标。改造成 `QListView + QAbstractListModel + QStyledItemDelegate` 属于高风险大重构，按用户"不要盲目重构、局部达标优先"原则，本轮**未擅自改动**，列为待授权的可选优化（见第 8 节）。

- **未测量项（NOT RUN）**：CPU 占用、滚动帧率、真实内存增量、DOM 节点数（Android 侧）——需真机或带 GUI 的性能分析工具，本环境不具备。
- **Android DOM 节点量化**：增量渲染与 rAF 合帧已实现并有 7 项专项测试（`test_app_render_opt.js`），但未在真机/webview 中量化 DOM 节点数与帧率。

---

## 4. 双端一致性结果

### Windows 验证情况
- 周期集合：`CRYPTO_INTERVALS`/`STOCK_INTERVALS`/`US_INTERVALS`/`HK_INTERVALS` 定义清晰，年K由月线聚合，美股 m1 映射已修正。
- 指标公式：MA/EMA/BOLL/MACD 与 JS 端公式一致，黄金数据集比对通过。
- 复权：kline 获取四路径全部接入复权引擎，缓存带 schema+指纹。
- 排序：置顶优先 → 自定义/市值/涨跌，多个置顶保持先后顺序。

### Android 验证情况
- 周期集合：本轮补齐后与 Windows 四市场完全一致（7/7 断言）。
- 指标公式：与 Python 端共用黄金数据集，结果一致。
- 复权：美股原始价走完整复权、腾讯 qfq 路径补成交量、年K走月线聚合，与桌面同口径。
- 配置导入：修正 onchain_symbols 别名，链上元数据可跨端恢复。
- 排序：`sort_reverse` 为 Android 独有"翻转升/降序"开关，桌面无对应字段。

### 仍存在的差异（如实列出）
1. **`sort_reverse` 开关**：Android 有独立升降序翻转开关，桌面排序方向内嵌在 `sort_mode` 循环中，行为语义不同。属既有交互设计差异，改动会影响用户习惯，未擅自统一。
2. **年K聚合细节**：两端都由月线聚合，但桌面 `_aggregate(monthly,"year")` 与 Android `aggregate(rows,'1year','month')` 的首根时间戳/标签处理实现不同，极端边界可能有细微差别，未做逐根对齐测试。
3. **设置字段集合**：桌面有大量窗口/看板娘/托盘专属字段（约 40+），Android 无对应 UI；`IMPORT_KEYS` 只平移双方共有键，这是设计取舍而非 bug。
4. **缓存有效期**：桌面 K 线 15min/预缓存 6h，Android 走 WebView 自有策略，`cache_keep_days` 键名一致但实现独立。

---

## 5. 测试结果

标记约定：**PASS** 实际通过 / **FAIL** 实际失败 / **NOT RUN** 未运行 / **BLOCKED** 环境限制无法运行。

### 5.1 本轮新增专项测试（全部实际运行）

| 测试 | 命令 | 结果 |
|---|---|---|
| 四类核心修复回归（QThread/调度器/元数据/时间戳）| `QT_QPA_PLATFORM=offscreen python tests/test_core_regressions.py` | **PASS 21/21** |
| 双端周期一致性 | `python tests/test_cross_platform_intervals.py` | **PASS 7/7** |
| 公司行为复权（Python）| `python tests/test_corporate_actions.py` | **PASS 42/42** |
| 指标一致性（Python 侧）| `python tests/test_indicator_consistency.py` | **PASS** |
| 指标一致性（JS 侧）| `node android/tests/test_app_indicator_consistency.js` | **PASS** |
| Android K 线竞态 | `node android/tests/test_app_kline_race.js` | **PASS** |
| Android 增量渲染 | `node android/tests/test_app_render_opt.js` | **PASS 7/7** |
| Android 公司行为 | `node android/tests/test_app_corp_actions.js` | **PASS** |
| 跨端导入（含于逻辑测试）| `node android/tests/test_app_logic.js` | **PASS 69/69** |
| 1000 品种性能测量 | `python tests/test_perf_1000.py` | **PASS（实测数据见第 3 节）** |

### 5.2 全量回归

- **Android**：10 套测试全部通过（约 260+ 项断言），含全部新增专项。命令：逐个 `node android/tests/test_*.js`。
- **桌面**：全量离线套件运行汇总见下方"全量回归汇总"行（网络依赖测试在 `CT_OFFLINE=1` 下按既有基线处理）。
- **既有失败基线**：`test_chart.py`（真实网络 K 线）、`test_chart_edit.py`（提示词长度断言）、`test_phase7_network.py`、`test_phase7_resource.py` —— 已用干净 worktree 在基线提交 `HEAD` 上复跑，**这 4 项在修改前即失败**（网络超时 / 提示词过长 / 缺 `ADAPTER_CLASSES`），本轮改动零回归。

> 全量回归汇总（离线模式 `QT_QPA_PLATFORM=offscreen CT_OFFLINE=1`，逐文件独立运行）：**51 通过 / 4 失败**。4 个失败项为 `test_chart.py`、`test_chart_edit.py`、`test_phase7_network.py`、`test_phase7_resource.py`，已确认均为既有基线失败（见上），本轮改动零回归。命令：
> ```bash
> export QT_QPA_PLATFORM=offscreen CT_OFFLINE=1
> for f in tests/test_*.py; do timeout 70 python "$f"; done
> ```

### 5.3 构建验证

| 项目 | 命令 | 结果 |
|---|---|---|
| Python 全量语法检查 | `python -m py_compile`（所有 .py）| **PASS，0 失败** |
| JS 全量语法检查 | `node --check`（所有 .js）| **PASS，0 失败** |
| Android APK 构建 | `python android/build_apk.py` | **PASS**，生成 `android/dist/Free Chart.apk`（1,539,879 字节），通过 Android 10-14 v3 签名校验与旧版 v1 回退校验 |
| Windows PyInstaller 打包 | — | **BLOCKED**：环境未安装 PyInstaller（`import PyInstaller` 失败）。已确认 `FreeChart.spec` 的 `datas` 含新增 `corporate_actions.json`、`hiddenimports` 含新增模块，打包配置已就绪，但未实际产出 EXE |
| 真机兼容性自测 | — | **NOT RUN**：无 Android 真机（对应任务 #93 历史遗留） |

---

## 6. 尚未解决的问题

1. **桌面"全部"页视口虚拟化**：翻到末页仍挂载全部已加载行（1000 品种实测 1000 行挂载），未做 `QAbstractListModel` 级虚拟列表。属高风险重构，需用户授权（见第 8 节）。
2. **EXE 实际打包验证**：环境无 PyInstaller，未产出 Windows 安装包；spec 配置已就绪但未验证冻结后资源路径（已按 `_MEIPASS` 惯例处理，`corporate_actions.py` 已兼容冻结运行）。
3. **真机验证**：APK 已构建并通过签名校验，但未在真实 Android 设备做兼容性/图表/网络自测（任务 #93）。
4. **纯现金分红复权**：因缺可信除权日前收盘价，只标记异常不主动复权（遵守"不猜测比例"红线）；如需精确复权需接入权威 prev_close 数据源。
5. **腾讯 qfq 成交量补量的真实验证**：本地构造数据验证了 `adjustVolumeOnly` 逻辑，但腾讯接口本环境返回 501，未能用真实 A 股 qfq 数据端到端验证。
6. **年K聚合细节**：双端都由月线聚合，但未做逐根对齐测试（见第 4 节差异 2）。
7. **网络恢复自动补充刷新**：已实现请求去重/退避/时间戳单调性，但"断网→恢复→自动补刷"的完整自动化回归在桌面侧仅覆盖调度器退避逻辑，未做端到端网络模拟。

> 用户任务清单中历史遗留的 #130（详情页单位标注+滚动）、#131（README 精简）、#132（支撑阻力仅 4h+ 显示）属于更早的独立需求，非本次深度修复范围，未纳入本轮改动。

---

## 7. 修改文件清单

### 修改的既有文件（11 个）
| 文件 | 修改原因 |
|---|---|
| `ui/main_window.py` | 隐藏/退出生命周期、线程安全收尾、元数据状态机、桌面 m1 映射相关 |
| `core/live_feed.py` | LiveFeed.shutdown 接入统一线程收尾 |
| `core/updater.py` | RefreshScheduler 幂等 start/stop、stop 后残留触发保护 |
| `data/prefetch.py` | PrefetchWorker.stop 返回清理结果、中断检查 |
| `ui/chart_view.py` | 指标函数抽出、shutdown_threads 统一收尾 |
| `data/klines.py` | 复权引擎接入四路径、qfq 补量、年K聚合、m1 映射修正 |
| `data/kline_cache.py` | schema v2 + 复权指纹失效 + DB 迁移兼容 |
| `data/history_stats.py` | 统计标注复权口径 |
| `android/assets/www/app.js` | K 线竞态守卫、增量渲染、时间戳单调性、复权、跨端键名、周期对齐 |
| `android/tests/test_app_logic.js` | 追加跨端导入回归断言 |
| `FreeChart.spec` | datas 增补 corporate_actions.json、hiddenimports 增补新模块 |

### 新增文件
| 文件 | 用途 |
|---|---|
| `core/thread_cleanup.py` | 统一 QThread 安全收尾工具 |
| `core/indicators.py` | 纯函数指标模块（PySide6 无关，供跨端测试） |
| `data/corporate_actions.py` / `.json` | 公司行为事件模型 + 已核实登记库 |
| `data/price_adjustment.py` | 复权数学核心（经验门控/量价一致/幂等） |
| `data/corporate_actions_fetch.py` | 东财分红送配抓取与解析 |
| `tests/test_core_regressions.py` | 四类核心修复回归 |
| `tests/test_corporate_actions.py` | 公司行为复权专项（42 项） |
| `tests/test_indicator_consistency.py` + `tests/fixtures/indicator_golden.json` | 指标黄金数据集与一致性 |
| `tests/test_cross_platform_intervals.py` | 双端周期一致性 |
| `tests/test_perf_1000.py` | 1000 品种性能测量 |
| `android/tests/test_app_kline_race.js` | K 线乱序返回回归 |
| `android/tests/test_app_render_opt.js` | 增量渲染/合帧回归 |
| `android/tests/test_app_indicator_consistency.js` | JS 侧指标一致性 |
| `android/tests/test_app_corp_actions.js` | Android 复权专项 |
| `复权修复报告.md` | 复权专项详细报告 |
| `FreeChart深度修复与全面完善报告.md` | 本文件 |

所有改动保留在独立分支、未提交，可用 `git diff` 完整审查、`git checkout -- <file>` 单文件回滚。

---

## 8. 最终建议（下一阶段最值得做的 3-5 项）

1. **[最高价值] 桌面"全部"页视口虚拟化**：用有限行对象池 + 可见区域挂载替换当前"按页累积挂载"，彻底解决浏览越久对象越多的累积问题。风险较高，建议单独分支、以本次 `test_perf_1000.py` 为性能基线，目标把末页挂载行数从 1000 压到 ~视口行数 + 缓冲。
2. **[完成交付闭环] 安装 PyInstaller 并实跑打包**：验证 `FreeChart.spec` 冻结后 `corporate_actions.json` 资源路径与新增模块导入，产出可安装 EXE；同时用真机跑 APK 兼容性自测（任务 #93），补齐最后两个 BLOCKED/NOT RUN 项。
3. **[数据准确性] 接入权威复权数据源**：当前因子来自已核实登记库 + 东财送转事件；建议接入带 prev_close 的权威分红数据源，把"只标记不修复"的纯现金分红纳入精确复权，并补腾讯 qfq 成交量补量的真实数据端到端验证。
4. **[一致性] 统一 `sort_reverse` 语义与年K逐根对齐**：与用户确认排序方向交互是否需要统一；补双端年K逐根对齐测试，消除聚合边界的潜在细微差异。
5. **[可靠性] 端到端网络恢复回归**：用可控 mock 模拟"断网→恢复"，验证桌面与 Android 都能自动补充刷新且旧数据不覆盖新数据，把第 6 节问题 7 从"部分覆盖"提升为完整验证。

---

**审查与授权**：以上修复均在 `fix/deep-review-20261115` 分支、**未提交、未推送、未建 PR**。请审查 `git diff` 与实际测试结果；确认后再决定是否提交、推送或打包发布。
