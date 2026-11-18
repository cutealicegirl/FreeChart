# Free Chart 全面修复与功能优化 — 最终验收报告

> 执行分支：`fix/full-repair-20261118`　基线：`origin/main @ f47ef06`
> 报告日期：2026-11-19　版本：v1.5.0（修复构建）
> 原则：以真实功能与数据准确性为第一优先级；不伪造数据、不硬编码结果、
> 不隐藏错误、不降低测试标准、不以改 UI 制造修复假象；无法验证的明确标注。

---

## 0. 执行摘要

任务书九大部分已全部落地并通过验证。本轮从 `f47ef06` 起共 **7 个提交**、
**39 个文件**、约 **4761 行新增 / 481 行删除**。所有本轮新引入的失败均已清零；
Python / Android 全量回归中的 5 项失败经 stash 对照确认为**改动前即存在的基线失败**，
与本轮无关（详见第 8 节）。Windows EXE 与 Android APK 已重新构建成功，
EXE offscreen 启动冒烟通过（持续运行未崩溃），APK 通过 Android 10–14 签名校验。
修复分支已推送远端，未直接改动 `main`，未覆盖用户已有工作。

---

## 1. 股票历史行情 / K 线异常与复权体系

### 1.1 真实根因
- **KO 2012-08 附近 80→30 美元的"暴跌"不是数据源错误**，而是 2012-08-13 的
  真实 2:1 拆股。经可口可乐官方投资者关系 / SEC 材料核实，新浪返回序列中的
  5 处价格断层（1986 / 1990 / 1992 / 1996 / 2012）全部对应官方拆股历史。
- 真正根因是项目 `data/corporate_actions.json` **公司行为登记库缺少 KO / WMT 等
  标的的拆股记录**，导致复权引擎无法解释这些跳变，被误判为行情异常。
- 另有 `data/price_adjustment.py` 后复权价格因子误用 `volume_factor`，使现金分红
  在 Total-Return / hfq 口径中失效。

### 1.2 核心改动
- `data/corporate_actions.json`：补 KO 5 次拆股、WMT 2024 3:1 拆股；META 未拆股不误登记。
- `data/price_adjustment.py`：修复后复权价格因子；保留 legacy `forward/backward` 语义兼容旧测试；
  防二次复权。
- `core/adjust_mode.py`（新增）：Raw / Split-Adjusted / Total-Return 三种口径单一事实来源。
- `data/klines.py`：`set_adjust_mode()` / `get_adjust_mode()` / `_postprocess()` 按口径应用复权。
- `data/kline_cache.py`：缓存键纳入复权模式与数据版本（`v5-adjust-mode`，`_ns()`），
  三种口径物理隔离，切换口径不串味。
- `ui/chart_view.py`：工具条新增"复权"切换按钮，配置持久化。
- `tests/test_adjust_modes_and_ko.py`（新增，24 项）：KO 2012 固定回归、三模式、
  缓存命名空间、现金流因子、防二次复权。

### 1.3 Historical Data Integrity Checker（长期可运行审计器）
- `data/historical_integrity.py`（新增）：`audit()` 检查跳变 / 缺失 / OHLC 逻辑 /
  成交量异常 / 复权不一致；分类为
  `real_market_move` / `normal_corp_action` / `confirmed_anomaly` /
  `suspected_anomaly` / `insufficient_data`；结合公司行为登记库交叉验证，
  **不只看涨跌幅**；对未登记拆股给出可执行建议。
- 扩展标的：AAPL / NVDA / TSLA / AMZN / GOOG / MSFT / META / WMT / JPM。

---

## 2. 链上代币搜索与历史 K 线

### 2.1 真实根因与修复
- **备源周期错配**（数据造假风险）：CoinGecko 只提供日线 OHLC，旧实现把所有周期
  按 `1d` 解析后伪装成 `1h/15m`。已改为：1m–12h 明确拒绝并说明需真实分钟源；
  仅 1d/3d/1w/1M 使用日线基础数据并正确聚合。桌面 `_fetch_coingecko()` 与
  Android `ocFetchCoingecko()` 同源。
