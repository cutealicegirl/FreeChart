/* FreeChart Android 移动端主逻辑。
 *
 * 数据全部来自与桌面端相同的公开接口，绝不使用模拟数据：
 *   Binance   https://data-api.binance.vision/api/v3/ticker/24hr | /klines
 *   腾讯行情   https://qt.gtimg.cn/q=               (GBK)
 *   腾讯 K 线  https://web.ifzq.gtimg.cn/appstock/app/(hk)fqkline/get
 *   新浪美股   https://stock.finance.sina.com.cn/usstock/api/...
 *   CoinLore  https://api.coinlore.net/api/tickers/
 * 取不到的字段一律显示「— 暂无公开数据」，不填 0、不估算、不编造。
 *
 * 网络与持久化走 Java Bridge（Native.*），在桌面浏览器预览时自动降级，
 * 便于用普通浏览器检查 UI 与交互；APK 内不依赖任何桌面运行环境。
 */
(function () {
  'use strict';

  // ===================== 常量（与桌面端保持一致） =====================
  var MARKETS = [['crypto', '加密'], ['cn', 'A股'], ['hk', '港股'], ['us', '美股']];
  var MARKET_NAME = { crypto: '加密货币', cn: 'A 股', hk: '港股', us: '美股' };
  var SUBS = [['watch', '自选'], ['all', '全部']];

  var SORT_GROUPS = [
    ['行情', ['change_desc', 'change_asc', 'price_desc', 'price_asc',
              'amount_desc', 'amount_asc']],
    ['规模', ['cap_desc', 'cap_asc']],
    ['流动性', ['liquidity_desc', 'liquidity_asc']],
    ['时间', ['listed_desc', 'listed_asc']],
    ['其它', ['default', 'custom']]
  ];
  var SORT_LABEL = {
    custom: '自定义排序', change_desc: '涨跌幅 高→低', change_asc: '涨跌幅 低→高',
    price_desc: '价格 高→低', price_asc: '价格 低→高',
    amount_desc: '成交额 高→低', amount_asc: '成交额 低→高',
    cap_desc: '市值 高→低', cap_asc: '市值 低→高',
    liquidity_desc: '流动性 高→低', liquidity_asc: '流动性 低→高',
    listed_desc: '上市/创立 新→旧', listed_asc: '上市/创立 旧→新',
    default: '默认（市值榜单序）'
  };
  var SORT_SHORT = {
    custom: '自定义', change_desc: '涨幅 ↓', change_asc: '涨幅 ↑',
    price_desc: '价格 ↓', price_asc: '价格 ↑', amount_desc: '成交额 ↓',
    amount_asc: '成交额 ↑', cap_desc: '市值 ↓', cap_asc: '市值 ↑',
    liquidity_desc: '流动性 ↓', liquidity_asc: '流动性 ↑',
    listed_desc: '上市 新', listed_asc: '上市 旧', default: '默认'
  };
  var REVERSE_SORT = {
    change_desc: 'change_asc', change_asc: 'change_desc',
    price_desc: 'price_asc', price_asc: 'price_desc',
    amount_desc: 'amount_asc', amount_asc: 'amount_desc',
    cap_desc: 'cap_asc', cap_asc: 'cap_desc',
    liquidity_desc: 'liquidity_asc', liquidity_asc: 'liquidity_desc',
    listed_desc: 'listed_asc', listed_asc: 'listed_desc'
  };
  var META_MODES = {
    cap_desc: 1, cap_asc: 1, liquidity_desc: 1, liquidity_asc: 1,
    listed_desc: 1, listed_asc: 1
  };

  var PAGE_SIZE = 60;          // 首屏只挂载 / 只请求一页
  var PREFETCH_ROWS = 60;      // 预取一页，滚动无缝
  var MAX_REFRESH_SYMBOLS = 300;
  var MAX_RETRY = 3;
  var MAX_SEARCH_HISTORY = 50;    // 与桌面一致：最近 30~50 条，按资产唯一标识去重
  // 长按手势参数（任务书：从 500~650ms / 8~12dp 起测，集中配置便于真机微调）
  var LONG_PRESS_MS = 560;        // 长按触发延迟，默认 560ms
  var LONG_PRESS_SLOP = 10;       // 移动容差(CSS px，约 10dp)
  var HISTORY_VERSION = 2;        // 搜索历史数据结构版本（1 = 旧版纯字符串）
  var META_TTL = 7 * 86400 * 1000;
  var MISSING = '— 暂无公开数据';

  // 指标参数：MA / EMA 各 4 条（天数 + 启停），BOLL 周期与标准差倍数。
  // 结构与桌面 core.indicator_params 完全一致，配置可互相导入导出。
  var IND_SCOPE_ALL = '*';
  var MA_COLORS = ['#f0b90b', '#b39ddb', '#4b9cff', '#26a69a'];
  var EMA_COLORS = ['#ff9f43', '#e040fb', '#26de81', '#f7d794'];
  var IND_DEFAULT = {
    ma: [{ period: 5, enabled: true }, { period: 10, enabled: true },
         { period: 20, enabled: true }, { period: 30, enabled: true }],
    ema: [{ period: 12, enabled: true }, { period: 26, enabled: true },
          { period: 50, enabled: true }, { period: 99, enabled: false }],
    boll: { period: 20, k: 2 },
    macd: { fast: 12, slow: 26, signal: 9 }
  };

  var BINANCE_TICKER = 'https://data-api.binance.vision/api/v3/ticker/24hr?symbols=';
  var BINANCE_KLINE = 'https://data-api.binance.vision/api/v3/klines';
  var TENCENT_QUOTE = 'https://qt.gtimg.cn/q=';
  var TENCENT_KLINE = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=';
  var HK_KLINE = 'https://web.ifzq.gtimg.cn/appstock/app/hkfqkline/get?param=';
  var SINA_US_MIN = 'https://stock.finance.sina.com.cn/usstock/api/json_v2.php/US_MinKService.getMinK?symbol=';
  var SINA_US_DAY = 'https://stock.finance.sina.com.cn/usstock/api/jsonp_v2.php/x/US_MinKService.getDailyK?symbol=';
  var COINLORE = 'https://api.coinlore.net/api/tickers/?start=';
  // 链上合约代币（pump.fun / Raydium 等）：国内可直连的真实链上报价。
  // 没有 K 线也能收藏、也能看价；不提供 24h 涨跌/成交额，一律留白。
  var RUGCHECK = 'https://api.rugcheck.xyz/v1/tokens/';

  var CRYPTO_INTERVALS = [['1分', '1m'], ['5分', '5m'], ['15分', '15m'],
                          ['30分', '30m'], ['1时', '1h'], ['2时', '2h'],
                          ['4时', '4h'], ['6时', '6h'], ['12时', '12h'],
                          ['日K', '1d'], ['3日', '3d'], ['周K', '1w'],
                          ['月K', '1M'], ['年K', '1y']];
  var STOCK_INTERVALS = [['日K', 'day'], ['3日', '3day'],
                         ['周K', 'week'], ['月K', 'month'], ['年K', '1year']];
  var CN_MINUTES = [['1分', 'm1'], ['5分', 'm5'], ['15分', 'm15'],
                    ['30分', 'm30'], ['1时', 'm60']];
  // 美股分钟线：新浪 type=1/5/15/30/60 分，与桌面 US_INTERVALS 完全对齐。
  var US_MINUTES = [['1分', 'm1'], ['5分', 'm5'], ['15分', 'm15'],
                    ['30分', 'm30'], ['1时', 'm60']];

  // ===================== 小工具 =====================
  // ===================== 链上合约品种工具 =====================
  var OC_PREFIX = 'ONCHAIN:';
  // 内置链上代币索引（与桌面 data/contract_search.py KNOWN 同口径）：
  // 名称 / 别名 / Symbol 离线可搜，身份用 chain + 合约地址，不靠名称合并。
  // 地址为公开可查的权威合约；数据不足的字段一律不编造。
  var OC_TOKENS = [
    { sym: 'BONK', name: 'Bonk', chain: 'Solana', cat: 'Meme',
      address: 'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263', aliases: ['bonk'] },
    { sym: 'WIF', name: 'dogwifhat', chain: 'Solana', cat: 'Meme',
      address: 'EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm', aliases: ['dogwifhat'] },
    { sym: 'PEPE', name: 'Pepe', chain: 'Ethereum', cat: 'Meme',
      address: '0x6982508145454Ce325DdbE47a25d4eC3d2311933', aliases: ['pepe'] },
    { sym: 'FARTCOIN', name: 'Fartcoin', chain: 'Solana', cat: 'Meme',
      address: '9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump', aliases: ['fartcoin'] },
    { sym: 'POPCAT', name: 'Popcat', chain: 'Solana', cat: 'Meme',
      address: '7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr', aliases: ['popcat'] },
    { sym: 'BRETT', name: 'Based Brett', chain: 'Base', cat: 'Meme',
      address: '0x532f27101965dd16442E59d40670FaF5eBB142E4', aliases: ['based brett'] },
    { sym: 'JUP', name: 'Jupiter', chain: 'Solana', cat: 'DeFi',
      address: 'JUPyiwrYJSkMiCe5P2iVit39ILjNmJ7kLo4wtGdwyrp', aliases: ['jupiter'] },
    { sym: 'RAY', name: 'Raydium', chain: 'Solana', cat: 'DeFi',
      address: '4k3Dyjzvzp8eMZWUXBbcjEvWSkkk59S5iCNLY3QrkX6R', aliases: ['raydium'] },
    { sym: 'UNI', name: 'Uniswap', chain: 'Ethereum', cat: 'DeFi',
      address: '0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984', aliases: ['uniswap'] },
    { sym: 'LINK', name: 'Chainlink', chain: 'Ethereum', cat: 'DeFi',
      address: '0x514910771AF9Ca656af840dff83E8264ECf986CA', aliases: ['chainlink'] },
    { sym: 'WLD', name: 'Worldcoin', chain: 'Optimism', cat: 'AI',
      address: '0x163f8C2467924be0ae7B5347228CABF26031875387', aliases: ['worldcoin'] },
    { sym: 'USDC', name: 'USD Coin (Solana)', chain: 'Solana', cat: 'Stablecoin',
      address: 'EPjFWdd5AufqSSqeM2qQN1xzybapC8G4wEGGkZwyTDt1v', aliases: [] }
  ];
  var OC_SOURCE = 'Rugcheck.xyz 链上代币报告';
  var RE_EVM = /^0x[0-9a-fA-F]{40}$/;
  var RE_TRON = /^T[1-9A-HJ-NP-Za-km-z]{33}$/;
  var RE_B58 = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;

  function isOnchain(s) { return typeof s === 'string' && s.indexOf(OC_PREFIX) === 0; }
  function ocAddr(s) { return isOnchain(s) ? s.slice(OC_PREFIX.length) : ''; }
  function ocSymbol(a) { return OC_PREFIX + a; }
  function isSolanaAddr(a) { return RE_B58.test(a || '') && !RE_TRON.test(a || ''); }
  function chainOfAddr(a) {
    if (RE_EVM.test(a || '')) return 'EVM';
    if (RE_TRON.test(a || '')) return 'Tron';
    if (isSolanaAddr(a)) return 'Solana';
    return '';
  }
  function shortAddr(a) {
    if (!a) return '';
    return a.length > 18 ? a.slice(0, 8) + '…' + a.slice(-6) : a;
  }
  function isContract(q) {
    var s = String(q || '').trim();
    return RE_EVM.test(s) || RE_TRON.test(s) || isSolanaAddr(s);
  }
  function ocCode(s) {
    var m = (CFG.onchain || {})[s] || {};
    return m.code || shortAddr(ocAddr(s));
  }

  // ===== 统一资产身份 / 搜索结果适配 / 搜索历史 =====
  // 与桌面 core/asset_search.py 同口径：chain id + address 为链上唯一标识，
  // 禁止仅凭名称/Symbol 合并；两端一致性由 test_unified_asset_search.py 与
  // android/tests/test_app_unified_search.js 共同保证。
  var CHAIN_IDS = {
    solana: 'solana', sol: 'solana', ethereum: 'eth', eth: 'eth', erc20: 'eth',
    base: 'base', 'bnb chain': 'bsc', bnbchain: 'bsc', bsc: 'bsc', bnb: 'bsc',
    arbitrum: 'arb', 'arbitrum one': 'arb', optimism: 'op',
    polygon: 'polygon', matic: 'polygon', avalanche: 'avax', avax: 'avax',
    sui: 'sui', ton: 'ton', tron: 'tron', evm: 'evm'
  };
  function chainId(c) {
    var k = String(c == null ? '' : c).trim().toLowerCase();
    return CHAIN_IDS[k] || k;
  }
  function normQ(s) {
    return String(s == null ? '' : s).replace(/\s+/g, ' ').trim().toLowerCase();
  }
  function assetId(h) {
    if (typeof h === 'string') return 'q:' + normQ(h);
    h = h || {};
    var t = h.asset_type || '', addr = String(h.address || '').trim();
    if (t === 'onchain' && addr) {
      var a = addr.toLowerCase().indexOf('0x') === 0 ? addr.toLowerCase() : addr;
      return (chainId(h.chain || h.chain_id || '') || 'unknown') + ':' + a;
    }
    var sym = String(h.symbol || '').trim();
    if (sym) return (String(h.market || '').trim() || 'na') + ':' + sym;
    return 'q:' + normQ(h.query || h.label || '');
  }
  function makeHit(o) {
    o = o || {};
    var h = {
      symbol: String(o.symbol || ''), label: String(o.label || o.symbol || ''),
      name: String(o.name || ''), asset_type: o.asset_type || '',
      market: o.market || '', chain: o.chain || '', address: o.address || '',
      logo: o.logo || '', query: o.query || '', aliases: o.aliases || []
    };
    if (o.kind) h.kind = o.kind;
    if (o.price !== undefined) h.price = o.price;
    h.id = assetId(h);
    return h;
  }
  function relevance(q, h) {
    q = normQ(q);
    if (!q) return 0;
    if (typeof h === 'string') h = { symbol: h, label: h };
    var sym = normQ(h.symbol), code = normQ(h.label),
        addr = normQ(h.address), name = normQ(h.name);
    if (addr && q === addr) return 200;               // 合约地址精确优先
    if (q === sym || q === code) return 100;
    if (q === name) return 95;
    if (code.indexOf(q) === 0 || sym.indexOf(q) === 0) return 80;
    if (name.indexOf(q) === 0) return 70;
    var al = h.aliases || [], i;
    for (i = 0; i < al.length; i++) {
      var na = normQ(al[i]);
      if (na === q) return 65;
      if (na.indexOf(q) === 0) return 55;
    }
    if (code.indexOf(q) >= 0 || sym.indexOf(q) >= 0 || name.indexOf(q) >= 0) return 40;
    for (i = 0; i < al.length; i++) if (normQ(al[i]).indexOf(q) >= 0) return 30;
    return 0;
  }
  function mergeHits(groups, q, limit) {
    var best = {}, order = 0, g, j;
    for (g = 0; g < (groups || []).length; g++) {
      var arr = groups[g] || [];
      for (j = 0; j < arr.length; j++) {
        var h = arr[j];
        if (!h) continue;
        var score = relevance(q, h);
        if (score <= 0) continue;
        var hid = h.id || assetId(h);
        var cand = { score: score, order: order, hit: h, id: hid };
        order++;
        var prev = best[hid];
        if (!prev || score > prev.score) best[hid] = cand;
      }
    }
    var list = [];
    for (var k in best) if (Object.prototype.hasOwnProperty.call(best, k)) list.push(best[k]);
    list.sort(function (x, y) { return (y.score - x.score) || (x.order - y.order); });
    var out = [];
    for (var i2 = 0; i2 < list.length; i2++) {
      var c = list[i2], hh = {};
      for (var kk in c.hit) if (Object.prototype.hasOwnProperty.call(c.hit, kk)) hh[kk] = c.hit[kk];
      hh.relevance = c.score; hh.id = c.id;
      out.push(hh);
    }
    return (limit && limit > 0) ? out.slice(0, limit) : out;
  }
  function normalizeHistory(raw) {
    var out = [], seen = {}, items = Array.isArray(raw) ? raw : [], i;
    for (i = 0; i < items.length; i++) {
      var it = items[i], h;
      if (typeof it === 'string') {
        var q = it.trim();
        if (!q) continue;
        h = { query: q, label: q, symbol: '', name: '', asset_type: '',
              market: '', chain: '', logo: '', ts: 0, id: 'q:' + normQ(q) };
      } else if (it && typeof it === 'object') {
        h = {
          query: it.query || it.label || it.symbol || '',
          label: it.label || it.query || '', symbol: it.symbol || '',
          name: it.name || '', asset_type: it.asset_type || '',
          market: it.market || '', chain: it.chain || '', logo: it.logo || '',
          ts: it.ts || 0, id: it.id || assetId(it)
        };
        if (!h.id) continue;
      } else continue;
      h.v = HISTORY_VERSION;
      if (seen[h.id]) continue;
      seen[h.id] = 1; out.push(h);
    }
    return out;
  }
  function recordHistory(entry, nowArg) {
    var items = normalizeHistory(CFG.search_history || []), e;
    if (typeof entry === 'string') {
      var q = entry.trim();
      if (!q) return items;
      e = { query: q, label: q, symbol: '', name: '', asset_type: '',
            market: '', chain: '', logo: '', id: 'q:' + normQ(q) };
    } else if (entry && typeof entry === 'object') {
      e = {
        query: entry.query || entry.label || entry.symbol || '',
        label: entry.label || entry.query || '', symbol: entry.symbol || '',
        name: entry.name || '', asset_type: entry.asset_type || '',
        market: entry.market || '', chain: entry.chain || '', logo: entry.logo || '',
        id: entry.id || assetId(entry)
      };
      if (!e.id) return items;
      if (!String(e.query).trim() && !String(e.symbol).trim()) return items;
    } else return items;
    e.ts = nowArg != null ? nowArg : nowMs();
    e.v = HISTORY_VERSION;
    var drop = {};
    drop[e.id] = 1;
    var keys = [e.query, e.label, e.symbol], k;
    for (k = 0; k < keys.length; k++) {
      var kv = String(keys[k] || '').trim();
      if (kv) drop['q:' + normQ(kv)] = 1;
    }
    var sym = String(e.symbol || '');
    if (sym.indexOf(':') >= 0) drop['q:' + normQ(sym.split(':').slice(1).join(':'))] = 1;
    var old = null;
    for (k = 0; k < items.length; k++) if (drop[items[k].id]) { old = items[k]; break; }
    if (old) {
      for (var kk in e) if (Object.prototype.hasOwnProperty.call(e, kk)) {
        var v = e[kk];
        if (v !== '' && v != null && v !== 0) old[kk] = v;
      }
      e = old;
    }
    var rest = items.filter(function (x) { return !drop[x.id]; });
    var out = [e].concat(rest.slice(0, Math.max(MAX_SEARCH_HISTORY - 1, 0)));
    CFG.search_history = out;
    saveCfg();
    return out;
  }
  function deleteHistory(key) {
    var items = normalizeHistory(CFG.search_history || []);
    CFG.search_history = items.filter(function (h) {
      return h.id !== key && String(h.query || '') !== key;
    });
    saveCfg();
    return CFG.search_history;
  }
  function clearHistory() {
    CFG.search_history = [];
    saveCfg();
    return CFG.search_history;
  }
  function historyQuery(h) {
    if (typeof h === 'string') return h;
    return String((h && (h.query || h.label)) || '');
  }
  function historySymbol(h) {
    if (typeof h === 'string') return '';
    return String((h && h.symbol) || '');
  }
  function historyLabel(h) {
    if (typeof h === 'string') return h;
    return String((h && (h.label || h.query || h.symbol)) || '');
  }

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function fnum(v) {
    if (v === null || v === undefined || v === '') return null;
    var n = Number(v);
    return isFinite(n) && n !== 0 ? n : (isFinite(n) && n === 0 ? 0 : null);
  }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function fmtNum(n, digits) {
    if (n === null || n === undefined || !isFinite(n)) return MISSING;
    var d = digits === undefined ? 2 : digits;
    return Number(n).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function fmtPrice(n) {
    if (n === null || !isFinite(n)) return '--';
    var d = n >= 1000 ? 2 : (n >= 1 ? 4 : (n >= 0.01 ? 6 : 8));
    return Number(n).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function fmtAmount(n) {
    if (n === null || !isFinite(n)) return MISSING;
    var a = Math.abs(n);
    if (a >= 1e12) return fmtNum(n / 1e12, 2) + ' 万亿';
    if (a >= 1e8) return fmtNum(n / 1e8, 2) + ' 亿';
    if (a >= 1e4) return fmtNum(n / 1e4, 2) + ' 万';
    return fmtNum(n, 2);
  }
  function fmtTime(ts) {
    if (!ts) return '—';
    var d = new Date(ts * 1000);
    if (isNaN(d.getTime())) return '—';
    function p(x) { return (x < 10 ? '0' : '') + x; }
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) +
      ' ' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
  }
  // 单一时钟入口：测试可注入固定时间，驱动跨日 / 跨月 / DST 边界。
  var __nowMsOverride = null;
  function nowMs() { return __nowMsOverride === null ? Date.now() : __nowMsOverride; }
  function nowSec() { return Math.floor(nowMs() / 1000); }

  // ---- K 线时间基准（与桌面 core/kline_time.py 同口径）----
  // 内部时间戳统一为 Unix 秒；桶边界按数据源所属市场时区，而不是设备时区。
  var KLINE_SEC = {
    '1m': 60, '5m': 300, '15m': 900, '30m': 1800,
    '1h': 3600, '2h': 7200, '4h': 14400, '6h': 21600, '12h': 43200,
    '1d': 86400, '3d': 259200, '1w': 604800, '1M': 2592000, '1y': 31536000,
    m1: 60, m5: 300, m15: 900, m30: 1800, m60: 3600,
    m120: 7200, m360: 21600, m720: 43200,
    day: 86400, '3day': 259200, week: 604800, month: 2592000, '1year': 31536000
  };
  function klineMarket(sym) {
    var s = String(sym || '');
    if (isOnchain(s) || s.indexOf('ONCHAIN:') === 0) return 'crypto';
    if (s.indexOf('US:') === 0) return 'us';
    if (/^(SH:|SZ:|HK:)/.test(s)) return 'cn';
    return 'crypto';
  }
  function klineNthSunday(y, m, nth) {
    var days = [];
    for (var d = 1; d <= 14; d++) {
      if (new Date(Date.UTC(y, m - 1, d)).getUTCDay() === 0) days.push(d);
    }
    return days[nth - 1];
  }
  function klineOffsetMs(sym, utcMs) {
    var mk = klineMarket(sym);
    if (mk === 'cn') return 8 * 3600000;
    if (mk !== 'us') return 0;
    var y = new Date(utcMs).getUTCFullYear();
    var mar = Date.UTC(y, 2, klineNthSunday(y, 3, 2), 7);
    var nov = Date.UTC(y, 10, klineNthSunday(y, 11, 1), 6);
    return (utcMs >= mar && utcMs < nov) ? -4 * 3600000 : -5 * 3600000;
  }
  function klineBucketStart(ts, iv, sym) {
    ts = Number(ts) || 0;
    var sec = KLINE_SEC[iv];
    if (!sec) return ts;
    var off = klineOffsetMs(sym, ts * 1000);
    if (sec < 86400) {
      var shifted = ts * 1000 + off;
      return (Math.floor(shifted / (sec * 1000)) * sec * 1000 - off) / 1000;
    }
    var d = new Date(ts * 1000 + off);
    var y = d.getUTCFullYear(), mo = d.getUTCMonth(), da = d.getUTCDate();
    var startMs;
    if (iv === '3d' || iv === '3day') {
      var dayNo = Math.floor(Date.UTC(y, mo, da) / 86400000);
      startMs = Math.floor(dayNo / 3) * 3 * 86400000;
    } else if (iv === '1w' || iv === 'week') {
      var dow = (d.getUTCDay() + 6) % 7;   // 周一为一周起点
      startMs = Date.UTC(y, mo, da) - dow * 86400000;
    } else if (iv === '1M' || iv === 'month') {
      startMs = Date.UTC(y, mo, 1);
    } else if (iv === '1y' || iv === '1year') {
      startMs = Date.UTC(y, 0, 1);
    } else {
      startMs = Date.UTC(y, mo, da);
    }
    return (startMs - off) / 1000;
  }
  function klineNextBucket(ts, iv, sym) {
    var sec = KLINE_SEC[iv];
    if (!sec) return ts;
    var b = klineBucketStart(ts, iv, sym);
    if (iv !== '1M' && iv !== 'month' && iv !== '1y' && iv !== '1year') {
      return b + sec;
    }
    var off = klineOffsetMs(sym, b * 1000);
    var d = new Date(b * 1000 + off);
    var y = d.getUTCFullYear(), mo = d.getUTCMonth();
    var next = (iv === '1y' || iv === '1year')
      ? Date.UTC(y + 1, 0, 1) : Date.UTC(y, mo + 1, 1);
    return (next - off) / 1000;
  }
  function klineLabel(ts, iv, sym) {
    var d = new Date(Number(ts) * 1000 + klineOffsetMs(sym, Number(ts) * 1000));
    function p(n) { return (n < 10 ? '0' : '') + n; }
    var md = p(d.getUTCMonth() + 1) + '-' + p(d.getUTCDate());
    if (iv === '1M' || iv === 'month') return d.getUTCFullYear() + '-' + p(d.getUTCMonth() + 1);
    if (iv === '1y' || iv === '1year') return String(d.getUTCFullYear());
    if (iv === '1d' || iv === '3d' || iv === '1w' ||
        iv === 'day' || iv === '3day' || iv === 'week') return md;
    return md + ' ' + p(d.getUTCHours()) + ':' + p(d.getUTCMinutes());
  }
  function refreshSeconds(iv) {
    var sec = KLINE_SEC[iv] || 60;
    if (sec <= 1800) return 10;
    if (sec <= 21600) return 30;
    return 60;
  }
  function klinePreviewFields(sym, iv, price, quoteTs) {
    var p = Number(price);
    if (!isFinite(p) || p <= 0) return null;
    var b = klineBucketStart(nowSec(), iv, sym);
    return {
      ts: b, label: klineLabel(b, iv, sym),
      o: p, h: p, l: p, c: p, v: 0, preview: true,
      quoteTs: Number(quoteTs) || nowSec()
    };
  }
  function uniq(arr) {
    var seen = {}, out = [];
    for (var i = 0; i < arr.length; i++) {
      if (!seen[arr[i]]) { seen[arr[i]] = 1; out.push(arr[i]); }
    }
    return out;
  }

  // ===================== 持久化（SharedPreferences / 浏览器降级） =====================
  var store = {
    get: function (k) {
      try {
        if (window.Native && Native.get) return Native.get(k) || '';
        return localStorage.getItem(k) || '';
      } catch (e) { return ''; }
    },
    set: function (k, v) {
      try {
        if (window.Native && Native.set) { Native.set(k, String(v)); return; }
        localStorage.setItem(k, String(v));
      } catch (e) { /* 存储不可用时不阻断主流程 */ }
    }
  };
  function readJSON(k, fallback) {
    try { var v = JSON.parse(store.get(k)); return v || fallback; }
    catch (e) { return fallback; }
  }
  function writeJSON(k, v) { try { store.set(k, JSON.stringify(v)); } catch (e) {} }

  var DEFAULT_SYMBOLS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'HYPE',
    'ENA', 'TAO', 'ZEC', 'ONDO', 'PUMP', 'NEAR', 'ARB', 'RENDER', 'FIL', 'AR'];
  var DEFAULTS = {
    symbols: DEFAULT_SYMBOLS.slice(),
    pinned_symbols: [],
    interval: 15,
    sort_mode: 'custom',
    sort_reverse: false,
    sub_tabs: { crypto: 'watch', cn: 'watch', hk: 'watch', us: 'watch' },
    last_tab: 'crypto',
    theme: 'binance',
    chart_interval: '',
    chart_view_count: 0,
    chart_view_pan: 0,
    last_symbol: '',
    // 链上合约品种元数据：{ 'ONCHAIN:<addr>': {address,code,name,chain,...} }
    onchain: {},
    // 搜索历史：最新在前，最多 100 条（与桌面 search_history 同构）
    search_history: [],
    // MA / EMA / BOLL 参数：'*' 为所有周期通用，也可按 '1h' 等周期覆盖
    indicator_params: {},
    show_ma: true,
    show_ema: true,
    show_boll: true,
    show_macd: true,
    show_vol: true,
    page_size: 60,
    retry_limit: 3,
    live_feed: true,
    live_interval_ms: 900,
    chart_font_scale: 120,
    show_currency: true,
    show_icons: true,
    cache_keep_days: 7
  };
  // 桌面端 config.json 里可平移到 Android 的键（保留用户设置与自定义排序）
  var IMPORT_KEYS = ['symbols', 'pinned_symbols', 'interval', 'sort_mode',
    'sub_tabs', 'last_tab', 'theme', 'chart_interval',
    'chart_view_count', 'chart_view_pan', 'onchain', 'search_history',
    'indicator_params', 'show_ma', 'show_ema', 'show_boll', 'show_macd',
    'show_vol', 'page_size', 'retry_limit', 'live_feed', 'live_interval_ms',
    'chart_font_scale', 'show_currency', 'show_icons', 'cache_keep_days'];

  // 桌面端 config.json 用 onchain_symbols 存链上品种元数据，Android 内部用 onchain。
  // 跨端导入时做别名归一化，否则链上收藏的代币代码/名称会静默丢失。
  // 只在新键缺失时回填，保留两端各自原生键，重复导入幂等。
  function normalizeImportedConfig(obj) {
    if (!obj || typeof obj !== 'object') return obj;
    if (obj.onchain_symbols !== undefined && obj.onchain_symbols !== null &&
        (obj.onchain === undefined || obj.onchain === null)) {
      obj.onchain = obj.onchain_symbols;
    }
    return obj;
  }

  var CFG = (function () {
    var c = {}, k;
    for (k in DEFAULTS) {
      if (Object.prototype.hasOwnProperty.call(DEFAULTS, k)) {
        c[k] = Array.isArray(DEFAULTS[k]) ? DEFAULTS[k].slice()
          : (typeof DEFAULTS[k] === 'object' ? JSON.parse(JSON.stringify(DEFAULTS[k]))
            : DEFAULTS[k]);
      }
    }
    var saved = normalizeImportedConfig(readJSON('ct_config', null));
    if (saved && typeof saved === 'object') {
      for (var j = 0; j < IMPORT_KEYS.length; j++) {
        var key = IMPORT_KEYS[j];
        if (saved[key] !== undefined && saved[key] !== null) c[key] = saved[key];
      }
      if (typeof saved.sort_reverse === 'boolean') c.sort_reverse = saved.sort_reverse;
    }
    if (!Array.isArray(c.symbols)) c.symbols = DEFAULT_SYMBOLS.slice();
    if (!Array.isArray(c.pinned_symbols)) c.pinned_symbols = [];
    if (!c.sub_tabs || typeof c.sub_tabs !== 'object') {
      c.sub_tabs = { crypto: 'watch', cn: 'watch', hk: 'watch', us: 'watch' };
    }
    if (!c.onchain || typeof c.onchain !== 'object' || Array.isArray(c.onchain)) {
      c.onchain = {};
    }
    // 搜索历史数据结构升级：旧版纯字符串数组 → 资产对象数组（自动兼容/去重/截断）
    c.search_history = normalizeHistory(c.search_history);
    c.search_history = c.search_history.slice(0, MAX_SEARCH_HISTORY);
    if (!c.indicator_params || typeof c.indicator_params !== 'object' ||
        Array.isArray(c.indicator_params)) c.indicator_params = {};
    // 与桌面一致：5~300 秒（旧版的 15 秒下限已放开）
    c.interval = clamp(Number(c.interval) || 15, 5, 300);
    c.page_size = clamp(Number(c.page_size) || 60, 20, 300);
    c.live_interval_ms = clamp(Number(c.live_interval_ms) || 900, 400, 3000);
    c.chart_font_scale = clamp(Number(c.chart_font_scale) || 120, 100, 160);
    return c;
  })();
  function saveCfg() { writeJSON('ct_config', CFG); }
  PAGE_SIZE = CFG.page_size;      // 设置页可改每页条数（20~300）

  // ============ 指标参数（与桌面 core.indicator_params 同构） ============
  function indInt(v, lo, hi, fb) {
    var n = Number(v);
    if (!isFinite(n)) return fb;
    n = Math.round(n);
    return clamp(n, lo, hi);
  }
  function indFloat(v, lo, hi, fb) {
    var n = Number(v);
    if (!isFinite(n)) return fb;
    return clamp(n, lo, hi);
  }
  function cloneInd(v) { return JSON.parse(JSON.stringify(v)); }
  function normIndLines(raw, defs) {
    var src = Array.isArray(raw) ? raw : [], out = [], i;
    for (i = 0; i < 4; i++) {
      var it = (i < src.length && src[i] && typeof src[i] === 'object')
        ? src[i] : defs[i];
      out.push({ period: indInt(it.period, 2, 500, defs[i].period),
                 enabled: !!it.enabled });
    }
    return out;
  }
  function normInd(raw) {
    var s = (raw && typeof raw === 'object') ? raw : {};
    var b = (s.boll && typeof s.boll === 'object') ? s.boll : {};
    var m = (s.macd && typeof s.macd === 'object') ? s.macd : {};
    var fast = indInt(m.fast, 2, 100, 12);
    var slow = indInt(m.slow, 3, 200, 26);
    if (slow <= fast) slow = fast + 1;
    return {
      ma: normIndLines(s.ma, IND_DEFAULT.ma),
      ema: normIndLines(s.ema, IND_DEFAULT.ema),
      boll: { period: indInt(b.period, 2, 200, 20),
              k: Math.round(indFloat(b.k, 0.5, 5, 2) * 100) / 100 },
      macd: { fast: fast, slow: slow,
              signal: indInt(m.signal, 2, 100, 9) }
    };
  }
  function indParams(interval) {
    var store = CFG.indicator_params || {};
    var base = normInd(store[IND_SCOPE_ALL]);
    var key = String(interval || '');
    var ov = (key && key !== IND_SCOPE_ALL) ? store[key] : null;
    if (!ov || typeof ov !== 'object') return base;
    var m = { ma: base.ma, ema: base.ema, boll: base.boll,
              macd: base.macd }, f;
    for (f in m) if (Object.prototype.hasOwnProperty.call(ov, f)) m[f] = ov[f];
    return normInd(m);
  }
  function writeIndParams(scope, params) {
    var clean = normInd(params);
    var store = (CFG.indicator_params && typeof CFG.indicator_params === 'object')
      ? CFG.indicator_params : {};
    var key = (!scope || scope === IND_SCOPE_ALL) ? IND_SCOPE_ALL : String(scope);
    if (key === IND_SCOPE_ALL) {
      store[key] = clean;
    } else {
      // 只存与全局不同的字段：之后改全局 BOLL 时该周期会跟着变
      var base = normInd(store[IND_SCOPE_ALL]), partial = {}, f;
      for (f in clean) if (Object.prototype.hasOwnProperty.call(clean, f)) {
        if (JSON.stringify(clean[f]) !== JSON.stringify(base[f])) partial[f] = clean[f];
      }
      if (Object.keys(partial).length) store[key] = partial;
      else delete store[key];
    }
    CFG.indicator_params = store;
    saveCfg();
    return clean;
  }
  function resetIndParams(scope) {
    var key = (!scope || scope === IND_SCOPE_ALL) ? IND_SCOPE_ALL : String(scope);
    var store = (CFG.indicator_params && typeof CFG.indicator_params === 'object')
      ? CFG.indicator_params : {};
    if (key === IND_SCOPE_ALL) store[key] = cloneInd(IND_DEFAULT);
    else delete store[key];
    CFG.indicator_params = store;
    saveCfg();
  }

  // ---- 指标计算：返回与 CANDLES 等长的数组，预热段为 null ----
  function maSeries(rows, n) {
    var out = [], s = 0;
    for (var i = 0; i < rows.length; i++) {
      s += rows[i].c;
      if (i >= n) s -= rows[i - n].c;
      out.push(i >= n - 1 ? s / n : null);
    }
    return out;
  }
  function emaSeries(rows, n) {
    var out = [], k = 2 / (n + 1), e = 0;
    for (var i = 0; i < rows.length; i++) {
      if (i < n - 1) { e += rows[i].c; out.push(null); continue; }
      if (i === n - 1) { e = (e + rows[i].c) / n; out.push(e); continue; }
      e = rows[i].c * k + e * (1 - k);
      out.push(e);
    }
    return out;
  }
  function bollSeries(rows, n, k) {
    var up = [], mid = [], dn = [];
    for (var i = 0; i < rows.length; i++) {
      if (i < n - 1) { up.push(null); mid.push(null); dn.push(null); continue; }
      var s = 0, j;
      for (j = i - n + 1; j <= i; j++) s += rows[j].c;
      var m = s / n, v = 0;
      for (j = i - n + 1; j <= i; j++) v += Math.pow(rows[j].c - m, 2);
      var sd = Math.sqrt(v / n);
      mid.push(m); up.push(m + k * sd); dn.push(m - k * sd);
    }
    return { up: up, mid: mid, dn: dn };
  }
  function macdSeries(rows, fast, slow, signal) {
    var ef = emaSeries(rows, fast), es = emaSeries(rows, slow);
    var dif = [], dea = [], hist = [], pv = [], pos = [], i, j;
    for (i = 0; i < rows.length; i++) {
      var d = (ef[i] === null || es[i] === null) ? null : ef[i] - es[i];
      dif.push(d); dea.push(null); hist.push(null);
      if (d !== null) { pv.push(d); pos.push(i); }
    }
    var dv = emaSeries(pv.map(function (v) { return { c: v }; }), signal);
    for (j = 0; j < pos.length; j++) {
      var k = pos[j];
      dea[k] = dv[j];
      hist[k] = dv[j] === null ? null : 2 * (dif[k] - dv[j]);
    }
    return { dif: dif, dea: dea, hist: hist };
  }
  function indLines(rows, params) {
    var out = [], seenMa = {}, seenEma = {}, i, l;
    if (CFG.show_ma !== false) {
      for (i = 0; i < params.ma.length; i++) {
        l = params.ma[i];
        if (!l.enabled || seenMa[l.period]) continue;
        seenMa[l.period] = 1;
        out.push({ label: 'MA' + l.period, values: maSeries(rows, l.period),
                   color: MA_COLORS[i], width: 1.2 });
      }
    }
    if (CFG.show_ema !== false) {
      for (i = 0; i < params.ema.length; i++) {
        l = params.ema[i];
        if (!l.enabled || seenEma[l.period]) continue;
        seenEma[l.period] = 1;
        out.push({ label: 'EMA' + l.period, values: emaSeries(rows, l.period),
                   color: EMA_COLORS[i], width: 1.5 });
      }
    }
    if (CFG.show_boll !== false) {
      var b = bollSeries(rows, params.boll.period, params.boll.k);
      out.push({ label: 'BOLL UP', values: b.up, color: '#4b9cff', width: 1 },
               { label: 'BOLL MB', values: b.mid, color: '#f0b90b', width: 1 },
               { label: 'BOLL DN', values: b.dn, color: '#4b9cff', width: 1 });
    }
    return out;
  }
  function enabledIndPeriods(params, kind) {
    var out = [], seen = {}, lines = params[kind] || [];
    for (var i = 0; i < lines.length; i++) {
      if (lines[i].enabled && !seen[lines[i].period]) {
        seen[lines[i].period] = 1; out.push(lines[i].period);
      }
    }
    return out;
  }

  // ===================== 网络桥（Promise 封装 + 回调分发） =====================
  var _cbSeq = 0, _cbMap = {};
  window.__nativeCb = function (id, body, err) {
    var e = _cbMap[id];
    if (!e) return;                       // 已超时/重复回调，直接忽略
    delete _cbMap[id];
    if (err) { e.reject(new Error(String(err))); return; }
    e.resolve(String(body));
  };
  function http(url, charset) {
    return new Promise(function (resolve, reject) {
      if (window.Native && Native.http) {
        var id = 'cb' + (++_cbSeq);
        _cbMap[id] = { resolve: resolve, reject: reject };
        setTimeout(function () {
          if (_cbMap[id]) { delete _cbMap[id]; reject(new Error('请求超时')); }
        }, 22000);
        try { Native.http(url, charset || 'UTF-8', id); }
        catch (e) { delete _cbMap[id]; reject(e); }
      } else {
        // 桌面浏览器预览降级：仅用于本地检查 UI，APK 内不走这条路径
        fetch(url).then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.text();
        }).then(resolve, reject);
      }
    });
  }

  // ===================== 品种清单与资料库 =====================
  var U = window.UNIVERSE || {};
  var ABOUT = (window.ABOUT_DB || {}).about || {};
  var ABOUT_DEFAULT = (window.ABOUT_DB || {}).market_default || {};
  // v37：发展历程 / 品种档案由 tools/export_profile_db.py 从桌面资料库导出
  var TL_DB = (window.ABOUT_DB || {}).timeline || {};
  var ARC_DB = (window.ABOUT_DB || {}).archive || {};
  var ARC_FIELDS = (window.ABOUT_DB || {}).archive_fields || [];
  var DB_META = (window.ABOUT_DB || {}).meta || {};
  // 行情里程碑：打开详情时按需用真实历史 K 线 / 本机报价采样计算
  var MILESTONES = {};
  var ALL = {}, NAME_OF = {}, INDEX_OF = {};
  (function () {
    for (var i = 0; i < MARKETS.length; i++) {
      var mk = MARKETS[i][0];
      var rows = U[mk] || [];
      ALL[mk] = [];
      INDEX_OF[mk] = {};
      for (var j = 0; j < rows.length; j++) {
        var sym = String(rows[j][0]), nm = String(rows[j][1] || rows[j][0]);
        ALL[mk].push(sym);
        NAME_OF[sym] = nm;
        INDEX_OF[mk][sym] = j;
      }
    }
  })();
  function marketOf(sym) {
    var i = sym.indexOf(':');
    if (i < 0) return 'crypto';
    var p = sym.slice(0, i).toLowerCase();
    return (p === 'sh' || p === 'sz') ? 'cn' : (p === 'hk' ? 'hk' : (p === 'us' ? 'us' : 'crypto'));
  }
  // 链上合约品种带冒号但不是股票，不能丢进腾讯行情请求里
  function isStock(sym) { return !isOnchain(sym) && sym.indexOf(':') >= 0; }
  function nameOf(sym) {
    if (isOnchain(sym)) return (CFG.onchain[sym] || {}).name || ocCode(sym);
    return NAME_OF[sym] || sym;
  }
  function aboutOf(sym) {
    if (isOnchain(sym)) {
      var m = CFG.onchain[sym] || {};
      // 项目背景 / 业务 / 前景没有数据源，一律留白，不用通用简介冒充
      return { title: m.name || ocCode(sym),
               category: (m.chain || '公链') + ' 链上合约代币',
               contract: ocAddr(sym), launchpad: m.launchpad || null,
               source: '链上合约地址', summary: null, background: null,
               business: null, highlights: null, purpose: null,
               outlook: null, founder: null, since: null, product: null };
    }
    var mk = marketOf(sym);
    return ABOUT[sym] || ABOUT_DEFAULT[mk] || null;
  }
  function listedYear(sym) {
    var a = ABOUT[sym] || {};
    var m = /(1[89]\d{2}|20\d{2})/.exec(String(a.since || ''));
    return m ? Number(m[1]) : null;
  }
  function toTencentCode(sym) {
    var i = sym.indexOf(':');
    if (i < 0) return null;
    var mk = sym.slice(0, i).toLowerCase(), code = sym.slice(i + 1);
    return mk === 'us' ? 'us' + code.toUpperCase() : mk + code.toLowerCase();
  }

  // ===================== 行情 / 元数据状态 =====================
  var TICKERS = readJSON('ct_tickers', {});       // 上次的真实快照（断网可读）
  var TICKER_ASOF = Number(store.get('ct_tickers_asof') || 0);
  var BATCH = {};                                 // 本轮实时命中的品种
  var META = readJSON('ct_meta', {});             // 真实排序元数据（7 天缓存）
  var SOURCE_TEXT = TICKER_ASOF ? '缓存' : '--';
  var _metaLoading = false, _metaDoneAt = 0;

  function priceOf(sym) {
    var t = TICKERS[sym];
    if (!t) return null;
    return { price: t.price, chg: t.chg, stale: !BATCH[sym] };
  }
  // 只落盘接口返回的真实数值；内置上市年份每次启动由资料库重算，
  // 避免把 1000 个空壳条目反复写进 SharedPreferences。
  function saveMeta() {
    var out = {}, s, m;
    for (s in META) {
      if (!Object.prototype.hasOwnProperty.call(META, s)) continue;
      m = META[s];
      if (!m) continue;
      if (m.cap !== undefined || m.turnover !== undefined ||
          m.volume24 !== undefined || m.rank !== undefined ||
          (m.source && m.source !== '内置公开资料库')) out[s] = m;
    }
    writeJSON('ct_meta', out);
  }

  // ===================== 链上合约品种（无 K 线也能收藏 / 看价） =====================
  var ONCHAIN_Q = readJSON('ct_onchain_quotes', {});   // 上次真实链上报价
  // 本设备采集的链上真实报价序列：{ sym: [[ts, price], ...] }。
  // 这不是交易所 K 线，没有 OHLC / 成交量；图表只连接真实采到的价格点，
  // 并在界面上明确标注来源与「非 K 线」，绝不插值或编造蜡烛。
  var OC_HIST = readJSON('ct_oc_hist', {});
  var OC_HIST_MAX = 720;
  var _ocBusy = false, _ocLast = 0;
  var _ocPending = {};   // busy 期间被强制请求的品种，完成后立即补取，避免首屏空采样

  function drawOnchainFallbackNote() {
    var src = OC_SOURCE;
    $('chartNote').textContent = '链上历史 K 线数据源暂不可用 · 显示本设备真实报价走势（' +
      src + ' 采样）· 无 OHLC / 成交量 · 网络恢复后自动重试';
  }

  function ocSeries(sym) {
    var a = OC_HIST[sym];
    return Array.isArray(a) ? a : [];
  }
  function recordOcSample(sym, ts, price) {
    ts = Number(ts); price = Number(price);
    if (!isFinite(ts) || ts <= 0 || !isFinite(price) || price <= 0) return false;
    var arr = OC_HIST[sym] || (OC_HIST[sym] = []);
    var last = arr.length ? arr[arr.length - 1] : null;
    // 同一轮 20 秒内的重复回调、以及报价没变化的轮询不重复记点
    if (last && Math.abs(ts - Number(last[0])) < 20 && last[1] === price) return false;
    arr.push([ts, price]);
    if (arr.length > OC_HIST_MAX) arr.splice(0, arr.length - OC_HIST_MAX);
    writeJSON('ct_oc_hist', OC_HIST);
    return true;
  }

  function parseRugcheck(text) {
    var d;
    try { d = JSON.parse(text); } catch (e) { return null; }
    if (!d || typeof d !== 'object') return null;
    var tok = d.token || {}, tm = d.tokenMeta || {}, ver = d.verification || {},
        lp = d.launchpad || {};
    var dec = tok.decimals, supply = null;
    if (typeof tok.supply === 'number' && typeof dec === 'number') {
      supply = tok.supply / Math.pow(10, dec);
    }
    var price = Number(d.price); if (!isFinite(price) || price <= 0) price = null;
    var liq = Number(d.totalMarketLiquidity); if (!isFinite(liq)) liq = null;
    var holders = Number(d.totalHolders); if (!isFinite(holders)) holders = null;

    // 真实链上结构数据：前 10 大持有地址占比、流动性池类型分布。
    // 这些是当前报告里的真实字段，用来在没有 K 线时提供「看得见」的图表，
    // 而不是画假蜡烛。没有的字段一律留空，界面会明确显示缺失。
    var tops = [], pools = [], poolMap = {}, i, h, mt, k;
    if (Array.isArray(d.topHolders)) {
      for (i = 0; i < Math.min(10, d.topHolders.length); i++) {
        h = d.topHolders[i] || {};
        var pct = Number(h.pct);
        if (!isFinite(pct) || pct <= 0) continue;
        tops.push({ pct: Math.round(pct * 100) / 100,
                    label: shortAddr(String(h.address || '')) });
      }
    }
    if (Array.isArray(d.markets)) {
      for (i = 0; i < d.markets.length; i++) {
        mt = String((d.markets[i] || {}).marketType || 'other');
        poolMap[mt] = (poolMap[mt] || 0) + 1;
      }
      for (k in poolMap) {
        if (Object.prototype.hasOwnProperty.call(poolMap, k)) {
          pools.push({ label: k, count: poolMap[k] });
        }
      }
      pools.sort(function (a, b) { return b.count - a.count; });
      pools = pools.slice(0, 6);
    }
    return {
      price: price,
      chg: null,            // 该数据源不提供 24h 涨跌，绝不编造
      high: null, low: null, amount: null,
      liquidity: liq, holders: holders, supply: supply,
      cap: (price && supply) ? price * supply : null,
      code: String(tm.symbol || ver.symbol || '').slice(0, 12).toUpperCase(),
      name: String(tm.name || ver.name || ''),
      launchpad: String(lp.name || ''),
      top_holders: tops, pool_types: pools,
      market_count: Array.isArray(d.markets) ? d.markets.length : null,
      source: OC_SOURCE, ts: nowSec()
    };
  }

  function applyOnchainQuote(sym, q) {
    NAME_OF[sym] = q.name || q.code || shortAddr(ocAddr(sym));
    if (q.price !== null) {
      TICKERS[sym] = { price: q.price, chg: null, high: null, low: null,
                       amount: null, ts: q.ts, stale: false };
      BATCH[sym] = 1;
      recordOcSample(sym, q.ts, q.price);   // 累积真实价格点，供走势图使用
    }
    META[sym] = {
      cap: q.cap, cap_unit: 'USD', liquidity: q.liquidity,
      supply_circulating: q.supply, supply_total: q.supply,
      holders: q.holders, source: q.source, asof: q.ts * 1000,
      chain: 'Solana', no_kline: true
    };
    var m = CFG.onchain[sym] || (CFG.onchain[sym] = {});
    m.address = ocAddr(sym);
    if (q.code) m.code = q.code;
    if (q.name) m.name = q.name;
    if (q.launchpad) m.launchpad = q.launchpad;
    m.chain = 'Solana'; m.source = q.source;
  }

  function refreshOnchain(syms, force) {
    if (!syms || !syms.length) return Promise.resolve(0);
    if (_ocBusy) {
      // 有请求在途：强制请求记入待办，完成后补取；普通请求直接跳过。
      if (force) { for (var pi = 0; pi < syms.length; pi++) _ocPending[syms[pi]] = 1; }
      return Promise.resolve(0);
    }
    if (!force && nowMs() - _ocLast < 60000) return Promise.resolve(0);
    _ocBusy = true; _ocLast = nowMs();
    // 记录发起时的图表请求序号：回调里据此判断图表是否需要跟着重绘，
    // 防止切到别的链上品种后，旧请求回来重绘当前图表（数据写入照常）。
    var chartSeqAtStart = chartLoadSeq;
    var jobs = syms.map(function (s) {
      var a = ocAddr(s);
      if (!isSolanaAddr(a)) return Promise.resolve([s, null]);
      return http(RUGCHECK + encodeURIComponent(a) + '/report')
        .then(function (txt) { return [s, parseRugcheck(txt)]; })
        .catch(function () { return [s, null]; });
    });
    return Promise.all(jobs).then(function (parts) {
      _ocBusy = false;
      var n = 0;
      for (var i = 0; i < parts.length; i++) {
        var s = parts[i][0], q = parts[i][1];
        if (!q) continue;
        ONCHAIN_Q[s] = q;
        applyOnchainQuote(s, q);
        n++;
      }
      if (n) {
        writeJSON('ct_onchain_quotes', ONCHAIN_Q);
        TICKER_ASOF = nowSec();
        writeJSON('ct_tickers', TICKERS);
        store.set('ct_tickers_asof', TICKER_ASOF);
        SOURCE_TEXT = OC_SOURCE;
        saveCfg();
        scheduleRender();            // 合帧：链上报价高频刷新不与主刷新重复重建列表
        // 仅当这次报价请求仍是当前图表请求时才重绘图表；
        // 否则数据已入 ONCHAIN_Q，待当前品种自己的请求回来再画。
        if (PAGE === 'chart' && chartSeqAtStart === chartLoadSeq) {
          updateChartHead();
          if (isOnchain(CHART_SYMBOL)) drawChart();   // 新采样点立即进走势图
        }
        if (openSheetId === 'detailSheet') {
          var d = $('detailSheet').getAttribute('data-sym');
          if (d && isOnchain(d)) $('detailBody').innerHTML = detailHTML(d);
        }
        setStatus('● 链上报价已更新 · ' + OC_SOURCE + ' · ' + fmtTime(TICKER_ASOF), false);
      }
      return n;
    }).catch(function () {
      _ocBusy = false;
      return 0;
    }).then(function (n) {
      // 补取 busy 期间被强制请求的品种（首屏快照竞态修复）
      var pending = Object.keys(_ocPending);
      _ocPending = {};
      if (pending.length) setTimeout(function () { refreshOnchain(pending, true); }, 300);
      return n;
    });
  }

  function addContract(addr) {
    addr = String(addr || '').trim();
    var chain = chainOfAddr(addr), sym = ocSymbol(addr);
    if (!chain) { toast('不是有效的链上合约地址'); return Promise.resolve(); }
    // EVM / Tron 目前没有可直连的公开链上报价源：仍允许收藏，但明确标注
    // 「暂无公开报价」，绝不用交易所价格冒充链上价格。
    if (chain !== 'Solana') {
      CFG.onchain[sym] = { address: addr, code: '', name: shortAddr(addr),
                           chain: chain, source: '链上合约地址' };
      if (CFG.symbols.indexOf(sym) < 0) CFG.symbols.push(sym);
      NAME_OF[sym] = shortAddr(addr);
      META[sym] = { no_kline: true, source: '链上合约地址' };
      saveCfg(); computeOrder(); renderList();
      toast('已收藏该链上合约 · 暂无可直连的公开链上报价源');
      return Promise.resolve();
    }
    setStatus('● 正在解析链上合约…', false);
    return http(RUGCHECK + encodeURIComponent(addr) + '/report')
      .then(function (txt) {
        var q = parseRugcheck(txt);
        if (!q) throw new Error('链上报告未返回有效数据');
        CFG.onchain[sym] = { address: addr, code: q.code, name: q.name,
                             chain: 'Solana', launchpad: q.launchpad,
                             source: q.source };
        if (CFG.symbols.indexOf(sym) < 0) CFG.symbols.push(sym);
        ONCHAIN_Q[sym] = q;
        applyOnchainQuote(sym, q);
        saveCfg();
        writeJSON('ct_onchain_quotes', ONCHAIN_Q);
        computeOrder(); renderList();
        toast((q.code || '链上代币') + ' 已加入自选 · 图表显示真实报价走势');
        return sym;
      }).catch(function (e) {
        setStatus('● 链上解析失败：' + (e && e.message ? e.message : '网络异常'), true);
        toast('链上解析失败，请检查网络或地址是否完整');
      });
  }

  // ---- 解析：腾讯行情（Java 已按 GBK 解码，JS 收到的是可读中文） ----
  function parseTencent(text) {
    var out = {};
    var lines = String(text).split(';');
    for (var i = 0; i < lines.length; i++) {
      var m = /v_(\w+)="(.*)"/.exec(lines[i].trim());
      if (!m) continue;
      var qt = m[1], f = m[2].split('~');
      if (f.length < 38) continue;
      var mk = qt.slice(0, 2).toUpperCase();
      var raw = qt.slice(2).split('.')[0].toUpperCase();
      var sym = mk + ':' + raw;
      var amount = fnum(f[37]);
      if (amount !== null && (mk === 'SH' || mk === 'SZ')) amount *= 1e4;
      var ts = 0;
      var tstr = String(f[30] || '');
      if (/^\d{14}$/.test(tstr)) {
        var D = new Date(Number(tstr.slice(0, 4)), Number(tstr.slice(4, 6)) - 1,
          Number(tstr.slice(6, 8)), Number(tstr.slice(8, 10)),
          Number(tstr.slice(10, 12)), Number(tstr.slice(12, 14)));
        ts = Math.floor(D.getTime() / 1000);
      }
      out[sym] = {
        price: fnum(f[3]), chg: fnum(f[32]),
        high: fnum(f[33]), low: fnum(f[34]), amount: amount,
        name: f[1] || nameOf(sym), ts: ts,
        cap: fnum(f[45]), float_cap: fnum(f[44]),
        turnover: fnum(f[38]), pe: fnum(f[39]), pb: fnum(f[46])
      };
      // 市值/流动性来自同一份真实返回，直接进元数据（不额外发请求）
      var meta = META[sym] || {};
      if (fnum(f[45]) !== null) meta.cap = fnum(f[45]);
      if (fnum(f[44]) !== null) meta.float_cap = fnum(f[44]);
      if (fnum(f[38]) !== null) meta.turnover = fnum(f[38]);
      if (fnum(f[39]) !== null) meta.pe = fnum(f[39]);
      if (fnum(f[46]) !== null) meta.pb = fnum(f[46]);
      meta.amount = amount;
      meta.listed = listedYear(sym);
      meta.cap_unit = '亿元（本市场计价货币）';
      meta.source = '腾讯行情';
      meta.asof = nowMs();
      META[sym] = meta;
    }
    return out;
  }

  // ---- 解析：Binance 24hr ----
  function parseBinance(text) {
    var out = {}, rows;
    try { rows = JSON.parse(text); } catch (e) { return out; }
    if (!Array.isArray(rows)) return out;
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i], s = String(r.symbol || '');
      if (s.slice(-4) !== 'USDT') continue;
      var sym = s.slice(0, -4);
      out[sym] = {
        price: fnum(r.lastPrice), chg: fnum(r.priceChangePercent),
        high: fnum(r.highPrice), low: fnum(r.lowPrice),
        amount: fnum(r.quoteVolume), name: sym, ts: nowSec()
      };
    }
    return out;
  }

  // ---- 解析：CoinLore（加密市值 / 供应量 / 成交额 / 排名） ----
  function applyCoinLore(text) {
    var d;
    try { d = JSON.parse(text); } catch (e) { return 0; }
    if (!d || !Array.isArray(d.data)) return 0;
    var n = 0;
    for (var i = 0; i < d.data.length; i++) {
      var r = d.data[i], sym = String(r.symbol || '').toUpperCase();
      if (!sym) continue;
      var cap = fnum(r.market_cap_usd), vol = fnum(r.volume24);
      var m = META[sym] || {};
      if (cap !== null) m.cap = cap;
      if (fnum(r.rank) !== null) m.rank = Number(r.rank);
      if (vol !== null) m.volume24 = vol;
      var csup = fnum(r.csupply), tsup = fnum(r.tsupply), msup = fnum(r.msupply);
      if (csup !== null) m.supply_circulating = csup;
      if (tsup !== null) m.supply_total = tsup;
      if (msup !== null) m.supply_max = msup;
      // 流动性 = 24h 成交额 ÷ 流通市值 × 100（同为 USD，真实可计算比率）
      if (cap !== null && cap > 0 && vol !== null) {
        m.liquidity = vol / cap * 100;
      }
      m.listed = listedYear(sym);
      m.cap_unit = 'USD';
      m.source = 'CoinLore';
      m.asof = nowMs();
      META[sym] = m;
      n++;
    }
    return n;
  }

  function mergeTickerMaps(parts) {
    var map = {}, p, s;
    for (p = 0; p < parts.length; p++) {
      for (s in parts[p]) {
        if (Object.prototype.hasOwnProperty.call(parts[p], s)) map[s] = parts[p][s];
      }
    }
    return map;
  }
  // 币安的 symbols 数组是「全有或全无」：只要有一个已下架 / 非法交易对，
  // 整批 100 个品种都返回 400。失败时把批次拆小重试，只丢真正无效的
  // 那一个，避免「整个加密货币页打开没数据」。
  function binanceBatch(pairs, depth) {
    depth = depth || 0;
    if (!pairs || !pairs.length) return Promise.resolve({});
    return http(BINANCE_TICKER + encodeURIComponent(JSON.stringify(pairs)))
      .then(parseBinance)
      .catch(function () {
        if (pairs.length <= 1 || depth >= 4) return {};
        var n = Math.max(1, Math.ceil(pairs.length / 4)), jobs = [], i;
        for (i = 0; i < pairs.length; i += n) {
          jobs.push(binanceBatch(pairs.slice(i, i + n), depth + 1));
        }
        return Promise.all(jobs).then(mergeTickerMaps);
      });
  }

  // ---- 行情批量请求（窗口化，后台执行，不阻塞 UI） ----
  function fetchTickers(symbols) {
    var crypto = [], stocks = [], i;
    for (i = 0; i < symbols.length; i++) {
      if (isOnchain(symbols[i])) continue;   // 走独立链上报价源
      if (isStock(symbols[i])) stocks.push(symbols[i]); else crypto.push(symbols[i]);
    }
    var jobs = [], sources = [];

    for (i = 0; i < crypto.length; i += 100) {
      var pairs = [];
      for (var j = i; j < Math.min(i + 100, crypto.length); j++) {
        pairs.push(crypto[j] + 'USDT');
      }
      jobs.push(binanceBatch(pairs));
      sources.push('Binance');
    }
    for (i = 0; i < stocks.length; i += 60) {
      var codes = [], group = stocks.slice(i, i + 60);
      for (var k = 0; k < group.length; k++) {
        var c = toTencentCode(group[k]);
        if (c) codes.push(c);
      }
      if (!codes.length) continue;
      jobs.push(http(TENCENT_QUOTE + codes.join(','), 'GBK')
        .then(parseTencent).catch(function () { return {}; }));
      sources.push('腾讯行情');
    }
    if (!jobs.length) return Promise.resolve({ map: {}, sources: [] });
    return Promise.all(jobs).then(function (parts) {
      var map = {};
      for (var p = 0; p < parts.length; p++) {
        for (var s in parts[p]) {
          if (Object.prototype.hasOwnProperty.call(parts[p], s)) map[s] = parts[p][s];
        }
      }
      return { map: map, sources: sources };
    });
  }

  // ---- CoinLore 元数据（仅在使用市值/流动性排序或打开加密详情时后台拉取） ----
  function needMeta(mode) { return !!META_MODES[mode]; }
  function metaFresh() {
    if (_metaDoneAt && nowMs() - _metaDoneAt < 30 * 60 * 1000) return true;
    var n = 0;
    for (var s in META) { if (META[s] && META[s].source === 'CoinLore') n++; }
    return n > 0;
  }
  function fetchMeta(force) {
    if (_metaLoading) return Promise.resolve();
    if (!force && metaFresh()) return Promise.resolve();
    _metaLoading = true;
    var jobs = [];
    for (var start = 0; start <= 400; start += 100) {
      jobs.push(http(COINLORE + start + '&limit=100').then(applyCoinLore)
        .catch(function () { return 0; }));
    }
    return Promise.all(jobs).then(function () {
      _metaDoneAt = nowMs();
      _metaLoading = false;
      saveMeta();
    }).catch(function () { _metaLoading = false; });
  }

  // ===================== 排序 / 筛选 / 分页 =====================
  var PAGE = 'list';
  var MARKET = CFG.last_tab in ALL ? CFG.last_tab : 'crypto';
  var SEARCH_TEXT = '';
  var LOADED = PAGE_SIZE;
  var ORDER = [];
  var CHART_SYMBOL = CFG.last_symbol || '';
  var CANDLES = [];
  var CHART_INTERVAL = '';
  // K 线异步请求序号：每次切换品种 / 周期递增，旧请求的回调一律作废，
  // 防止「AAPL 请求晚于 TSLA 返回」把当前图表覆盖成旧品种/旧周期数据。
  var chartLoadSeq = 0;
  var VIEW = { count: Number(CFG.chart_view_count) || 90,
               pan: Number(CFG.chart_view_pan) || 0 };
  // 当前品种/周期的轻量 K 线缓存：只保留最近使用的 6 个序列，避免 localStorage 膨胀。
  // checkedBucket 表示“该周期桶已向数据源确认过没有新根”，防止边界附近反复打源。
  var KLINE_CACHE = readJSON('ct_kline', {});
  var _klineTimer = null;
  var openSheetId = '';
  // 长按手势状态（模块级，便于在 touchcancel/失焦/页面隐藏/滚动时统一清理）。
  var LP = { timer: null, sym: null, startX: 0, startY: 0, active: false, el: null };
  // 长按/右键弹出菜单后，抑制「同一次手势」产生的普通 click；按具体行判定，
  // 且只抑制一次（避免旧版全局时间窗吞掉后续不相干的轻触）。
  var _suppressClickSym = null;
  function lpCancel() {
    if (LP.timer) { clearTimeout(LP.timer); LP.timer = null; }
    LP.sym = null; LP.active = false; LP.el = null;
  }
  function lpArmClickSuppress(sym) { _suppressClickSym = sym; }
  function lpConsumeClickSuppress(sym) {
    if (_suppressClickSym !== null && _suppressClickSym === sym) {
      _suppressClickSym = null; return true;   // 该手势的 click 已被消费
    }
    _suppressClickSym = null;                 // 其它手势：清标记，绝不吞正常点击
    return false;
  }

  function watchList(mk) {
    var out = [];
    for (var i = 0; i < CFG.symbols.length; i++) {
      var s = String(CFG.symbols[i]);
      // 只要市场归属一致就算自选：离线清单没收录的代码（ETF、新上市股票、
      // 从桌面导入的配置）也是用户真实收藏，不能静默丢掉，否则该市场
      // 永远显示「自选为空」，看起来就像加不进自选。
      if (marketOf(s) === mk) out.push(s);
    }
    return out;
  }
  function baseList() {
    var sub = CFG.sub_tabs[MARKET] === 'all' ? 'all' : 'watch';
    if (sub === 'watch') {
      // 绝不在这里把 sub_tabs 悄悄改成 'all'：旧逻辑会让用户点「自选」
      // 后立刻被弹回「全部」，按钮看起来完全点不动。空列表交给
      // renderList 显示明确的引导卡片。
      return watchList(MARKET);
    }
    return ALL[MARKET].slice();
  }
  function rankValue(sym, mode) {
    var t = TICKERS[sym], m = META[sym] || {};
    if (/^change/.test(mode)) return t ? t.chg : null;
    if (/^price/.test(mode)) return t ? t.price : null;
    if (/^amount/.test(mode)) return t ? t.amount : null;
    if (/^cap/.test(mode)) return (m.cap === undefined ? null : m.cap);
    if (/^liquidity/.test(mode)) {
      if (m.turnover !== undefined && m.turnover !== null) return m.turnover;
      return (m.liquidity === undefined ? null : m.liquidity);
    }
    if (/^listed/.test(mode)) return (m.listed === undefined ? null : m.listed);
    if (mode === 'default') {
      if (m.rank) return -Number(m.rank);   // 真实 CoinLore 排名：越小越靠前
      var idx = INDEX_OF[MARKET][sym];
      return idx === undefined ? null : -idx;
    }
    return null; // custom：用自选顺序
  }
  function computeOrder() {
    var list = baseList();
    var q = SEARCH_TEXT.trim().toLowerCase();
    if (q) {
      list = list.filter(function (s) {
        return (s + ' ' + nameOf(s)).toLowerCase().indexOf(q) >= 0;
      });
    }
    var mode = CFG.sort_mode || 'custom';
    var asc = /_asc$/.test(mode) || (mode === 'listed_asc');
    if (CFG.sort_reverse) asc = !asc;

    if (mode === 'custom') {
      var pos = {}, i;
      for (i = 0; i < CFG.symbols.length; i++) pos[String(CFG.symbols[i])] = i;
      var universePos = {};
      for (i = 0; i < ALL[MARKET].length; i++) universePos[ALL[MARKET][i]] = i;
      list.sort(function (a, b) {
        var pa = pos[a] === undefined ? 100000 + (universePos[a] || 0) : pos[a];
        var pb = pos[b] === undefined ? 100000 + (universePos[b] || 0) : pos[b];
        return asc ? pb - pa : pa - pb;
      });
    } else if (mode === 'default') {
      list.sort(function (a, b) {
        var va = rankValue(a, mode), vb = rankValue(b, mode);
        if (va === null && vb === null) return (INDEX_OF[MARKET][a] || 0) - (INDEX_OF[MARKET][b] || 0);
        if (va === null) return 1;
        if (vb === null) return -1;
        return asc ? va - vb : vb - va;
      });
    } else {
      list.sort(function (a, b) {
        var va = rankValue(a, mode), vb = rankValue(b, mode);
        if (va === null && vb === null) return (INDEX_OF[MARKET][a] || 0) - (INDEX_OF[MARKET][b] || 0);
        if (va === null) return 1;     // 没有真实数据的一律排末尾
        if (vb === null) return -1;
        return asc ? va - vb : vb - va;
      });
    }
    // 置顶优先于一切排序规则，按用户置顶先后排列
    var pins = [];
    for (var p = 0; p < CFG.pinned_symbols.length; p++) {
      var ps = String(CFG.pinned_symbols[p]);
      if (list.indexOf(ps) >= 0) pins.push(ps);
    }
    if (pins.length) {
      var ps2 = {};
      for (var z = 0; z < pins.length; z++) ps2[pins[z]] = 1;
      list = pins.concat(list.filter(function (s) { return !ps2[s]; }));
    }
    ORDER = list;
    return list;
  }

  function windowSymbols() {
    var n = Math.min(LOADED + PREFETCH_ROWS, ORDER.length, MAX_REFRESH_SYMBOLS);
    return uniq(ORDER.slice(0, n));
  }

  // 内置公开资料库里的上市/创立年份无需联网，启动即填好（不覆盖真实值）。
  // 未收录品种保持 null，排序时排末尾，绝不猜测年份。
  function ensureListedMeta() {
    for (var mi = 0; mi < MARKETS.length; mi++) {
      var rows = ALL[MARKETS[mi][0]] || [];
      for (var j = 0; j < rows.length; j++) {
        var s = rows[j], m = META[s] || {};
        if (m.listed === undefined || m.listed === null) m.listed = listedYear(s);
        if (!m.source) m.source = '内置公开资料库';
        META[s] = m;
      }
    }
  }

  // ===================== 列表渲染 =====================
  var _renderQueued = false;
  function scheduleRender() {
    if (_renderQueued) return;
    _renderQueued = true;
    (window.requestAnimationFrame || function (f) { setTimeout(f, 16); })(function () {
      _renderQueued = false;
      // 合帧渲染只由行情数据刷新触发，市场/子页状态未变，无需重建标签按钮
      renderList({ skipTabs: true });
    });
  }

  // 行级增量渲染缓存：可见行的顺序签名 + 每行 HTML。
  // 数据刷新时若行集合与顺序不变，只就地替换内容真正变化的行，
  // 避免整表 innerHTML 重建（同时保留图标 <img> 节点，防止重复加载与滚动抖动）。
  // 当运行环境 DOM 能力不足（如测试桩）或结构变化时自动回退到全量重建。
  var _lastRenderSig = null;
  var _lastRowHTML = [];
  function rowsSignature(rows) { return rows.join('\u0001'); }
  function patchRowsFromHTML(list, htmls) {
    if (!list.querySelectorAll || !document.createElement) return false;
    var nodes = list.querySelectorAll('.trow');
    if (!nodes || nodes.length !== htmls.length) return false;
    for (var i = 0; i < htmls.length; i++) {
      if (htmls[i] === _lastRowHTML[i]) continue;
      var holder = document.createElement('div');
      holder.innerHTML = htmls[i];
      var fresh = holder.firstElementChild || holder.firstChild;
      if (!fresh || !fresh.querySelector) return false;
      var old = nodes[i];
      var oldInfo = old.querySelector('.info'), newInfo = fresh.querySelector('.info');
      var oldRight = old.querySelector('.right'), newRight = fresh.querySelector('.right');
      if (!oldInfo || !newInfo || !oldRight || !newRight) return false;
      old.className = fresh.className;            // 置顶高亮
      oldInfo.innerHTML = newInfo.innerHTML;      // 名字 / 置顶标记 / 市值 / 换手
      oldRight.innerHTML = newRight.innerHTML;    // 价格 / 涨跌 / 缓存标记
    }
    return true;
  }
  function chgClass(v) { return v === null ? 'flat' : (v > 0 ? 'up' : (v < 0 ? 'down' : 'flat')); }
  function chgText(v) {
    if (v === null || !isFinite(v)) return '--';
    return (v > 0 ? '+' : '') + fmtNum(v, 2) + '%';
  }
  // 品种图标：加密用 APK 内官方 64px logo，美股用 Finnhub 品牌 logo，
  // A股/港股/链上品种用文字徽章；图片加载失败自动退回字徽。
  function symbolIconHTML(sym, code) {
    var fallback = esc(String(code).slice(0, 3));
    if (CFG.show_icons === false || isOnchain(sym)) return fallback;
    var mk = marketOf(sym), src = '';
    if (mk === 'crypto') src = 'coins/' + encodeURIComponent(String(code).toLowerCase()) + '.png';
    else if (String(sym).indexOf('US:') === 0) {
      src = 'https://static2.finnhub.io/file/publicdatany/finnhubimage/stock_logo/' +
        encodeURIComponent(String(code)) + '.png';
    } else return esc(String(nameOf(sym) || code).slice(0, 1));
    return '<img src="' + src + '" alt="" data-fallback="' + fallback +
           '" loading="lazy">';
  }
  function rowHTML(sym) {
    var t = priceOf(sym);
    var pinned = CFG.pinned_symbols.indexOf(sym) >= 0;
    var price = t ? t.price : null;
    var chg = t ? t.chg : null;
    var meta = META[sym] || {};
    var isOc = isOnchain(sym);
    var code = isOc ? ocCode(sym) : String(sym).replace(/^.*:/, '');
    var stats = [];
    if (isOc) {
      var m = CFG.onchain[sym] || {};
      stats.push((m.chain || '链上') + '合约 · 真实报价走势（非 K 线）');
      if (meta.liquidity !== undefined && meta.liquidity !== null) {
        stats.push('链上流动性 ' + fmtAmount(meta.liquidity) + ' USD');
      }
      if (meta.holders !== undefined && meta.holders !== null) {
        stats.push('持有地址 ' + fmtAmount(meta.holders));
      }
      if (price === null) stats.push('暂无公开链上报价');
    } else {
      if (meta.cap !== undefined && meta.cap !== null) {
        stats.push('市值 ' + fmtAmount(meta.cap) + (meta.cap_unit === 'USD' ? ' USD' : ''));
      }
      if (meta.turnover !== undefined && meta.turnover !== null) {
        stats.push('换手 ' + fmtNum(meta.turnover, 2) + '%');
      }
      if (!stats.length && meta.listed) stats.push('上市/创立 ' + meta.listed);
      if (!stats.length) stats.push(t && t.stale ? '缓存价 · 待联网刷新' : '等待行情…');
    }
    return '<div class="trow' + (pinned ? ' pinned' : '') + '" data-sym="' + esc(sym) + '">' +
      '<div class="ico">' + symbolIconHTML(sym, code) + '</div>' +
      '<div class="info">' +
        '<div><span class="code">' + esc(code) + '</span>' +
        '<span class="name">' + esc(nameOf(sym)) + '</span>' +
        (pinned ? ' <span class="pin">置顶</span>' : '') + '</div>' +
        '<div class="stats">' + esc(stats.join(' · ')) + '</div>' +
      '</div>' +
      '<div class="right">' +
        '<div class="price ' + chgClass(chg) + '">' +
          (price === null ? '--' : esc((isOc ? '$' : '') + fmtPrice(price))) +
          (t && t.stale && !isOc ? ' <span class="flat" style="font-size:10px">缓存</span>' : '') + '</div>' +
        '<div class="chg ' + chgClass(chg) + '">' + (isOc ? '—' : chgText(chg)) + '</div>' +
      '</div>' +
    '</div>';   // 价格右侧 ⋯ 方框已按需求删除：长按行 / 桌面右键出行菜单
  }
  function contractHitHTML(query) {
    var q = String(query === undefined ? SEARCH_TEXT : query).trim();
    if (!isContract(q)) return '';
    var chain = chainOfAddr(q) || '链上';
    var sym = ocSymbol(q);
    var added = CFG.symbols.indexOf(sym) >= 0;
    // 搜索结果行：点行进图表（不默认收藏），右侧 ＋ 才加入自选
    return '<div class="sresult" data-search-open="' + esc(sym) + '">' +
      '<div class="ico">' + esc(chain.slice(0, 3)) + '</div>' +
      '<div class="info"><div><span class="code">' + esc(shortAddr(q)) +
      '</span><span class="name">' + esc(chain) + ' 合约</span></div>' +
      '<div class="sub">' + (chain === 'Solana'
        ? '解析真实链上报价。没有 K 线也能收藏、也能看价；点击进入图表。'
        : '没有 K 线；当前链暂无公开报价源，价格标注「暂无公开报价」；点击进入图表。') +
      '</div></div>' +
      '<button class="add" data-addcontract="' + esc(q) + '" aria-label="加入自选">' +
      (added ? '✓ 已收藏 · 重新解析' : '＋ 解析并加入自选') + '</button></div>';
  }
  function renderList(opts) {
    opts = opts || {};
    computeOrder();
    var n = Math.min(LOADED, ORDER.length);
    var visible = ORDER.slice(0, n);
    // 空态：保持原有引导卡片 / 提示，整块写入
    if (!ORDER.length) {
      var html = '';
      if (CFG.sub_tabs[MARKET] === 'watch' && !SEARCH_TEXT.trim()) {
        html = '<div class="empty"><b>「' + MARKET_NAME[MARKET] +
          '」自选还是空的</b><br><span class="dim">到「全部」里长按品种 → ＋ 加入自选</span>' +
          '<button class="big-btn" data-goall="1">去全部行情添加</button></div>';
      } else {
        html = '<div class="empty">没有匹配的品种<br>试试切换「全部」或修改搜索关键词</div>';
      }
      $('list').innerHTML = html;
      _lastRenderSig = null; _lastRowHTML = [];
    } else {
      var sig = rowsSignature(visible);
      var htmls = [];
      for (var i = 0; i < visible.length; i++) htmls.push(rowHTML(visible[i]));
      // 行集合/顺序不变：尝试行级增量替换（仅动价格/涨跌/市值文本）
      if (sig === _lastRenderSig && patchRowsFromHTML($('list'), htmls)) {
        _lastRowHTML = htmls;
      } else {
        // 结构变化或环境不支持增量：整表重建（保持原有行为）
        var full = '';
        for (var j = 0; j < htmls.length; j++) full += htmls[j];
        $('list').innerHTML = full;
        _lastRenderSig = sig; _lastRowHTML = htmls;
      }
    }
    $('loadMore').hidden = n >= ORDER.length;
    $('loadMore').textContent = n >= ORDER.length ? '' :
      '加载更多（已显示 ' + n + ' / ' + ORDER.length + '）';
    $('sectionCount').textContent = String(ORDER.length);
    $('sectionTitle').textContent =
      (CFG.sub_tabs[MARKET] === 'all' ? '全部行情' : '自选行情') + ' · ' + MARKET_NAME[MARKET];
    $('sortLabel').textContent = SORT_SHORT[CFG.sort_mode] || CFG.sort_mode;
    // 标签按钮只在市场/子页真正变化时重建；数据刷新（skipTabs）跳过
    if (!opts.skipTabs) renderTabs();
  }
  function renderTabs() {
    var mh = '', sh = '', i;
    for (i = 0; i < MARKETS.length; i++) {
      var mk = MARKETS[i][0];
      mh += '<button data-market="' + mk + '" class="' + (mk === MARKET ? 'active' : '') +
        '">' + MARKETS[i][1] + '</button>';
    }
    for (i = 0; i < SUBS.length; i++) {
      var sk = SUBS[i][0];
      sh += '<button data-sub="' + sk + '" class="' +
        (CFG.sub_tabs[MARKET] === sk ? 'active' : '') + '">' + SUBS[i][1] + '</button>';
    }
    $('markets').innerHTML = mh;
    $('subs').innerHTML = sh;
  }
  function loadMore() {
    if (LOADED >= ORDER.length) return;
    LOADED = Math.min(LOADED + PAGE_SIZE, ORDER.length);
    scheduleRender();                // 合帧：与紧随的刷新请求合并渲染，避免双次重建
    requestWindow();                 // 只补请求新增窗口，不重刷已显示行
  }

  // ===================== 刷新调度（去重 / 合并 / 有限重试） =====================
  var _inFlight = false, _pendingForce = false, _lastKey = '', _lastAt = 0;
  var _fails = 0, _timer = null, _burst = null;

  function setStatus(text, canRetry) {
    $('statusText').textContent = text;
    $('btnRetry').hidden = !canRetry;
  }
  // 时间戳单调性保护：并发请求乱序返回时，旧快照不得覆盖更新的快照。
  // 只有新旧双方 ts 都是有效数字、且 incoming.ts 严格更旧时才拒绝写入；
  // 缺少 ts 的历史数据维持原行为（照常写入），保证兼容性。
  function _quoteIsStale(sym, incoming) {
    var old = TICKERS[sym];
    if (!old) return false;
    var it = incoming && Number(incoming.ts), ot = Number(old.ts);
    if (!isFinite(it) || !isFinite(ot) || it <= 0 || ot <= 0) return false;
    return it < ot;
  }
  function applyTickers(map, sources) {
    var n = 0;
    for (var s in map) {
      if (Object.prototype.hasOwnProperty.call(map, s)) {
        if (_quoteIsStale(s, map[s])) continue;   // 拒绝过期快照覆盖新快照
        TICKERS[s] = map[s]; n++;
      }
    }
    BATCH = {};
    for (var b in map) { if (Object.prototype.hasOwnProperty.call(map, b)) BATCH[b] = 1; }
    // 链上报价按自己的低频节奏刷新，不能被交易所批次清成「缓存价」
    for (var o in ONCHAIN_Q) {
      if (Object.prototype.hasOwnProperty.call(ONCHAIN_Q, o)) BATCH[o] = 1;
    }
    if (n) {
      TICKER_ASOF = nowSec();
      writeJSON('ct_tickers', TICKERS);
      store.set('ct_tickers_asof', TICKER_ASOF);
      SOURCE_TEXT = sources.length ? uniq(sources).join(' + ') : '缓存';
      saveMeta();
    }
    return n;
  }
  function refreshTickers(force) {
    var syms = windowSymbols();
    if (!syms.length) {
      setStatus('● 当前列表为空', false);
      return Promise.resolve();
    }
    var oc = syms.filter(isOnchain);
    if (oc.length) refreshOnchain(oc, force);
    var normal = syms.filter(function (s) { return !isOnchain(s); });
    if (!normal.length) {
      setStatus('● 链上报价刷新中 · ' + OC_SOURCE, false);
      return Promise.resolve();       // 全是链上品种：不发交易所请求
    }
    var key = syms.join(',');
    if (!force && key === _lastKey && nowMs() - _lastAt < 3000) return Promise.resolve();
    if (_inFlight) { if (force) _pendingForce = true; return Promise.resolve(); }
    _inFlight = true;
    _lastKey = key; _lastAt = nowMs();
    setStatus('● 刷新中 · ' + syms.length + ' 个品种', false);

    return fetchTickers(syms).then(function (res) {
      var n = applyTickers(res.map, res.sources);
      _inFlight = false;
      if (n) {
        _fails = 0;
        setStatus('● 已更新 · ' + SOURCE_TEXT + ' · ' + fmtTime(TICKER_ASOF), false);
        scheduleRender();            // 合帧：与主刷新/链上刷新合并为一次列表渲染
      } else {
        onFail('行情接口未返回数据');
      }
      if (_pendingForce) { _pendingForce = false; refreshTickers(true); }
    }).catch(function (e) {
      _inFlight = false;
      onFail(e && e.message ? e.message : '网络异常');
      if (_pendingForce) { _pendingForce = false; refreshTickers(true); }
    });
  }
  function onFail(msg) {
    _fails++;
    var cached = Object.keys(TICKERS).length > 0;
    var limit = clamp(Number(CFG.retry_limit) || MAX_RETRY, 1, 5);
    setStatus('● ' + msg + (cached ? ' · 显示上次真实快照' : ' · 暂无缓存'), _fails >= limit);
    restartTimer(true);
  }
  function requestWindow() {
    // 滚动 / 切页触发：120ms 内合并为一次，避免重复请求
    if (_burst) clearTimeout(_burst);
    _burst = setTimeout(function () { _burst = null; refreshTickers(true); }, 120);
  }
  function restartTimer(backoff) {
    if (_timer) clearInterval(_timer);
    var secs = clamp(Number(CFG.interval) || 15, 5, 300);
    if (backoff) secs = secs * Math.min(Math.pow(2, _fails), 8);
    var limit = clamp(Number(CFG.retry_limit) || MAX_RETRY, 1, 5);
    if (_fails > limit + 3) return;       // 连续失败后停止自动轮询，等用户点重试
    _timer = setInterval(function () { refreshTickers(false); }, secs * 1000);
  }

  // 图表页秒级实时价：只请求当前品种，不整表刷新（对齐桌面 live_feed）
  var _liveTimer = null;
  function refreshChartSymbol() {
    var sym = CHART_SYMBOL;
    if (!sym) return;
    // 链上报告比交易所报价慢得多：走 60 秒节流，不能按 900ms 实时轮询
    // 去打 Rugcheck，否则既拖慢界面也容易被限流。
    if (isOnchain(sym)) {
      // 链上报告比交易所报价慢得多：走 60 秒节流，不能按 900ms 实时轮询
      // 去打 Rugcheck，否则既拖慢界面也容易被限流。
      refreshOnchain([sym], false).then(function () {
        updateChartHead();
        var q = ONCHAIN_Q[sym];
        if (q && q.price) applyChartQuote(q.price, q.ts || nowSec());
      });
      return;
    }
    fetchTickers([sym]).then(function (res) {
      applyTickers(res.map, res.sources);
      updateChartHead();
      var q = TICKERS[sym];
      if (q && q.price !== null && q.price !== undefined) {
        applyChartQuote(q.price, q.ts || nowSec());
      }
    }).catch(function () { /* 静默：下一次轮询自动重试 */ });
  }
  function restartLiveTimer() {
    if (_liveTimer) { clearInterval(_liveTimer); _liveTimer = null; }
    if (CFG.live_feed === false || PAGE !== 'chart') return;
    _liveTimer = setInterval(function () {
      if (PAGE === 'chart') refreshChartSymbol();
    }, clamp(Number(CFG.live_interval_ms) || 900, 400, 3000));
  }

  // ===================== 页面 / 导航 =====================
  function setTitle(t) { $('pageTitle').textContent = t; }
  function setNav(tab) {
    var t = tab === 'search' ? 'list' : tab;   // 搜索页归在「行情」导航下
    var bs = $('bottomNav').getElementsByTagName('button');
    for (var i = 0; i < bs.length; i++) {
      bs[i].className = bs[i].getAttribute('data-tab') === t ? 'active' : '';
    }
  }
  // ============ v38：列表顶部工具区随滚动自动折叠 / 展开 ============
  // 手指上滑（scrollTop 增大）收起「市场 / 子页 / 搜索」，下滑立即展开。
  // 用同方向累计位移 + 滞回阈值，而不是单帧 delta：惯性滚动、轻微手抖、
  // 折叠时 WebView 对 scrollTop 的锚定补偿都不会让头部来回跳。
  // 展开态写入实测高度（px）而不是 auto，CSS 才能做平滑的 max-height 过渡。
  var HEAD_HIDE_AFTER = 56;    // 上滑累计 56px 收起
  var HEAD_SHOW_AFTER = 20;    // 下滑累计 20px 展开
  var HEAD_TOP_RESET = 24;     // 距顶部 24px 内强制展开
  var HEAD_FALLBACK_H = 156;   // 离线回归桩测不到真实高度时的兜底
  var headH = 0, headLastTop = 0, headAcc = 0, headHidden = false;

  function headEl() { return $('listHead'); }

  function measureHead() {
    var h = headEl(); if (!h) return;
    h.style.maxHeight = '';                  // 先放开，收起态否则量到 0
    var v = h.offsetHeight || 0;
    if (v > 0) headH = v + 6;               // 6px 余量，防止字体换行裁掉末行
    h.style.maxHeight = headHidden ? '0px' : ((headH || HEAD_FALLBACK_H) + 'px');
  }

  function setHeadHidden(hidden) {
    hidden = !!hidden;
    if (headHidden === hidden) return;
    headHidden = hidden;
    headAcc = 0;
    var h = headEl(), page = $('pageList');
    if (h) {
      h.style.maxHeight = hidden ? '0px' : ((headH || HEAD_FALLBACK_H) + 'px');
      h.style.opacity = hidden ? '0' : '1';
      h.style.transform = hidden ? 'translateY(-10px)' : 'translateY(0)';
      h.style.pointerEvents = hidden ? 'none' : '';
    }
    if (page) {
      var cn = String(page.className || '').replace(/\s*head-hidden\b/g, '');
      page.className = cn + (hidden ? ' head-hidden' : '');
    }
  }

  // 切回列表 / 输入框聚焦 / 点顶栏时恢复展开，保证搜索与选项卡随时可达
  function resetHead() {
    var list = $('list');
    headLastTop = list ? (list.scrollTop || 0) : 0;
    headAcc = 0;
    if (!headH) measureHead();
    setHeadHidden(false);
  }

  function headOnScroll(top) {
    if (PAGE !== 'list') return;
    top = Number(top) || 0;
    var dy = top - headLastTop;
    headLastTop = top;
    if (top <= HEAD_TOP_RESET) { headAcc = 0; setHeadHidden(false); return; }
    if (!dy) return;
    if ((dy > 0 && headAcc < 0) || (dy < 0 && headAcc > 0)) headAcc = 0;
    headAcc += dy;
    if (headAcc > 400) headAcc = 400;
    if (headAcc < -400) headAcc = -400;
    if (!headHidden && headAcc >= HEAD_HIDE_AFTER) setHeadHidden(true);
    else if (headHidden && headAcc <= -HEAD_SHOW_AFTER) setHeadHidden(false);
  }

  function pageTitle(page) {
    if (page === 'list') return '行情';
    if (page === 'chart') return '图表';
    if (page === 'search') return '搜索';
    return '设置';
  }
  // 返回按钮层级：仅顶栏保留「一个」返回按钮，按导航栈状态显示。
  // 根页（首页 / 底部导航直接切换到的顶层 tab）无上一级 -> 隐藏；
  // 子页（列表行→图表、搜索→图表等下钻）-> 显示，返回优先回到上一级。
  // 页面组件里的 #btnSearchBack / #btnSettingsBack 属于重复返回按钮，统一隐藏，
  // 避免「同一页两个返回箭头」。弹窗关闭由 openSheetId 单独处理，不与页面返回混淆。
  var ROOT_PAGES = { list: 1, chart: 1, settings: 1 };
  var NAV_STACK = [];       // 下钻时记录上一级页面
  function navCanBack() { return NAV_STACK.length > 0 && !(PAGE === 'list' && NAV_STACK.length === 0); }
  function syncBackButton() {
    var btn = $('btnBack');
    var show = NAV_STACK.length > 0;         // 有上一级才显示
    if (btn) btn.hidden = !show;
    // 统一隐藏页面内重复返回按钮（保留顶栏唯一一个）
    ['btnSearchBack', 'btnSettingsBack'].forEach(function (id) {
      var b = $(id); if (b) b.hidden = true;
    });
  }
  function go(page, opts) {
    opts = opts || {};
    if (!opts.fromBack && page !== PAGE) {
      if (opts.resetStack) NAV_STACK.length = 0;   // 底部导航 tab = 顶层切换
      else {
        NAV_STACK.push(PAGE);
        if (NAV_STACK.length > 16) NAV_STACK.shift();
      }
    }
    closeSheets();
    PAGE = page;
    $('pageList').hidden = page !== 'list';
    $('pageChart').hidden = page !== 'chart';
    $('pageSettings').hidden = page !== 'settings';
    $('pageSearch').hidden = page !== 'search';
    setNav(page);
    setTitle(pageTitle(page));
    syncBackButton();
    if (page === 'list') {
      if (_klineTimer) { clearInterval(_klineTimer); _klineTimer = null; }
      resetHead(); renderList(); requestWindow();
    }
    if (page === 'chart') {
      if (!CHART_SYMBOL) {
        CHART_SYMBOL = (watchList(MARKET)[0] || ALL[MARKET][0] || 'BTC');
      }
      openChart(CHART_SYMBOL);
    }
    if (page === 'settings') syncSettings();
    if (page === 'search') renderSearchPage($('searchBox').value || '');
    restartLiveTimer();
    restartKlineTimer();
  }

  // ===================== 弹出层 =====================
  function openSheet(id) {
    closeSheets();
    openSheetId = id;
    $(id).hidden = false;
    $('scrim').hidden = false;
  }
  function closeSheets() {
    ['sortSheet', 'rowSheet', 'detailSheet', 'textSheet',
     'indicatorSheet'].forEach(function (id) {
      var el = $(id); if (el) el.hidden = true;
    });
    openSheetId = '';
    $('scrim').hidden = true;
  }
  function toast(msg) {
    var el = $('toast');
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(el._t);
    el._t = setTimeout(function () { el.hidden = true; }, 2200);
  }

  function showSortSheet() {
    var html = '';
    for (var g = 0; g < SORT_GROUPS.length; g++) {
      html += '<div class="group-title">' + esc(SORT_GROUPS[g][0]) + '</div>';
      var modes = SORT_GROUPS[g][1];
      for (var i = 0; i < modes.length; i++) {
        var m = modes[i];
        html += '<button class="opt' + (CFG.sort_mode === m ? ' active' : '') +
          '" data-sort="' + m + '">' + esc(SORT_LABEL[m]) +
          (CFG.sort_mode === m ? '  ✓' : '') + '</button>';
      }
    }
    html += '<div class="group-title">顺序</div>' +
      '<button class="opt" data-flip="1">⇅ 翻转当前维度升/降序</button>';
    $('sortOptions').innerHTML = html;
    openSheet('sortSheet');
  }
  function setSort(mode) {
    CFG.sort_mode = mode;
    CFG.sort_reverse = false;
    saveCfg();
    closeSheets();
    LOADED = PAGE_SIZE;
    renderList();
    if (needMeta(mode)) {
      // 真实元数据后台补齐，不阻塞 UI：加密走 CoinLore，股票走腾讯批量行情。
      // 上市年份来自内置公开资料库，无需联网，缺失的品种一律排末尾。
      setStatus('● 正在获取真实市值 / 流动性 / 上市时间…', false);
      var jobs = [];
      if (MARKET === 'crypto') jobs.push(fetchMeta(false));
      else {
        var batch = ORDER.slice(0, MAX_REFRESH_SYMBOLS);
        jobs.push(fetchTickers(batch).then(function (res) {
          applyTickers(res.map, res.sources);
        }).catch(function () {}));
      }
      Promise.all(jobs).then(function () {
        renderList();
        setStatus('● 排序依据已更新 · ' + SOURCE_TEXT, false);
      });
    }
    requestWindow();
    toast('排序：' + SORT_LABEL[mode]);
  }

  function showRowSheet(sym) {
    var pinned = CFG.pinned_symbols.indexOf(sym) >= 0;
    var watched = CFG.symbols.indexOf(sym) >= 0;
    $('rowSheetTitle').textContent =
      (isOnchain(sym) ? ocCode(sym) : sym) + ' · ' + nameOf(sym);
    $('rowOptions').innerHTML =
      '<button class="opt" data-row="chart">' +
        (isOnchain(sym) ? '▥ 查看链上报价 / 图表' : '▥ 查看 K 线图表') + '</button>' +
      '<button class="opt" data-row="detail">ⓘ 查看品种详情</button>' +
      '<button class="opt" data-row="pin">' + (pinned ? '✕ 取消置顶' : '★ 移到顶部（置顶）') + '</button>' +
      '<button class="opt" data-row="watch">' + (watched ? '－ 移出自选' : '＋ 加入自选') + '</button>';
    $('rowSheet').setAttribute('data-sym', sym);
    openSheet('rowSheet');
  }
  function setPinned(sym, on) {
    var i = CFG.pinned_symbols.indexOf(sym);
    if (on && i < 0) CFG.pinned_symbols.push(sym);
    if (!on && i >= 0) CFG.pinned_symbols.splice(i, 1);
    saveCfg();
    closeSheets();
    renderList();                 // 立即生效
    toast(on ? sym + ' 已置顶（切页/刷新后保留）' : sym + ' 已取消置顶');
  }
  function toggleWatch(sym) {
    var i = CFG.symbols.indexOf(sym);
    if (i >= 0) CFG.symbols.splice(i, 1); else CFG.symbols.push(sym);
    saveCfg();
    closeSheets();
    renderList();
    toast(i >= 0 ? sym + ' 已移出自选' : sym + ' 已加入自选');
  }

  // ===================== 详情（真实字段 + 缺失标注） =====================
  function cell(label, value) {
    return '<div class="cell"><span>' + esc(label) + '</span><b>' +
      (value === null || value === undefined || value === '' ? MISSING : esc(value)) + '</b></div>';
  }
  function card(title, inner) {
    return '<div class="detail-card"><h4>' + esc(title) + '</h4>' + inner + '</div>';
  }

  // ---------- v37：发展历程 / 品种档案 / 行情里程碑 ----------
  function ym(ts) {
    var d = new Date(Number(ts) * 1000);
    if (!isFinite(d.getTime())) return '—';
    return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2);
  }
  function computeMilestones(rows, source, interval, note) {
    var clean = [];
    for (var i = 0; i < (rows || []).length; i++) {
      var c = rows[i];
      var ts = Number(c.ts), hi = Number(c.h), lo = Number(c.l), cl = Number(c.c);
      if (!isFinite(ts) || ts <= 0 || !isFinite(hi) || hi <= 0 ||
          !isFinite(lo) || lo <= 0 || !isFinite(cl) || cl <= 0) continue;
      clean.push([ts, Math.max(hi, lo, cl), Math.min(hi, lo, cl), cl]);
    }
    if (clean.length < 2) {
      return { ok: false, reason: '历史样本不足', source: source };
    }
    clean.sort(function (a, b) { return a[0] - b[0]; });
    var hiRow = clean[0], loRow = clean[0], peak = clean[0][3], mdd = 0;
    for (var j = 0; j < clean.length; j++) {
      if (clean[j][1] > hiRow[1]) hiRow = clean[j];
      if (clean[j][2] < loRow[2]) loRow = clean[j];
      peak = Math.max(peak, clean[j][3]);
      if (peak > 0) mdd = Math.min(mdd, clean[j][3] / peak - 1);
    }
    var first = clean[0][3], last = clean[clean.length - 1][3];
    return {
      ok: true, bars: clean.length,
      start: ym(clean[0][0]), end: ym(clean[clean.length - 1][0]),
      high: hiRow[1], high_date: ym(hiRow[0]),
      low: loRow[2], low_date: ym(loRow[0]),
      change_pct: (last / first - 1) * 100,
      max_drawdown: mdd * 100,
      source: source, interval: interval, note: note || ''
    };
  }
  function timelineHTML(sym) {
    var rows = (TL_DB[sym] || []).slice().sort(function (a, b) {
      return String(a.date).localeCompare(String(b.date));
    });
    var meta = DB_META || {};
    if (!rows.length) {
      return card('⑦ 发展历程 · 里程碑',
        '<p class="muted">' +
        esc(meta.no_data || '资料库未收录该品种的发展历程，请以官方披露为准。') +
        '</p>');
    }
    var h = '<div class="timeline">';
    for (var i = 0; i < rows.length; i++) {
      var e = rows[i];
      h += '<div class="tl-item"><div class="tl-date">' + esc(e.date) + '</div>' +
        '<div class="tl-body"><b>' + esc(e.title) + '</b>' +
        (e.detail ? '<p>' + esc(e.detail) + '</p>' : '') +
        '<span class="tl-src">来源：' + esc(e.src || '公开资料整理') + '</span>' +
        '</div></div>';
    }
    h += '</div><p class="muted">' + esc(meta.source_note || '') +
      ' · 共 ' + rows.length + ' 条，核验于 ' + esc(meta.verified_at || '') +
      '。</p>';
    return card('⑦ 发展历程 · 里程碑', h);
  }
  function archiveHTML(sym) {
    var a = ARC_DB[sym];
    if (!a) {
      return card('⑧ 品种档案 · 可核对字段',
        '<p class="muted">资料库未收录该品种档案；仅能由代码推断交易所类型，' +
        '其余字段留白，不用同类品种的典型值填充。</p>');
    }
    var g = '<div class="grid">';
    for (var i = 0; i < ARC_FIELDS.length; i++) {
      var k = ARC_FIELDS[i][0], label = ARC_FIELDS[i][1];
      if (a[k] === undefined || a[k] === null || a[k] === '') continue;
      g += cell(label, a[k]);
    }
    g += '</div><p class="muted">' + esc((DB_META || {}).source_note || '') +
      '</p>';
    return card('⑧ 品种档案 · 可核对字段', g);
  }
  function milestoneHTML(sym) {
    var m = MILESTONES[sym];
    if (!m || !m.ok) {
      return card('⑨ 行情里程碑 · 真实历史数据',
        '<div class="grid">' + cell('统计区间', null) + cell('区间最高', null) +
        cell('区间最低', null) + cell('区间涨跌', null) +
        cell('最大回撤', null) + cell('样本 / 来源', null) + '</div>' +
        '<p class="muted">打开详情时会按需加载真实历史数据；样本不足或接口' +
        '不可用时留白，不做估算。</p>');
    }
    return card('⑨ 行情里程碑 · 真实历史数据',
      '<div class="grid">' +
      cell('统计区间', m.start + ' → ' + m.end) +
      cell('区间最高', fmtPrice(m.high) + ' · ' + m.high_date) +
      cell('区间最低', fmtPrice(m.low) + ' · ' + m.low_date) +
      cell('区间涨跌', (m.change_pct >= 0 ? '+' : '') + fmtNum(m.change_pct, 2) + '%') +
      cell('最大回撤', fmtNum(m.max_drawdown, 2) + '%') +
      cell('样本 / 来源', m.bars + ' 根 · ' + m.source) +
      '</div><p class="muted">' + esc(m.note || '') +
      ' 统计区间以数据源返回范围为准，不等同于上市以来全历史。</p>');
  }
  function extraDetailHTML(sym) {
    return timelineHTML(sym) + archiveHTML(sym) + milestoneHTML(sym);
  }
  function loadMilestones(sym) {
    function redraw() {
      if (openSheetId === 'detailSheet' &&
          $('detailSheet').getAttribute('data-sym') === sym) {
        $('detailBody').innerHTML = detailHTML(sym);
      }
    }
    if (isOnchain(sym)) {
      var rows = ocSeries(sym).map(function (p) {
        var px = Number(p[1]);
        return { ts: Number(p[0]), h: px, l: px, c: px };
      });
      MILESTONES[sym] = computeMilestones(rows, '本机真实报价采样',
        '真实报价点',
        '链上合约没有交易所 K 线，区间统计基于本设备采集的真实报价点');
      redraw();
      return;
    }
    var iv = isStock(sym) ? 'month' : '1M';
    var src = isStock(sym) ? '腾讯 / 新浪日 K 聚合月线' : 'Binance 月 K';
    var note = '统计区间以数据源本次返回的历史为准；A 股 / 港股单次约 640 根日线';
    try {
      Promise.resolve(fetchCandles(sym, iv)).then(function (rows) {
        MILESTONES[sym] = computeMilestones(rows, src, '月 K', note);
        redraw();
      }).catch(function () {
        MILESTONES[sym] = { ok: false, reason: '历史数据接口不可用', source: src };
        redraw();
      });
    } catch (err) {
      MILESTONES[sym] = { ok: false, reason: '历史数据接口不可用', source: src };
    }
  }

  function onchainDetailHTML(sym) {
    var t = TICKERS[sym] || {}, m = META[sym] || {}, a = aboutOf(sym) || {},
        om = CFG.onchain[sym] || {};
    var html = '';
    html += card('① 行情数据', '<div class="grid">' +
      cell('最新价（USD）', t.price === undefined || t.price === null ? null : '$' + fmtPrice(t.price)) +
      cell('24h 涨跌幅', null) + cell('最高', null) + cell('最低', null) +
      '</div><p class="muted">链上报价源不提供 24h 涨跌幅与最高 / 最低价，不显示估算值。</p>');
    html += card('② 市值与估值', '<div class="grid">' +
      cell('总市值', m.cap === undefined || m.cap === null ? null : fmtAmount(m.cap) + ' USD') +
      cell('流通市值', null) + cell('市值排名', null) +
      cell('市盈率 PE', null) + cell('市净率 PB', null) + cell('换手率', null) +
      '</div><p class="muted">市值 = 链上价 × 链上总供应量；估值类字段无公开数据源。</p>');
    html += card('③ 供应 · 成交 · 流动性', '<div class="grid">' +
      cell('24h 成交额', null) +
      cell('流通供应量', m.supply_circulating === undefined || m.supply_circulating === null ? null : fmtAmount(m.supply_circulating)) +
      cell('总供应量', m.supply_total === undefined || m.supply_total === null ? null : fmtAmount(m.supply_total)) +
      cell('最大供应量', null) +
      cell('链上流动性（USD）', m.liquidity === undefined || m.liquidity === null ? null : fmtAmount(m.liquidity)) +
      cell('持有地址数', m.holders === undefined || m.holders === null ? null : fmtAmount(m.holders)) +
      '</div>');
    html += card('④ 项目用途 / 代币经济学',
      '<div class="grid">' + cell('代币分配', null) + cell('解锁计划', null) +
      cell('协议收入', null) + '</div>' +
      '<p class="muted">项目用途、代币经济学、解锁与协议收入属于项目方披露信息，' +
      '链上报告未提供；此处不做估算，请以白皮书 / 官方披露为准。</p>');
    html += card('⑤ 项目 / 公司介绍',
      '<p><b>' + esc(a.title || ocCode(sym)) + '</b></p>' +
      '<p>类别：' + esc(a.category || '—') + '</p>' +
      '<p>链：' + esc(om.chain || chainOfAddr(ocAddr(sym)) || '—') + '</p>' +
      '<p>合约地址：' + esc(ocAddr(sym)) + '</p>' +
      '<p>发行平台：' + esc(om.launchpad || '—') + '</p>' +
      '<p class="muted">项目背景、业务、核心特点与前景暂无公开资料，不展示推测内容。</p>');
    html += card('⑥ 数据来源与更新时间', '<div class="grid">' +
      cell('数据来源', OC_SOURCE) +
      cell('行情时间', t.ts ? fmtTime(t.ts) : null) +
      cell('元数据来源', m.source || null) +
      cell('元数据时间', m.asof ? fmtTime(Math.floor(m.asof / 1000)) : null) +
      '</div><p class="muted">所有数值均为公开接口真实返回；未返回的字段标注「' +
      MISSING + '」，不使用估算或假数据。该币种没有交易所 K 线；' +
      '图表页展示本设备采集的真实报价走势与链上结构数据。</p>');
    html += extraDetailHTML(sym);
    return html;
  }
  function detailHTML(sym) {
    if (isOnchain(sym)) return onchainDetailHTML(sym);
    var t = TICKERS[sym] || {}, m = META[sym] || {}, a = aboutOf(sym) || {};
    var mk = marketOf(sym), isCrypto = mk === 'crypto';
    var html = '';

    html += card('① 行情数据', '<div class="grid">' +
      cell('最新价', t.price === undefined || t.price === null ? null : fmtPrice(t.price)) +
      cell('24h 涨跌幅', t.chg === undefined || t.chg === null ? null : chgText(t.chg)) +
      cell('最高', t.high === undefined || t.high === null ? null : fmtPrice(t.high)) +
      cell('最低', t.low === undefined || t.low === null ? null : fmtPrice(t.low)) +
      '</div>');

    html += card('② 市值与估值', '<div class="grid">' +
      cell('总市值', m.cap === undefined || m.cap === null ? null :
        fmtAmount(m.cap) + ' ' + (m.cap_unit === 'USD' ? 'USD' : (m.cap_unit || ''))) +
      cell('流通市值', m.float_cap === undefined || m.float_cap === null ? null :
        fmtAmount(m.float_cap) + (m.cap_unit === 'USD' ? ' USD' : '')) +
      cell('市值排名', m.rank || null) +
      cell('市盈率 PE', m.pe === undefined || m.pe === null ? null : fmtNum(m.pe, 2)) +
      cell('市净率 PB', m.pb === undefined || m.pb === null ? null : fmtNum(m.pb, 2)) +
      cell('流动性（换手率）', (m.turnover === undefined || m.turnover === null) ?
        (m.liquidity === undefined || m.liquidity === null ? null : fmtNum(m.liquidity, 2) + '%（成交额/流通市值）')
        : fmtNum(m.turnover, 2) + '%') +
      '</div>');

    html += card('③ 供应 · 成交 · 流动性', '<div class="grid">' +
      cell('24h 成交额', t.amount === undefined || t.amount === null ? null : fmtAmount(t.amount)) +
      cell('24h 成交量', m.volume24 === undefined || m.volume24 === null ? null : fmtAmount(m.volume24) + ' USD') +
      cell('流通供应量', m.supply_circulating === undefined || m.supply_circulating === null ? null : fmtNum(m.supply_circulating, 2)) +
      cell('总供应量', m.supply_total === undefined || m.supply_total === null ? null : fmtNum(m.supply_total, 2)) +
      cell('最大供应量', m.supply_max === undefined || m.supply_max === null ? null : fmtNum(m.supply_max, 2)) +
      cell('上市/创立年份', m.listed || null) +
      '</div>');

    if (isCrypto) {
      html += card('④ 项目用途 / 代币经济学',
        '<p><b>项目用途：</b>' + esc(a.summary || '该品种用途需查阅项目官网与白皮书，接口未提供结构化说明。') + '</p>' +
        '<div class="grid">' +
        cell('代币分配', null) + cell('解锁计划', null) + cell('协议收入', null) +
        '</div>' +
        '<p class="muted">代币分配、解锁计划与协议收入属于项目方披露信息，当前公开行情接口不提供；需以项目白皮书 / 官方披露为准，此处不做估算。</p>');
    } else {
      html += card('④ 公司业务 / 财务指标',
        '<p><b>主营业务：</b>' + esc(a.product || '以公司年报与交易所公告为准。') + '</p>' +
        '<div class="grid">' +
        cell('营业收入', null) + cell('净利润', null) + cell('毛利率', null) +
        '</div>' +
        '<p class="muted">营收、利润等财务数据需以定期报告 / SEC 备案为准，当前行情接口不提供；此处不做估算。</p>');
    }

    html += card('⑤ 项目 / 公司介绍',
      '<p><b>' + esc(a.title || nameOf(sym)) + '</b></p>' +
      '<p>类别：' + esc(a.category || '—') + '</p>' +
      '<p>创始人 / 主体：' + esc(a.founder || '—') + '</p>' +
      '<p>创立 / 上市：' + esc(a.since || '—') + '</p>' +
      '<p>' + esc(a.summary || '') + '</p>' +
      (ABOUT[sym] ? '' : '<p class="muted">未收录结构化资料，仅显示市场通用说明；详细背景请查阅官方披露。</p>'));

    var src = [];
    if (isCrypto) src.push('Binance（行情 / K 线）', 'CoinLore（市值 / 供应量）');
    else src.push('腾讯行情（行情 / 市值 / 财务字段）', '腾讯 / 新浪（K 线）');
    if (a.title) src.push('内置公开资料库 data/about.py');
    html += card('⑥ 数据来源与更新时间',
      '<div class="grid">' +
      cell('数据来源', src.join(' · ')) +
      cell('行情时间', t.ts ? fmtTime(t.ts) : (TICKER_ASOF ? fmtTime(TICKER_ASOF) + '（本机获取）' : null)) +
      cell('元数据来源', m.source || null) +
      cell('元数据时间', m.asof ? fmtTime(Math.floor(m.asof / 1000)) : null) +
      '</div><p class="muted">所有数值均为公开接口真实返回；未返回的字段标注「' +
      MISSING + '」，不使用估算或假数据。</p>');
    html += extraDetailHTML(sym);
    return html;
  }
  function showDetail(sym) {
    if (isOnchain(sym)) {
      // 详情打开才请求链上报告；没有 K 线不影响收藏与价格
      $('detailBody').innerHTML = detailHTML(sym);
      openSheet('detailSheet');
      $('detailSheet').setAttribute('data-sym', sym);
      loadMilestones(sym);          // v37：本机真实报价采样算区间里程碑
      refreshOnchain([sym], true).then(function () {
        if (openSheetId === 'detailSheet' &&
            $('detailSheet').getAttribute('data-sym') === sym) {
          $('detailBody').innerHTML = detailHTML(sym);
        }
      });
      return;
    }
    $('detailBody').innerHTML = detailHTML(sym);
    openSheet('detailSheet');
    loadMilestones(sym);          // v37：真实历史数据算区间里程碑（按需）
    // 打开详情时才请求该品种的精确数据（按需，不进列表刷新）
    var jobs = [];
    if (isStock(sym)) {
      var c = toTencentCode(sym);
      if (c) jobs.push(http(TENCENT_QUOTE + c, 'GBK').then(parseTencent).catch(function () { return {}; }));
    } else {
      jobs.push(http(BINANCE_TICKER + encodeURIComponent(JSON.stringify([sym + 'USDT'])))
        .then(parseBinance).catch(function () { return {}; }));
      jobs.push(fetchMeta(false));
    }
    if (!jobs.length) return;
    Promise.all(jobs).then(function (parts) {
      var map = {};
      for (var i = 0; i < parts.length; i++) {
        if (!parts[i] || typeof parts[i] !== 'object') continue;
        for (var s in parts[i]) {
          if (Object.prototype.hasOwnProperty.call(parts[i], s) &&
              typeof parts[i][s] === 'object') map[s] = parts[i][s];
        }
      }
      // 只合并该品种的精确快照，不重置本轮实时批次 BATCH，
      // 否则列表里其它行会被误标成「缓存价」。
      if (Object.keys(map).length) {
        for (var s2 in map) {
          if (Object.prototype.hasOwnProperty.call(map, s2)) {
            if (_quoteIsStale(s2, map[s2])) continue;   // 同样防乱序旧快照
            TICKERS[s2] = map[s2];
          }
        }
        TICKER_ASOF = nowSec();
        writeJSON('ct_tickers', TICKERS);
        store.set('ct_tickers_asof', TICKER_ASOF);
      }
      if (!openSheetId || openSheetId !== 'detailSheet') return;
      var el = $('detailSheet');
      if (el.getAttribute('data-sym') === sym) {
        $('detailBody').innerHTML = detailHTML(sym);   // 只更新详情，不动列表
      }
      if (PAGE === 'chart') updateChartHead();
    });
    $('detailSheet').setAttribute('data-sym', sym);
  }

  // ===================== 链上标的历史 K 线（真实 DEX OHLCV） =====================
  // 与桌面端 data/onchain_kline.py 同口径：GeckoTerminal 主源 + CoinGecko 备源，
  // 只取真实 OHLCV，拿不到就回退采样折线，绝不插值 / 伪造。
  var GT_BASE = 'https://api.geckoterminal.com/api/v2';
  var CG_OHLC = 'https://api.coingecko.com/api/v3/coins/{p}/contract/{a}/ohlc';
  // v2：数据结构加入 pool（交易池身份）与 volume_reliable（成交量可靠性）。
  // 版本写在缓存体内，schema 变更时一次性丢弃旧格式，避免跨口径拼接。
  var OC_KLINE_SCHEMA = 'oc-v2-pool-volume';
  var OC_KLINE_CACHE = readJSON('ct_oc_kline', {});
  if (OC_KLINE_CACHE.v !== OC_KLINE_SCHEMA) OC_KLINE_CACHE = { v: OC_KLINE_SCHEMA };
  var OC_POOL_CACHE = readJSON('ct_oc_pools', {});     // { addr: {net, pool, ts} }
  var OC_TF = {
    '1m': ['minute', 1], '5m': ['minute', 5], '15m': ['minute', 15],
    '30m': ['minute', 30], '1h': ['hour', 1], '2h': ['hour', 2],
    '4h': ['hour', 4], '6h': ['hour', 6], '12h': ['hour', 12],
    '1d': ['day', 1], '3d': ['day', 3], '1w': ['week', 1], '1M': ['month', 1]
  };
  var OC_TF_SEC = {
    '1m': 60, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600,
    '2h': 7200, '4h': 14400, '6h': 21600, '12h': 43200,
    '1d': 86400, '3d': 259200, '1w': 604800, '1M': 2592000
  };
  var OC_INTERVALS = [['1分', '1m'], ['5分', '5m'], ['15分', '15m'],
                      ['30分', '30m'], ['1时', '1h'], ['2时', '2h'],
                      ['4时', '4h'], ['6时', '6h'], ['12时', '12h'],
                      ['日K', '1d'], ['3日', '3d'], ['周K', '1w'], ['月K', '1M']];
  var OC_STATUS = {};   // { sym: {state, source, ts} } 最近一次获取状态

  function ocCacheKey(sym, iv) { return sym + '|' + iv; }

  // 标准化：[ts,o,h,l,c,v] → candle；自动识别秒/毫秒、校验 OHLC、去重排序
  function ocNormalize(rows, interval, opts) {
    var ex = opts || {}, out = [];
    for (var i = 0; i < (rows || []).length; i++) {
      var r = rows[i];
      if (!Array.isArray(r) || r.length < 5) continue;
      var ts = Number(r[0]), o = Number(r[1]), h = Number(r[2]),
          l = Number(r[3]), c = Number(r[4]), v = (r[5] != null) ? Number(r[5]) : 0;
      if (ts > 1e14) ts = ts / 1e6; else if (ts > 1e11) ts = ts / 1e3;
      if (!(ts > 0 && o > 0 && h > 0 && l > 0 && c > 0)) continue;
      if (h + 1e-12 < Math.max(o, c) || l - 1e-12 > Math.min(o, c) || h < l) continue;
      if (v < 0 || !isFinite(v)) continue;
      if (KLINE_SEC[interval]) {
        ts = klineBucketStart(ts, interval, 'ONCHAIN:UTC');
      }
      out.push(candle(ts, o, h, l, c, v, interval, 'ONCHAIN:UTC', ex));
    }
    out.sort(function (a, b) { return a.ts - b.ts; });
    var seen = {}, uniq = [];
    for (var j = 0; j < out.length; j++) {
      if (!seen[out[j].ts]) { seen[out[j].ts] = 1; uniq.push(out[j]); }
      else uniq[uniq.length - 1] = out[j];   // 同 ts 保留最后
    }
    return uniq;
  }

  // 解析交易池：全局搜索选流动性最高的池，结果落 localStorage 缓存
  function ocResolvePool(addr) {
    var hit = OC_POOL_CACHE[addr];
    if (hit && hit.net && hit.pool && nowMs() - (hit.ts || 0) < 6 * 3600 * 1000) {
      return Promise.resolve(hit);
    }
    return http(GT_BASE + '/search/pools?query=' + encodeURIComponent(addr) + '&page=1')
      .then(function (txt) {
        var d = JSON.parse(txt), best = null;
        var rows = (d && d.data) || [];
        for (var i = 0; i < rows.length; i++) {
          var id = String(rows[i].id || ''), at = rows[i].attributes || {};
          var k = id.indexOf('_');
          if (k <= 0) continue;
          var liq = Number(at.reserve_in_usd || 0);
          var vol = Number(((at.volume_usd || {}).h24) || 0);
          var txn = at.txns && at.txns.h24 || {};
          var trades = Number(txn.buys || 0) + Number(txn.sells || 0);
          // 与桌面 _pick_pool_from_payload 同口径：流动性+成交量+活跃度综合，
          // 零成交的死池重罚，避免搜索能中、历史却取不到。
          var score = Math.log1p(Math.max(liq, 0)) +
            0.8 * Math.log1p(Math.max(vol, 0)) +
            0.6 * Math.log1p(Math.max(trades, 0));
          if (liq <= 0) score -= 20;
          if (vol <= 0) score -= 6;
          if (trades <= 0) score -= 6;
          if (!best || score > best.score) {
            best = { net: id.slice(0, k), pool: id.slice(k + 1),
              liq: liq, score: score, ts: nowMs() };
          }
        }
        if (best) { OC_POOL_CACHE[addr] = best; writeJSON('ct_oc_pools', OC_POOL_CACHE); }
        return best;
      }).catch(function () { return null; });
  }

  function ocFetchGecko(addr, interval) {
    var tfAgg = OC_TF[interval] || ['hour', 1];
    return ocResolvePool(addr).then(function (pool) {
      if (!pool) throw new Error('未找到公开 DEX 交易池');
      var url = GT_BASE + '/networks/' + encodeURIComponent(pool.net) +
        '/pools/' + encodeURIComponent(pool.pool) + '/ohlcv/' + tfAgg[0] +
        '?aggregate=' + tfAgg[1] + '&limit=1000&currency=usd&page=1';
      return http(url).then(function (txt) {
        var d = JSON.parse(txt);
        var attrs = (d && d.data && d.data.attributes) || {};
        return ocNormalize(attrs.ohlcv_list || [], interval,
          { pool: pool.net + '_' + pool.pool });
      });
    });
  }

  // 把日线 K 聚合为 3d/1w/1M（与桌面 onchain_kline._aggregate 同口径）。
  // 仅在 CoinGecko 日线备源使用；OHLC=首开/高低/末收，成交量求和。
  function ocAggregateDaily(bars, interval, sym) {
    if (['3d', '1w', '1M'].indexOf(interval) < 0) return bars;
    var groups = {}, order = [];
    for (var i = 0; i < bars.length; i++) {
      var b = bars[i];
      var start = klineBucketStart(b.ts, interval, sym || 'ONCHAIN:agg');
      if (!(start in groups)) {
        groups[start] = { o: b.open, h: b.high, l: b.low, c: b.close, v: b.volume };
        order.push(start);
      } else {
        var g = groups[start];
        if (b.high > g.h) g.h = b.high;
        if (b.low < g.l) g.l = b.low;
        g.c = b.close;
        g.v += b.volume;
      }
    }
    var out = [];
    for (var j = 0; j < order.length; j++) {
      var t = order[j], x = groups[t];
      out.push({ ts: t, time_label: klineLabel(t, interval, sym || 'ONCHAIN:agg'),
        open: x.o, high: x.h, low: x.l, close: x.c, volume: x.v,
        volume_reliable: false, pool: '' });
    }
    return out;
  }

  function ocFetchCoingecko(addr, interval) {
    // CoinGecko 仅提供日线 OHLC：低周期不得用日线冒充，诚实拒绝。
    if (['1d', '3d', '1w', '1M'].indexOf(interval) < 0) {
      return Promise.reject(new Error('CoinGecko 仅提供日线，无法提供 ' + interval));
    }
    var chain = isSolanaAddr(addr) ? 'solana' : (addr.charAt(0) === 'T' ? 'tron' : 'ethereum');
    var url = CG_OHLC.replace('{p}', chain).replace('{a}', encodeURIComponent(addr)) +
      '?vs_currency=usd&days=365';
    return http(url).then(function (txt) {
      var rows = JSON.parse(txt);
      // CoinGecko 无成交量：v=0（界面据此不画量柱）
      var six = (rows || []).map(function (r) {
        return [r[0], r[1], r[2], r[3], r[4], 0];
      });
      return ocAggregateDaily(ocNormalize(six, '1d', { volume_reliable: false }),
        interval, addr);
    });
  }

  // 统一入口：缓存命中优先 → 主源 → 备源 → 失败抛错（由 loadChart 回退采样）
  function fetchOnchainCandles(sym, interval) {
    var addr = ocAddr(sym), key = ocCacheKey(sym, interval);
    var cached = OC_KLINE_CACHE[key];
    if (cached && cached.bars && cached.bars.length &&
        nowMs() - (cached.ts || 0) < 15 * 60 * 1000) {
      OC_STATUS[sym] = { state: 'cache', source: cached.source || '本地缓存', ts: cached.ts };
      return Promise.resolve(cached.bars);
    }
    return ocFetchGecko(addr, interval).catch(function () {
      return ocFetchCoingecko(addr, interval);
    }).then(function (bars) {
      if (!bars || !bars.length) throw new Error('数据源未返回历史数据');
      // 跨池保护：迁移前后两段走势可能不连续，禁止无缝拼接制造假历史。
      // 双方都有明确池身份且不同 -> 以新池为准，丢弃旧缓存。
      var oldPool = '', newPool = '', q;
      for (q = 0; q < (cached && cached.bars || []).length; q++) {
        if (cached.bars[q].pool) { oldPool = cached.bars[q].pool; break; }
      }
      for (q = 0; q < bars.length; q++) {
        if (bars[q].pool) { newPool = bars[q].pool; break; }
      }
      var crossPool = !!(oldPool && newPool && oldPool !== newPool);
      var base = crossPool ? [] : (cached && cached.bars || []);
      // 增量合并：与本地缓存按 ts 去重（保留最新真实值）
      var merged = {}, all = base.concat(bars);
      for (var i = 0; i < all.length; i++) merged[all[i].ts] = all[i];
      var final = Object.keys(merged).map(function (k) { return merged[k]; })
        .sort(function (a, b) { return a.ts - b.ts; });
      if (final.length > 10000) final = final.slice(final.length - 10000);
      OC_KLINE_CACHE[key] = { bars: final, source: 'DEX OHLCV', ts: nowMs() };
      writeJSON('ct_oc_kline', OC_KLINE_CACHE);
      OC_STATUS[sym] = { state: 'ok', source: 'DEX OHLCV', ts: nowMs(),
        message: crossPool ? '交易池已迁移：已按新池重建历史，未拼接旧池数据' : '' };
      return final;
    });
  }

  // ===================== K 线 =====================
  function intervalsFor(sym) {
    if (isOnchain(sym)) return OC_INTERVALS;   // 链上真实 DEX K 线周期
    var mk = marketOf(sym);
    if (mk === 'crypto') return CRYPTO_INTERVALS;
    if (mk === 'cn') return CN_MINUTES.concat(STOCK_INTERVALS);
    if (mk === 'us') return US_MINUTES.concat(STOCK_INTERVALS);
    return STOCK_INTERVALS;                  // 港股：仅日线及以上（腾讯 hkfqkline 无分钟线）
  }
  function defaultInterval(sym) {
    if (isOnchain(sym)) return '1h';
    return marketOf(sym) === 'crypto' ? '15m' : 'day';
  }
  function labelFor(ts, interval, sym) {
    // 与桌面 core.kline_time.label_for 同源；不再用设备本地时间
    return klineLabel(ts, interval, sym || CHART_SYMBOL || 'crypto');
  }
  function candle(ts, o, h, l, c, v, interval, sym, opts) {
    var ex = opts || {};
    return { ts: ts, label: labelFor(ts, interval, sym), o: o, h: h, l: l, c: c, v: v,
      volume_reliable: ex.volume_reliable !== false,   // 备源无真实量则不画量柱
      pool: ex.pool || '' };                            // 跨池历史不可无缝拼接
  }
  function aggregate(rows, mode, interval, sym) {
    if (!rows.length) return [];
    var iv = (mode === '3day') ? '3day' : (mode === 'week') ? 'week'
      : (mode === 'month') ? 'month' : '1year';
    var groups = {}, order = [];
    for (var i = 0; i < rows.length; i++) {
      // 桶起点统一按市场时区；输出 ts=桶起点，不再用组内首根时间
      var key = klineBucketStart(rows[i].ts, iv, sym || CHART_SYMBOL);
      if (!groups[key]) {
        groups[key] = { ts: key, o: rows[i].o, h: rows[i].h,
                        l: rows[i].l, c: rows[i].c, v: rows[i].v };
        order.push(key);
      } else {
        var g = groups[key];
        g.h = Math.max(g.h, rows[i].h); g.l = Math.min(g.l, rows[i].l);
        g.c = rows[i].c; g.v += rows[i].v;
      }
    }
    var out = [];
    for (var j = 0; j < order.length; j++) {
      var x = groups[order[j]];
      out.push(candle(x.ts, x.o, x.h, x.l, x.c, x.v,
        iv === '1year' ? '1year' : iv, sym));
    }
    return out;
  }

  // ===================== 公司行为复权（与桌面端 data/corporate_actions.py + price_adjustment.py 同口径） =====================
  // 已核实公司行为登记库（ratio=除权后每1旧份额换到的新份额数；价格因子=1/ratio）。
  // 与 data/corporate_actions.json 保持一致；只处理 verified 且比例确定的事件。
  var CORPORATE_ACTIONS = {
    'US:AAPL': [
      { d: '2000-06-21', r: 2, k: 'split' }, { d: '2005-02-28', r: 2, k: 'split' },
      { d: '2014-06-09', r: 7, k: 'split' }, { d: '2020-08-31', r: 4, k: 'split' }
    ],
    'US:TSLA': [
      { d: '2020-08-31', r: 5, k: 'split' }, { d: '2022-08-25', r: 3, k: 'split' }
    ],
    'US:NVDA': [
      { d: '2021-07-20', r: 4, k: 'split' }, { d: '2024-06-10', r: 10, k: 'split' }
    ],
    'US:AMZN': [{ d: '2022-06-06', r: 20, k: 'split' }],
    'US:GOOGL': [{ d: '2022-07-18', r: 20, k: 'split' }],
    'US:MSFT': [{ d: '2003-02-18', r: 2, k: 'split' }]
  };
  // 数据源是否自带前复权：腾讯 A股/HK 日线 qfq 已复权价格，美股新浪为原始价。
  var SHARE_CHANGE_KINDS = { split: 1, reverse_split: 1, bonus: 1, rights: 1,
    token_migration: 1, token_redenom: 1 };

  function _candleDate(ts) {
    var d = new Date(ts * 1000);
    var mm = d.getMonth() + 1, dd = d.getDate();
    return d.getFullYear() + '-' + (mm < 10 ? '0' : '') + mm + '-' + (dd < 10 ? '0' : '') + dd;
  }
  // 经验门控：只有观测跳空 ≈ 1/ratio 才认定"未复权"；≈1 视为已复权跳过。
  function detectUnadjustedEvents(rows, actions) {
    if (!rows || rows.length < 2 || !actions || !actions.length) return [];
    var ordered = rows.slice().sort(function (a, b) { return a.ts - b.ts; });
    var neighbors = {};
    for (var i = 1; i < ordered.length; i++) {
      var prev = ordered[i - 1], cur = ordered[i];
      if (prev.c > 0 && cur.c > 0) neighbors[_candleDate(cur.ts)] = [prev.c, cur.c];
    }
    var eff = [];
    for (var j = 0; j < actions.length; j++) {
      var a = actions[j], obs = neighbors[a.d];
      if (!obs) continue;
      var expected = SHARE_CHANGE_KINDS[a.k] ? (1 / a.r) : 1;
      if (!expected || !isFinite(expected)) continue;
      var observed = obs[1] / obs[0];
      if (Math.abs(observed - expected) / expected <= 0.12) eff.push(a);
    }
    return eff;
  }
  // 登记库之外的拆股品种：用「收盘价比例 + 成交量比例 + 事件后延续」三条件识别，
  // 与桌面端 price_adjustment.detect_split_actions_from_prices 同口径。
  var SHARE_RATIOS = [2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 25, 30, 50, 100];
  function detectSplitActionsFromPrices(rows) {
    if (!rows || rows.length < 3) return [];
    var ordered = rows.slice().sort(function (a, b) { return a.ts - b.ts; });
    var seen = {}, out = [];
    for (var i = 1; i < ordered.length - 1; i++) {
      var prev = ordered[i - 1], cur = ordered[i], nxt = ordered[i + 1];
      if (!(prev.c > 0 && cur.c > 0 && nxt.c > 0)) continue;
      var pr = prev.c / cur.c;
      var vr = prev.v > 0 ? cur.v / prev.v : null;
      if (Math.abs(nxt.c / cur.c - 1) > 0.25) continue;
      var hit = null;
      for (var j = 0; j < SHARE_RATIOS.length; j++) {
        var r = SHARE_RATIOS[j], inv = 1 / r;
        if (Math.abs(pr - r) / r <= 0.10 &&
            (vr === null || Math.abs(vr - r) / r <= 0.35 || (vr >= r * 0.6 && vr <= r * 1.8))) {
          hit = { r: r, k: 'split' }; break;
        }
        if (Math.abs(pr - inv) / inv <= 0.10 &&
            (vr === null || Math.abs(vr - inv) / inv <= 0.35 || (vr >= inv * 0.6 && vr <= inv * 1.8))) {
          hit = { r: inv, k: 'reverse_split' }; break;
        }
      }
      if (!hit) continue;
      var d = _candleDate(cur.ts), key = d + ':' + hit.k;
      if (seen[key]) continue;
      seen[key] = 1;
      out.push({ d: d, r: hit.r, k: hit.k });
    }
    return out;
  }
  function mergeActions(rows, actions) {
    var out = (actions || []).slice(), seen = {};
    out.forEach(function (a) { seen[a.d + ':' + a.k] = 1; });
    detectSplitActionsFromPrices(rows).forEach(function (a) {
      var key = a.d + ':' + a.k;
      if (!seen[key]) { seen[key] = 1; out.push(a); }
    });
    return out;
  }
  // 对原始价做前复权：除权日之前的 OHLC 乘 1/ratio，成交量乘 ratio。
  function applyAdjustment(rows, actions) {
    var all = mergeActions(rows, actions);
    if (!all.length) return rows;
    var eff = detectUnadjustedEvents(rows, all);
    if (!eff.length) return rows;
    return rows.map(function (r) {
      var d = _candleDate(r.ts), pf = 1, vf = 1;
      for (var i = 0; i < eff.length; i++) {
        if (eff[i].d > d) { pf *= 1 / eff[i].r; vf *= eff[i].r; }
      }
      return candle(r.ts, r.o * pf, r.h * pf, r.l * pf, r.c * pf, r.v * vf, 'day');
    });
  }
  // 腾讯 qfq：价格已前复权，只把成交量按份额事件放大到同口径。
  function adjustVolumeOnly(rows, symbol) {
    var actions = CORPORATE_ACTIONS[symbol];
    if (!actions || !actions.length) return rows;
    var usable = actions.filter(function (a) { return SHARE_CHANGE_KINDS[a.k]; });
    if (!usable.length) return rows;
    return rows.map(function (r) {
      var d = _candleDate(r.ts), vf = 1;
      for (var i = 0; i < usable.length; i++) {
        if (usable[i].d > d) vf *= usable[i].r;
      }
      if (vf === 1) return r;
      return candle(r.ts, r.o, r.h, r.l, r.c, r.v * vf, 'day');
    });
  }

  function parseDate(s) {
    // "2026-11-12" / "202611121500" / "2026-11-12 15:00:00"
    var str = String(s).trim();
    var m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(str);
    if (m) return new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]).getTime() / 1000;
    m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(str);
    if (m) return new Date(+m[1], +m[2] - 1, +m[3]).getTime() / 1000;
    m = /^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})/.exec(str);
    if (m) return new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]).getTime() / 1000;
    return NaN;
  }
  function parseMarketDate(s, sym) {
    // 交易所返回的是当地墙钟（无时区）。按市场时区解释，不再依赖设备时区。
    var str = String(s).trim();
    var m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(str);
    if (!m) m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(str);
    if (!m) m = /^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})/.exec(str);
    if (!m) return NaN;
    var withTime = m.length >= 6;
    var wall = Date.UTC(+m[1], +m[2] - 1, +m[3],
      withTime ? +m[4] : 0, withTime ? +m[5] : 0);
    return (wall - klineOffsetMs(sym || CHART_SYMBOL, wall)) / 1000;
  }
  function parseTencentKlines(text, interval, sym) {
    var body;
    try { body = JSON.parse(text); } catch (e) { return []; }
    var data = (body && body.data) || {}, rows = null;
    for (var code in data) {
      if (!Object.prototype.hasOwnProperty.call(data, code)) continue;
      var d = data[code] || {};
      rows = d['qfq' + interval] || d[interval] || d.qfqday || d.day || null;
      if (rows && rows.length) break;
    }
    if (!rows || !rows.length) return [];
    var out = [];
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i], ts = parseMarketDate(r[0], sym);
      if (!isFinite(ts)) continue;
      out.push(candle(ts, Number(r[1]), Number(r[3]), Number(r[4]),
        Number(r[2]), Number(r[5] || 0), interval === 'day' ? 'day' : interval, sym));
    }
    return out;
  }
  function parseBinanceKlines(text, interval, sym) {
    var rows;
    try { rows = JSON.parse(text); } catch (e) { return []; }
    if (!Array.isArray(rows)) return [];
    var out = [];
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var ts = Number(r[0]) / 1000;    // Binance 毫秒 -> 统一 Unix 秒
      out.push(candle(ts, Number(r[1]), Number(r[2]),
        Number(r[3]), Number(r[4]), Number(r[5] || 0), interval, sym));
    }
    return out;
  }
  function parseSinaRows(text, withTime, sym) {
    var t = String(text);
    var i = t.indexOf('('), j = t.lastIndexOf(')');
    if (i >= 0 && j > i) t = t.slice(i + 1, j);
    var rows;
    try { rows = JSON.parse(t); } catch (e) { return []; }
    if (!Array.isArray(rows)) return [];
    var out = [];
    for (var k = 0; k < rows.length; k++) {
      var r = rows[k], ts = parseMarketDate(r.d, sym);
      if (!isFinite(ts)) continue;
      out.push(candle(ts, Number(r.o), Number(r.h), Number(r.l), Number(r.c),
        Number(r.v || 0), withTime ? 'm5' : 'day', sym));
    }
    return out;
  }
  function fetchCandles(sym, interval) {
    var mk = marketOf(sym), code;
    if (mk === 'crypto') {
      // 年K：Binance 无原生年线，与桌面端同口径用月线(1M)本地聚合，避免透传非法 interval。
      if (interval === '1y') {
        return http(BINANCE_KLINE + '?symbol=' + encodeURIComponent(sym + 'USDT') +
          '&interval=1M&limit=1000')
          .then(function (txt) { return aggregate(parseBinanceKlines(txt, '1M', sym), '1year', 'month', sym); });
      }
      return http(BINANCE_KLINE + '?symbol=' + encodeURIComponent(sym + 'USDT') +
        '&interval=' + interval + '&limit=1000')
        .then(function (txt) { return parseBinanceKlines(txt, interval, sym); });
    }
    code = sym.replace(':', '').toLowerCase();
    if (mk === 'us') {
      if (interval === 'day' || interval === '3day' || interval === 'week' ||
          interval === 'month' || interval === '1year') {
        return http(SINA_US_DAY + encodeURIComponent(sym.slice(3).toLowerCase()))
          .then(function (txt) {
            var rows = parseSinaRows(txt, false, sym);
            // 新浪美股日线为原始价：按已核实拆股事件前复权后再聚合，保证多周期同口径。
            rows = applyAdjustment(rows, CORPORATE_ACTIONS[sym]);
            return (interval === 'day') ? rows : aggregate(rows, interval, 'day', sym);
          });
      }
      var typeMap = { m1: '1', m5: '5', m15: '15', m30: '30', m60: '60' };
      return http(SINA_US_MIN + encodeURIComponent(sym.slice(3).toLowerCase()) +
        '&type=' + (typeMap[interval] || '5'))
        .then(function (txt) {
          // 分钟线同样可能是未复权原始价，按同一套事件前复权后再展示。
          return applyAdjustment(parseSinaRows(txt, true, sym), CORPORATE_ACTIONS[sym]);
        });
    }
    if (interval === 'm5' || interval === 'm15' || interval === 'm30' || interval === 'm60') {
      return http(TENCENT_KLINE + encodeURIComponent(code + ',' + interval + ',,,1000'))
        .then(function (txt) { return parseTencentKlines(txt, interval, sym); });
    }
    var url = (mk === 'hk' ? HK_KLINE : TENCENT_KLINE) +
      encodeURIComponent(code + ',day,,,640,qfq');
    return http(url).then(function (txt) {
      var rows = parseTencentKlines(txt, 'day', sym);
      // 腾讯 qfq 已前复权价格，但成交量仍是原始份额 -> 补齐成交量口径。
      rows = adjustVolumeOnly(rows, sym);
      if (interval === 'day') return rows;
      var mode = interval === '3day' ? '3day' : (interval === 'week' ? 'week'
        : (interval === 'month' ? 'month' : '1year'));
      return aggregate(rows, mode, 'day', sym);
    });
  }

  function openChart(sym) {
    CHART_SYMBOL = sym;
    CFG.last_symbol = sym;
    saveCfg();
    var ivs = intervalsFor(sym);
    CHART_INTERVAL = CFG.chart_interval || defaultInterval(sym);
    var valid = false;
    for (var i = 0; i < ivs.length; i++) if (ivs[i][1] === CHART_INTERVAL) valid = true;
    if (!valid) CHART_INTERVAL = defaultInterval(sym);
    renderIntervals(ivs);
    updateChartHead();
    loadChart();
    restartKlineTimer();
  }
  function renderIntervals(ivs) {
    var h = '';
    for (var i = 0; i < ivs.length; i++) {
      h += '<button data-iv="' + ivs[i][1] + '" class="' +
        (ivs[i][1] === CHART_INTERVAL ? 'active' : '') + '">' + ivs[i][0] + '</button>';
    }
    $('intervals').innerHTML = h;
  }
  function updateChartHead() {
    var oc = isOnchain(CHART_SYMBOL);
    var code = oc ? ocCode(CHART_SYMBOL)
      : String(CHART_SYMBOL).replace(/^.*:/, '');
    $('chartCode').textContent = code;
    $('chartIco').innerHTML = symbolIconHTML(CHART_SYMBOL, code);
    $('chartName').textContent = nameOf(CHART_SYMBOL);
    var t = priceOf(CHART_SYMBOL);
    var el = $('chartPrice'), ch = $('chartChange');
    el.textContent = t && t.price !== null
      ? unitPrefix(CHART_SYMBOL) + fmtPrice(t.price) : '--';
    el.className = chgClass(t ? t.chg : null);
    ch.textContent = oc ? '—' : (t ? chgText(t.chg) : '--');
    ch.className = chgClass(t ? t.chg : null);
  }
  // 判断一次 K 线异步回执是否仍是「当前有效请求」：
  // 序号必须等于最新，且品种/周期仍与快照一致（防止快速往返同序号错配）。
  function chartLoadIsCurrent(seq, sym, iv) {
    return seq === chartLoadSeq && sym === CHART_SYMBOL && iv === CHART_INTERVAL;
  }

  // ---- K 线缓存 / 增量合并 / 视口时间锚定 ----
  function klineKey(sym, iv) { return String(sym) + '|' + String(iv); }
  function mergeCandles(oldRows, incoming) {
    var m = {}, i;
    for (i = 0; i < (oldRows || []).length; i++) {
      var o = oldRows[i];
      if (!o.preview) m[o.ts] = o;       // 预览根绝不参与合并
    }
    for (i = 0; i < (incoming || []).length; i++) {
      m[incoming[i].ts] = incoming[i];   // 服务端真实值覆盖旧值
    }
    return Object.keys(m).map(function (k) { return m[k]; })
      .sort(function (a, b) { return a.ts - b.ts; });
  }
  function klineCacheGet(sym, iv) {
    var e = KLINE_CACHE[klineKey(sym, iv)];
    return (e && e.bars && e.bars.length) ? e.bars : null;
  }
  function klineCacheFresh(sym, iv) {
    var e = KLINE_CACHE[klineKey(sym, iv)];
    if (!e || !e.bars || !e.bars.length) return false;
    var bucket = klineBucketStart(nowSec(), iv, sym);
    if ((e.checkedBucket || 0) >= bucket) return true;
    var last = e.bars[e.bars.length - 1].ts;
    return last >= bucket && nowMs() - (e.ts || 0) < 15 * 60 * 1000;
  }
  function klineCachePut(sym, iv, bars, checkedBucket) {
    if (!bars || !bars.length) return;
    var key = klineKey(sym, iv), old = KLINE_CACHE[key] || {};
    KLINE_CACHE[key] = {
      bars: mergeCandles(old.bars, bars).slice(-2000),
      checkedBucket: Math.max(Number(old.checkedBucket) || 0,
                              Number(checkedBucket) || 0),
      ts: nowMs()
    };
    var keys = Object.keys(KLINE_CACHE);
    while (keys.length > 6) delete KLINE_CACHE[keys.shift()];
    writeJSON('ct_kline', KLINE_CACHE);
  }
  function klineCacheMark(sym, iv, bucket) {
    var key = klineKey(sym, iv), e = KLINE_CACHE[key];
    if (!e) return;
    e.checkedBucket = Math.max(Number(e.checkedBucket) || 0, Number(bucket) || 0);
    e.ts = nowMs();
    writeJSON('ct_kline', KLINE_CACHE);
  }
  function chartAnchorTs() {
    if (!CANDLES.length) return null;
    var idx = Math.round(CANDLES.length - VIEW.pan);
    idx = Math.max(0, Math.min(CANDLES.length - 1, idx));
    return CANDLES[idx].ts;
  }
  function chartReanchor(ts) {
    if (ts === null || ts === undefined || !CANDLES.length) return;
    var idx = 0;
    while (idx < CANDLES.length - 1 && CANDLES[idx].ts < ts) idx++;
    VIEW.pan = CANDLES.length - idx;
    clampPan();
  }
  function restartKlineTimer() {
    if (_klineTimer) { clearInterval(_klineTimer); _klineTimer = null; }
    if (PAGE !== 'chart' || !CHART_SYMBOL) return;
    _klineTimer = setInterval(function () {
      if (PAGE === 'chart' && CHART_SYMBOL) loadChart(true);
    }, refreshSeconds(CHART_INTERVAL) * 1000);
  }
  // 实时价推进当前周期：只在服务端最新根仍落后于当前桶时创建预览根。
  // 预览根的 OHLC 全部来自真实报价，volume=0，绝不缓存、绝不冒充已完成 K 线。
  function applyChartQuote(price, quoteTs) {
    if (PAGE !== 'chart' || !CHART_SYMBOL || !CANDLES.length) return;
    var anchor = chartAnchorTs(), p = Number(price);
    if (!isFinite(p) || p <= 0) return;
    var realLastTs = 0, i;
    for (i = CANDLES.length - 1; i >= 0; i--) {
      if (!CANDLES[i].preview) { realLastTs = CANDLES[i].ts; break; }
    }
    var f = klinePreviewFields(CHART_SYMBOL, CHART_INTERVAL, p, quoteTs);
    var last = CANDLES[CANDLES.length - 1];
    if (f && f.ts > realLastTs) {
      if (last && last.preview && last.ts === f.ts) {
        last.c = p; last.h = Math.max(last.h, p); last.l = Math.min(last.l, p);
        last.quoteTs = f.quoteTs;
      } else {
        CANDLES = CANDLES.filter(function (c) { return !c.preview; });
        CANDLES.push({ ts: f.ts, label: f.label, o: p, h: p, l: p, c: p,
                       v: 0, preview: true, quoteTs: f.quoteTs });
      }
      $('chartNote').textContent = '当前 ' + CHART_INTERVAL +
        ' 周期 · 实时报价预览（非已完成 K 线，无成交量）';
    } else {
      if (last && last.preview) {
        CANDLES = CANDLES.filter(function (c) { return !c.preview; });
        last = CANDLES[CANDLES.length - 1];
      }
      if (last) {
        last.c = p; last.h = Math.max(last.h, p); last.l = Math.min(last.l, p);
      }
    }
    chartReanchor(anchor);
    drawChart();
  }

  function loadChart(refreshOnly) {
    // 每次进入都递增序号，使此前所有在途请求的回执立即失效。
    var seq = ++chartLoadSeq;
    var sym = CHART_SYMBOL, iv = CHART_INTERVAL;
    var anchor = chartAnchorTs();
    if (isOnchain(sym)) {
      // 先尝试真实 DEX 历史 K 线（GeckoTerminal / CoinGecko）；拿到就画蜡烛，
      // 拿不到才回退到本设备真实报价采样折线，绝不画假 K 线。
      if (!refreshOnly) {
        $('chartNote').textContent = '正在加载链上历史 K 线（' + iv + '）…';
        CANDLES = [];
        drawChart();
      }
      refreshOnchain([sym], true);   // 同时取一次真实报价快照（含首次兜底数据）
      fetchOnchainCandles(sym, iv).then(function (rows) {
        if (!chartLoadIsCurrent(seq, sym, iv)) return;
        CANDLES = refreshOnly
          ? mergeCandles(CANDLES, rows || []) : (rows || []);
        VIEW.count = clamp(VIEW.count || 90, 20, 400);
        $('chartNote').textContent = CANDLES.length
          ? '共 ' + CANDLES.length + ' 根真实 DEX K 线 · 左右拖动 · ＋/－ 缩放'
          : '该链上标的暂无可用历史 K 线（显示真实报价走势）';
        chartReanchor(anchor);
        drawChart();
      }).catch(function (e) {
        if (!chartLoadIsCurrent(seq, sym, iv)) return;
        if (refreshOnly && CANDLES.length) return;   // 刷新失败保留旧真实数据
        CANDLES = [];
        drawOnchainFallbackNote();
        drawChart();
      });
      return;
    }
    var cached = klineCacheGet(sym, iv);
    if (!refreshOnly && cached) {
      CANDLES = cached.slice();
      $('chartNote').textContent = '本地缓存 ' + CANDLES.length + ' 根 · 校验更新中';
      drawChart();
    }
    if (refreshOnly && klineCacheFresh(sym, iv) && CANDLES.length) {
      drawChart();
      return;
    }
    if (!refreshOnly) {
      $('chartNote').textContent = '正在加载 ' + sym + ' K 线（' + iv + '）…';
      CANDLES = [];
      drawChart();
    }
    fetchCandles(sym, iv).then(function (rows) {
      // 迟到 / 已切换品种或周期：丢弃，绝不触碰当前图表状态。
      if (!chartLoadIsCurrent(seq, sym, iv)) return;
      CANDLES = refreshOnly
        ? mergeCandles(CANDLES, rows || []) : (rows || []);
      VIEW.count = clamp(VIEW.count || 90, 20, 400);
      VIEW.pan = Number(VIEW.pan) || 0;   // 保留上次的自由位置（含右侧留白）
      klineCachePut(sym, iv, CANDLES);
      var bucket = klineBucketStart(nowSec(), iv, sym);
      var newest = CANDLES.length ? CANDLES[CANDLES.length - 1].ts : 0;
      if (newest < bucket) klineCacheMark(sym, iv, bucket);
      $('chartNote').textContent = CANDLES.length
        ? '共 ' + CANDLES.length + ' 根真实 K 线 · 左右拖动平移 · 双指或 ＋/－ 缩放'
        : '该品种暂无公开 K 线数据（数据源未返回）';
      chartReanchor(anchor);
      drawChart();
    }).catch(function (e) {
      // 旧请求的失败也不能把当前新请求的界面改成「加载失败」。
      if (!chartLoadIsCurrent(seq, sym, iv)) return;
      if (refreshOnly && CANDLES.length) return;
      $('chartNote').textContent = 'K 线加载失败：' + (e && e.message ? e.message : '网络异常') +
        ' · 点「最新」或切换周期重试';
      drawChart();
    });
  }

  function unitPrefix(sym) {
    if (CFG.show_currency === false) return '';
    var s = String(sym || '');
    if (s.indexOf('SH:') === 0 || s.indexOf('SZ:') === 0) return '¥';
    if (s.indexOf('HK:') === 0) return 'HK$';
    return '$';
  }
  function ocTimeLabel(ts) {
    var d = new Date(Number(ts) * 1000);
    function p(n) { return n < 10 ? '0' + n : String(n); }
    return p(d.getMonth() + 1) + '/' + p(d.getDate()) + ' ' +
      p(d.getHours()) + ':' + p(d.getMinutes());
  }

  // 链上品种没有交易所 OHLC，这里画两种「真实存在」的图：
  //   ① 本设备历次刷新采到的真实报价点连成的走势（非 K 线，无成交量）；
  //   ② 当前 Rugcheck 报告里的前十大持有地址占比 / 流动性池类型分布。
  // 所有数值都来自接口真实字段，缺失就明确写「暂不可用」。
  function drawOnchainChart(g, w, h, fpx, colText, colSub, colLine, accent) {
    var q = ONCHAIN_Q[CHART_SYMBOL] || {};
    var series = [], raw = ocSeries(CHART_SYMBOL), i, r;
    for (i = 0; i < raw.length; i++) {
      r = raw[i];
      if (Array.isArray(r) && isFinite(Number(r[1])) && Number(r[1]) > 0) {
        series.push([Number(r[0]), Number(r[1])]);
      }
    }
    var holders = Array.isArray(q.top_holders) ? q.top_holders : [];
    var pools = Array.isArray(q.pool_types) ? q.pool_types : [];
    var padL = 8, padR = 62;
    var padT = Math.round(fpx * 4.8), padB = 20;
    var mainY0 = padT, mainY1 = Math.round(h * 0.60);
    var structY0 = mainY1 + Math.round(fpx * 2.6), structY1 = h - padB;
    var plotW = Math.max(40, w - padR - padL);

    g.textAlign = 'left'; g.fillStyle = colText; g.font = fpx + 'px sans-serif';
    g.fillText('链上真实报价走势 · 非交易所 K 线（无 OHLC / 成交量）',
      padL, padT - fpx * 2.5);
    g.fillStyle = accent; g.font = (fpx - 1) + 'px sans-serif';
    g.fillText('来源 ' + OC_SOURCE + ' · ' + series.length + ' 个真实采样点' +
      (q.ts ? ' · 更新 ' + ocTimeLabel(q.ts) : ' · 等待首次报价'),
      padL, padT - fpx);

    var lo = Infinity, hi = -Infinity;
    for (i = 0; i < series.length; i++) {
      lo = Math.min(lo, series[i][1]); hi = Math.max(hi, series[i][1]);
    }
    if (!isFinite(lo) || !isFinite(hi)) { lo = 0; hi = 1; }
    if (hi <= lo) { var d0 = Math.abs(hi) * 0.02 || 1; hi += d0; lo -= d0; }
    else { var sp = hi - lo; hi += sp * 0.12; lo -= sp * 0.12; }
    function Y(v) { return mainY1 - (v - lo) / (hi - lo) * (mainY1 - mainY0); }
    function X(k) {
      return padL + (series.length <= 1 ? plotW / 2 : plotW * k / (series.length - 1));
    }

    g.strokeStyle = colLine; g.lineWidth = 1;
    g.fillStyle = colSub; g.font = (fpx - 1) + 'px sans-serif'; g.textAlign = 'left';
    for (i = 0; i <= 4; i++) {
      var yy = mainY0 + (mainY1 - mainY0) * i / 4;
      g.beginPath(); g.moveTo(padL, yy); g.lineTo(padL + plotW, yy); g.stroke();
      g.fillText('$' + fmtPrice(hi - (hi - lo) * i / 4), padL + plotW + 4, yy + 3);
    }

    if (series.length >= 2) {
      g.strokeStyle = accent; g.lineWidth = 2; g.beginPath();
      for (i = 0; i < series.length; i++) {
        var x = X(i), y = Y(series[i][1]);
        if (i === 0) g.moveTo(x, y); else g.lineTo(x, y);
      }
      g.stroke();
      g.fillStyle = accent;
      var skip = Math.max(1, Math.ceil(series.length / 80));
      for (i = 0; i < series.length; i += skip) {
        g.fillRect(X(i) - 1.5, Y(series[i][1]) - 1.5, 3, 3);
      }
      g.fillStyle = colSub; g.textAlign = 'center';
      g.fillText(ocTimeLabel(series[0][0]), padL + 34, h - 5);
      g.fillText(ocTimeLabel(series[series.length - 1][0]), padL + plotW - 34, h - 5);
    } else {
      g.textAlign = 'center'; g.fillStyle = colSub;
      g.fillText(series.length === 1
        ? '已采到 1 个真实价格点 · 行情刷新后自动累积走势'
        : '等待首个真实链上报价…', padL + plotW / 2, (mainY0 + mainY1) / 2);
      if (series.length === 1) {
        g.fillStyle = accent;
        g.fillRect(X(0) - 3, Y(series[0][1]) - 3, 6, 6);
      }
    }

    // ---- 真实链上结构图 ----
    var bars = [], title = '';
    if (holders.length) {
      title = '前 ' + Math.min(6, holders.length) + ' 大持有地址占比 · 真实快照';
      for (i = 0; i < Math.min(6, holders.length); i++) {
        bars.push({ label: String(holders[i].label || ('#' + (i + 1))),
                    value: Number(holders[i].pct) || 0,
                    text: (Number(holders[i].pct) || 0).toFixed(2) + '%' });
      }
    } else if (pools.length) {
      title = '流动性池类型分布 · 共 ' + (q.market_count || pools.length) + ' 个池';
      for (i = 0; i < Math.min(6, pools.length); i++) {
        bars.push({ label: String(pools[i].label || 'other'),
                    value: Number(pools[i].count) || 0,
                    text: String(pools[i].count || 0) });
      }
    }
    g.textAlign = 'left'; g.fillStyle = colText; g.font = fpx + 'px sans-serif';
    if (!bars.length) {
      g.fillStyle = colSub;
      g.fillText('链上结构数据暂不可用（数据源未返回持有地址 / 池信息）',
        padL, structY0 + 8);
      return;
    }
    g.fillText(title, padL, structY0);
    var maxV = 0;
    for (i = 0; i < bars.length; i++) maxV = Math.max(maxV, bars[i].value);
    var rowH = Math.max(12, (structY1 - structY0 - 6) / bars.length);
    var barX = padL + 72, barW = Math.max(24, plotW - 118);
    for (i = 0; i < bars.length; i++) {
      var by = structY0 + 8 + i * rowH;
      g.fillStyle = colSub; g.font = (fpx - 1) + 'px sans-serif'; g.textAlign = 'left';
      g.fillText(bars[i].label.slice(0, 10), padL, by + rowH * 0.6);
      var bw = maxV ? barW * bars[i].value / maxV : 0;
      g.fillStyle = accent;
      g.fillRect(barX, by + rowH * 0.2, Math.max(2, bw), Math.max(4, rowH * 0.5));
      g.fillStyle = colText; g.textAlign = 'right';
      g.fillText(bars[i].text, w - 4, by + rowH * 0.6);
    }
  }

  function drawChart() {
    var cv = $('kline');
    if (!cv) return;
    var dpr = window.devicePixelRatio || 1;
    var w = cv.clientWidth || 320, h = cv.clientHeight || 260;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    }
    var g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    var css = getComputedStyle(document.body);
    var colText = css.getPropertyValue('--text').trim() || '#eaecef';
    var colSub = css.getPropertyValue('--sub').trim() || '#848e9c';
    var colLine = css.getPropertyValue('--line').trim() || '#2b3139';
    var UP = css.getPropertyValue('--up').trim() || '#f6465d';
    var DOWN = css.getPropertyValue('--down').trim() || '#0ecb81';
    var scale = (Number(CFG.chart_font_scale) || 120) / 100;
    var fpx = Math.round(10 * scale);
    g.clearRect(0, 0, w, h);
    g.font = fpx + 'px sans-serif';
    if (isOnchain(CHART_SYMBOL) && !CANDLES.length) {
      // 只有确实没有真实 K 线时才画本设备报价采样折线（非 K 线）
      drawOnchainChart(g, w, h, fpx, colText, colSub, colLine,
        css.getPropertyValue('--accent').trim() || '#f0b90b');
      return;
    }
    if (!CANDLES.length) {
      g.fillStyle = colSub; g.textAlign = 'center';
      g.fillText('暂无 K 线数据', w / 2, h / 2);
      return;
    }

    // ---- 视口：pan 可为负（右侧留白）也可超过历史长度（左侧留白），
    // 不再强制把最新一根钉在右边，也不再吸附到第一根。----
    var padR = 54 + Math.round(fpx * 1.5), padB = 20;
    var showVol = CFG.show_vol !== false;
    var showMacd = CFG.show_macd !== false;
    var volH = showVol ? Math.round(h * 0.14) : 0;
    var macdH = showMacd ? Math.round(h * 0.16) : 0;
    var padT = Math.round(18 * scale) + 20;   // 两行图例
    var plotH = Math.max(80, h - padB - volH - macdH - padT - 10);
    var plotW = w - padR;
    var total = CANDLES.length;
    var count = clamp(Math.round(VIEW.count), 10, 400);
    var end = total - VIEW.pan;               // 浮点，跟手
    var start = end - count;
    var i0 = Math.floor(start);
    var view = [], giOf = [], i, gi;
    for (i = 0; i < count; i++) {
      gi = i0 + i;
      giOf.push(gi);
      view.push((gi >= 0 && gi < total) ? CANDLES[gi] : null);
    }

    // 指标：按当前周期作用域取参数，一次算全量序列
    var params = indParams(CHART_INTERVAL);
    var lines = indLines(CANDLES, params);
    var macd = showMacd ? macdSeries(CANDLES, params.macd.fast,
                                     params.macd.slow, params.macd.signal)
                        : null;

    var lo = Infinity, hi = -Infinity, vmax = 0;
    for (i = 0; i < view.length; i++) {
      if (!view[i]) continue;
      lo = Math.min(lo, view[i].l); hi = Math.max(hi, view[i].h);
      vmax = Math.max(vmax, view[i].v);
      for (var li = 0; li < lines.length; li++) {
        var lv = lines[li].values[giOf[i]];
        if (lv !== null && lv !== undefined) {
          lo = Math.min(lo, lv); hi = Math.max(hi, lv);
        }
      }
    }
    if (!isFinite(lo) || !isFinite(hi) || hi <= lo) { hi = lo + 1; }
    var span = hi - lo; hi += span * 0.06; lo -= span * 0.06;
    function Y(p) { return padT + (hi - p) / (hi - lo) * plotH; }
    var bw = plotW / Math.max(1, count);
    function X(idx) { return (idx + 0.5) * bw; }

    // 网格 + 价格轴
    g.strokeStyle = colLine; g.lineWidth = 1; g.fillStyle = colSub; g.textAlign = 'left';
    for (i = 0; i <= 4; i++) {
      var yy = padT + plotH * i / 4;
      g.beginPath(); g.moveTo(0, yy); g.lineTo(plotW, yy); g.stroke();
      g.fillText(unitPrefix(CHART_SYMBOL) + fmtPrice(hi - (hi - lo) * i / 4),
                 plotW + 5, yy + 3);
    }

    // 成交量副图
    var volTop = padT + plotH + 6;
    if (showVol) {
      // 备源（CoinGecko）无真实成交量：volume_reliable=false 的柱子不画，
      // 也不参与 vmax，避免用 0 量或伪量误导（与桌面端同口径）。
      var volSeen = false, vvmax = 0;
      for (i = 0; i < view.length; i++) {
        if (!view[i] || view[i].volume_reliable === false) continue;
        volSeen = true;
        vvmax = Math.max(vvmax, view[i].v);
      }
      for (i = 0; i < view.length; i++) {
        if (!view[i] || view[i].volume_reliable === false) continue;
        var vr = view[i];
        g.fillStyle = vr.c >= vr.o ? UP : DOWN; g.globalAlpha = 0.45;
        var vh = vvmax ? (vr.v / vvmax) * (volH - 8) : 0;
        g.fillRect(X(i) - bw * 0.3, volTop + (volH - 8 - vh), bw * 0.6, vh);
        g.globalAlpha = 1;
      }
      g.fillStyle = colSub; g.textAlign = 'left';
      g.fillText(volSeen ? ('VOL ' + fmtAmount(vvmax)) : '该数据源无成交量',
        2, volTop + fpx);
    }

    // MACD 副图：柱 + DIF / DEA 两条线
    if (showMacd && macd) {
      var mTop = volTop + volH + (showVol ? 6 : 2);
      var mh = Math.max(20, macdH - 10), mmax = 1e-9;
      for (i = 0; i < view.length; i++) {
        if (giOf[i] < 0 || giOf[i] >= total) continue;
        var hv = macd.hist[giOf[i]];
        if (hv !== null && hv !== undefined) mmax = Math.max(mmax, Math.abs(hv));
      }
      var zero = mTop + mh / 2;
      g.strokeStyle = colLine; g.beginPath();
      g.moveTo(0, zero); g.lineTo(plotW, zero); g.stroke();
      for (i = 0; i < view.length; i++) {
        if (giOf[i] < 0 || giOf[i] >= total) continue;
        var hv2 = macd.hist[giOf[i]];
        if (hv2 === null || hv2 === undefined) continue;
        g.fillStyle = hv2 >= 0 ? UP : DOWN;
        g.globalAlpha = 0.7;
        var bh2 = Math.abs(hv2) / mmax * (mh / 2 - 2);
        g.fillRect(X(i) - bw * 0.25, hv2 >= 0 ? zero - bh2 : zero,
                   bw * 0.5, bh2);
        g.globalAlpha = 1;
      }
      var mseries = [[macd.dif, '#f0b90b'], [macd.dea, '#e040fb']];
      for (var ms = 0; ms < mseries.length; ms++) {
        g.strokeStyle = mseries[ms][1]; g.lineWidth = 1; g.beginPath();
        var begun = false;
        for (i = 0; i < view.length; i++) {
          var mv = mseries[ms][0][giOf[i]];
          if (mv === null || mv === undefined || giOf[i] < 0 ||
              giOf[i] >= total) { begun = false; continue; }
          var my2 = zero - mv / mmax * (mh / 2 - 2);
          if (!begun) { g.moveTo(X(i), my2); begun = true; }
          else g.lineTo(X(i), my2);
        }
        g.stroke();
      }
      g.fillStyle = colSub; g.textAlign = 'left';
      g.fillText('MACD(' + params.macd.fast + ',' + params.macd.slow + ',' +
                 params.macd.signal + ')', 2, mTop + fpx);
    }

    // 蜡烛
    for (i = 0; i < view.length; i++) {
      if (!view[i]) continue;
      var r = view[i], x = X(i), col = r.c >= r.o ? UP : DOWN;
      g.strokeStyle = col; g.fillStyle = col; g.lineWidth = 1;
      // 预览根：半透明空心，明确区别于已完成的真实 K 线
      g.globalAlpha = r.preview ? 0.55 : 1;
      g.beginPath(); g.moveTo(x, Y(r.h)); g.lineTo(x, Y(r.l)); g.stroke();
      var top = Math.min(Y(r.o), Y(r.c));
      var bh3 = Math.max(1, Math.abs(Y(r.o) - Y(r.c)));
      if (r.preview) g.strokeRect(x - Math.max(1, bw * 0.32), top,
        Math.max(2, bw * 0.64), bh3);
      else g.fillRect(x - Math.max(1, bw * 0.32), top,
        Math.max(2, bw * 0.64), bh3);
      g.globalAlpha = 1;
    }

    // 主图指标线：MA / EMA / BOLL，天数由参数面板控制
    for (var l2 = 0; l2 < lines.length; l2++) {
      var line = lines[l2];
      g.strokeStyle = line.color; g.lineWidth = line.width || 1.2;
      g.beginPath();
      var started = false;
      for (i = 0; i < view.length; i++) {
        var v = line.values[giOf[i]];
        if (v === null || v === undefined || giOf[i] < 0 ||
            giOf[i] >= total) { started = false; continue; }
        if (!started) { g.moveTo(X(i), Y(v)); started = true; }
        else g.lineTo(X(i), Y(v));
      }
      g.stroke();
    }

    // 最新价虚线（取视口内最后一根有数据的 K 线）
    var last = null;
    for (i = view.length - 1; i >= 0; i--) { if (view[i]) { last = view[i]; break; } }
    if (last) {
      g.setLineDash([4, 4]); g.strokeStyle = colSub; g.beginPath();
      g.moveTo(0, Y(last.c)); g.lineTo(plotW, Y(last.c)); g.stroke();
      g.setLineDash([]);
      g.fillStyle = last.c >= last.o ? UP : DOWN;
      g.fillRect(plotW + 1, Y(last.c) - 8, padR - 2, 16);
      g.fillStyle = '#fff'; g.textAlign = 'left';
      g.fillText(unitPrefix(CHART_SYMBOL) + fmtPrice(last.c), plotW + 4, Y(last.c) + 3);
    }

    // 顶部两行图例：OHLC + 指标数值（只列 MA/EMA，避免 BOLL 挤占）
    var hover = null;
    for (i = view.length - 1; i >= 0; i--) { if (view[i]) { hover = { r: view[i], gi: giOf[i] }; break; } }
    if (hover) {
      g.fillStyle = colLine; g.globalAlpha = 0.55;
      g.fillRect(0, 0, plotW, padT - 4); g.globalAlpha = 1;
      g.font = fpx + 'px sans-serif'; g.textAlign = 'left'; g.fillStyle = colText;
      g.fillText(hover.r.label + '  O ' + fmtPrice(hover.r.o) +
                 '  H ' + fmtPrice(hover.r.h) + '  L ' + fmtPrice(hover.r.l) +
                 '  C ' + fmtPrice(hover.r.c), 3, fpx + 2);
      var tx = 3, legend = '';
      for (var l3 = 0; l3 < lines.length; l3++) {
        var ln = lines[l3];
        if (ln.label.indexOf('BOLL') === 0) continue;
        var vv = ln.values[hover.gi];
        var piece = ln.label + ' ' + (vv === null || vv === undefined
          ? '--' : fmtPrice(vv)) + '   ';
        if (tx + piece.length * fpx * 0.6 > plotW) break;
        legend += piece; tx += piece.length * fpx * 0.6;
      }
      g.fillStyle = colSub;
      g.fillText(legend || '指标已全部关闭', 3, fpx * 2 + 5);
    }

    // 时间轴
    g.fillStyle = colSub; g.textAlign = 'center';
    var step = Math.max(1, Math.floor(view.length / 4));
    for (i = 0; i < view.length; i += step) {
      if (view[i]) g.fillText(view[i].label, X(i), h - 5);
    }
  }

  // ===================== 统一搜索结果页（本地索引优先 + 对象化历史） =====================
  var SEARCH_QUERY = '';
  // 统一资产类型标签：股票 / 交易所加密货币 / 链上代币，清楚标识市场与区块链
  var ASSET_TYPE_TAG = { stock: '股票', cex: '交易所', onchain: '链上代币' };
  function assetKindLabel(h) {
    var t = ASSET_TYPE_TAG[h.asset_type] || '资产';
    var where = h.chain || (MARKET_NAME[h.market] || h.market || '');
    return t + (where ? ' · ' + where : '');
  }

  // 把一个内部 symbol 归一为统一 hit；onchain 用 chain+address 作身份
  function hitFromSymbol(sym) {
    sym = String(sym || '');
    var code = isOnchain(sym) ? ocCode(sym) : sym.replace(/^.*:/, '');
    var nm = nameOf(sym) || '';
    if (isOnchain(sym)) {
      var meta = (CFG.onchain || {})[sym] || {};
      return makeHit({ symbol: sym, label: code, name: nm,
        asset_type: 'onchain', market: 'onchain',
        chain: meta.chain || chainOfAddr(ocAddr(sym)) || '链上',
        address: ocAddr(sym), query: '' });
    }
    var mk = marketOf(sym);
    return makeHit({ symbol: sym, label: code, name: nm,
      asset_type: mk === 'crypto' ? 'cex' : 'stock', market: mk, query: '' });
  }

  // 本地索引：股票 + CEX + 自选 + 内置链上代币索引，统一建模后按相关性排序
  function buildUnifiedHits(q) {
    var i, j, hits = [];
    for (i = 0; i < MARKETS.length; i++) {
      var mk = MARKETS[i][0], list = (ALL[mk] || []).slice();
      for (j = 0; j < list.length; j++) hits.push(hitFromSymbol(list[j]));
    }
    var watch = CFG.symbols.slice();
    for (j = 0; j < watch.length; j++) hits.push(hitFromSymbol(watch[j]));
    // 内置链上代币索引：名称 / Symbol / 别名可搜，身份 = chain + address
    for (j = 0; j < OC_TOKENS.length; j++) {
      var t = OC_TOKENS[j];
      hits.push(makeHit({ symbol: ocSymbol(t.address), label: t.sym, name: t.name,
        asset_type: 'onchain', market: 'onchain', chain: t.chain,
        address: t.address, aliases: t.aliases || [], query: '' }));
    }
    return mergeHits([hits], q, 60);
  }

  // 兼容旧测试：searchMatches 返回内部 symbol 数组（顺序 = 相关性顺序）
  function searchMatches(q) {
    var s = String(q || '').trim();
    if (!s) return [];
    var hits = buildUnifiedHits(s), out = [], i;
    for (i = 0; i < hits.length; i++) out.push(hits[i].symbol);
    return out;
  }
  // 渲染统一结果行：清楚标识资产类型 / 市场 / 区块链；无数据字段不编造
  function searchResultHTML(symOrHit) {
    var h = (symOrHit && typeof symOrHit === 'object') ? symOrHit : hitFromSymbol(symOrHit);
    var sym = h.symbol, code = h.label || sym.replace(/^.*:/, '');
    var watched = CFG.symbols.indexOf(sym) >= 0;
    var sub = assetKindLabel(h);
    if (h.asset_type === 'onchain' && h.address) sub += ' · ' + shortAddr(h.address);
    var addAttr = h.asset_type === 'onchain' && h.address
      ? 'data-addcontract="' + esc(h.address) + '"'
      : 'data-search-add="' + esc(sym) + '"';
    return '<div class="sresult" data-search-open="' + esc(sym) + '">' +
      '<div class="ico">' + symbolIconHTML(sym, code) + '</div>' +
      '<div class="info"><div><span class="code">' + esc(code) + '</span>' +
      '<span class="name">' + esc(h.name || nameOf(sym)) + '</span></div>' +
      '<div class="sub">' + esc(sub) + ' · 点击进图表</div></div>' +
      '<button class="add" ' + addAttr + ' aria-label="加入自选">' +
      (watched ? '✓' : '＋') + '</button></div>';
  }
  function renderSearchPage(q) {
    SEARCH_QUERY = String(q || '').trim();
    var box = $('searchBox');
    if (box) box.value = SEARCH_QUERY;
    var body = $('searchBody'), html = '', count = 0;
    if (!SEARCH_QUERY) {
      // 聚焦且内容为空 -> 显示历史记录（对象化，单条删除 / 点击直接打开资产）
      var hist = normalizeHistory(CFG.search_history || []);
      count = hist.length;
      for (var i = 0; i < hist.length; i++) {
        var e = hist[i], label = historyLabel(e);
        html += '<div class="hist-row" data-history="' + esc(e.id) + '">' +
          '<span>🕘 ' + esc(label) +
          (e.asset_type ? ' <small>' + esc(assetKindLabel(e)) + '</small>' : '') +
          '</span>' +
          '<button class="del" data-history-del="' + esc(e.id) + '">✕</button></div>';
      }
      if (!count) html = '<div class="empty">还没有搜索记录<br>输入代码、名称或链上合约地址后点 🔍</div>';
      $('searchTitle').textContent = '最近搜索（最多 ' + MAX_SEARCH_HISTORY + ' 条）';
    } else {
      html += contractHitHTML(SEARCH_QUERY);
      var hits = buildUnifiedHits(SEARCH_QUERY);
      count = hits.length;
      for (var j = 0; j < hits.length; j++) html += searchResultHTML(hits[j]);
      if (isContract(SEARCH_QUERY)) count += 1;
      if (!count) html += '<div class="empty">没有匹配的品种<br>可换一个代码或粘贴完整合约地址</div>';
      $('searchTitle').textContent = '搜索结果 · ' + esc(SEARCH_QUERY);
    }
    body.innerHTML = html;
    $('searchCount').textContent = String(count);
  }
  // 只在「确认搜索」时记录：有结果才记，避免防抖脏数据 / 失败或无效输入被永久保存
  function submitSearch(q) {
    q = String(q || '').trim();
    if (q) {
      var hits = buildUnifiedHits(q);
      if (hits.length || isContract(q)) {
        var top = hits.length ? hits[0] : null;
        var entry = top ? {
          query: q, label: top.label || q, symbol: '', name: top.name || '',
          asset_type: top.asset_type || '', market: top.market || '',
          chain: top.chain || '', logo: '', id: ''
        } : { query: q, label: q };
        // 查询历史用 q: 键（不占用具体资产身份，点击时回填重搜）
        if (top) entry.id = 'q:' + normQ(q);
        recordHistory(entry);
      }
    }
    renderSearchPage(q);
  }
  function clearSearchHistory() {
    clearHistory();
    renderSearchPage('');
    toast('搜索历史已清空');
  }
  // 兼容旧入口 / 测试：按查询字符串记录一条历史（内部走对象化模型）
  function recordSearchHistory(q) {
    q = String(q || '').trim();
    if (!q) return;
    recordHistory(q);
  }
  // 点击结果：记录「具体资产」到历史（含 symbol，可直接打开），再进图表
  function openSearchResult(symOrHit) {
    if (!symOrHit) return;
    var h = (symOrHit && typeof symOrHit === 'object') ? symOrHit : hitFromSymbol(symOrHit);
    var sym = h.symbol;
    if (!sym) return;
    recordHistory({ query: SEARCH_QUERY || h.label || h.name,
      label: h.label || h.name, symbol: sym, name: h.name || '',
      asset_type: h.asset_type || '', market: h.market || '',
      chain: h.chain || '', logo: h.logo || '' });
    CHART_SYMBOL = sym; CFG.last_symbol = sym; saveCfg();
    go('chart');
  }

  // ===================== 指标参数面板 =====================
  function indScopeKey(value) {
    // 还没进过图表页时没有当前周期，此时「仅当前周期」回落为全局，
    // 避免把参数写到空字符串键上（等价于误改全局配置）。
    if (!value || value === IND_SCOPE_ALL || !CHART_INTERVAL) return IND_SCOPE_ALL;
    return CHART_INTERVAL;
  }
  function indVal(id, fallback) {
    var e = $(id), v = e ? e.value : '';
    return (v === '' || v === undefined) ? fallback : v;
  }
  function indChk(id, fallback) {
    var e = $(id);
    return (e && typeof e.checked === 'boolean') ? e.checked : fallback;
  }
  function indicatorLineRows(kind, lines, colors) {
    var title = kind === 'ma' ? 'MA 简单移动平均 · 天数' : 'EMA 指数移动平均 · 天数';
    var h = '<div class="ind-card"><h4>' + title + '</h4>';
    for (var i = 0; i < 4; i++) {
      h += '<div class="ind-line">' +
        '<label><input type="checkbox" id="ind' + kind + 'On' + i + '"' +
        (lines[i].enabled ? ' checked' : '') + '>' +
        '<span class="dot" style="background:' + colors[i] + '"></span>第 ' +
        (i + 1) + ' 条</label>' +
        '<input type="number" min="2" max="500" step="1" id="ind' + kind +
        'P' + i + '" value="' + lines[i].period + '"></div>';
    }
    h += '<p class="ind-note">天数按 K 线根数计：日线 20 = 20 天，' +
      '1 小时 20 = 20 根 1 小时 K 线。未勾选的线不绘制。</p></div>';
    return h;
  }
  function showIndicatorSheet() {
    var params = indParams(CHART_INTERVAL);
    var labels = intervalsFor(CHART_SYMBOL || 'BTC'), lab = CHART_INTERVAL;
    for (var i = 0; i < labels.length; i++) {
      if (labels[i][1] === CHART_INTERVAL) lab = labels[i][0];
    }
    var h = '<select id="indScope" class="ind-scope">' +
      '<option value="*">应用到：全部周期（默认）</option>' +
      '<option value="@current">仅当前周期（' + esc(lab) + '）</option></select>' +
      '<p class="ind-note">可为不同 K 线周期分别设天数；未单独设置的字段沿用「全部周期」。</p>';
    h += indicatorLineRows('ma', params.ma, MA_COLORS);
    h += indicatorLineRows('ema', params.ema, EMA_COLORS);
    h += '<div class="ind-card"><h4>BOLL 布林线</h4>' +
      '<div class="ind-line"><label>周期（天数）</label>' +
      '<input type="number" min="2" max="200" id="indBollN" value="' +
      params.boll.period + '"></div>' +
      '<div class="ind-line"><label>标准差倍数 K</label>' +
      '<input type="number" min="0.5" max="5" step="0.1" id="indBollK" value="' +
      params.boll.k + '"></div></div>';
    h += '<div class="ind-card"><h4>MACD 参数</h4>' +
      '<div class="ind-line"><label>快线 EMA</label>' +
      '<input type="number" min="2" max="100" id="indMacdF" value="' +
      params.macd.fast + '"></div>' +
      '<div class="ind-line"><label>慢线 EMA</label>' +
      '<input type="number" min="3" max="200" id="indMacdS" value="' +
      params.macd.slow + '"></div>' +
      '<div class="ind-line"><label>信号线 DEA</label>' +
      '<input type="number" min="2" max="100" id="indMacdG" value="' +
      params.macd.signal + '"></div></div>';
    $('indicatorBody').innerHTML = h;
    openSheet('indicatorSheet');
  }
  function collectIndicatorSheet() {
    var cur = indParams(indScopeKey(indVal('indScope', IND_SCOPE_ALL)));
    var ma = [], ema = [], i;
    for (i = 0; i < 4; i++) {
      ma.push({ period: indInt(indVal('indmaP' + i, cur.ma[i].period), 2, 500,
                               cur.ma[i].period),
                enabled: indChk('indmaOn' + i, cur.ma[i].enabled) });
      ema.push({ period: indInt(indVal('indemaP' + i, cur.ema[i].period), 2, 500,
                                cur.ema[i].period),
                 enabled: indChk('indemaOn' + i, cur.ema[i].enabled) });
    }
    return normInd({
      ma: ma, ema: ema,
      boll: { period: indInt(indVal('indBollN', cur.boll.period), 2, 200,
                             cur.boll.period),
              k: indFloat(indVal('indBollK', cur.boll.k), 0.5, 5, cur.boll.k) },
      macd: { fast: indInt(indVal('indMacdF', cur.macd.fast), 2, 100,
                           cur.macd.fast),
              slow: indInt(indVal('indMacdS', cur.macd.slow), 3, 200,
                           cur.macd.slow),
              signal: indInt(indVal('indMacdG', cur.macd.signal), 2, 100,
                             cur.macd.signal) }
    });
  }
  function applyIndicatorSheet() {
    var scope = indScopeKey(indVal('indScope', IND_SCOPE_ALL));
    writeIndParams(scope, collectIndicatorSheet());
    closeSheets();
    if (PAGE === 'chart') drawChart();
    toast(scope === IND_SCOPE_ALL ? '指标参数已应用到全部周期'
      : '指标参数已应用到 ' + CHART_INTERVAL);
  }
  function resetIndicatorSheet() {
    resetIndParams(indScopeKey(indVal('indScope', IND_SCOPE_ALL)));
    if (PAGE === 'chart') drawChart();
    showIndicatorSheet();
    toast('已恢复该作用范围的默认参数');
  }

  // ===================== 设置 =====================
  var THEMES = ['binance', 'midnight', 'oled', 'light', 'cyber', 'sepia'];
  function syncSettings() {
    $('setIntervalNum').value = String(CFG.interval);
    $('setMarket').value = MARKET;
    $('setTheme').value = THEMES.indexOf(CFG.theme) >= 0 ? CFG.theme : 'binance';
    var so = '';
    for (var i = 0; i < SORT_GROUPS.length; i++) {
      var modes = SORT_GROUPS[i][1];
      for (var j = 0; j < modes.length; j++) {
        so += '<option value="' + modes[j] + '">' +
          esc(SORT_LABEL[modes[j]] || modes[j]) + '</option>';
      }
    }
    $('setSort').innerHTML = so;
    $('setSort').value = CFG.sort_mode;
    $('setPageSize').value = String(CFG.page_size);
    $('setRetry').value = String(CFG.retry_limit || 3);
    $('setLive').checked = CFG.live_feed !== false;
    $('setLiveMs').value = String(CFG.live_interval_ms);
    $('setFontScale').value = String(CFG.chart_font_scale);
    $('setCurrency').checked = CFG.show_currency !== false;
    $('setIcons').checked = CFG.show_icons !== false;
    $('setShowMa').checked = CFG.show_ma !== false;
    $('setShowEma').checked = CFG.show_ema !== false;
    $('setShowBoll').checked = CFG.show_boll !== false;
    $('setShowMacd').checked = CFG.show_macd !== false;
    $('setShowVol').checked = CFG.show_vol !== false;
    $('setCacheKeep').value = String(CFG.cache_keep_days || 7);
    $('setWatchCount').textContent = String(CFG.symbols.length);
    $('setPinCount').textContent = String(CFG.pinned_symbols.length);
    $('setHistoryCount').textContent = String((CFG.search_history || []).length);
    $('appVersion').textContent =
      (window.Native && Native.version ? Native.version() : '1.1.0') + ' · Android';
    var qs = $('quickIntervals').getElementsByTagName('button');
    for (var k = 0; k < qs.length; k++) {
      qs[k].className = Number(qs[k].getAttribute('data-quick')) ===
        Number(CFG.interval) ? 'active' : '';
    }
  }
  function applyTheme() {
    var t = THEMES.indexOf(CFG.theme) >= 0 ? CFG.theme : 'binance';
    document.body.className = (t === 'binance' ? '' : t);
    if (PAGE === 'chart') drawChart();
  }
  function openTextSheet(title, initial, editable, onOk) {
    var el = $('textSheet');
    if (!el) {
      el = document.createElement('div');
      el.id = 'textSheet'; el.className = 'sheet';
      document.body.appendChild(el);
    }
    // index.html 里已经有静态骨架，但没有输入框，这里补齐内容
    if (!$('textSheetInput') || !el.innerHTML) {
      el.innerHTML = '<div class="sheet-head"><b id="textSheetTitle"></b>' +
        '<button data-close="textSheet">✕</button></div>' +
        '<div class="sheet-body"><textarea id="textSheetInput" spellcheck="false"></textarea>' +
        '<button id="textSheetOk" class="big-btn">确定</button></div>';
    }
    $('textSheetTitle').textContent = title;
    var ta = $('textSheetInput');
    ta.value = initial || '';
    ta.readOnly = !editable;
    $('textSheetOk').hidden = !editable;
    $('textSheetOk').onclick = function () { onOk(ta.value); };
    openSheet('textSheet');
  }
  function exportConfig() {
    var json = JSON.stringify(CFG, null, 2);
    if (window.Native && Native.copy) {
      Native.copy(json);
      toast('配置已复制到剪贴板（' + json.length + ' 字节）');
    }
    openTextSheet('导出配置 · 可长按复制', json, false, function () { closeSheets(); });
  }
  function importConfig() {
    var preset = '';
    if (window.Native && Native.paste) { try { preset = Native.paste() || ''; } catch (e) {} }
    openTextSheet('导入配置 · 粘贴桌面端 config.json 或导出内容', preset, true,
      function (text) {
        var obj;
        try { obj = JSON.parse(text); }
        catch (e) { toast('JSON 格式错误，未做任何修改'); return; }
        if (!obj || typeof obj !== 'object') { toast('内容不是配置对象'); return; }
        normalizeImportedConfig(obj);
        var n = 0;
        for (var i = 0; i < IMPORT_KEYS.length; i++) {
          var k = IMPORT_KEYS[i];
          if (obj[k] !== undefined && obj[k] !== null) { CFG[k] = obj[k]; n++; }
        }
        if (!Array.isArray(CFG.symbols)) CFG.symbols = DEFAULT_SYMBOLS.slice();
        if (!Array.isArray(CFG.pinned_symbols)) CFG.pinned_symbols = [];
        if (!CFG.sub_tabs || typeof CFG.sub_tabs !== 'object') {
          CFG.sub_tabs = { crypto: 'watch', cn: 'watch', hk: 'watch', us: 'watch' };
        }
        CFG.interval = clamp(Number(CFG.interval) || 15, 5, 300);
        CFG.page_size = clamp(Number(CFG.page_size) || 60, 20, 300);
        PAGE_SIZE = CFG.page_size;
        MARKET = CFG.last_tab in ALL ? CFG.last_tab : 'crypto';
        saveCfg();
        closeSheets();
        applyTheme();
        go('list');
        restartTimer(false);
        toast('已导入 ' + n + ' 项设置（自选 / 置顶 / 排序已恢复）');
      });
  }

  // ===================== 事件绑定 =====================
  function onListClick(e) {
    var el = e.target;
    while (el && el !== document.body) {
      if (el.getAttribute) {
        if (el.getAttribute('data-goall')) {
          lpConsumeClickSuppress(null);
          CFG.sub_tabs[MARKET] = 'all'; saveCfg();
          LOADED = PAGE_SIZE; renderList(); requestWindow();
          return;
        }
        var addr = el.getAttribute('data-addcontract');
        if (addr) { lpConsumeClickSuppress(null); addContract(addr); return; }
        var sym = el.getAttribute('data-sym');
        if (sym && el.className && String(el.className).indexOf('trow') >= 0) {
          // 长按/右键刚弹过菜单的同一次手势：吞掉这次 click；其它轻触正常打开详情
          if (lpConsumeClickSuppress(sym)) return;
          CHART_SYMBOL = sym; CFG.last_symbol = sym; saveCfg();
          go('chart');            // go 内部会 openChart 一次，避免重复请求 K 线
          return;
        }
      }
      el = el.parentNode;
    }
  }
  function bind() {
    var list = $('list');
    // 长按触发延迟 / 移动容差为可配置常量（LONG_PRESS_MS 500~650、LONG_PRESS_SLOP 8~12dp），
    // 不写死在事件里；双轴判定，滚动/移动/取消/失焦都会取消识别。
    function rowElOf(e) {
      var el = e.target;
      while (el && el !== list && !(el.getAttribute && el.getAttribute('data-sym'))) {
        el = el.parentNode;
      }
      return (el && el !== list) ? el : null;
    }
    list.addEventListener('touchstart', function (e) {
      var el = rowElOf(e);
      var t = e.touches && e.touches[0];
      if (!el || !t) return;
      _suppressClickSym = null;              // 新手势开始，清掉上一次的抑制标记
      lpCancel();
      LP.sym = el.getAttribute('data-sym');
      LP.startX = t.clientX; LP.startY = t.clientY;
      LP.active = true; LP.el = el;
      LP.timer = setTimeout(function () {
        if (LP.active && LP.sym) {
          lpArmClickSuppress(LP.sym);        // 长按已触发：抑制同手势 click
          showRowSheet(LP.sym);
          lpCancel();
        }
      }, LONG_PRESS_MS);
    }, { passive: true });
    list.addEventListener('touchmove', function (e) {
      if (!LP.active) return;
      var t = e.touches && e.touches[0];
      if (!t) return;
      // 双轴移动容差：任一轴超过阈值即视为滚动 / 平移，取消长按
      if (Math.abs(t.clientX - LP.startX) > LONG_PRESS_SLOP ||
          Math.abs(t.clientY - LP.startY) > LONG_PRESS_SLOP) {
        lpCancel();
      }
    }, { passive: true });
    function onTouchEnd() { lpCancel(); }     // 抬手即结束识别（未到延迟不弹菜单）
    list.addEventListener('touchend', onTouchEnd, { passive: true });
    list.addEventListener('touchcancel', onTouchEnd, { passive: true });
    // 页面失焦：清理手势状态，避免幽灵定时器（切后台由统一 visibilitychange 处理）
    window.addEventListener('blur', lpCancel);
    // 桌面式右键（WebView 长按键 / 鼠标右键）：保留原有菜单功能，补 click 抑制
    list.addEventListener('contextmenu', function (e) {
      var el = rowElOf(e);
      if (el) {
        if (e.preventDefault) e.preventDefault();
        lpCancel();
        var sym = el.getAttribute('data-sym');
        lpArmClickSuppress(sym);
        showRowSheet(sym);
      }
    });
    // 图标加载失败退回字徽（error 不冒泡，用捕获阶段接住）
    document.addEventListener('error', function (e) {
      var t = e.target;
      if (t && t.getAttribute && t.getAttribute('data-fallback')) {
        t.style.display = 'none';
        if (t.parentNode) t.parentNode.textContent = t.getAttribute('data-fallback');
      }
    }, true);
    list.addEventListener('click', onListClick);
    list.addEventListener('scroll', function () {
      // 列表开始正常滚动 -> 取消长按识别，绝不弹菜单（惯性滚动同样触发）
      if (LP.active) lpCancel();
      var el = $('list');
      headOnScroll(el.scrollTop);          // v38：顶部工具区随滚动收起 / 展开
      if (el.scrollTop + el.clientHeight > el.scrollHeight - 240) loadMore();
    }, { passive: true });
    $('loadMore').addEventListener('click', loadMore);

    // 输入框聚焦 / 点顶栏 / 尺寸变化时，保证工具区可见且实测高度准确
    $('search').addEventListener('focus', function () { resetHead(); });
    $('topbar').addEventListener('click', function (e) {
      if (!headHidden) return;
      if (e.target && e.target.tagName === 'BUTTON') return; // 不抢返回 / 刷新
      setHeadHidden(false);
    });
    window.addEventListener('resize', measureHead);

    // 市场 / 子页（筛选文本保持不变）
    $('markets').addEventListener('click', function (e) {
      var mk = e.target.getAttribute && e.target.getAttribute('data-market');
      if (!mk) return;
      MARKET = mk; CFG.last_tab = mk; saveCfg();
      headAcc = 0; headLastTop = list.scrollTop || 0;
      LOADED = PAGE_SIZE; renderList(); requestWindow();
    });
    $('subs').addEventListener('click', function (e) {
      var sk = e.target.getAttribute && e.target.getAttribute('data-sub');
      if (!sk) return;
      CFG.sub_tabs[MARKET] = sk; saveCfg();
      headAcc = 0; headLastTop = list.scrollTop || 0;
      LOADED = PAGE_SIZE; renderList(); requestWindow();
    });
    $('search').addEventListener('input', function (e) {
      SEARCH_TEXT = e.target.value || '';
      LOADED = PAGE_SIZE; renderList(); requestWindow();
    });
    $('btnSortDir').addEventListener('click', function () {
      var cur = CFG.sort_mode;
      if (REVERSE_SORT[cur]) { setSort(REVERSE_SORT[cur]); return; }
      CFG.sort_reverse = !CFG.sort_reverse; saveCfg(); renderList();
      toast((CFG.sort_reverse ? '已翻转升/降序' : '恢复原顺序') + ' · ' + SORT_LABEL[cur]);
    });
    $('btnSortMenu').addEventListener('click', showSortSheet);
    $('sortOptions').addEventListener('click', function (e) {
      var m = e.target.getAttribute && e.target.getAttribute('data-sort');
      if (m) { setSort(m); return; }
      if (e.target.getAttribute && e.target.getAttribute('data-flip')) {
        closeSheets();
        $('btnSortDir').click();
      }
    });

    // 行操作 / 详情
    $('rowOptions').addEventListener('click', function (e) {
      var act = e.target.getAttribute && e.target.getAttribute('data-row');
      if (!act) return;
      var sym = $('rowSheet').getAttribute('data-sym');
      if (act === 'pin') setPinned(sym, CFG.pinned_symbols.indexOf(sym) < 0);
      else if (act === 'watch') toggleWatch(sym);
      else if (act === 'detail') { closeSheets(); showDetail(sym); }
      else if (act === 'chart') {
        CHART_SYMBOL = sym; CFG.last_symbol = sym; saveCfg();
        closeSheets(); go('chart');
      }
    });

    // 图表
    $('intervals').addEventListener('click', function (e) {
      var iv = e.target.getAttribute && e.target.getAttribute('data-iv');
      if (!iv) return;
      CHART_INTERVAL = iv; CFG.chart_interval = iv; saveCfg();
      renderIntervals(intervalsFor(CHART_SYMBOL));
      loadChart();
      restartKlineTimer();
    });
    // v38：不再提供 ＋/－ 缩放按钮，缩放完全交给双指捏合（zoomBy 保留给手势）；
    // 「最新」只复位平移，不改缩放倍数，避免误触把用户调好的视野重置掉。
    $('btnReset').addEventListener('click', function () {
      VIEW.pan = 0; saveView(); drawChart();
    });
    $('btnDetail').addEventListener('click', function () { showDetail(CHART_SYMBOL); });

    // 触摸：单指平移 / 双指缩放
    var cv = $('kline'), tStart = null, lastDist = 0;
    cv.addEventListener('touchstart', function (e) {
      if (e.touches.length === 1) {
        tStart = { x: e.touches[0].clientX, pan: VIEW.pan };
      } else if (e.touches.length === 2) {
        lastDist = Math.abs(e.touches[0].clientX - e.touches[1].clientX);
        tStart = null;
      }
      e.preventDefault();
    }, { passive: false });
    cv.addEventListener('touchmove', function (e) {
      if (e.touches.length === 1 && tStart && CANDLES.length) {
        var dx = e.touches[0].clientX - tStart.x;
        var wpx = cv.clientWidth - 54;
        var per = wpx / clamp(VIEW.count, 10, 400);
        VIEW.pan = clampPan(tStart.pan + dx / Math.max(1, per));
        drawChart();
      } else if (e.touches.length === 2) {
        var d = Math.abs(e.touches[0].clientX - e.touches[1].clientX);
        if (lastDist && Math.abs(d - lastDist) > 12) {
          zoomBy(d > lastDist); lastDist = d;
        }
      }
      e.preventDefault();
    }, { passive: false });
    cv.addEventListener('touchend', function () {
      tStart = null; lastDist = 0; saveView();
    }, { passive: true });

    // ---- 设置：刷新间隔 5~300 秒 ----
    function setIntervalSecs(v) {
      CFG.interval = clamp(Number(v) || 15, 5, 300);
      saveCfg(); restartTimer(false); syncSettings();
      toast('刷新间隔已设为 ' + CFG.interval + ' 秒');
    }
    $('setIntervalNum').addEventListener('change', function (e) {
      setIntervalSecs(e.target.value);
    });
    $('quickIntervals').addEventListener('click', function (e) {
      var q = e.target.getAttribute && e.target.getAttribute('data-quick');
      if (q) setIntervalSecs(q);
    });
    $('setMarket').addEventListener('change', function (e) {
      MARKET = e.target.value; CFG.last_tab = MARKET; saveCfg();
      LOADED = PAGE_SIZE; toast('默认市场已设为 ' + MARKET_NAME[MARKET]);
    });
    $('setTheme').addEventListener('change', function (e) {
      CFG.theme = e.target.value; saveCfg(); applyTheme();
    });
    $('setSort').addEventListener('change', function (e) {
      CFG.sort_mode = e.target.value; saveCfg(); renderList();
      toast('默认排序：' + (SORT_LABEL[CFG.sort_mode] || CFG.sort_mode));
    });
    $('setPageSize').addEventListener('change', function (e) {
      CFG.page_size = clamp(Number(e.target.value) || 60, 20, 300);
      PAGE_SIZE = CFG.page_size; LOADED = PAGE_SIZE;
      saveCfg(); renderList(); requestWindow();
    });
    $('setRetry').addEventListener('change', function (e) {
      CFG.retry_limit = clamp(Number(e.target.value) || 3, 1, 5); saveCfg();
      toast('失败重试次数已设为 ' + CFG.retry_limit);
    });
    $('setLive').addEventListener('change', function (e) {
      CFG.live_feed = !!e.target.checked; saveCfg(); restartLiveTimer();
    });
    $('setLiveMs').addEventListener('change', function (e) {
      CFG.live_interval_ms = clamp(Number(e.target.value) || 900, 400, 3000);
      saveCfg(); restartLiveTimer();
    });
    $('setFontScale').addEventListener('change', function (e) {
      CFG.chart_font_scale = clamp(Number(e.target.value) || 120, 100, 160);
      saveCfg(); if (PAGE === 'chart') drawChart();
    });
    $('setCurrency').addEventListener('change', function (e) {
      CFG.show_currency = !!e.target.checked; saveCfg();
      if (PAGE === 'chart') drawChart();
    });
    $('setIcons').addEventListener('change', function (e) {
      CFG.show_icons = !!e.target.checked; saveCfg(); renderList();
      if (PAGE === 'chart') updateChartHead();
    });
    [['setShowMa', 'show_ma'], ['setShowEma', 'show_ema'],
     ['setShowBoll', 'show_boll'], ['setShowMacd', 'show_macd'],
     ['setShowVol', 'show_vol']].forEach(function (pair) {
      $(pair[0]).addEventListener('change', function (e) {
        CFG[pair[1]] = !!e.target.checked; saveCfg();
        if (PAGE === 'chart') drawChart();
      });
    });
    $('setCacheKeep').addEventListener('change', function (e) {
      CFG.cache_keep_days = Number(e.target.value) || 7; saveCfg();
    });
    $('btnClearCache').addEventListener('click', function () {
      writeJSON('ct_tickers', {}); writeJSON('ct_meta', {});
      toast('本地行情缓存已清除（不影响自选与设置）');
    });
    $('btnOpenIndicators').addEventListener('click', showIndicatorSheet);
    $('btnExport').addEventListener('click', exportConfig);
    $('btnImport').addEventListener('click', importConfig);
    // 页面内重复返回按钮已隐藏；保留监听器但统一走系统返回逻辑，避免行为分叉
    $('btnSettingsBack').addEventListener('click', function () { window.__androidBack(); });

    // 顶部 / 底部导航 / 状态
    $('btnRefresh').addEventListener('click', function () {
      _fails = 0; _lastKey = ''; refreshTickers(true); restartTimer(false);
      if (PAGE === 'chart') { updateChartHead(); loadChart(); }
    });
    $('btnRetry').addEventListener('click', function () {
      _fails = 0; _lastKey = ''; refreshTickers(true); restartTimer(false);
    });
    $('btnBack').addEventListener('click', function () { window.__androidBack(); });
    $('bottomNav').addEventListener('click', function (e) {
      var el = e.target;
      while (el && !el.getAttribute('data-tab')) el = el.parentNode;
      // 底部导航 = 顶层 tab 切换：清空下钻栈，回到根层级（不显示返回箭头）
      if (el) go(el.getAttribute('data-tab'), { resetStack: true });
    });

    // ---- 搜索独立页 / 历史 ----
    function openSearchPage(q) {
      $('searchBox').value = q || '';
      go('search');
    }
    $('btnSearch').addEventListener('click', function () {
      openSearchPage(($('search').value || '').trim());
    });
    $('search').addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.keyCode === 13) {
        var q = ($('search').value || '').trim();
        openSearchPage(q);
        if (q) submitSearch(q);
      }
    });
    $('btnSearchGo').addEventListener('click', function () {
      submitSearch($('searchBox').value);
    });
    $('searchBox').addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.keyCode === 13) submitSearch($('searchBox').value);
    });
    $('searchBox').addEventListener('input', function (e) {
      renderSearchPage(e.target.value || '');
    });
    $('btnClearHistory').addEventListener('click', clearSearchHistory);
    $('btnSearchBack').addEventListener('click', function () { window.__androidBack(); });
    $('searchBody').addEventListener('click', function (e) {
      var el = e.target, attr = function (k) {
        return el.getAttribute && el.getAttribute(k);
      };
      var del = attr('data-history-del');
      if (del) {
        deleteHistory(del);          // 按资产唯一 id 删除单条（兼容旧字符串键）
        renderSearchPage(SEARCH_QUERY); return;
      }
      var add = attr('data-search-add');
      if (add) {
        toggleWatch(add); renderSearchPage(SEARCH_QUERY); return;
      }
      var addr = attr('data-addcontract');
      if (addr) {
        var job = addContract(addr);
        if (job && job.then) job.then(function () { renderSearchPage(SEARCH_QUERY); });
        else renderSearchPage(SEARCH_QUERY);
        return;
      }
      var hist = attr('data-history');
      if (hist) {
        // 点击历史：有明确资产 symbol 就直接打开图表；否则回填查询词重搜
        var entries = normalizeHistory(CFG.search_history || []);
        var picked = null;
        for (var hi = 0; hi < entries.length; hi++) {
          if (entries[hi].id === hist) { picked = entries[hi]; break; }
        }
        var sym = historySymbol(picked);
        if (sym) { openSearchResult(hitFromSymbol(sym)); return; }
        var q = historyQuery(picked || hist);
        $('searchBox').value = q; submitSearch(q); return;
      }
      var open = attr('data-search-open');
      if (open) { openSearchResult(open); return; }
      // 点在结果行空白处：冒泡到父节点再取一次
      var p = el.parentNode;
      while (p && p.getAttribute) {
        var o2 = p.getAttribute('data-search-open');
        if (o2) { openSearchResult(o2); return; }
        p = p.parentNode;
      }
    });

    // ---- 指标参数面板 ----
    $('btnIndicators').addEventListener('click', showIndicatorSheet);
    $('btnIndApply').addEventListener('click', applyIndicatorSheet);
    $('btnIndReset').addEventListener('click', resetIndicatorSheet);

    // 弹出层关闭
    document.addEventListener('click', function (e) {
      var c = e.target.getAttribute && e.target.getAttribute('data-close');
      if (c) closeSheets();
    });
    $('scrim').addEventListener('click', closeSheets);
    window.addEventListener('resize', function () { if (PAGE === 'chart') drawChart(); });
  }

  // 与桌面 _clamp_pan 同规则：可回看到最早一批，也可继续右移留出空白。
  // 旧版把 pan 钳死在 [0, total-20]，所以「拖到头就卡住、右侧不能留白」。
  function clampPan(v) {
    var total = CANDLES.length || 0;
    var count = clamp(Math.round(VIEW.count), 10, 400);
    var maxBack = Math.max(0, total - 8);
    var maxForward = Math.max(8, count * 0.8);
    return clamp(v, -maxForward, maxBack);
  }
  function saveView() {
    VIEW.pan = clampPan(VIEW.pan);
    CFG.chart_view_count = VIEW.count;
    CFG.chart_view_pan = VIEW.pan;
    saveCfg();
  }
  function zoomBy(zoomIn) {
    if (!CANDLES.length) return;
    var old = clamp(VIEW.count, 10, 400);
    var next = clamp(Math.round(old * (zoomIn ? 0.8 : 1.25)), 20, 400);
    if (next === old) return;
    // 以当前视口中心为锚点缩放，不强制贴到最右侧
    var end = CANDLES.length - VIEW.pan;
    var center = end - old / 2;
    VIEW.count = next;
    VIEW.pan = clampPan(CANDLES.length - (center + next / 2));
    saveView();
    drawChart();
  }

  // 系统返回键 / 返回手势：
  //   1. 有弹出层 -> 只关闭弹窗（弹窗关闭 != 页面返回，二者严格区分）
  //   2. 有下钻父页 -> 返回上一级（优先于直接回首页）
  //   3. 非根页且无父页 -> 回首页
  //   4. 根页(首页) -> 交还 Native 退出应用（不在根页显示无意义返回按钮）
  window.__androidBack = function () {
    if (openSheetId) { closeSheets(); return; }
    var prev = NAV_STACK.length ? NAV_STACK.pop() : null;
    if (prev && prev !== PAGE) { go(prev, { fromBack: true }); return; }
    if (PAGE !== 'list') { go('list', { fromBack: true, resetStack: true }); return; }
    if (window.Native && Native.finish) Native.finish();
  };

  // ===================== 启动 =====================
  function pruneCache() {
    var days = clamp(Number(CFG.cache_keep_days) || 7, 1, 30);
    if (!TICKER_ASOF || nowSec() - TICKER_ASOF <= days * 86400) return;
    for (var k in TICKERS) {
      if (Object.prototype.hasOwnProperty.call(TICKERS, k)) delete TICKERS[k];
    }
    TICKER_ASOF = 0;
    writeJSON('ct_tickers', {});
    store.set('ct_tickers_asof', '0');
    // K 线同样受保留期约束（此前只清 TICKERS，缓存会悄悄陈旧）
    KLINE_CACHE = {};
    writeJSON('ct_kline', KLINE_CACHE);
    // 链上 K 线 / 池缓存也一并清理，保留版本字段，避免陈旧池指向已迁移交易池
    OC_KLINE_CACHE = { v: OC_KLINE_SCHEMA };
    OC_POOL_CACHE = {};
    writeJSON('ct_oc_kline', OC_KLINE_CACHE);
    writeJSON('ct_oc_pools', OC_POOL_CACHE);
  }
  function boot() {
    applyTheme();
    bind();
    pruneCache();
    // 恢复链上合约品种：名称 / 代码 / 上次真实报价（断网也能显示缓存价）
    for (var os in CFG.onchain) {
      if (!Object.prototype.hasOwnProperty.call(CFG.onchain, os)) continue;
      var om = CFG.onchain[os] || {};
      NAME_OF[os] = om.name || om.code || shortAddr(ocAddr(os));
      if (ONCHAIN_Q[os]) applyOnchainQuote(os, ONCHAIN_Q[os]);
      else if (!META[os]) META[os] = { no_kline: true,
                                       source: om.source || '链上合约地址' };
    }
    ensureListedMeta();
    computeOrder();
    renderList();
    setNav('list');
    setTitle('行情');
    syncBackButton();   // 首页为根层级：隐藏返回箭头、隐藏页内重复返回按钮
    setStatus(TICKER_ASOF
      ? '● 上次真实快照 · ' + fmtTime(TICKER_ASOF) + ' · 正在刷新…'
      : '● 连接中 · 来源 ' + SOURCE_TEXT, false);
    refreshTickers(false);
    restartTimer(false);
    measureHead();   // v38：DOM 填充完毕后量一次真实高度，供折叠动画用
  }
  // 从后台切回：立即按当前周期边界校验一次，避免跨日后仍显示旧快照。
  // 切到后台时同时取消未完成的长按识别，避免幽灵定时器弹菜单。
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState !== 'visible') { lpCancel(); return; }
    if (PAGE === 'chart') {
      loadChart(true);
      restartLiveTimer();
      restartKlineTimer();
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else boot();

  // 供自动化测试 / 调试读取内部解析结果（不改变任何界面行为）
  window.__CT_DEBUG = {
    cfg: CFG, all: ALL, tickers: TICKERS, meta: META,
    parseTencent: parseTencent, parseBinance: parseBinance,
    parseBinanceKlines: parseBinanceKlines, parseTencentKlines: parseTencentKlines,
    parseSinaRows: parseSinaRows, aggregateKlines: aggregate,
    corporateActions: CORPORATE_ACTIONS, detectUnadjustedEvents: detectUnadjustedEvents,
    detectSplitActionsFromPrices: detectSplitActionsFromPrices, mergeActions: mergeActions,
    applyAdjustment: applyAdjustment, adjustVolumeOnly: adjustVolumeOnly,
    applyCoinLore: applyCoinLore, computeOrder: computeOrder,
    detailHTML: detailHTML, setSort: setSort, setPinned: setPinned,
    rankValue: rankValue, http: http, refreshTickers: refreshTickers,
    go: go, drawChart: drawChart, zoomBy: zoomBy,
    showSortSheet: showSortSheet, showRowSheet: showRowSheet,
    showDetail: showDetail, exportConfig: exportConfig, importConfig: importConfig,
    isOnchain: isOnchain, isContract: isContract, ocSymbol: ocSymbol,
    ocCode: ocCode, ocAddr: ocAddr, chainOfAddr: chainOfAddr,
    parseRugcheck: parseRugcheck, addContract: addContract,
    refreshOnchain: refreshOnchain, applyOnchainQuote: applyOnchainQuote,
    onchainQuotes: ONCHAIN_Q, contractHitHTML: contractHitHTML,
    rowHTML: rowHTML, renderList: renderList, scheduleRender: scheduleRender,
    loadChart: loadChart, applyTickers: applyTickers, quoteIsStale: _quoteIsStale,
    updateChartHead: updateChartHead, intervalsFor: intervalsFor,
    // 链上真实历史 K 线（DEX OHLCV）
    ocNormalize: ocNormalize, fetchOnchainCandles: fetchOnchainCandles,
    ocFetchGecko: ocFetchGecko, ocFetchCoingecko: ocFetchCoingecko,
    ocCacheKey: ocCacheKey, defaultInterval: defaultInterval,
    OC_STATUS: OC_STATUS, OC_KLINE_CACHE: OC_KLINE_CACHE,
    // v1.6 K 线时间同步：周期边界 / 预览 / 自动刷新 / 缓存
    klineBucketStart: klineBucketStart, klineNextBucket: klineNextBucket,
    klineLabel: klineLabel, klineOffsetMs: klineOffsetMs,
    refreshSeconds: refreshSeconds, klinePreviewFields: klinePreviewFields,
    applyChartQuote: applyChartQuote, mergeCandles: mergeCandles,
    klineCacheGet: klineCacheGet, klineCacheFresh: klineCacheFresh,
    KLINE_CACHE: KLINE_CACHE,
    restartKlineTimer: restartKlineTimer, chartAnchorTs: chartAnchorTs,
    setNowMs: function (ms) { __nowMsOverride = (ms === null ? null : Number(ms)); },
    // v34：指标参数 / 搜索独立页 / 自由平移 / 图标
    normInd: normInd, indParams: indParams, writeIndParams: writeIndParams,
    resetIndParams: resetIndParams, maSeries: maSeries, emaSeries: emaSeries,
    bollSeries: bollSeries, macdSeries: macdSeries, indLines: indLines,
    enabledIndPeriods: enabledIndPeriods, showIndicatorSheet: showIndicatorSheet,
    collectIndicatorSheet: collectIndicatorSheet,
    applyIndicatorSheet: applyIndicatorSheet, resetIndicatorSheet: resetIndicatorSheet,
    renderSearchPage: renderSearchPage, submitSearch: submitSearch,
    recordSearchHistory: recordSearchHistory, clearSearchHistory: clearSearchHistory,
    searchMatches: searchMatches, searchResultHTML: searchResultHTML,
    openSearchResult: openSearchResult, symbolIconHTML: symbolIconHTML,
    // 统一资产模型 / 搜索历史（对象化）
    chainId: chainId, assetId: assetId, makeHit: makeHit,
    relevance: relevance, mergeHits: mergeHits, buildUnifiedHits: buildUnifiedHits,
    hitFromSymbol: hitFromSymbol, assetKindLabel: assetKindLabel,
    normalizeHistory: normalizeHistory, recordHistory: recordHistory,
    deleteHistory: deleteHistory, clearHistory: clearHistory,
    historyQuery: historyQuery, historySymbol: historySymbol,
    historyLabel: historyLabel, OC_TOKENS: OC_TOKENS,
    MAX_SEARCH_HISTORY: MAX_SEARCH_HISTORY,
    clampPan: clampPan, syncSettings: syncSettings, applyTheme: applyTheme,
    // v35：批量行情失败拆分降级（含非法交易对不再让整批空白）
    binanceBatch: binanceBatch, fetchTickers: fetchTickers,
    pruneCache: pruneCache, restartLiveTimer: restartLiveTimer,
    unitPrefix: unitPrefix, pageTitle: pageTitle,
    setScope: function (v) { $('indScope').value = v; },
    setIndInput: function (id, value, checked) {
      var e = $(id); e.value = value;
      if (checked !== undefined) e.checked = checked;
    },
    setIntervalKey: function (k) { CHART_INTERVAL = k; },
    setSearch: function (q) { SEARCH_TEXT = String(q || ''); renderList(); },
    setChartSymbol: function (s) { CHART_SYMBOL = s; },
    setPage: function (p) { PAGE = p; },
    setCandles: function (rows) { CANDLES = rows; },
    // K 线竞态回归：只读观测点（不改变行为）
    candles: function () { return CANDLES; },
    loadSeq: function () { return chartLoadSeq; },
    symbol: function () { return CHART_SYMBOL; },
    interval: function () { return CHART_INTERVAL; },
    view: function () { return VIEW; },
    page: function () { return PAGE; },
    sheet: function () { return openSheetId; },
    // v36：链上真实图表 + 股票市场自选修复
    ocSeries: ocSeries, recordOcSample: recordOcSample,
    drawOnchainChart: drawOnchainChart, ocHist: OC_HIST,
    watchList: watchList, baseList: baseList,
    // v37：发展历程 / 品种档案 / 行情里程碑
    timelineHTML: timelineHTML, archiveHTML: archiveHTML,
    milestoneHTML: milestoneHTML, extraDetailHTML: extraDetailHTML,
    computeMilestones: computeMilestones, loadMilestones: loadMilestones,
    milestones: MILESTONES, dbMeta: DB_META,
    timelineDB: TL_DB, archiveDB: ARC_DB,
    // v38：列表顶部折叠状态机（供离线回归驱动滚动）
    headOnScroll: headOnScroll, setHeadHidden: setHeadHidden,
    measureHead: measureHead, resetHead: resetHead,
    headState: function () {
      return { hidden: headHidden, height: headH,
               acc: headAcc, last: headLastTop };
    },
    back: function () { return window.__androidBack(); },
    // 返回按钮层级 / 导航栈（只读观测点 + 可直接 go 带 opts）
    syncBackButton: syncBackButton, closeSheets: closeSheets,
    navStack: function () { return NAV_STACK.slice(); },
    navCanBack: navCanBack,
    goWith: function (p, o) { return go(p, o || {}); },
    backBtnHidden: function () { return $('btnBack').hidden; },
    // 长按手势：可配置参数 + 只读状态 + 事件注入口
    lpConfig: function (ms, slop) {
      if (ms !== undefined) LONG_PRESS_MS = clamp(Number(ms) || LONG_PRESS_MS, 300, 1500);
      if (slop !== undefined) LONG_PRESS_SLOP = clamp(Number(slop) || LONG_PRESS_SLOP, 4, 30);
      return { ms: LONG_PRESS_MS, slop: LONG_PRESS_SLOP };
    },
    lpState: function () {
      return { active: LP.active, sym: LP.sym, hasTimer: !!LP.timer,
               suppressSym: _suppressClickSym };
    },
    lpCancel: lpCancel,
    lpArmSuppress: lpArmClickSuppress,
    lpConsumeSuppress: lpConsumeClickSuppress
  };
})();
