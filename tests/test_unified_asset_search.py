# -*- coding: utf-8 -*-
"""统一资产身份 / 搜索结果适配 / 搜索历史 回归（离线可测）。"""
import sys
sys.path.insert(0, ".")

from core import asset_search as a  # noqa: E402

passed = failed = 0


def ok(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS", name)
    else:
        failed += 1
        print("  FAIL", name, extra or "")


print("=" * 60)
print("统一资产搜索模型回归")
print("=" * 60)

# ---- 1. 资产唯一标识：chain + address ----
print("\n[1] 资产唯一标识")
h1 = a.make_hit("ONCHAIN:0xAbC", asset_type=a.ASSET_ONCHAIN,
                 chain="Base", address="0xAbCdEf0123456789012345678901234567890AbCdEf")
ok("EVM 地址转小写", h1["id"].endswith("0xabcdef0123456789012345678901234567890abcdef"))
ok("EVM 链前缀", h1["id"].startswith("base:"))
h2 = a.make_hit("ONCHAIN:DezX", asset_type=a.ASSET_ONCHAIN,
                 chain="Solana", address="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263")
ok("Solana mint 保持原样", h2["id"] == "solana:DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263")
# 同名同符号、不同链必须区分
h3 = a.make_hit("USDC", asset_type=a.ASSET_ONCHAIN, chain="Ethereum",
                address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
h4 = a.make_hit("USDC", asset_type=a.ASSET_ONCHAIN, chain="Solana",
                address="EPjFWdd5AufqSSqeM2qQN1xzybapC8G4wEGGkZwyTDt1v")
ok("不同链同名同符号 id 不同", h3["id"] != h4["id"])
ok("禁止仅凭 symbol 合并", h3["id"] != h4["id"] and "USDC" not in h3["id"])
# 股票 / CEX 用 market:symbol
s1 = a.make_hit("US:NVDA", asset_type=a.ASSET_STOCK, market="us", label="NVDA")
ok("股票 id = market:symbol", s1["id"] == "us:US:NVDA")
c1 = a.make_hit("BTC", asset_type=a.ASSET_CEX, market="crypto", label="BTC")
ok("CEX id = market:symbol", c1["id"] == "crypto:BTC")
ok("股票与 CEX 不同 id", s1["id"] != c1["id"])

# ---- 2. chain_id 归一 ----
print("\n[2] Chain ID 归一")
for raw, expect in [("Solana", "solana"), ("BNB Chain", "bsc"),
                   ("Ethereum", "eth"), ("Base", "base"),
                   ("Arbitrum", "arb"), ("Optimism", "op"),
                   ("Polygon", "polygon"), ("Avalanche", "avax"),
                   ("Sui", "sui"), ("TON", "ton")]:
    ok(f"chain_id({raw})={expect}", a.chain_id(raw) == expect)

# ---- 3. 相关性排序 ----
print("\n[3] 相关性排序")
nvda = a.make_hit("US:NVDA", label="NVDA", name="英伟达",
                  asset_type=a.ASSET_STOCK, market="us", aliases=["NVIDIA"])
nvda_w = a.make_hit("US:NVDAX", label="NVDAX", name="英伟达相关",
                    asset_type=a.ASSET_STOCK, market="us")
cex_pump = a.make_hit("PUMPUSDT", label="PUMP", name="Pump",
                      asset_type=a.ASSET_CEX, market="crypto")
onchain_pump = a.make_hit("ONCHAIN:pumpCmXqMfrsAkQ5r49WcJnRayYRqmX6WP5",
                         label="PUMP", name="pump.fun",
                         asset_type=a.ASSET_ONCHAIN, chain="Solana",
                         address="pumpCmXqMfrsAkQ5r49WcJnRayYRqmX6WP5")
ok("NVDA 精确 > 前缀", a.relevance("NVDA", nvda) > a.relevance("NVDA", nvda_w))
merged = a.merge_hits([nvda_w, cex_pump, onchain_pump, nvda], query="NVDA")
ok("无关联结果被过滤", all("NVDA" in h["label"] for h in merged))
ok("精确命中排第一", merged and merged[0]["id"] == nvda["id"])
# 合约地址精确匹配最高
addr = "0x532f27101965dd16442e59d40670faf5ebb142e4"
brett = a.make_hit("ONCHAIN:" + addr, asset_type=a.ASSET_ONCHAIN,
                   chain="Base", address=addr, label="BRETT")
ok("合约地址精确 = 200", a.relevance(addr, brett) == 200)
ok("合约精确 > 代码精确", a.relevance(addr, brett) > a.relevance("BRETT", brett))
# 去重
dup = a.merge_hits([nvda, dict(nvda), dict(nvda, name="英伟达公司")], query="NVDA")
ok("按 asset_id 去重", len(dup) == 1)
ok("去重保留高信息版本", dup[0]["name"] in ("英伟达", "英伟达公司"))

# ---- 4. PUMP 区分 CEX 与链上 ----
print("\n[4] 同名资产区分")
pm = a.merge_hits([cex_pump, onchain_pump], query="PUMP")
ok("PUMP 返回两类资产", len(pm) == 2)
types = {h["asset_type"] for h in pm}
ok("同时含 CEX 与链上", types == {a.ASSET_CEX, a.ASSET_ONCHAIN})

# ---- 5. 搜索历史：对象化 / 去重 / 上限 / 单删 / 旧版兼容 ----
print("\n[5] 搜索历史模型")
old = ["BTC", "ETH", "BTC", "  NVDA  "]
norm = a.normalize_history(old)
ok("旧字符串包装为对象", all(isinstance(h, dict) for h in norm))
ok("旧版去重", len(norm) == 3)
ok("去多余空格", any(h["label"] == "NVDA" for h in norm))
ok("全部带 v 版本号", all(h["v"] == a.HISTORY_VERSION for h in norm))

hit = a.make_hit("US:AAPL", label="AAPL", name="苹果",
                 asset_type=a.ASSET_STOCK, market="us", logo="aapl.png")
h = a.record_history([], hit, now=1000)
ok("记录资产对象", len(h) == 1 and h[0]["id"] == hit["id"])
ok("保存 name/type/market/logo", h[0]["name"] == "苹果" and
   h[0]["asset_type"] == a.ASSET_STOCK and h[0]["logo"] == "aapl.png")
h = a.record_history(h, a.make_hit("BTC", label="BTC", asset_type=a.ASSET_CEX,
                                    market="crypto"), now=2000)
h = a.record_history(h, hit, now=3000)   # 重复 -> 移至最前
ok("重复搜索移至最前", h[0]["id"] == hit["id"])
ok("按 asset_id 去重", len(h) == 2 and len({x["id"] for x in h}) == 2)
# 旧 q: 条目被资产命中折叠
h = a.record_history(["AAPL"], hit, now=4000)
ok("旧 q: 条目被资产折叠", len(h) == 1 and h[0]["id"] == hit["id"])
# 上限
big = a.record_history([], "K0", now=1)
for i in range(1, 80):
    big = a.record_history(big, "K%d" % i, now=i + 1)
ok("上限 50 条", len(big) == 50)
ok("最新在前", a.history_query(big[0]) == "K79")
ok("最旧的被淘汰", not any(a.history_query(x) == "K0" for x in big))
# 单条删除 / 清空
d = a.delete_history(big, big[0]["id"])
ok("单条删除生效", len(d) == 49 and all(x["id"] != big[0]["id"] for x in d))
ok("清空", a.clear_history() == [])
# 无效输入不记录
ok("空输入不记录", a.record_history(big, "", now=9) == a.normalize_history(big))
ok("无 query 无 symbol 不记录",
   a.record_history(big, {"asset_type": a.ASSET_STOCK}, now=9)
   == a.normalize_history(big))
# 直接打开
ok("history_symbol 可直接打开", a.history_symbol(h[0]) == "US:AAPL")
ok("history_display 展示 label", a.history_display(h[0]) == "AAPL")

print("\n" + "=" * 60)
print(f"结果: {passed} 通过 / {failed} 失败")
print("=" * 60)
sys.exit(1 if failed else 0)