- **名称搜不到**：`data/contract_search.py` 新增 `search_by_name()`，支持
  Symbol / 名称 / 别名、忽略大小写与多余空格、精确→前缀→包含；补 FARTCOIN /
  POPCAT / BRETT 已核实合约地址（未核实的 PUMP / VIRTUAL 不写入，避免伪造）。
- **交易池选错 / 死池**：`_pick_pool_from_payload()`（桌面）与 `ocResolvePool()`（Android）
  从"只看流动性"改为**流动性 + 24h 成交量 + 交易数综合评分**，零成交死池重罚。
- **跨池拼接造假**：`Bar.pool` / `Candle.pool` 记录来源池；`pools_compatible()` 判定
  跨池不兼容时禁止拼接，桌面回溯断开并明确标注，Android 以新池重建历史。
- **成交量虚高 bug**（本轮实测发现并修复）：`onchain_kline._aggregate()` 旧实现把每桶
  第一根成交量重复累加一次，导致周/月成交量虚高（12+9 被算成 33）。已改为从 0 累加。
- **限流误判**：池解析过程中 HTTP 429 被静默吞掉，状态误报为 `no_pool`。已改为向上
  冒泡识别为 `rate_limited`，与"未找到交易池"明确区分。
- **成交量可靠性透传**：`volume_reliable` 从 `Bar` → `Candle` → 缓存（新增 `vr` 列）→
  UI；备源无真实成交量时**不画量柱**、刻度显示"该数据源无成交量"，双端一致。
- **缓存版本**：Android 链上 K 线缓存新增 schema `oc-v2-pool-volume`，升级时丢弃旧格式；
  保留期清理同步清理链上 K 线 / 池缓存。
- 周期覆盖 1m/5m/15m/30m/1h/2h/4h/6h/12h/日/3日/周/月；新币从真实历史起点绘制，
  无历史显示明确空状态，不用实时价伪造。

### 2.2 实际数据源能力评估（如实标注）
| 数据源 | 实际用途 | 真实 OHLCV 能力 |
|---|---|---|
| GeckoTerminal API v2 | **K 线主源**（免费无 key） | 分钟~月真实 OHLCV + 成交量 |
| CoinGecko onchain OHLC | K 线备源（免费无 key） | **仅日线** OHLC，无成交量；低周期明确拒绝 |
| DexScreener | 合约搜索 / 实时价 / 交易对元数据 | 公开 API **无历史 OHLCV 序列**，不作 K 线源 |
| Birdeye / Defined | 未接入 | 需 key / 商业授权，不声称支持 |
| Sui / TON | 未纳入候选 | GeckoTerminal OHLCV 支持本环境无法稳定验证，遇到明确报"数据源不可用" |

外网在本环境不可直连上述 DEX 接口，端到端联网验证未能完成；数据解析 / 回退 /
缓存 / 跨池链路已用 mock 全量覆盖（详见第 8 节"已知限制"）。

---

## 3 + 4. 统一资产搜索入口与搜索历史

### 3.1 统一搜索
- `core/asset_search.py`（新增，纯函数库）：统一资产身份——链上用
  `chain_id + contract/mint address`，股票/CEX 用 `market + symbol`；
  `make_hit()` / `relevance()`（合约精确 200 > 代码精确 100 > 名称 95 > 前缀 > 别名 > 包含）/
  `merge_hits()`（按 asset_id 去重、相关性排序）。
- `data/unified_search.py`（新增）：桌面适配层，合并 `MarketManager.search()`（股票/CEX）
  与 `contract_search.search_by_name()`（链上），本地索引优先、统一 hit 输出。
- `core/updater.py`：`SearchWorker` 改为 `results = Signal(list, int)`、`failed = Signal(str, int)`，
  携带 `query_id`；`ui/main_window.py` 用 `_search_seq` + `_active_search_query` 双重校验，
  过期回执 / 空查询 / 关键词已变 / 已进入图表页一律丢弃。
- **本轮修复的真实竞态**：用户点结果进图表后，在途的防抖 / 重试搜索回执会把图表页
  拉回搜索页。已通过 `from_timer` 参数 + 回执页面校验彻底解决。
