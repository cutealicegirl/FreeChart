# Free Chart K 线时间同步与实时更新专项修复 · 验收报告

- 项目版本基线：v1.5.0（本轮为源码修复，未构建新发行版）
- 修复日期：2026-11-17
- 覆盖范围：Windows 桌面端（PySide6） + Android H5 端（WebView）
- 验收结论：**9 类根因全部定位并修复；专项测试全绿；全量回归无新增失败；双端口径一致**

---

## 1. Bug 根本原因及具体触发条件

| # | 根本原因 | 具体触发条件 | 用户可见现象 |
|---|----------|--------------|--------------|
| 1 | 缓存新鲜度只看墙钟 TTL（15 分钟） |  crosses `00:00`/`04:00` 等周期边界，但缓存 `updated` 仍在 15 分钟内 | 各周期停留在前一日 23 点多，最长滞后 15 分钟；TTL 一到**一次性补齐** |
| 2 | 没有「当前未完成周期」概念 | 实时报价到来时服务端最新根已落在上一周期 | 实时价永远修改 `candles[-1]`，新周期不出现；15m 因刷新快看似正常 |
| 3 | 历史回溯泵持续刷新 `updated` | 无限回溯分页持续 `kline_cache.save()` | 缓存一直显示"刚更新"，挡住最新行情请求 |
| 4 | UTC / 本地 / 市场时区混用 | 数据源按 UTC 分桶，标签用 `datetime.fromtimestamp()` / `new Date().getHours()` | 标签时间与桶错位，跨日判断不一致 |
| 5 | 固定秒数分桶：`1w=604800`、`1M=2592000` | 按 epoch 取模聚合周/月线 | 周线从周四起、月线变成固定 30 天块 |
| 6 | Android 图表页无自动刷新 | 仅在进入页 / 切周期 / 点「最新」时加载 | 手机端停在前一日，回到前台也不校验边界 |
| 7 | 视口按「倒数第几根」锚定 | 隔夜一次补齐 N 根 | 整张图突然左移 N 格，视觉跳变 |
| 8 | 异步回执无版本号 | 旧请求在网络差时晚于新请求返回 | 旧数据覆盖新数据，时间倒退 |
| 9 | 缺 `2h / 6h / 12h` 周期 | 用户选择这些周期 | 被静默 fallback 到其它周期 |

> 关键结论：**不是单一图表渲染问题**，而是「数据源时间 → 分桶 → 缓存 → 异步更新 → 视口」整条链路的语义不一致。因此禁止只改横轴显示、禁止用系统时间覆盖真实 K 线、禁止伪造价格/成交量。

---

## 2. 修改涉及的文件及核心代码

### 2.1 新增：统一时间基准 `core/kline_time.py`

把时间戳单位、市场时区、周期桶边界、当前周期预览全部收口；桌面与 Android 使用同一套语义。

```python
def bucket_start(ts, interval, symbol=""):
    sec = interval_seconds(interval)
    market, tz = market_of(symbol), tz_for(symbol)
    if sec < 86400:
        if market == "crypto":
            return float(int(math.floor(float(ts) / sec) * sec))   # UTC 自然刻线
        local = datetime.fromtimestamp(float(ts), tz)
        # 按市场当地自然刻线对齐
        ...
    # 日/周/月/年：按市场当地自然日历，不再用固定秒数

def preview_fields(symbol, interval, price, quote_ts=0.0, now=None):
    """当前周期预览：OHLC 全部来自真实报价；volume=0；不写缓存。"""
```

- 市场时区：加密/DEX = UTC；A股/港股 = Asia/Shanghai；美股 = America/New_York（含 DST，无第三方依赖实现）。

### 2.2 `data/klines.py`

- 补齐 `2h / 6h / 12h`；`Candle` 增加 `preview / quote_ts / source`。
- `refresh_seconds()` 按周期长度分档：`≤30m → 10s`、`1h~6h → 30s`、`≥12h → 60s`。
- `_aggregate()` / `_fmt_label()` / 历史翻页全部改为市场时区同源。

### 2.3 `data/kline_cache.py`（Schema `v3-auto-split` → `v4-time-sync`）

```python
def is_fresh(symbol, interval, ttl=900):
    last = last_bar_ts(symbol, interval)
    bucket = expected_bucket(symbol, interval, now)
    if last >= bucket and (now - updated) <= ttl:   # 已拿到当前桶
        return True
    if checked >= bucket and (now - updated) <= ttl: # 源确认本桶无新根
        return True
    return False
```

- 新增 `checked_bucket` / `mark_checked()`：数据源确认本桶无新根后 TTL 内不再重复打源。
- `save(touch=False)`：历史回溯不刷新 `updated`。
- 预览根一律不落盘。

