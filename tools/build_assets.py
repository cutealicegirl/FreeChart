# -*- coding: utf-8 -*-
"""开发期一次性生成：各市场前 300 品类清单 + 加密货币官方图标。

产物：
  data/top300.json          运行期内置清单（离线可用）
  assets/coins/<code>.png   品种官方 logo（CoinCap / cryptocurrency-icons）

运行：python tools/build_assets.py
"""
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from data.api_base import HTTP  # noqa: E402
from data.tencent_stock_api import QUOTE_URL  # noqa: E402

TOP_N = 300
OUT_JSON = os.path.join(ROOT, "data", "top300.json")
ICON_DIR = os.path.join(ROOT, "assets", "coins")
os.makedirs(ICON_DIR, exist_ok=True)

# 稳定币 / 杠杆 / 法币 / 代币化股票等，不作为「品类」展示
EXCLUDE_BASE = {
    "USDC", "USDT", "FDUSD", "TUSD", "BUSD", "DAI", "USD1", "BFUSD",
    "RWUSD", "USDE", "USDF", "USDY", "PYUSD", "XUSD", "EURI", "EUR",
    "TRY", "BRL", "ARS", "AEUR", "USDP", "PAXG", "XAUT", "WBTC",
    "WBETH", "STETH", "WSTETH", "BTCB", "BTCT", "USDB", "USDD",
}
EXCLUDE_SUFFIX = ("UP", "DOWN", "BULL", "BEAR")

# 币圈项目英文名（用于展示，来源：各项目官方命名）
CRYPTO_NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "BNB": "BNB",
    "XRP": "XRP", "DOGE": "Dogecoin", "ADA": "Cardano",
    "AVAX": "Avalanche", "LINK": "Chainlink", "DOT": "Polkadot",
    "TRX": "TRON", "LTC": "Litecoin", "SUI": "Sui", "NEAR": "NEAR",
    "ARB": "Arbitrum", "UNI": "Uniswap", "PEPE": "Pepe", "WIF": "dogwifhat",
    "OP": "Optimism", "APT": "Aptos", "INJ": "Injective", "TIA": "Celestia",
    "SEI": "Sei", "JUP": "Jupiter", "ENA": "Ethena", "TAO": "Bittensor",
    "RENDER": "Render", "FIL": "Filecoin", "ATOM": "Cosmos",
    "ETC": "Ethereum Classic", "XLM": "Stellar", "HBAR": "Hedera",
    "ICP": "Internet Computer", "ALGO": "Algorand", "HYPE": "Hyperliquid",
    "ZEC": "Zcash", "ONDO": "Ondo", "PUMP": "Pump.fun", "AR": "Arweave",
    "AAVE": "Aave", "MKR": "Maker", "CRV": "Curve", "LDO": "Lido DAO",
    "PENDLE": "Pendle", "JTO": "Jito", "BONK": "Bonk", "FLOKI": "Floki",
    "SHIB": "Shiba Inu", "TON": "Toncoin", "TONCOIN": "Toncoin",
    "POL": "Polygon", "MATIC": "Polygon", "FET": "Fetch.ai",
    "GRT": "The Graph", "SAND": "The Sandbox", "MANA": "Decentraland",
    "AXS": "Axie Infinity", "IMX": "Immutable", "GALA": "Gala",
    "CHZ": "Chiliz", "ENJ": "Enjin", "BAT": "Basic Attention",
    "COMP": "Compound", "SNX": "Synthetix", "SUSHI": "SushiSwap",
    "1INCH": "1inch", "ZRX": "0x", "DYDX": "dYdX", "GMX": "GMX",
    "RUNE": "THORChain", "KAVA": "Kava", "EOS": "EOS", "XTZ": "Tezos",
    "FLOW": "Flow", "EGLD": "MultiversX", "WLD": "Worldcoin",
    "STX": "Stacks", "TIA": "Celestia", "PYTH": "Pyth Network",
}


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- crypto
def crypto_top():
    r = HTTP.get("https://data-api.binance.vision/api/v3/ticker/24hr",
                 timeout=25)
    r.raise_for_status()
    items = [d for d in r.json() if d.get("symbol", "").endswith("USDT")]
    items.sort(key=lambda d: float(d.get("quoteVolume") or 0), reverse=True)
    out = []
    for d in items:
        base = d["symbol"][:-4]
        if base in EXCLUDE_BASE or base.endswith(EXCLUDE_SUFFIX):
            continue
        out.append((base, CRYPTO_NAMES.get(base, base)))
        if len(out) >= TOP_N:
            break
    log("crypto:", len(out), out[:5])
    return out


