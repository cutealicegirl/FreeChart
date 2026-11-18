# Free Chart v1.5.0 链上标的真实历史 K 线修复与正式发布验收报告

报告时间：2026-11-17 07:46（+0800）  
项目地址：https://github.com/cutealicegirl/FreeChart  
发布版本：v1.5.0  
发布地址：https://github.com/cutealicegirl/FreeChart/releases/tag/v1.5.0

---

## 一、最终结论

本次“链上标的历史行情与 K 线系统深度修复及正式发布”任务已完成工程实现、双端回归、构建、GitHub 发布与 main 快进推送。

- 代码提交：`f47ef06 feat(onchain): 接入链上标的真实历史 K 线并修复全链路`
- 完整提交号：`f47ef066378486948f4549717436a0d85d24f4e1`
- 本地 `main` 与 `origin/main` 一致：`f47ef066378486948f4549717436a0d85d24f4e1`
- 工作区状态：干净，无未提交改动
- 合并方式：`git merge --ff-only`，未强制覆盖远端
- GitHub Release：`v1.5.0`，ID `447758945`，目标分支 `main`，非草稿、非预发布
- 三个发布资产均已上传：`FreeChart-Setup-1.5.0.exe`、`FreeChart-Windows-1.5.0.exe`、`FreeChart-Android-1.5.0.apk`

结论：可以验收。唯一保留项是“真实 Android 10+ 设备人工兼容性自测”，该事项需要真机环境，无法在无设备沙箱内替代完成。

---

## 二、问题根因

用户反馈的链上标的（Solana / Pump.fun / DEX / Meme 币）历史行情空白，不是单纯的前端渲染问题，而是全链路缺失：

1. 链上标的符号使用 `ONCHAIN:<address>` 格式，旧行情链路没有对应的历史 OHLCV 数据源。
2. 图表页在识别到链上标的后主动跳过 K 线加载，只画本设备采集的实时报价采样折线。
3. 桌面端与 Android 端对链上标的均没有真实 K 线周期集合，周期按钮不可用或点击后无数据。
4. 没有链上 K 线的本地持久化、增量补齐和断网回退策略。
5. 旧预缓存逻辑会把链上标的误送入交易所批量请求，造成无效请求和限流放大。

因此首次打开链上图表必然出现“图表空白 / 数据不完整 / 看起来没有历史行情”的现象。

---

## 三、修复内容

### 3.1 数据获取层

- 新增 `data/onchain_kline.py`，为 `ONCHAIN:<address>` 提供真实 DEX OHLCV 适配。
- 主数据源：GeckoTerminal `/search/pools` 与 `/ohlcv/{timeframe}`。
- 备数据源：CoinGecko onchain OHLC。
- 自动解析交易池，支持池迁移后重新解析，优先选择流动性最高池。
- 支持分页回溯，按 `before_ts` 拉取更早的真实历史 K 线。
- 周期映射覆盖 `1m / 5m / 15m / 30m / 1h / 4h / 1d / 3d / 1w / 1M`。
- 数据源不可达时有总时间预算 `_TOTAL_BUDGET = 15.0`，实测约 16 秒快速失败，不长期卡死。
- 明确遵守诚实数据原则：无法获取真实历史时标注缺失，不伪造价格、不伪造成交量、不插值、不外推、不复制当前价充当历史。

### 3.2 数据处理层

- 新增 OHLCV 标准化：识别秒 / 毫秒 / 微秒时间戳，统一为秒级时间戳。
- 校验 OHLC 约束：`high >= max(open, close)`、`low <= min(open, close)`、`high >= low`。
- 过滤非法成交量：`volume < 0` 或 `NaN` 的行直接丢弃。
- 按周期桶对齐时间戳。
- 相同时间戳去重排序，保证图表输入稳定。
- 状态上报支持：`ok / empty / no_pool / unavailable / rate_limited / invalid / cache`。

### 3.3 数据存储层

- 链上 K 线写入本地 SQLite，按 `(symbol, interval, ts)` 去重。
- 支持增量补齐，避免重复请求已缓存区间。
- 断网时优先显示本地真实缓存，而不是伪造一段走势。
- 新增 `kline_cache.prune()`，每个序列最多保留 10000 根，并清除 `exhausted` 标记，防止历史被裁剪后仍被误判为完整。
- 启动入口 `main.py` 后台调用 `kline_cache.prune()`。