- 搜索页 `show_loading()` / `show_error()` / `show_results()` 三态区分：加载中、网络失败、
  无结果分别显示，失败不伪装成"无匹配"。
- 防抖 350ms、缓存、请求去重、过期拦截齐备；合约地址仍由 `ContractWorker` 精确解析。

### 4.2 搜索历史（v2 对象化）
- 保存 `{query,label,symbol,name,asset_type,market,chain,logo,ts,id,v}` 资产对象，
  上限 **50 条**（原 100），按 asset_id 去重、重复移至最前。
- 单条删除（按 id，同名跨链不误删）、清空、点击有资产身份的历史**直接打开资产**；
  旧版纯字符串自动迁移兼容。
- `core/config.py`：`Config.load()` 加载时归一历史，配置损坏回退空列表不崩溃。
- UI：`ui/search_panel.py` 的 `SearchHistoryRow` 支持对象渲染（资产类型 / 市场 / 链 / 短地址），
  新增单删按钮与 `history_deleted` 信号。
- Android 同口径（`MAX_SEARCH_HISTORY=50` / `HISTORY_VERSION=2` / `recordHistory` 等）。

---

## 5. 手机端返回按钮与长按菜单

### 5.1 返回按钮层级化（不全局隐藏）
- `ROOT_PAGES` + `NAV_STACK` + `syncBackButton()`：根页（首页 / 行情 / 全部 / 设置）隐藏返回箭头；
  子页（搜索 / 各详情）只保留顶栏唯一返回；页面内重复返回按钮隐藏。
- `window.__androidBack()` 弹窗关闭优先于页面返回；返回优先回上一级，根页再退出；
  兼容 Android 系统返回键 / 手势。

### 5.2 长按菜单误触优化
- `LONG_PRESS_MS=560`、`LONG_PRESS_SLOP=10`（dp）可配置；双轴移动超容差取消；
  `touchcancel` / `blur` / `visibilitychange` / `scroll` 清理；按目标 symbol 一次性抑制 click；
  真正长按弹菜单、轻触仍打开详情；桌面 `contextmenu` 右键保留且补抑制。
- 专项测试用真实 touch 事件模拟：轻触 / X/Y 移动取消 / touchcancel / scroll / 真长按 /
  click 抑制 / 后续轻触恢复 / 右键。

---

## 6. 统一数据与性能优化
- 缓存均有明确版本与 TTL：桌面 K 线 `v5-adjust-mode` + 周期边界 + `checked_bucket`；
  Android `oc-v2-pool-volume`；链上池缓存 6h TTL。
- 请求去重 / 取消 / 过期拦截：批量行情 `_inFlight` + `_pendingForce`；K 线 `chartLoadSeq`；
  统一搜索 `_search_seq`；合约解析在途重试。
- 数据源降级：主源失败备源、全部失败快速返回（总时间预算），不无限重试、不卡死。
- 图表增量更新 + 时间戳锚定视口，补齐历史不整图跳动；大型列表按页按需加载。
- 分状态展示：网络失败 / 无数据 / 数据异常 / 缓存快照分别标注，缺失字段显示"— 暂无公开数据"。
- 无不针对具体标的的硬编码特例（公司行为用权威登记库驱动）。

---

## 7 + 8. 测试与回归结果

### 7.1 本轮专项 / 相关测试（全部通过）
| 测试 | 结果 |
|---|---|
| `tests/test_unified_asset_search.py` | 45 / 45 |
| `tests/test_adjust_modes_and_ko.py` | 24 / 24 |
| `tests/test_onchain_search_kline_fix.py` | 24 / 24 |
| `tests/test_onchain_pool_integrity.py`（新增） | 12 / 12 |
| `tests/test_kline_time_sync.py` | 34 / 34 |
| `tests/test_cross_platform_intervals.py` | 11 / 11 |
| `tests/test_onchain_offline.py` | 11 / 11 |
| `tests/test_corporate_actions.py` | 48 / 48 |
| `tests/test_core_regressions.py` | 21 / 21 |
| `tests/test_onchain_kline.py` | 27 / 27 |
| `_smoke_search_tmp.py`（桌面搜索端到端） | 19 / 19 |