# ---------------------------------------------------------------- cn (sina)
def cn_top():
    url = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/"
           "json_v2.php/Market_Center.getHQNodeData")
    out = []
    for page in range(1, 6):
        try:
            r = HTTP.get(url, params={"page": page, "num": 80,
                                      "sort": "amount", "asc": 0,
                                      "node": "hs_a"},
                         headers={"User-Agent": "Mozilla/5.0",
                                  "Referer": "https://finance.sina.com.cn/"},
                         timeout=15)
            rows = r.json()
        except Exception as e:
            log("sina page", page, "ERR", e)
            continue
        if not rows:
            break
        for row in rows:
            sym = row.get("symbol", "")   # sh600519 / sz000001
            name = row.get("name", "")
            if not re.match(r"^(sh|sz)\d{6}$", sym):
                continue
            out.append((f"{sym[:2].upper()}:{sym[2:]}", name))
        if len(out) >= TOP_N:
            break
        time.sleep(0.15)
    # 去重保序
    seen, uniq = set(), []
    for s, n in out:
        if s not in seen:
            seen.add(s)
            uniq.append((s, n))
    log("cn:", len(uniq), uniq[:5])
    return uniq[:TOP_N]


# ---------------------------------------------------------------- 腾讯批量校验
def tencent_batch(tencent_codes):
    """返回 {qt_code: (name, amount)}，无效代码自动忽略。"""
    try:
        r = HTTP.get(QUOTE_URL + ",".join(tencent_codes), timeout=20)
        r.encoding = "gbk"
    except Exception as e:
        log("tencent batch ERR", type(e).__name__, str(e)[:60])
        return {}
    out = {}
    for line in r.text.split(";"):
        line = line.strip()
        m = re.match(r'v_(\w+)="(.*)"', line)
        if not m:
            continue
        code, f = m.group(1), m.group(2).split("~")
        if len(f) < 38 or not f[1]:
            continue
        try:
            amount = float(f[37] or 0)
        except ValueError:
            amount = 0.0
        out[code] = (f[1], amount)
    return out


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def build_from_codes(codes, label, key_fn):
    """codes: 腾讯请求码列表；key_fn: qt_code -> 统一代码。"""
    found = {}
    for i, batch in enumerate(chunks(codes, 300)):
        found.update(tencent_batch(batch))
        if i % 8 == 0:
            log(f"  {label} batch {i + 1}: valid={len(found)}")
        time.sleep(0.06)
    ranked = sorted(found.items(), key=lambda kv: kv[1][1], reverse=True)
    out = []
    for qt_code, (name, _amt) in ranked:
        symbol = key_fn(qt_code)
        if symbol:
            out.append((symbol, name))
        if len(out) >= TOP_N:
            break
    log(f"{label}: valid={len(found)} -> top {len(out)}", out[:5])
    return out


def hk_top():
    codes = [f"hk{i:05d}" for i in range(1, 10000)]

    def key(qt_code):
        raw = qt_code[2:]
        if not raw.isdigit():
            return None
        return f"HK:{raw.upper()}"

    return build_from_codes(codes, "hk", key)