### 3.4 桌面展示层

- `ui/chart_view.py` 解耦“链上标的”和“采样兜底视图”：
  - `_onchain`：是否是链上标的
  - `_no_kline`：是否进入采样兜底
  - `_has_real_kline`：是否拿到真实 DEX K 线
- 打开链上标的时先尝试真实历史 K 线，不再直接跳过。
- 周期栏恢复生成链上可用周期按钮。
- 拿到真实 K 线后退出采样视图，使用标准蜡烛图渲染。
- 只有当真实 K 线获取失败时，才回退到“本设备采集的真实报价走势”，并明确提示数据源不可用。
- `update_onchain()` 在真实 K 线模式下只更新头部价格，不再覆盖蜡烛数据。
- `_prefetch_intervals()` 对链上标的直接返回，避免一次打开图表触发 9 个 DEX 请求导致 429。

### 3.5 Android 展示层

- `android/assets/www/app.js` 新增完整链上 K 线 JS 适配：
  - GeckoTerminal 主源
  - CoinGecko 备源
  - `ocNormalize()` 标准化
  - `ocResolvePool()` 池解析
  - `ocFetchGecko()` / `ocFetchCoingecko()`
  - `fetchOnchainCandles()` 统一入口
  - `OC_KLINE_CACHE` / `OC_POOL_CACHE` 本地缓存
- `intervalsFor()` 对链上返回 `OC_INTERVALS`；`defaultInterval()` 返回 `1h`。
- `loadChart()` 链上分支先加载真实 DEX K 线，失败才回退到采样折线。
- `drawChart()` 仅在链上且 `CANDLES` 为空时才画采样折线。
- 修复链上首屏快照竞态：新增 `_ocPending`，在批量刷新忙时记录待处理品种，空闲后补刷。
- `__CT_DEBUG` 暴露测试钩子，便于自动化验证。

### 3.6 预缓存与限流治理

- `data/prefetch.py` 跳过链上标的，改由图表打开时按需加载。
- 桌面与 Android 均避免链上周期预取造成请求放大。
- 交易池解析加入缓存与失效机制，减少重复搜索。

### 3.7 同版本包含的历史修复

本版本同时包含此前完成的：

- 窗口拉伸 / 拖动 / 最大化 / 全屏恢复，窄窗口不再隐藏最大化和全屏按钮。
- 系统级边缘缩放兜底。
- 股票拆分、反向拆股、送转、分红送配、代码变更、代币迁移等公司行为复权链路。
- 未登记拆股双确认识别，历史 K 线与成交量同步调整，缓存指纹失效，防二次复权。

---

## 四、测试与验证

### 4.1 自动化测试

| 范围 | 结果 |
|---|---|
| 桌面全量测试 | 184 项通过，0 失败 |
| Android 全量测试 | 131 项通过，0 失败 |
| `tests/test_onchain_kline.py` | 27 项通过 |
| `tests/test_onchain_offline.py` | 11 项通过 |
| `tests/test_cross_platform_intervals.py` | 9 项通过 |
| `android/tests/test_app_onchain_kline.js` | 12 项通过 |
| 窗口回归 `tests/test_window_resize.py` | 10/10 通过 |

覆盖内容包括：

- 时间戳单位识别、OHLC 约束、去重排序、非法行过滤。
- 交易池解析、池迁移重解析、缓存失效。
- GeckoTerminal 主源与 CoinGecko 备源。
- 分页回溯与 `before_ts`。
- `fetch_klines()` 对链上标的正确分派。
- 断网快速失败、限流识别、空响应不伪造。
- 桌面 / Android 周期集合一致、timeframe 映射一致。
- Android 缓存命中、首屏竞态处理。

### 4.2 真实网络与异常环境

- 真实 Binance K 线链路冒烟通过：拉取 2000 根，OHLC 约束正常。
- 链上数据源在当前沙箱不可直连，已验证快速失败路径：约 16 秒返回 `no_pool`，未伪造任何数据。
- 产物文件头校验：
  - `dist/Free Chart.exe`：`4d 5a`（MZ）
  - `installer/out/FreeChart-Setup-1.5.0.exe`：`4d 5a`（MZ）
  - `android/dist/Free Chart.apk`：`50 4b`（PK）