### 2.4 `data/onchain_kline.py`

- 链上周期补齐 `2h / 6h / 12h`；`normalize()` / `_aggregate()` 统一走 `core.kline_time`，自然周/月/年分桶。

### 2.5 `ui/chart_view.py`

- 真实 K 线与 `preview=True` 预览根分离；预览根半透明空心绘制，不参与历史极值、不落缓存。
- 视口由「倒数第几根」改为**按时间戳锚定**，隔夜补齐多根不再整图左移。
- `_load_seq` / `_hist_seq` 请求序号，旧回执不得覆盖新数据。
- `showEvent()` 切回图表立即校验周期边界。

### 2.6 `android/assets/www/app.js`

- 新增与桌面同口径的 `klineBucketStart / klineNextBucket / klineLabel / refreshSeconds / klinePreviewFields`。
- 新增 `KLINE_CACHE` 与 `checked_bucket` 语义。
- 新增 `_klineTimer` 自动刷新，`visibilitychange` 回到图表立即校验边界。
- `chartLoadSeq` 请求序号；`pruneCache()` 清理 `ct_kline`。

### 2.7 其它

- `FreeChart.spec`：`hiddenimports` 加入 `core.kline_time`，避免冻结版缺模块。
- 测试文件：`tests/test_kline_time_sync.py`（新增）、`android/tests/test_app_kline_time_sync.js`（新增）、`tests/test_cross_platform_intervals.py` 等 8 个适配。

---

## 3. 修复前后行为对比

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| `23:59 → 00:00`（15m/1h/4h/日/周） | 停在 23:45/23:00，最多滞后 15 分钟或等到 TTL 到期一次性补齐 | 跨桶立即 stale，下个刷新档（10/30/60s）发起请求并连续落地 |
| 服务端尚未产出新根 | 无新根，图表空白或停在旧根 | 生成 `preview=True` 预览根，OHLC 来自真实报价、volume=0，明确标注"非已完成 K 线" |
| 隔夜补齐 30 根 | 整图左移 30 格，突然跳变 | 按时间戳锚定，同一时刻保持在原屏幕位置，新根从右侧连续生长 |
| 历史回溯分页 | 持续刷新 `updated`，挡住最新行情 | `touch=False`，最新请求不受影响 |
| 周线 / 月线 | 从周四起、固定 30 天块 | 自然周（周日起）/ 自然月（1 日起） |
| A股 / 美股日线 | UTC 午夜切桶 | 北京午夜 / 美东当地午夜（自动 DST） |
| Android 图表页 | 无自动刷新，回前台不校验 | 自动刷新 + 回前台立即校验边界 |
| 2h / 6h / 12h | 被静默 fallback | 双端均可用，且纳入映射一致性测试 |

---

## 4. 所有周期测试结果

`tests/test_kline_time_sync.py`：**34 通过 / 0 失败**；`android/tests/test_app_kline_time_sync.js`：**20 通过 / 0 失败**；`tests/test_cross_platform_intervals.py`：**11 通过 / 0 失败**。

| 周期 | 桌面 | Android | 桶语义 | 结果 |
|------|------|---------|--------|------|
| 1m / 5m | ✅ | ✅ | UTC / 市场当地自然分钟 | 通过 |
| 15m | ✅ | ✅ | 自然刻线（23:59→23:45，00:00 新桶） | 通过 |
| 30m | ✅ | ✅ | 自然刻线 | 通过 |
| 1h | ✅ | ✅ | 23:59→23:00，00:00→00:00 | 通过 |
| 2h | ✅ | ✅ | 01:00 归 00:00 桶，04:00 新桶 | 通过 |
| 4h | ✅ | ✅ | 03:59 归 00:00，04:00 切桶 | 通过 |
| 6h | ✅ | ✅ | 04:00 归 00:00，06:00 切桶 | 通过 |
| 12h | ✅ | ✅ | 00:00/01:00 同桶，12:00 切桶 | 通过 |
| 日线 | ✅ | ✅ | 加密 UTC；A股北京；美股美东 | 通过 |
| 3日 | ✅ | ✅ | 自然日聚合 | 通过 |
| 周线 | ✅ | ✅ | 自然周（不再从周四起） | 通过 |
| 月线 | ✅ | ✅ | 自然月（不再固定 30 天） | 通过 |
| 年线 | ✅ | ✅ | 自然年，含闰年 2/29 | 通过 |

刷新分档统一：≤30m → 10s；1h~6h → 30s；≥12h → 60s。

---

## 5. 跨日测试结果

注入固定时钟，逐点验证 `23:45 → 23:59 → 00:00 → 00:01 → 00:15 → 01:00 → 04:00`：