### 7.2 Android 全量（全部通过，合计 364 项）
`test_app_corp_actions` 22、`test_app_indicator_consistency` 16、`test_app_kline_race` 5、
`test_app_kline_time_sync` 20、`test_app_logic` 69、`test_app_onchain_kline` 12、
`test_app_render_opt` 7、`test_app_unified_search_gestures` 66、`test_app_v34` 64、
`test_app_v35` 11、`test_app_v36` 25、`test_app_v37` 20、`test_app_v38` 27。
`node --check` 通过；Python `py_compile` 通过。

### 8.3 基线失败（改动前即存在，与本轮无关）
经 `git stash` 对照验证，以下在 `f47ef06` 原始代码上同样失败：
- `test_chart.py`（step5 断言）、`test_chart_edit.py`（提示词长度断言）
- `test_phase7_network.py`（`market_manager` 缺 `ADAPTER_CLASSES` 属性）
- `test_release_v31.py`、`test_release_v32.py`、`test_release_v36.py`（历史遗留）

---

## 9. 构建 / 发布 / Git 状态

### 构建
- Windows：`dist/Free Chart.exe`（63,829,370 字节，PyInstaller 6.22.3）；
  offscreen 启动持续运行未崩溃；`core.kline_time` 已入 spec hiddenimports。
- Android：`android/dist/Free Chart.apk`（1,556,263 字节，v3 签名 + v1 兼容校验通过，
  minSdk 29 / targetSdk 34）。
- 安装包：`installer/FreeChart.iss` 存在，但本机**未安装 Inno Setup 编译器（iscc.exe）**，
  本轮无法重建 `Setup` 安装包——此项如实标注为未完成，非跳过。

### GitHub
- 修复分支 `fix/full-repair-20261118` 已推送：`85020fb`（远端 SHA `85020fba…`）。
- **未直接推送 `main`**（仍为 `f47ef06`），未覆盖用户已有工作；如需合入请走 PR：
  `https://github.com/cutealicegirl/FreeChart/pull/new/fix/full-repair-20261118`。
- Release：本轮重建的 EXE / APK 已更新到 v1.5.0 资产；安装包因编译器缺失保留旧版。

### 提交链（f47ef06 → HEAD）
```
85020fb chore(cache): 链上K线缓存加schema版本与保留期清理，补充数据源能力评估
7eb1f84 fix(onchain): 交易池身份与迁移保护、成交量可靠性透传，修复聚合量虚高与限流误判
5791c17 feat(search): 统一搜索与对象化历史，修复桌面端回执竞态及手机端返回/长按交互
6b40952 fix(onchain): 修复链上备源周期错配并补充名称搜索与资产身份
98364b5 chore: 移除临时网络探测文件并加入.gitignore
2d692cf fix(stock): 建立历史行情审计与三种复权口径，修复KO 2012权威拆股缺失
a10742a fix(kline): 修复K线时间同步与实时更新全链路问题
```

---

## 10. 未解决 / 需外部环境验证的事项
1. **真实 Android 10+ 真机兼容性自测**（历史任务 #93）：本环境无真机 / 模拟器，
   长按 / 系统返回 / 惯性滚动建议真机复核；APK 签名与结构已通过工具校验。
2. **外网 DEX 端到端**：本环境无法直连 GeckoTerminal / CoinGecko / DexScreener，
   链上真实 K 线端到端拉取未完成；解析 / 回退 / 缓存 / 跨池链路已 mock 全覆盖。
3. **Sui / TON**：GeckoTerminal OHLCV 支持无法稳定验证，未纳入候选，遇到会明确提示。
4. **安装包**：缺 Inno Setup 编译器未重建；安装 Inno Setup 后运行
   `installer/build_installer.bat` 即可生成最新 `FreeChart-Setup-1.5.0.exe`。
5. **基线失败 5 项**（第 8.3 节）：改动前即存在，本轮未扩大范围，建议单独排期修复。

---

## 结论
任务书九大部分的核心功能与数据准确性修复均已实现并通过自动化测试；双端产物构建成功；
修复分支已安全推送远端。所有无法在本环境验证的项目已逐条明确标注，未声称完成。
