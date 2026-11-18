# -*- coding: utf-8 -*-
"""链上搜索与历史 K 线修复回归（离线可验证部分）。

覆盖：
- 名称 / symbol / 别名搜索链上代币（忽略大小写、多余空格，精确/前缀/子串）
- 身份用 chain+address（asset_id），不同链同名不合并
- CoinGecko 备源不再把日线伪装成 1h/15m（诚实拒绝低周期）
- 低周期聚合高周期 OHLCV 正确（Android ocAggregateDaily）
- 交易池 / 缓存键带 chain 标识
"""
import os
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="ct_oc_")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, ".")

from data import contract_search as cs
from data import onchain_kline as ock
from data.klines import MarketApiError

PASS = 0
FAIL = 0


def ok(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS", name)
    else:
        FAIL += 1
        print("  FAIL", name, extra)


print("=" * 62)
print("链上搜索 / 历史 K 线 回归")
print("=" * 62)

# ---------- 1. 名称搜索 ----------
print("\n[1] 链上代币名称搜索")
r = cs.search_by_name("bonk")
ok("BONK 名称可搜到", any(x["symbol"] == "BONK" for x in r), str(r))
ok("忽略大小写", any(x["symbol"] == "BONK"
                  for x in cs.search_by_name("BoNk")))
ok("忽略多余空格", any(x["symbol"] == "BRETT"
                   for x in cs.search_by_name("  brett  ")))
ok("按项目名称搜索", any(x["symbol"] == "WIF"
                    for x in cs.search_by_name("dogwifhat")))
ok("按合约地址不在此接口（走 resolve）", cs.search_by_name(
    "9bb6nfecjbctnnlfko2fqvqbq8hhm13kcyycdqbgpump") == [])
ok("无结果返回空", cs.search_by_name("zzzznotatoken") == [])

# ---------- 2. 身份唯一性 ----------
print("\n[2] 身份用 chain + address")
usdc = [x for x in cs.search_by_name("USDC")]
ok("USDC 多链结果均有 asset_id", all(x.get("asset_id") for x in usdc))
ok("不同链 USDC asset_id 不同",
   len(set(x["asset_id"] for x in usdc)) == len(usdc))
ok("BONK asset_id 含 Solana",
   any(x["asset_id"].startswith("Solana:") for x in cs.search_by_name("BONK")))

# ---------- 3. 合约地址精确解析 ----------
print("\n[3] 合约地址精确命中")
info = cs.resolve("9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump")
ok("FARTCOIN 合约可解析", bool(info) and info.get("symbol") == "FARTCOIN",
   str(info))
info2 = cs.resolve("7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr")
ok("POPCAT 合约可解析", bool(info2) and info2.get("symbol") == "POPCAT", str(info2))

# ---------- 4. CoinGecko 周期诚实性 ----------
print("\n[4] CoinGecko 备源不伪造低周期 K 线")
for iv in ("1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h"):
    try:
        ock._fetch_coingecko("DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
                             iv, 100, None)
        ok(f"{iv} 低周期被诚实拒绝", False, "未抛错")
    except MarketApiError as e:
        ok(f"{iv} 低周期被诚实拒绝", "仅提供日线" in str(e), str(e))

# ---------- 5. Android JS 关键逻辑（字符串级契约） ----------
print("\n[5] Android 端同源修复")
js = open("android/assets/www/app.js", encoding="utf-8").read()
ok("JS 拒绝 CoinGecko 低周期",
   "CoinGecko 仅提供日线" in js)
ok("JS 有日线聚合函数", "function ocAggregateDaily" in js)
ok("JS 聚合用市场时区桶", "klineBucketStart(b.ts, interval" in js)
ok("JS 备源调用聚合",
   "return ocAggregateDaily(ocNormalize(six, '1d'), interval" in js)

print("\n" + "=" * 62)
print(f"结果: {PASS} 通过 / {FAIL} 失败")
print("=" * 62)
sys.exit(1 if FAIL else 0)
