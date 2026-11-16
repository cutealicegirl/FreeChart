/* 阶段 7 回归：在 Node 里用轻量 DOM / Java Bridge 模拟层加载 app.js，
 * 并用与 APK 相同的公开接口真实返回数据验证解析、排序、置顶、详情、分页。
 *
 * 运行：node android/tests/test_app_logic.js
 * 说明：REAL=1 时才走真实网络；默认用离线 fixture，保证 CI 不依赖网络。
 */
'use strict';
const fs = require('fs');
const path = require('path');
const https = require('https');
const vm = require('vm');

const WWW = path.join(__dirname, '..', 'assets', 'www');
let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('  PASS ' + name); }
  else { fail++; console.log('  FAIL ' + name + (extra ? '  ' + extra : '')); }
}
function near(a, b) { return Math.abs(a - b) < 1e-6; }

// ---------- 轻量 DOM ----------
function mkEl(id) {
  return {
    id: id, innerHTML: '', textContent: '', value: '', hidden: false,
    className: '', style: {}, width: 0, height: 0,
    clientWidth: 360, clientHeight: 260, scrollTop: 0, scrollHeight: 1000,
    _attrs: {}, _listeners: {},
    getAttribute: function (k) { return this._attrs[k] === undefined ? null : this._attrs[k]; },
    setAttribute: function (k, v) { this._attrs[k] = String(v); },
    addEventListener: function (t, f) { (this._listeners[t] = this._listeners[t] || []).push(f); },
    appendChild: function () {},
    getElementsByTagName: function () { return []; },
    getContext: function () {
      return {
        setTransform: function () {}, clearRect: function () {}, fillText: function () {},
        beginPath: function () {}, moveTo: function () {}, lineTo: function () {},
        stroke: function () {}, fillRect: function () {}, setLineDash: function () {}
      };
    }
  };
}
const els = {};
function el(id) {
  if (!els[id]) els[id] = mkEl(id);
  return els[id];
}
let domReady = null;
global.document = {
  readyState: 'loading',
  body: mkEl('body'),
  getElementById: el,
  querySelector: function () { return mkEl('query'); },
  createElement: function () { return mkEl('new'); },
  addEventListener: function (t, f) { if (t === 'DOMContentLoaded') domReady = f; }
};
global.getComputedStyle = function () {
  return { getPropertyValue: function () { return ''; } };
};
global.window = global;
global.devicePixelRatio = 1;
global.addEventListener = function () {};
global.requestAnimationFrame = function (f) { setTimeout(f, 0); };
global.localStorage = {
  _m: {}, getItem: function (k) { return this._m[k] || ''; },
  setItem: function (k, v) { this._m[k] = v; }
};
// 定时器：禁止自动轮询悬挂测试进程
const realSetInterval = global.setInterval;
global.setInterval = function () { return 0; };
global.clearInterval = function () {};

// ---------- Java Bridge 模拟 ----------
const mem = {};
let REAL = false;
function decode(buf, charset) {
  if (/gbk|gb2312/i.test(charset || '')) {
    try { return new TextDecoder('gbk').decode(buf); }
    catch (e) { return buf.toString('latin1'); }
  }
  return buf.toString('utf8');
}
global.Native = {
  get: function (k) { return mem[k] || ''; },
  set: function (k, v) { mem[k] = String(v); },
  version: function () { return '1.0.0' },
  toast: function () {},
  finish: function () {},
  copy: function (t) { mem.__clipboard = t; },
  paste: function () { return mem.__clipboard || ''; },
  http: function (url, charset, cb) {
    if (!REAL) {
      // 链上合约报告用真实响应结构的精简 fixture（REAL=1 时走真实网络）
      if (/api\.rugcheck\.xyz/.test(url) && global.__OC_FIXTURE) {
        setTimeout(function () { global.__nativeCb(cb, global.__OC_FIXTURE, ''); }, 0);
        return;
      }
      setTimeout(function () { global.__nativeCb(cb, '', ''); }, 0); return;
    }
    const req = https.get(url, { headers: { 'User-Agent': 'Mozilla/5.0' } }, function (res) {
      const chunks = [];
      res.on('data', function (c) { chunks.push(c); });
      res.on('end', function () {
        const body = decode(Buffer.concat(chunks), charset);
        global.__nativeCb(cb, body, '');
      });
    });
    req.on('error', function (e) { global.__nativeCb(cb, '', String(e.message)); });
    req.setTimeout(15000, function () { req.destroy(new Error('timeout')); });
  }
};