# 标普 500 成分（Wikipedia 名单）+ 常见 ETF / 中概股
SP500 = """MMM,AOS,ABT,ABBV,ACN,ADBE,AMD,AES,AFL,A,APD,ABNB,AKAM,ALB,ARE,ALGN,ALLE,LNT,ALL,GOOGL,GOOG,MO,AMZN,AMCR,AEE,AEP,AXP,AIG,AMT,AWK,AMP,AME,AMGN,APH,ADI,AON,APA,APO,AAPL,AMAT,APP,APTV,ACGL,ADM,ARES,ANET,AJG,AIZ,T,ATO,ADSK,ADP,AZO,AVY,AXON,BKR,BALL,BAC,BAX,BDX,BRK.B,BBY,TECH,BIIB,BLK,BX,XYZ,BE,BNY,BA,BKNG,BSX,BMY,AVGO,BR,BRO,BF.B,BG,BXP,CHRW,CDNS,CPT,COF,CAH,CCL,CARR,CVNA,CASY,CAT,CBOE,CBRE,CDW,COR,CNC,CNP,CF,CRL,SCHW,CHTR,CVX,CMG,CB,CHD,CIEN,CI,CINF,CTAS,CSCO,C,CFG,CLX,CME,CMS,KO,CTSH,COHR,COIN,CL,CMCSA,FIX,COP,ED,STZ,CEG,COO,CPRT,GLW,CPAY,CSGP,COST,CRH,CRWD,CCI,CSX,CMI,CVS,DHR,DRI,DDOG,DVA,DECK,DE,DELL,DAL,DVN,DXCM,FANG,DLR,DG,DLTR,D,DPZ,DASH,DOV,DOW,DHI,DTE,DUK,DD,ETN,EBAY,ECHO,ECL,EIX,EW,ELV,EME,EMR,ETR,EOG,EQT,EFX,EQIX,ERIE,ESS,EL,EG,EVRG,P,ES,EXC,EXE,EXPE,EXPD,EXR,XOM,FFIV,FDS,FICO,FAST,FRT,FDX,FERG,FIS,FITB,FSLR,FE,FLEX,F,FTNT,FTV,FOXA,FOX,BEN,FCX,GRMN,IT,GE,GEHC,GEV,GEN,GNRC,GD,GIS,GM,GPC,GILD,GPN,GL,GDDY,GS,HAL,HIG,HAS,HCA,HSIC,HSY,HPE,HLT,HD,HON,HRL,HST,HWM,HPQ,HUBB,HUM,HBAN,HII,IBM,IEX,IDXX,ITW,ILMN,INCY,IR,PODD,INTC,IBKR,ICE,IFF,IP,INTU,ISRG,IVZ,INVH,IQV,IRM,JBHT,JBL,JKHY,J,JNJ,JCI,JPM,KDP,KEY,KEYS,KMB,KIM,KMI,KKR,KLAC,KHC,KR,LHX,LH,LRCX,LVS,LDOS,LEN,LII,LLY,LIN,LYV,LMT,L,LOW,LULU,LITE,LYB,MTB,MPC,MAR,MRSH,MLM,MRVL,MAS,MA,MKC,MCD,MCK,MDT,MRK,META,MET,MTD,MGM,MCHP,MU,MSFT,MAA,MRNA,MDLZ,MPWR,MNST,MCO,MS,MOS,MSI,MSCI,NDAQ,NTAP,NFLX,NEM,NWSA,NWS,NEE,NKE,NI,NDSN,NSC,NTRS,NOC,NCLH,NRG,NUE,NVDA,NVR,NXPI,ORLY,OXY,OKTA,ODFL,OMC,ON,OKE,ORCL,OTIS,PCAR,PKG,PLTR,PANW,PH,PAYX,PYPL,PNR,PEP,PFE,PCG,PM,PSX,PNW,PNC,PPG,PPL,PFG,PG,PGR,PLD,PRU,PTC,PEG,PSA,PHM,Q,QCOM,PWR,DGX,RL,RJF,RDDT,O,REG,REGN,RF,RSG,RMD,RVTY,HOOD,ROK,ROL,ROP,ROST,RCL,RTX,SPGI,CRM,SNDK,SBAC,SLB,STX,SRE,NOW,SHW,SPG,SWKS,SJM,SW,SNA,SOLV,SO,LUV,SWK,SBUX,STT,STLD,STE,SYK,SMCI,SYF,SNPS,SYY,TMUS,TROW,TTWO,TPR,TRGP,TGT,TEL,TDY,TER,TSLA,TXN,TPL,TXT,TMO,TJX,TKO,TSCO,TT,TDG,TRV,TRMB,TFC,TWLO,TYL,TSN,USB,UBER,UDR,ULTA,UNP,UAL,UPS,URI,UNH,UHS,VLO,VEEV,VTR,VLTO,VRSN,VRSK,VZ,VRTX,VRT,VTRS,VICI,V,VST,VMC,WRB,GWW,WAB,WMT,DIS,WM,WAT,WEC,WFC,WELL,WST,WDC,WY,WSM,WMB,WTW,WDAY,WYNN,XEL,XYL,YUM,ZBRA,ZBH,ZTS"""
EXTRA_US = ("SPY,QQQ,IWM,DIA,TLT,GLD,SLV,ARKK,SOFI,COIN,PLTR,BABA,PDD,JD,"
            "BIDU,NIO,XPEV,LI,BEKE,TME,YMM,HTHT,EDU,TAL,VNET,KC,SMH,XLK,"
            "XLF,XLE,XLV,XLI,XLP,XLY,XLU,XLB,XLRE,XLC,HYG,LQD,EEM,EFA,FXI,"
            "KWEB,MCHI,UVXY,VXX,SQQQ,TQQQ,SOXL,SARK,ARM,ASML,TSM,ERIC,"
            "NOK,SHEL,BP,TTE,HSBC,RIO,BHP,VALE,SBS,ABB,TM,SONY,HMC").split(",")


