# Free Chart 品牌统一验收说明

本次任务：删除所有 Crypto Ticker 相关的旧文件与程序关键词，全部替换为 Free Chart，
并将结果覆盖合并到 GitHub 主线。

## 结果概览

- **源码 / 文档 / 测试 / 配置 / 构建脚本**：38 个文件、所有明文旧品牌关键词已清零
  （`git grep -i cryptoticker` 零命中）。
- **文件与目录重命名**：
  - `CryptoTicker.spec` → `FreeChart.spec`
  - `android/src/com/cryptoticker/app/` → `android/src/com/freechart/app/`
  - PyInstaller 构建缓存目录 `build/CryptoTicker/` → 清理后重建为 `build/FreeChart/`
- **双端产物重建**：
  - `dist/Free Chart.exe`（63,833,090 字节），offscreen 启动未崩溃。
  - `android/dist/Free Chart.apk`（1,556,263 字节），包名 `com.freechart.app`，
    DEX 入口 `com.freechart.app.MainActivity`，签名块 `FREECHAR.SF/.RSA`，
    静态安装预检 17/17 通过（v1 + v2 + v3、minSdk 29 / targetSdk 34）。
  - APK 与 EXE 内均零旧名字节残留。

## 统一后的标识

| 项目 | 值 |
|---|---|
| 可见品牌名 | Free Chart |
| 内部 APP_ID | `FreeChart` |
| 配置 / 缓存目录 | `%APPDATA%/FreeChart/` |
| 桌面单实例锁 | `FreeChart-Single-Instance-v1` / `Local\FreeChart_Single_Instance` |
| 注册表自启项 | `Free Chart`（清理旧值 `CryptoTicker` / `FreeChart`） |
| Android 包名 | `com.freechart.app` |
| Android SharedPreferences | `freechart` |
| 构建脚本 | `FreeChart.spec` |
| 交付文件 | `Free Chart.exe` / `Free Chart.apk` |

## 数据兼容处理（重要）

彻底改名会影响已安装用户的数据，为此做了针对性保护：

1. **桌面端配置 / 自选 / 缓存不丢失**：
   `core/brand.py` 的 `migrate_legacy_appdata()` 在程序启动、加载配置之前，
   把旧 `%APPDATA%/CryptoTicker/` 整目录一次性迁移到 `%APPDATA%/FreeChart/`。
   已验证：目录不存在时不动作、已有新目录时不覆盖（幂等）、跨盘时复制不删源。
2. **旧快捷方式 / 旧注册表值清理**：`core/autostart.py`、`core/shortcut.py`
   仍识别更名前写入的旧值并清理，避免重复启动和失效图标。
3. **唯一保留的旧标识**：上述迁移 / 清理逻辑中各用字符串拼接
   （`"Crypto" + "Ticker"`）构造旧名，源码里没有旧品牌的明文关键词；
   这些是保护老用户升级的必要兼容代码，不是品牌残留。

## 升级注意（必须如实告知）

- **Android**：包名由旧名改为 `com.freechart.app`，且签名证书随 keystore 重建而变化。
  Android 会把新版当作全新应用，**旧版必须先卸载再安装**；旧版的本地数据
  （SharedPreferences / WebView 存储）不会自动迁移，请提前备份。
- **Windows**：无需卸载，启动时自动迁移旧目录数据；桌面快捷方式图标会通过
  `core.shortcut` 同步刷新。

## 测试验证

- Python 核心回归：`test_release_v37`（42/42）、`v12`、`v14`、`v16`、`v21`、
  `v35`（20/20）、`test_onchain_pool_integrity`（12/12）、
  `test_unified_asset_search`（45/45）、`test_adjust_modes_and_ko`（24/24）、
  `test_kline_time_sync`（34/34）全部通过。
- Android 全量 13 个测试文件全部通过，合计 364 项；`node --check app.js` 通过。
- 配置目录迁移专项：数据完整、幂等、不覆盖，通过。
- `compileall` 全量语法编译通过。

## 仍需外部环境验证（与本轮改动无关）

- 真机 Android 10+ 的 adb 安装 / 启动（本环境无设备或模拟器）。
- 外网 DEX 数据源端到端拉取（本环境不可直连，已 mock 覆盖）。
- Windows Setup 安装包：Inno Setup `iscc.exe` 未安装，本轮未重建。