| 时刻 | 15m | 1h | 4h | 日线 | 行为 |
|------|-----|----|----|------|------|
| 23:45 | 23:45 桶 | 23:00 桶 | 00:00 桶 | D 日 | 缓存命中，无请求 |
| 23:59 | 23:45 桶 | 23:00 桶 | 00:00 桶 | D 日 | 缓存命中，无请求 |
| 00:00 | **00:00 新桶** | **00:00 新桶** | 00:00 桶 | **D+1 新桶** | `is_fresh` 立即返回 False；10/30/60s 内发请求 |
| 00:01 | 00:00 桶 | 00:00 桶 | 00:00 桶 | D+1 桶 | 若真实根未到 → 生成 00:00 预览根（volume=0） |
| 00:15 | **00:15 新桶** | 00:00 桶 | 00:00 桶 | D+1 桶 | 15m 再切一次；其余周期继续在各自桶内 |
| 01:00 | 01:00 桶 | **01:00 新桶** | 00:00 桶 | D+1 桶 | 1h 切桶 |
| 04:00 | 04:00 桶 | 04:00 桶 | **04:00 新桶** | D+1 桶 | 4h 切桶 |

附加通过项：跨周（周日→周一）、跨月（11-30→12-01、1/31→2/1）、跨年（12-31→01-01）、闰年 2/29、A股北京午夜、美股 DST 夏/冬两套偏移、UTC 分桶与北京跨日错位。

---

## 6. Windows / Android 双端测试结果

| 测试集 | 结果 |
|--------|------|
| 桌面专项 `tests/test_kline_time_sync.py` | **34 通过 / 0 失败** |
| Android 专项 `android/tests/test_app_kline_time_sync.js` | **20 通过 / 0 失败** |
| 双端周期一致性 `tests/test_cross_platform_intervals.py` | **11 通过 / 0 失败** |
| Android 全量 JS 回归（12 个文件） | **12 通过 / 0 失败 / 0 跳过** |
| Python 全量回归（59 个文件） | **50 通过 / 5 失败 / 4 跳过** |
| Python 语法编译 | 通过（6 个核心文件 + 4 个测试文件） |
| Android JS 语法检查 | 通过（`node --check`） |

**关于 Python 全量回归的 5 项失败**：`test_groups.py`、`test_phase7_network.py`、`test_release_v31.py`、`test_release_v36.py`、`test_upgrade.py`。已逐项在**未修改的基线 worktree**（`f47ef06`）上复跑，5 项**全部在基线即失败**，本轮改动**没有引入新的回归**。4 项跳过为依赖实时网络的 `test_chart.py` / `test_chart_edit.py` / `test_chart_upgrade.py` / `test_phase7_resource.py`（45s 超时）。

---

## 7. 已知限制与未解决问题

1. **真实 Android 设备兼容性自测未完成**：任务 #93 仍待在有真机的环境按 `android/INSTALL_AND_COMPATIBILITY.md` 执行；本轮验证基于 Node 测试与 WebView 同源 JS 语义。
2. **未构建新发行版 / 未提交 GitHub**：本轮任务要求是源码修复与验收，未要求重新打包 EXE/APK 或发布 Release；版本仍为 v1.5.0，改动保留在工作区（15 个修改文件 + 4 个新增文件）。
3. **预览根生命周期**：预览根不落盘，进程重启后由服务端真实 K 线补齐；这是"不伪造数据"的刻意取舍。
4. **数据源节奏上限**：若上游数据源本身在周期切换后延迟产出第一根，预览根会以真实报价先展示，真实根到达后按同一时间戳覆盖（根数不增加），不会出现双根。
5. **历史基线失败**：上述 5 项 Python 测试在基线即失败，其中 `test_upgrade.py` 的 `panel.isVisible()` 与 `test_phase7_network.py` 的 `ADAPTER_CLASSES` 缺失属于更早版本遗留问题，本轮未扩大改动范围去修复。

---

## 附：验收标准对照

> "无论何时跨越新的 K 线周期，图表都应按照正确的数据源时间规则及时、连续地更新，不再出现长时间停留在旧时间、随后突然补齐或跳变的情况。"

- **及时**：周期边界即时 stale + 10/30/60s 分档刷新 + Android 回前台校验 → 达成
- **连续**：当前周期预览根 + 按时间戳锚定视口 → 达成
- **正确时间规则**：统一 `core.kline_time` / `klineBucketStart`，市场时区与自然日历 → 达成
- **不伪造**：预览 volume=0、不落缓存、不参与极值；无有效报价不生成预览 → 达成
- **双端一致**：周期集合、分桶语义、刷新分档、请求序号四端对齐并有回归测试锁定 → 达成
