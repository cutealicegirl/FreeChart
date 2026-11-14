# -*- coding: utf-8 -*-
"""链上合约地址 -> 品种解析。

支持 EVM（0x+40 十六进制）、Solana（base58 32~44）、Tron（T+33 base58）。

解析顺序（重要）：
  1. 内置主流地址表（离线秒回）；
  2. Solana：直接读链上账户——SPL Mint 给精度/总量，Token-2022 的
     TokenMetadata 扩展或 Metaplex 元数据账户给名称/代码；
  3. DexScreener：补价格与交易对信息（国内网络经常不可达，探活失败后
     本次运行不再重试，避免每次搜索都白等 8 秒）。

之前只查 DexScreener，国内直连超时，任何新币地址都会返回空结果，表现就是
「输入合约地址搜不到币」——这才是真正的病根。
"""
import base64
import hashlib
import json
import re
import struct

from PySide6.QtCore import QThread, Signal

from data.api_base import HTTP

_DEX = "https://api.dexscreener.com/latest/dex/search"
_DEX_TOKEN = "https://api.dexscreener.com/latest/dex/tokens/"
_BINANCE_PRICE = "https://data-api.binance.vision/api/v3/ticker/price"
# 国内可直连的 Solana 公共 RPC（官方 api.mainnet-beta 在国内被墙）
_SOLANA_RPC = ("https://solana.publicnode.com", "https://solana-rpc.publicnode.com")

_EVM = re.compile(r"^0x[0-9a-fA-F]{40}$")
_B58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_TRON = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")

# 程序 ID / 元数据常量
_SPL_TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
_TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
_METAPLEX = "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"
_EXT_METADATA = 19          # Token-2022 扩展：TokenMetadata
_TLV_START = 166            # 165 字节基础账户 + 1 字节 account_type


# 主流合约地址（小写 -> (代码, 名称, 链)），离线兜底
KNOWN = {
    "0xdac17f958d2ee523a2206206994597c13d831ec7": ("USDT", "Tether USD", "Ethereum"),
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": ("USDC", "USD Coin", "Ethereum"),
    "0x6b175474e89094c44da98b954eedeac495271d0f": ("DAI", "Dai Stablecoin", "Ethereum"),
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": ("WETH", "Wrapped Ether", "Ethereum"),
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": ("WBTC", "Wrapped BTC", "Ethereum"),
    "0x514910771af9ca656af840dff83e8264ecf986ca": ("LINK", "Chainlink", "Ethereum"),
    "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984": ("UNI", "Uniswap", "Ethereum"),
    "0x6982508145454ce325ddbe47a25d4ec3d2311933": ("PEPE", "Pepe", "Ethereum"),
    "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce": ("SHIB", "Shiba Inu", "Ethereum"),
    "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9": ("AAVE", "Aave", "Ethereum"),
    "0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2": ("MKR", "Maker", "Ethereum"),
    "0xd533a949740bb3306d119cc777fa900ba034cd52": ("CRV", "Curve DAO", "Ethereum"),
    "0x111111111117dc0aa78b770fa6a738034120c302": ("1INCH", "1inch", "Ethereum"),
    "0x5a98fcbea516cf06857215779fd812ca3bef1b32": ("LDO", "Lido DAO", "Ethereum"),
    "0xc00e94cb662c3520282e6f5717214004a7f26888": ("COMP", "Compound", "Ethereum"),
    "0x6b3595068778dd592e39a122f4f5a5cf09c90fe2": ("SUSHI", "SushiSwap", "Ethereum"),
    "0x0bc529c00c6401aef6d220be8c6ea1667f6ad93e": ("YFI", "yearn.finance", "Ethereum"),
    "0x57e114b691db790c35207b2e685d4a43181e6061": ("ENA", "Ethena", "Ethereum"),
    "0xfaba6f8e4a5e8ab82f62fe7c39859e7a1941f6f": ("ONDO", "Ondo", "Ethereum"),
    "0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0": ("MATIC", "Polygon", "Ethereum"),
    "0x4e15361fd6b4bb609fa63c81a2be19d873717870": ("FTM", "Fantom", "Ethereum"),
    "0xc011a73ee8576fb46f5e1c5751ca3b9fe0af2a6f": ("SNX", "Synthetix", "Ethereum"),
    "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c": ("WBNB", "Wrapped BNB", "BSC"),
    "0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82": ("CAKE", "PancakeSwap", "BSC"),
    "0x912ce59144191c1204e64559fe8253a0e49e6548": ("ARB", "Arbitrum", "Arbitrum"),
    "0x4200000000000000000000000000000000000042": ("OP", "Optimism", "Optimism"),
    "0x163f8c2467924be0ae7b5347228cabf26031875387": ("WLD", "Worldcoin", "Optimism"),
    "dezxaz8z7pnrnrjjz3wxborgixca6xjnb7yab1ppb263": ("BONK", "Bonk", "Solana"),
    "jupyiwryjskmice5p2ivit39iljnmj7klo4wtgdwyrp": ("JUP", "Jupiter", "Solana"),
    "ekpqgsjtjmfqkz9kqansqyxrcf8fbopzlhyxdm65zcjm": ("WIF", "dogwifhat", "Solana"),
    "hz1jovnivv6gnsidkq7opfngwfflhx4bmppy9wx8k7": ("PYTH", "Pyth Network", "Solana"),
    "jtojtomepa8bep8auqc6ext5frijwffmwqx2v2f9mcl": ("JTO", "Jito", "Solana"),
    "4k3dyjzvzp8emzwuxbbcjevwskkk59s5icnly3qrkx6r": ("RAY", "Raydium", "Solana"),
    "epjfwdd5aufqssqem2qn1xzybapc8g4weggkzwytdt1v":
        ("USDC", "USD Coin", "Solana"),
}