### 4.3 EXE 冒烟说明

曾出现一次 `CRASHED exit=0` 的误判。经核查是已有安装版 FreeChart 正在运行，单实例机制把新启动请求转交现有实例后自身退出，退出码为 0，不是崩溃。

---

## 五、构建产物

| 文件 | 大小 | 用途 |
|---|---:|---|
| `dist/Free Chart.exe` | 63,791,507 字节 | Windows 绿色版单文件 |
| `installer/out/FreeChart-Setup-1.5.0.exe` | 65,430,426 字节 | Windows 安装包 |
| `android/dist/Free Chart.apk` | 1,543,975 字节 | Android 10+ 安装包 |

版本统一：

- `core/brand.py`：`APP_VERSION = 1.5.0`
- `android/AndroidManifest.xml`：`versionCode = 9`，`versionName = 1.5.0`
- `installer/FreeChart.iss`：`MyAppVersion = 1.5.0`
- `CryptoTicker.spec`：加入 `data.onchain_kline` 到 `hiddenimports`

---

## 六、GitHub 发布状态

Release API 实测结果：

- `tag_name`：`v1.5.0`
- `target_commitish`：`main`
- `id`：`447758945`
- `draft`：`false`
- `prerelease`：`false`
- `published_at`：`2026-11-16T23:43:30Z`

资产清单：

| 资产 | 大小 | 状态 |
|---|---:|---|
| `FreeChart-Android-1.5.0.apk` | 1,543,975 | uploaded |
| `FreeChart-Setup-1.5.0.exe` | 65,430,426 | uploaded |
| `FreeChart-Windows-1.5.0.exe` | 63,791,507 | uploaded |

发布页：https://github.com/cutealicegirl/FreeChart/releases/tag/v1.5.0

Git 状态：

- 当前分支：`main`
- `HEAD`：`f47ef066378486948f4549717436a0d85d24f4e1`
- `origin/main`：`f47ef066378486948f4549717436a0d85d24f4e1`
- 工作区：干净

---

## 七、已知限制与未完成项

1. **链上 DEX 真实联网端到端验证未完成**  
   当前环境无法直连 GeckoTerminal / CoinGecko / DexScreener。解析、回退、缓存、分页、状态分支已用 mock 全量覆盖，但“真实网络返回一根真实链上 K 线”的端到端验证需要在可联网环境执行。

2. **真实 Android 10+ 设备兼容性自测未完成**  
   对应任务 #93 仍为 pending。需要在真机按 `android/INSTALL_AND_COMPATIBILITY.md` 执行安装、权限、图表加载、周期切换、断网回退、升级覆盖等检查。

3. **无网络时链上图表显示的是真实报价走势，不是 K 线**  
   这是刻意设计的诚实回退，不是数据伪造。界面已明确标注数据源不可用。

---

## 八、最终验收清单

- [x] 根因定位完成
- [x] 数据获取、处理、存储、展示全链路修复
- [x] 不伪造价格 / 成交量 / K 线
- [x] Windows 与 Android 双端实现
- [x] 桌面与 Android 周期、timeframe 一致
- [x] 离线与异常环境快速失败、缓存回退
- [x] 缓存裁剪与请求限流治理
- [x] 全量自动化测试通过
- [x] Windows EXE / 安装包 / Android APK 构建完成
- [x] 产物文件头与版本字段校验通过
- [x] GitHub Release v1.5.0 发布完成
- [x] main 与 origin/main 一致，工作区干净
- [x] 未强制覆盖远端
- [x] 工作日志已追加
- [ ] 真机 Android 兼容性自测（需真机环境）
- [ ] 链上 DEX 真实联网端到端验证（需可联网环境）

---

## 九、交付物

- GitHub 仓库：https://github.com/cutealicegirl/FreeChart
- Release：https://github.com/cutealicegirl/FreeChart/releases/tag/v1.5.0
- 桌面安装包：`FreeChart-Setup-1.5.0.exe`
- 桌面绿色版：`FreeChart-Windows-1.5.0.exe`
- Android 安装包：`FreeChart-Android-1.5.0.apk`
- 本报告：`FreeChart链上K线修复与正式发布验收报告.md`

行情数据来自公开接口，不构成投资建议。
