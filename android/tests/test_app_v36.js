/* v36 手机端回归：股票市场自选可点 + 链上币真实图表。
 *
 * 运行：node android/tests/test_app_v36.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const WWW = path.join(__dirname, '..', 'assets', 'www');
let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('  PASS ' + name); }
  else { fail++; console.log('  FAIL ' + name + (extra ? '  ' + extra : '')); }
}
function mkCtx() {
  return {
    _texts: [], _rects: [], _lines: 0,
    setTransform() {}, clearRect() {},
    beginPath() {}, moveTo() {}, lineTo() { this._lines++; }, stroke() {},
    fillRect(x, y, w, h) { this._rects.push([x, y, w, h]); },
    fillText(t) { this._texts.push(String(t)); },
    setLineDash() {}
  };
}
function mkEl(id) {
  const ctx = mkCtx();
  return {
    id: id, innerHTML: '', textContent: '', value: '', hidden: false,
    className: '', style: {}, width: 0, height: 0,
    clientWidth: 360, clientHeight: 300, scrollTop: 0, scrollHeight: 1000,
    _attrs: {}, _listeners: {}, _ctx: ctx,
    getAttribute: function (k) { return this._attrs[k] === undefined ? null : this._attrs[k]; },
    setAttribute: function (k, v) { this._attrs[k] = String(v); },
    addEventListener: function (t, f) { (this._listeners[t] = this._listeners[t] || []).push(f); },
    appendChild: function () {},
    getElementsByTagName: function () { return []; },
    getContext: function () { return this._ctx; }
  };
}
const els = {};
function el(id) { if (!els[id]) els[id] = mkEl(id); return els[id]; }
let domReady = null;
global.document = {
  readyState: 'loading', body: mkEl('body'), getElementById: el,
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
global.setInterval = function () { return 0; };
global.clearInterval = function () {};
const mem = {};
global.Native = {
  get: function (k) { return mem[k] || ''; },
  set: function (k, v) { mem[k] = String(v); },
  version: function () { return '1.1.2'; },
  toast: function () {}, finish: function () {},
  copy: function () {}, paste: function () { return ''; },
  http: function (u, c, cb) {
    setTimeout(function () { if (global.__nativeCb) global.__nativeCb(cb, '', ''); }, 0);
  }
};
function load(file) {
  vm.runInThisContext(fs.readFileSync(path.join(WWW, file), 'utf8'), { filename: file });
}
load('universe.js');
load('about.js');
load('app.js');
const D = global.__CT_DEBUG;
if (domReady) domReady();

const OC = 'ONCHAIN:9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump';
function click(id, type, attrKey, attrVal) {
  const e = el(id);
  (e._listeners[type] || []).forEach(function (f) {
    f({ target: { getAttribute: function (k) { return k === attrKey ? attrVal : null; } } });
  });
}

console.log('=== v36 · 手机端股票自选 + 链上真实图表回归 ===\n');

// ---------- 1. 股票市场「自选」按钮 ----------
ok('1. 初始四个子页都是自选',
  ['crypto', 'cn', 'hk', 'us'].every(function (k) { return D.cfg.sub_tabs[k] === 'watch'; }));
click('markets', 'click', 'data-market', 'cn');
ok('2. 切到 A股 后仍停留在自选（不再被静默改成全部）',
  D.cfg.sub_tabs.cn === 'watch', D.cfg.sub_tabs.cn);
click('subs', 'click', 'data-sub', 'watch');
ok('3. 点「自选」保持自选状态',
  D.cfg.sub_tabs.cn === 'watch', D.cfg.sub_tabs.cn);
ok('4. 自选按钮处于选中态',
  el('subs').innerHTML.indexOf('data-sub="watch" class="active"') >= 0,
  el('subs').innerHTML);
ok('5. 空自选显示引导卡片与一键跳全部',
  el('list').innerHTML.indexOf('data-goall') >= 0 &&
  el('list').innerHTML.indexOf('自选还是空的') >= 0);
D.cfg.symbols.push('US:ZZZZ_NOT_IN_UNIVERSE');
ok('6. 不在离线清单的股票也算自选（导入配置不丢）',
  D.watchList('us').indexOf('US:ZZZZ_NOT_IN_UNIVERSE') >= 0);
ok('7. 空自选不再返回全部列表', D.baseList().length === 0);
click('subs', 'click', 'data-sub', 'all');
ok('8. 点「全部」能正常切换', D.cfg.sub_tabs.cn === 'all' && D.baseList().length > 0);

// ---------- 2. Rugcheck 真实结构字段 ----------
const report = {
  price: 0.047, totalMarketLiquidity: 1704443, totalHolders: 384611,
  token: { supply: 997354258520195, decimals: 6 },
  tokenMeta: { symbol: 'ANSEM', name: 'The Black Bull' },
  topHolders: [
    { address: 'GdrKtm8einYWAfjWhAtmoi6Em5cqEitsF4u1GxZkL3f', pct: 49.23 },
    { address: 'Abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGH', pct: 3.11 },
    { address: 'bad', pct: -1 }
  ],
  markets: [
    { marketType: 'pump_fun_amm' }, { marketType: 'pump_fun_amm' },
    { marketType: 'raydium' }
  ]
};
const q = D.parseRugcheck(JSON.stringify(report));
ok('9. 解析真实价格', q && q.price === 0.047);
ok('10. 不编造 24h 涨跌 / 高低 / 成交额',
  q.chg === null && q.high === null && q.low === null && q.amount === null);
ok('11. 前十大持有人占比为真实字段',
  q.top_holders.length === 2 && q.top_holders[0].pct === 49.23,
  JSON.stringify(q.top_holders));
ok('12. 池类型按数量降序聚合',
  q.pool_types.length === 2 && q.pool_types[0].label === 'pump_fun_amm' &&
  q.pool_types[0].count === 2, JSON.stringify(q.pool_types));
ok('13. 记录池总数', q.market_count === 3);

// ---------- 3. 真实报价采样历史 ----------
D.ocHist[OC] = [];
ok('14. 首次采样写入', D.recordOcSample(OC, 1700000000, 0.045) === true &&
  D.ocSeries(OC).length === 1);
ok('15. 20 秒内同价不重复记点',
  D.recordOcSample(OC, 1700000010, 0.045) === false &&
  D.ocSeries(OC).length === 1);
ok('16. 价格变化会记新点',
  D.recordOcSample(OC, 1700000060, 0.047) === true &&
  D.ocSeries(OC).length === 2);
ok('17. 无效价格不写入',
  D.recordOcSample(OC, 1700000120, 0) === false &&
  D.ocSeries(OC).length === 2);
ok('18. 采样持久化到原生存储',
  JSON.parse(mem['ct_oc_hist'])[OC].length === 2);

// ---------- 4. 链上图表绘制 ----------
D.onchainQuotes[OC] = q;
D.setChartSymbol(OC);
const kctx = el('kline')._ctx;
kctx._texts = []; kctx._rects = []; kctx._lines = 0;
D.drawChart();
const txt = kctx._texts.join(' | ');
ok('19. 链上图表走真实数据分支（不再只显示「暂无 K 线数据」）',
  txt.indexOf('非交易所 K 线') >= 0, txt.slice(0, 200));
ok('20. 明确标注真实采样点数量', txt.indexOf('2 个真实采样点') >= 0, txt.slice(0, 240));
ok('21. 画出了价格折线', kctx._lines >= 2, kctx._lines);
ok('22. 画出真实持有人结构条',
  txt.indexOf('前 2 大持有地址占比') >= 0 && kctx._rects.length >= 2,
  txt.slice(0, 260));
ok('23. 价格轴是真实美元价', txt.indexOf('$') >= 0);

D.ocHist[OC] = [];
D.drawChart();
const txt2 = el('kline')._ctx._texts.join(' | ');
ok('24. 没有采样点时明确提示等待，不画假线',
  txt2.indexOf('等待首个真实链上报价') >= 0, txt2.slice(0, 200));

D.setChartSymbol('BTC');
D.setCandles([{ ts: 1, label: 'a', o: 1, h: 2, l: 0.5, c: 1.5, v: 10 }]);
el('kline')._ctx._texts = [];
D.drawChart();
ok('25. 普通品种仍走蜡烛绘制',
  el('kline')._ctx._texts.join(' | ').indexOf('非交易所 K 线') < 0);

console.log('\n=== ' + pass + '/' + (pass + fail) + ' 通过 ===');
process.exit(fail ? 1 : 0);