def us_top():
    tickers = list(dict.fromkeys(
        [t.strip() for t in SP500.split(",") if t.strip()] + EXTRA_US))
    codes = [f"us{t}" for t in tickers]

    def key(qt_code):
        raw = qt_code[2:]
        parts = raw.split(".")
        if len(parts) == 2 and parts[1].lower() in (
                "oq", "n", "am", "pr", "uq", "ut"):
            raw = parts[0]
        if not raw or not re.match(r"^[A-Za-z][A-Za-z.\-]{0,7}$", raw):
            return None
        return f"US:{raw.upper()}"

    return build_from_codes(codes, "us", key)


# ---------------------------------------------------------------- 图标
ICON_SOURCES = [
    "https://assets.coincap.io/assets/icons/{s}@2x.png",
    "https://gcore.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/"
    "128/color/{s}.png",
]


def download_icon(code):
    dest = os.path.join(ICON_DIR, code.lower() + ".png")
    if os.path.exists(dest) and os.path.getsize(dest) > 300:
        return code, True
    s = code.lower()
    for tpl in ICON_SOURCES:
        try:
            r = HTTP.get(tpl.format(s=s), timeout=10)
            if r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n" \
                    and len(r.content) > 400:
                with open(dest, "wb") as f:
                    f.write(r.content)
                return code, True
        except Exception:
            continue
    return code, False


def build_icons(crypto):
    codes = list(dict.fromkeys(
        [c for c, _ in crypto] +
        list(CRYPTO_NAMES.keys()) +
        ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "HYPE", "ENA",
         "TAO", "ZEC", "ONDO", "PUMP", "NEAR", "ARB", "RENDER", "FIL", "AR"]))
    log("icon targets:", len(codes))
    ok = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, (code, success) in enumerate(
                ex.map(download_icon, codes), 1):
            ok += bool(success)
            if i % 50 == 0:
                log(f"  icons {i}/{len(codes)} ok={ok}")
    log("icons done:", ok, "/", len(codes))
    return ok


def main():
    data = {"generated": time.strftime("%Y-%m-%d"), "top_n": TOP_N}
    try:
        data["crypto"] = crypto_top()
    except Exception as e:
        log("crypto FAILED", e)
        data["crypto"] = [[s, n] for s, n in CRYPTO_NAMES.items()][:TOP_N]
    try:
        data["cn"] = cn_top()
    except Exception as e:
        log("cn FAILED", e)
        data["cn"] = []
    for fn in (hk_top, us_top):
        try:
            data[fn.__name__[:2]] = fn()
        except Exception as e:
            log(fn.__name__, "FAILED", e)
            data[fn.__name__[:2]] = []
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    log("saved", OUT_JSON,
        {k: len(v) for k, v in data.items() if isinstance(v, list)})
    build_icons(data["crypto"])


if __name__ == "__main__":
    main()