_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_MAP = {c: i for i, c in enumerate(_B58_ALPHABET)}

# DexScreener 探活状态：None 未试 / True 可用 / False 本次运行不达
_DEX_OK = None

# Solana 链上解析结果缓存（同一地址重复搜索不再走网络）
_SOL_CACHE: dict = {}


def b58decode(text: str) -> bytes:
    num = 0
    for ch in text:
        num = num * 58 + _B58_MAP[ch]
    raw = num.to_bytes((num.bit_length() + 7) // 8, "big") if num else b""
    pad = len(text) - len(text.lstrip("1"))
    return b"\x00" * pad + raw


def _is_on_curve(pubkey: bytes) -> bool:
    """ed25519 公钥解压：判定 32 字节是否落在曲线上（PDA 派生要用）。"""
    p = 2 ** 255 - 19
    d = -121665 * pow(121666, p - 2, p) % p
    y = int.from_bytes(pubkey, "little") & ((1 << 255) - 1)
    if y >= p:
        return False
    y2 = y * y % p
    u = (y2 - 1) % p
    v = (d * y2 + 1) % p
    x2 = u * pow(v, p - 2, p) % p
    if x2 == 0:
        return True
    # p % 8 == 5：候选平方根 x = x2^((p+3)/8)
    x = pow(x2, (p + 3) // 8, p)
    if (x * x - x2) % p != 0:
        x = x * pow(2, (p - 1) // 4, p) % p
    return (x * x - x2) % p == 0


def _find_pda(seeds: list, program: bytes):
    """create_program_address：sha256(seeds || program_id || 标记)，取不在曲线上的 bump。"""
    for bump in range(255, -1, -1):
        data = b"".join(seeds) + bytes([bump]) + program + \
            b"ProgramDerivedAddress"
        digest = hashlib.sha256(data).digest()
        if not _is_on_curve(digest):
            return digest
    return None


def _b58encode(raw: bytes) -> str:
    num = int.from_bytes(raw, "big")
    out = ""
    while num:
        num, rem = divmod(num, 58)
        out = _B58_ALPHABET[rem] + out
    pad = len(raw) - len(raw.lstrip(b"\x00"))
    return "1" * pad + out


def _rpc_call(method: str, params: list, timeout: float = 8.0):
    for url in _SOLANA_RPC:
        try:
            resp = HTTP.post(url, json={"jsonrpc": "2.0", "id": 1,
                                        "method": method, "params": params},
                             timeout=timeout)
            body = resp.json()
            if body.get("error"):
                continue
            return body.get("result")
        except Exception:
            continue
    return None


def _read_string(buf: bytes, pos: int):
    """borsh / token-2022 String：u32 小端长度 + UTF-8。

    Metaplex 的 name/symbol 字段是定长 32 字节、后面补 \\x00，直接 decode
    会带一串空字符，这里统一剥掉。
    """
    if pos + 4 > len(buf):
        return "", len(buf)
    n = struct.unpack_from("<I", buf, pos)[0]
    pos += 4
    if n > len(buf) - pos:
        return "", len(buf)
    text = buf[pos:pos + n].decode("utf-8", "replace")
    return text.strip("\x00 \t\r\n"), pos + n


def _token2022_meta(raw: bytes):
    """从 Token-2022 账户的 TLV 扩展里取 (name, symbol, uri)。"""
    pos = _TLV_START
    while pos + 4 <= len(raw):
        kind, length = struct.unpack_from("<HH", raw, pos)
        if kind == 0 and length == 0:
            break
        pos += 4
        if pos + length > len(raw):
            break
        if kind == _EXT_METADATA:
            val = raw[pos:pos + length]
            p = 32 + 32                    # update_authority + mint
            name, p = _read_string(val, p)
            symbol, p = _read_string(val, p)
            uri, p = _read_string(val, p)
            return name, symbol, uri
        pos += length
    return "", "", ""


def _metaplex_meta(mint: str):
    """老 SPL 代币：读 Metaplex 元数据 PDA。"""
    try:
        program = b58decode(_METAPLEX)
        pda = _find_pda([b"metadata", program, b58decode(mint)], program)
    except (KeyError, ValueError):
        return "", "", ""
    if pda is None:
        return "", "", ""
    info = _rpc_call("getAccountInfo",
                     [_b58encode(pda), {"encoding": "base64"}]) or {}
    value = info.get("value") or {}
    data = value.get("data") or []
    if len(data) < 2:
        return "", "", ""
    try:
        raw = base64.b64decode(data[0])
    except (ValueError, TypeError):
        return "", "", ""
    if len(raw) < 68:
        return "", "", ""
    pos = 1 + 32 + 32                      # key + update_authority + mint
    name, pos = _read_string(raw, pos)
    symbol, pos = _read_string(raw, pos)
    uri, pos = _read_string(raw, pos)
    return name, symbol, uri


def solana_token(mint: str, timeout: float = 8.0) -> dict:
    """链上解析一个 Solana 代币：{name, symbol, supply, decimals, uri}。

    账户不存在或不是 Mint（例如随便编的 44 位字符串）返回空 dict，
    由上层继续走 DexScreener / 内置表。
    """
    if mint in _SOL_CACHE:
        return dict(_SOL_CACHE[mint])
    info = _rpc_call("getAccountInfo",
                     [mint, {"encoding": "base64"}], timeout=timeout) or {}
    value = info.get("value") or {}
    owner = value.get("owner") or ""
    data = value.get("data") or []
    if owner not in (_SPL_TOKEN, _TOKEN_2022) or len(data) < 2:
        return {}
    try:
        raw = base64.b64decode(data[0])
    except (ValueError, TypeError):
        return {}
    if len(raw) < 82:
        return {}
    supply = struct.unpack_from("<Q", raw, 36)[0]
    decimals = raw[44]
    name = symbol = uri = ""
    if owner == _TOKEN_2022:
        name, symbol, uri = _token2022_meta(raw)
    if not symbol:
        m_name, m_symbol, m_uri = _metaplex_meta(mint)
        name = name or m_name
        symbol = symbol or m_symbol
        uri = uri or m_uri
    out = {"name": name, "symbol": symbol.upper()[:12],
           "supply": supply / (10 ** decimals) if decimals else supply,
           "decimals": decimals, "uri": uri,
           "chain": "Solana", "program": ("Token-2022" if owner == _TOKEN_2022
                                          else "SPL Token")}
    _SOL_CACHE[mint] = dict(out)
    return out


def _solana_address(q: str) -> bool:
    """32~44 位 base58 且不是 Tron 地址：按 Solana Mint 处理。"""
    return bool(_B58.match(q)) and not _TRON.match(q)


def is_contract(query: str) -> bool:
    q = (query or "").strip()
    if q.lower().startswith("0x"):
        q = q[2:]
        return len(q) == 40 and all(c in "0123456789abcdefABCDEF" for c in q)
    return bool(_TRON.match(q) or _B58.match(q))


def _pair_info(pair, address):
    base = pair.get("baseToken") or {}
    sym = (base.get("symbol") or "").upper()
    if not sym:
        return None
    return {
        "address": address, "symbol": sym,
        "name": base.get("name") or sym,
        "chain": pair.get("chainId") or "",
        "price": (pair.get("priceUsd") or ""),
        "change": ((pair.get("priceChange") or {}).get("h24") or ""),
        "url": pair.get("url") or "",
    }


def _dex_pairs(q: str):
    """先查「按代币地址」专接口，再退回全文搜索；取回候选交易对列表。

    DexScreener 在国内直连基本不通，第一次超时就把它标记为不可用，
    之后整轮运行直接跳过——否则每次搜索都要白等 8 秒。
    """
    global _DEX_OK
    if _DEX_OK is False:
        return []
    for url, params in ((_DEX_TOKEN + q, None), (_DEX, {"q": q})):
        try:
            resp = HTTP.get(url, params=params, timeout=3,
                            headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                _DEX_OK = False
                continue
            pairs = (resp.json() or {}).get("pairs") or []
            _DEX_OK = True
        except Exception:
            _DEX_OK = False
            continue
        if pairs:
            return pairs
    return []


def _tradable(symbol: str) -> bool:
    """币安是否有 SYMBOLUSDT 现货交易对：决定能不能加入自选看 K 线。"""
    if not symbol:
        return False
    try:
        resp = HTTP.get(_BINANCE_PRICE, params={"symbol": f"{symbol}USDT"},
                        timeout=4, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            body = resp.json()
            return bool(isinstance(body, dict) and body.get("price"))
    except Exception:
        pass
    return False


def _empty(address: str) -> dict:
    return {"address": address, "symbol": "", "name": "", "chain": "",
            "price": "", "change": "", "url": "", "tradable": False,
            "supply": 0.0, "program": "", "exists": False}


def resolve(query: str) -> dict | None:
    """返回 {address, symbol, name, chain, price, change, url, tradable,
    supply, program, exists} 或 None。"""
    q = (query or "").strip()
    if not is_contract(q):
        return None
    # 内置主流地址直接命中：省掉网络往返，USDT/USDC 这类必然查得到的
    # 地址不该让用户等十几秒。
    known = KNOWN.get(q.lower())
    if known:
        sym, name, chain = known
        return {"address": q, "symbol": sym, "name": name,
                "chain": chain, "price": "", "change": "", "url": "",
                "tradable": _tradable(sym), "supply": 0.0,
                "program": "", "exists": True}

    # ---- Solana：先读链上账户，这条路国内稳定可达 ----
    sol = {}
    if _solana_address(q):
        try:
            sol = solana_token(q)
        except Exception:
            sol = {}
        if sol:
            sym = (sol.get("symbol") or "").upper()
            info = _empty(q)
            info.update({"symbol": sym, "name": sol.get("name") or "",
                         "chain": "Solana", "supply": sol.get("supply") or 0.0,
                         "program": sol.get("program") or "",
                         "exists": True, "url": sol.get("uri") or ""})
            if sym:
                info["tradable"] = _tradable(sym)
            # 链上真实报价：无论有没有币安交易对 / K 线都取。
            # Rugcheck 国内可直连；DexScreener 常超时，只在它失败时兜底。
            # 没有 24h 涨跌幅时保持空，绝不用 0 或交易所数据冒充。
            from data import onchain
            q_chain = onchain.quote(q)
            if q_chain:
                info["price"] = q_chain.get("price") or ""
                info["change"] = ""      # 链上源不提供 24h 涨跌，不编造
                info["liquidity"] = q_chain.get("liquidity")
                info["holders"] = q_chain.get("holders")
                info["price_source"] = q_chain.get("source")
                info["price_ts"] = q_chain.get("ts")
                info["onchain"] = True
                if not sym and q_chain.get("code"):
                    info["symbol"] = q_chain["code"]
                if not info.get("name") and q_chain.get("name"):
                    info["name"] = q_chain["name"]
                if not info.get("supply") and q_chain.get("supply"):
                    info["supply"] = q_chain["supply"]
                if q_chain.get("decimals") is not None:
                    info["decimals"] = q_chain["decimals"]
                if q_chain.get("launchpad"):
                    info["launchpad"] = q_chain["launchpad"]
            else:
                for pair in _dex_pairs(q):
                    got = _pair_info(pair, q)
                    if got:
                        info["price"] = got.get("price") or ""
                        info["change"] = got.get("change") or ""
                        info["url"] = got.get("url") or info["url"]
                        break
            return info

    # ---- 其它链：DexScreener 全文/地址检索 ----
    pairs = _dex_pairs(q)
    # 优先取「baseToken 地址精确匹配」的交易对（流动性最大的一条在最前）
    exact = [p for p in pairs
             if ((p.get("baseToken") or {}).get("address") or "").lower()
             == q.lower()]
    for pair in exact or pairs:
        info = _pair_info(pair, q)
        if info:
            info["tradable"] = _tradable(info["symbol"])
            info["supply"] = 0.0
            info["program"] = ""
            info["exists"] = True
            return info
    return _empty(q)


class ContractWorker(QThread):
    """后台解析合约地址，避免网络请求卡住界面。"""

    resolved = Signal(dict)

    def __init__(self, query: str, parent=None):
        super().__init__(parent)
        self._query = query

    def run(self):
        info = resolve(self._query) or {"address": self._query}
        self.resolved.emit(info)