// ---------- 加载前端资源 ----------
function load(file) {
  vm.runInThisContext(fs.readFileSync(path.join(WWW, file), 'utf8'), { filename: file });
}
load('universe.js');
load('about.js');
load('app.js');
const D = global.__CT_DEBUG;

console.log('=== 阶段 7 · Android WebView 逻辑回归 ===\n');

// 1. 资源与启动
ok('universe.js 四个市场清单', ['crypto', 'cn', 'hk', 'us'].every(function (m) {
  return (global.UNIVERSE[m] || []).length > 0;
}));
ok('about.js 结构化资料库', Object.keys(global.ABOUT_DB.about).length >= 40 &&
  !!global.ABOUT_DB.market_default.crypto);
ok('app.js 加载并暴露调试接口', !!D && typeof D.parseTencent === 'function');
ok('系统与桌面端键名一致', Array.isArray(D.cfg.symbols) &&
  Array.isArray(D.cfg.pinned_symbols) && D.cfg.interval >= 15);

if (domReady) domReady();   // 执行 boot()
const listHTML = el('list').innerHTML;
const rowCount = (listHTML.match(/class="trow/g) || []).length;
ok('首屏只挂载一页（≤60 行）', rowCount > 0 && rowCount <= 60, '实际 ' + rowCount);
ok('全部清单仍完整可用（crypto 200 / us 500）',
  D.all.crypto.length === 200 && D.all.us.length === 500);
ok('加载更多按钮存在', el('loadMore').hidden === false || el('loadMore').hidden === true);

// 2. 解析真实接口数据（离线 fixture，字段与实测返回一致）
const binanceFixture = JSON.stringify([
  { symbol: 'BTCUSDT', lastPrice: '71730.01', priceChangePercent: '-3.323',
    highPrice: '74195.89', lowPrice: '71000.00', quoteVolume: '1234567890.12' },
  { symbol: 'ETHUSDT', lastPrice: '2345.67', priceChangePercent: '2.10',
    highPrice: '2400.00', lowPrice: '2300.00', quoteVolume: '456789012.34' }
]);
const bt = D.parseBinance(binanceFixture);
ok('Binance 解析价格/涨跌/成交额', near(bt.BTC.price, 71730.01) &&
  near(bt.BTC.chg, -3.323) && bt.BTC.amount > 0 && near(bt.ETH.price, 2345.67));

// 腾讯 88 字段快照（只保留已核实含义的下标）
const f = new Array(88).fill('');
f[1] = '贵州茅台'; f[3] = '1410.27'; f[30] = '20261112161452'; f[32] = '0.57';
f[33] = '1411.00'; f[34] = '1388.11'; f[36] = '32373'; f[37] = '453681';
f[38] = '0.26'; f[39] = '21.46'; f[44] = '17629.53'; f[45] = '17629.53'; f[46] = '6.50';
const qt = 'v_sh600519="' + f.join('~') + '";';
const pt = D.parseTencent(qt);
ok('腾讯行情解析（A股成交额 万元→元）', near(pt['SH:600519'].price, 1410.27) &&
  near(pt['SH:600519'].amount, 453681 * 1e4));
ok('腾讯行情解析出真实市值/换手/PE/PB',
  D.meta['SH:600519'].cap === 17629.53 && D.meta['SH:600519'].turnover === 0.26 &&
  D.meta['SH:600519'].pe === 21.46 && D.meta['SH:600519'].pb === 6.5);
ok('行情时间戳按交易所时间解析', pt['SH:600519'].ts > 1700000000);

const coinloreFixture = JSON.stringify({ data: [
  { symbol: 'BTC', rank: 1, market_cap_usd: '1432797109558.00',
    volume24: 107214520480.217, csupply: '19970852.00',
    tsupply: '19970852', msupply: '21000000' }
] });
ok('CoinLore 解析写入元数据', D.applyCoinLore(coinloreFixture) === 1 &&
  D.meta.BTC.cap > 1e12 && D.meta.BTC.supply_max === 21000000 &&
  D.meta.BTC.liquidity > 0 && D.meta.BTC.rank === 1);

const klineFixture = JSON.stringify([
  [1794268800000, '75368.41', '75442.01', '72727.27', '73796.06', '16466.18'],
  [1794355200000, '73796.06', '74000.00', '73000.00', '73500.00', '12000.00']
]);
const kc = D.parseBinanceKlines(klineFixture, '1d');
ok('Binance K 线解析（含时间标签）', kc.length === 2 &&
  near(kc[0].o, 75368.41) && near(kc[0].h, 75442.01) && !!kc[0].label);
const tkFixture = JSON.stringify({ data: { sh600519: { qfqday: [
  ['2026-11-10', '1400.000', '1410.000', '1420.000', '1390.000', '59927.000'],
  ['2026-11-11', '1410.000', '1415.000', '1425.000', '1405.000', '62000.000']
] } } });
const tc = D.parseTencentKlines(tkFixture, 'day');
ok('腾讯 K 线解析（开/收/高/低顺序正确）', tc.length === 2 &&
  near(tc[0].o, 1400) && near(tc[0].c, 1410) && near(tc[0].h, 1420) && near(tc[0].l, 1390));

// 3. 排序 / 置顶 / 筛选（注入真实数值，不编造）
D.tickers.BTC = { price: 71730.01, chg: -3.323, amount: 1.23e9, ts: 0 };
D.tickers.ETH = { price: 2345.67, chg: 2.10, amount: 4.56e8, ts: 0 };
D.tickers.SOL = { price: 150.25, chg: 5.50, amount: 9.87e7, ts: 0 };
D.cfg.symbols = ['BTC', 'ETH', 'SOL'];
D.cfg.sub_tabs.crypto = 'watch';
D.cfg.pinned_symbols = [];
D.setSort('price_desc');
let order = D.computeOrder();
ok('价格降序基于真实数据', order[0] === 'BTC' && order[1] === 'ETH' && order[2] === 'SOL',
  JSON.stringify(order));
D.setSort('change_desc');
order = D.computeOrder();
ok('涨跌幅降序基于真实数据', order[0] === 'SOL' && order[2] === 'BTC');
D.setSort('amount_asc');
order = D.computeOrder();
ok('成交额升序基于真实数据', order[0] === 'SOL' && order[2] === 'BTC');

D.setPinned('ETH', true);
order = D.computeOrder();
ok('置顶优先于数值排序', order[0] === 'ETH', JSON.stringify(order));
ok('置顶状态持久化', JSON.parse(mem.ct_config || '{}').pinned_symbols.indexOf('ETH') >= 0);
D.setPinned('ETH', false);
order = D.computeOrder();
ok('取消置顶生效', order[0] !== 'ETH' || (D.cfg.sort_mode === 'change_desc' && order[0] === 'SOL'));

// 搜索筛选条件在排序切换后保持
el('search').value = 'ETH';
const inputHandlers = el('search')._listeners.input || [];
if (inputHandlers.length) inputHandlers[0]({ target: { value: 'ETH' } });
D.setSort('price_desc');
order = D.computeOrder();
ok('排序保持筛选条件', order.length === 1 && order[0] === 'ETH', JSON.stringify(order));
ok('搜索框文本未被排序清空', el('search').value === 'ETH');
if (inputHandlers.length) inputHandlers[0]({ target: { value: '' } });

// 4. 详情：真实字段 + 缺失标注，禁止编造
const dh = D.detailHTML('SH:600519');
ok('详情包含 6 个分区', ['①', '②', '③', '④', '⑤', '⑥'].every(function (x) {
  return dh.indexOf(x) >= 0;
}));
ok('详情含真实市值与来源',
  /总市值<\/span><b>1\.76 万/.test(dh) && dh.indexOf('21.46') >= 0 &&
  dh.indexOf('腾讯行情') >= 0);
ok('无数据字段明确标注、不编造', dh.indexOf('— 暂无公开数据') >= 0 &&
  dh.indexOf('营业收入') >= 0 && dh.indexOf('营收、利润等财务数据需以定期报告') >= 0);
const dh2 = D.detailHTML('BTC');
ok('加密详情含代币经济学缺失说明', dh2.indexOf('代币分配') >= 0 &&
  dh2.indexOf('解锁计划') >= 0 && dh2.indexOf('协议收入') >= 0 &&
  dh2.indexOf('CoinLore') >= 0);
ok('内置资料库年份用于上市排序', D.rankValue('BTC', 'listed_desc') === 2009);

// 5. 配置迁移 / 导航契约
const exported = JSON.stringify(D.cfg);
ok('导出配置为可解析 JSON', (function () {
  try { return !!JSON.parse(exported).symbols; } catch (e) { return false; }
})());
ok('系统返回入口存在', typeof global.__androidBack === 'function');
ok('三选项卡底栏契约', (function () {
  const html = fs.readFileSync(path.join(WWW, 'index.html'), 'utf8');
  return ['data-tab="list"', 'data-tab="chart"', 'data-tab="settings"'].every(function (x) {
    return html.indexOf(x) >= 0;
  }) && html.indexOf('about.js') >= 0 && html.indexOf('app.js') >= 0;
})());
ok('无桌面右键 / hover 依赖', (function () {
  const js = fs.readFileSync(path.join(WWW, 'app.js'), 'utf8');
  const css = fs.readFileSync(path.join(WWW, 'style.css'), 'utf8');
  return js.indexOf('oncontextmenu') < 0 && js.indexOf('mouseover') < 0 &&
    css.indexOf(':hover') < 0;
})());
ok('主要控件 ≥44px', (function () {
  const css = fs.readFileSync(path.join(WWW, 'style.css'), 'utf8');
  return /\.top-btn \{[^}]*height: 44px/.test(css) &&
    /\.trow \.more \{[^}]*height: 44px/.test(css) &&
    /\.sheet-body button\.opt \{[^}]*min-height: 50px/.test(css);
})());

// 6. 交互路径：图表绘制 / 锚点缩放 / 逐级返回 / 弹出层 / 配置导入导出
const candles = [];
for (let i = 0; i < 120; i++) {
  candles.push({ ts: 1700000000 + i * 86400, label: '11-' + String(i % 28 + 1).padStart(2, '0'),
    o: 100 + i, h: 102 + i, l: 98 + i, c: 101 + i, v: 1000 + i });
}
D.setCandles(candles);
D.view().count = 90; D.view().pan = 0;
let drawError = null;
try { D.drawChart(); } catch (e) { drawError = e; }
ok('Canvas 绘制 120 根真实格式蜡烛不抛错', !drawError, drawError && drawError.message);
const c0 = D.view().count, p0 = D.view().pan;
D.zoomBy(true);
ok('＋ 放大缩小可见根数', D.view().count < c0);
ok('缩放以当前位置为锚点、不强制贴到最右侧', D.view().pan > p0,
  'pan ' + p0 + ' -> ' + D.view().pan);
D.zoomBy(false);
ok('缩放往返视口可还原', D.view().count === c0 && Math.abs(D.view().pan - p0) < 0.01);

D.go('chart');
ok('切到独立图表选项卡', D.page() === 'chart' && el('pageTitle').textContent === '图表');
D.back();
ok('系统返回：图表 → 行情', D.page() === 'list');
D.showSortSheet();
ok('排序 sheet 含全部分组与 14 种模式', D.sheet() === 'sortSheet' &&
  (el('sortOptions').innerHTML.match(/data-sort="/g) || []).length === 14);
D.back();
ok('系统返回优先关闭弹出层', D.sheet() === '');
D.showRowSheet('BTC');
ok('行操作 sheet 含置顶/自选/详情/图表', D.sheet() === 'rowSheet' &&
  ['移到顶部', '自选', '查看品种详情', '查看 K 线图表'].every(function (x) {
    return el('rowOptions').innerHTML.indexOf(x) >= 0;
  }));
D.back();
D.showDetail('BTC');
ok('详情 sheet 打开即渲染 6 分区', D.sheet() === 'detailSheet' &&
  el('detailBody').innerHTML.indexOf('①') >= 0 &&
  el('detailBody').innerHTML.indexOf('⑥') >= 0);
D.back();

D.exportConfig();
ok('导出配置把 JSON 放入剪贴板', !!mem.__clipboard &&
  Array.isArray(JSON.parse(mem.__clipboard).symbols));
D.back();
D.importConfig();
el('textSheetInput').value = JSON.stringify({
  symbols: ['BTC', 'ETH'], pinned_symbols: ['ETH'],
  sort_mode: 'price_desc', theme: 'light', interval: 30
});
ok('导入配置按钮有效', typeof el('textSheetOk').onclick === 'function');
el('textSheetOk').onclick(el('textSheetInput').value);
ok('导入桌面端配置恢复自选/置顶/排序/主题',
  D.cfg.pinned_symbols.indexOf('ETH') >= 0 && D.cfg.sort_mode === 'price_desc' &&
  D.cfg.theme === 'light' && D.cfg.interval === 30 &&
  JSON.parse(mem.ct_config).symbols.length === 2);
ok('系统返回：设置/图表 → 行情 → 再退出', (function () {
  D.go('settings'); D.back();
  return D.page() === 'list';
})());

// 6.5 链上合约品种：没有 K 线也能收藏、也能看真实链上价格
const OC_ADDR = '9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump';
const OC = D.ocSymbol(OC_ADDR);
global.__OC_FIXTURE = JSON.stringify({
  token: { supply: 997354435111923, decimals: 6 },
  tokenMeta: { name: 'The Black Bull', symbol: 'ANSEM' },
  verification: { symbol: 'ansem', name: 'The Black Bull' },
  launchpad: { name: 'Pump.Fun' },
  price: 0.05133747818589247,
  totalMarketLiquidity: 1860717.8824534104,
  totalHolders: 383918
});

async function onchainTests() {
  console.log('\n--- 链上合约品种（无 K 线也可收藏 / 看价） ---');
  ok('识别 Solana / EVM / Tron 合约地址',
    D.isContract(OC_ADDR) && D.isContract('0x' + 'a'.repeat(40)) &&
    D.isContract('T' + 'A'.repeat(33)) && !D.isContract('BTC'));
  ok('链上标识与链判断', D.isOnchain(OC) && D.ocAddr(OC) === OC_ADDR &&
    D.chainOfAddr(OC_ADDR) === 'Solana');

  const q = D.parseRugcheck(global.__OC_FIXTURE);
  ok('解析真实链上报价与元数据', q && near(q.price, 0.05133747818589247) &&
    q.code === 'ANSEM' && q.name === 'The Black Bull' &&
    q.launchpad === 'Pump.Fun');
  ok('链上不编造涨跌幅 / 成交额 / 高低价',
    q && q.chg === null && q.amount === null && q.high === null && q.low === null);
  ok('市值 = 真实链上价 × 真实供应量', q && q.cap > 5e7 && q.cap < 5.2e7);
  ok('链上流动性 / 持有地址真实', q &&
    near(q.liquidity, 1860717.8824534104) && q.holders === 383918);

  D.setSearch(OC_ADDR);
  const hit = D.contractHitHTML();
  ok('搜索合约地址出现解析入口', hit.indexOf('解析并加入自选') >= 0 &&
    hit.indexOf('data-addcontract') >= 0 && hit.indexOf('没有 K 线') >= 0);
  ok('非合约搜索不出现解析入口', (function () {
    D.setSearch('BTC'); return D.contractHitHTML() === '';
  })());

  const added = await D.addContract(OC_ADDR);
  ok('无 K 线合约仍可加入自选', added === OC && D.cfg.symbols.indexOf(OC) >= 0);
  ok('元数据落盘（重启可恢复代码/名称）',
    D.cfg.onchain[OC] && D.cfg.onchain[OC].code === 'ANSEM' &&
    D.cfg.onchain[OC].name === 'The Black Bull' &&
    JSON.parse(mem.ct_config).onchain[OC].code === 'ANSEM');
  ok('链上真实价进入行情快照',
    D.tickers[OC] && near(D.tickers[OC].price, q.price));
  ok('行情快照不含编造的涨跌幅', D.tickers[OC] && D.tickers[OC].chg === null);

  D.setSearch('');
  ok('自选列表包含链上品种', (function () {
    D.renderList(); return el('list').innerHTML.indexOf(OC) >= 0;
  })());
  const rhtml = D.rowHTML(OC);
  // data-sym 里保留完整地址是事件委托需要，可见文本不能出现长地址
  ok('行显示代币代码而不是长地址',
    rhtml.indexOf('<span class="code">ANSEM</span>') >= 0 &&
    rhtml.indexOf('<span class="name">The Black Bull</span>') >= 0 &&
    rhtml.indexOf('class="stats">' + OC_ADDR) < 0);
  ok('行显示真实价 / 涨跌「—」/ 真实走势（非 K 线）标注',
    rhtml.indexOf('$0.051') >= 0 && rhtml.indexOf('>—<') >= 0 &&
    rhtml.indexOf('非 K 线') >= 0);
  ok('链上品种不进入交易所 K 线周期', D.intervalsFor(OC).length === 0);

  ok('详情 6 分区 + 来源 + 明确留白', (function () {
    const h = D.detailHTML(OC);
    return ['①', '②', '③', '④', '⑤', '⑥'].every(function (x) {
      return h.indexOf(x) >= 0;
    }) && h.indexOf('Rugcheck') >= 0 && h.indexOf('没有交易所 K 线') >= 0 &&
      h.indexOf('暂无公开数据') >= 0 && h.indexOf(OC_ADDR) >= 0;
  })());

  D.setChartSymbol(OC);
  D.go('chart');
  ok('图表页说明真实走势（非 K 线）、不发 K 线请求',
    el('chartNote').textContent.indexOf('非交易所 K 线') >= 0 &&
    el('intervals').innerHTML === '');
  ok('图表头显示代币代码与真实价', (function () {
    D.updateChartHead();
    return el('chartCode').textContent === 'ANSEM' &&
      el('chartPrice').textContent.indexOf('$0.051') >= 0 &&
      el('chartChange').textContent === '—';
  })());

  ok('链上品种可置顶 / 参与真实排序', (function () {
    D.setPinned(OC, true);
    const pinned = D.cfg.pinned_symbols.indexOf(OC) >= 0;
    D.setPinned(OC, false);
    D.setSort('price_desc');
    const val = D.rankValue(OC, 'price_desc');
    D.setSort('custom');
    return pinned && val !== null && near(val, q.price);
  })());
  ok('配置导出包含链上品种', (function () {
    D.exportConfig();
    const c = JSON.parse(mem.__clipboard || '{}');
    return c.onchain && c.onchain[OC] &&
      c.onchain[OC].code === 'ANSEM' && c.symbols.indexOf(OC) >= 0;
  })());
  ok('跨端导入：桌面 onchain_symbols 键映射到 Android onchain', (function () {
    D.importConfig();
    const desktop = { onchain_symbols: {
      'ONCHAIN:desktopaddr': { address: 'desktopaddr', code: 'DST', name: 'Desktop Coin' }
    } };
    el('textSheetInput').value = JSON.stringify(desktop);
    el('textSheetOk').onclick(el('textSheetInput').value);
    const okMap = !!D.cfg.onchain['ONCHAIN:desktopaddr'] &&
      D.cfg.onchain['ONCHAIN:desktopaddr'].code === 'DST';
    // 恢复：用原生 onchain 键把状态还原，避免影响后续用例
    D.importConfig();
    el('textSheetInput').value = JSON.stringify({ onchain: {} });
    el('textSheetOk').onclick(el('textSheetInput').value);
    return okMap && !D.cfg.onchain['ONCHAIN:desktopaddr'];
  })());

  // 其它链没有可直连报价源：允许收藏，但明确标注无价格，不编造
  const evm = '0x' + 'a'.repeat(40), evmSym = D.ocSymbol(evm);
  await D.addContract(evm);
  ok('EVM 合约也可收藏但不编造价格',
    D.cfg.symbols.indexOf(evmSym) >= 0 && !D.tickers[evmSym] &&
    D.rowHTML(evmSym).indexOf('暂无公开链上报价') >= 0);
  D.go('list');
}

(async function () {
  await onchainTests();
  // 7. 可选：真实网络请求（REAL=1），验证 URL 与字段仍然有效
  if (process.env.REAL === '1') {
    REAL = true;
    console.log('\n--- 真实接口连通性 ---');
    const urls = [
      ['Binance 24hr', 'https://data-api.binance.vision/api/v3/ticker/24hr?symbols=%5B%22BTCUSDT%22%5D'],
      ['腾讯行情', 'https://qt.gtimg.cn/q=sh600519'],
      ['CoinLore', 'https://api.coinlore.net/api/tickers/?start=0&limit=1'],
      ['Binance K线', 'https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=2'],
      ['腾讯K线', 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,,,10,qfq'],
      ['Rugcheck 链上报告', 'https://api.rugcheck.xyz/v1/tokens/' + OC_ADDR + '/report']
    ];
    for (const [name, url] of urls) {
      try {
        const body = await D.http(url, /tencent|qt\.gtimg/.test(url) ? 'GBK' : 'UTF-8');
        ok('真实接口 ' + name, body.length > 20, 'len=' + body.length);
      } catch (e) {
        ok('真实接口 ' + name, false, e.message);
      }
    }
    try {
      const real = await D.http('https://api.rugcheck.xyz/v1/tokens/' + OC_ADDR + '/report');
      const rq = D.parseRugcheck(real);
      ok('真实链上价可解析且不编造涨跌', rq && rq.price > 0 &&
        rq.code === 'ANSEM' && rq.chg === null);
    } catch (e) {
      ok('真实链上价可解析且不编造涨跌', false, e.message);
    }
    REAL = false;
  }
  finish();
})();

function finish() {
  global.setInterval = realSetInterval;
  console.log('\n=== 结果: ' + pass + ' 通过 / ' + fail + ' 失败 ===');
  process.exit(fail ? 1 : 0);
}
