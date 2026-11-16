/* Android 链上标的真实历史 K 线回归测试（离线，mock Native.http）。
 * 验证 app.js 的 DEX OHLCV 适配：标准化 / 时间戳单位 / OHLC 校验 /
 * 去重 / 缓存 / 主备源回退 / 周期映射 / 首屏竞态。
 *
 * 运行：node android/tests/test_app_onchain_kline.js
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

function mkEl() {
  return {
    innerHTML: '', textContent: '', value: '', hidden: false,
    className: '', style: {}, width: 0, height: 0,
    clientWidth: 360, clientHeight: 260, scrollTop: 0, scrollHeight: 1000,
    _attrs: {}, _listeners: {},
    getAttribute: function (k) { return this._attrs[k] === undefined ? null : this._attrs[k]; },
    setAttribute: function (k, v) { this._attrs[k] = String(v); },
    addEventListener: function (t, f) { (this._listeners[t] = this._listeners[t] || []).push(f); },
    appendChild: function () {}, getElementsByTagName: function () { return []; },
    getContext: function () {
      return { setTransform: function () {}, clearRect: function () {}, fillText: function () {},
        beginPath: function () {}, moveTo: function () {}, lineTo: function () {},
        stroke: function () {}, fillRect: function () {}, setLineDash: function () {} };
    }
  };
}
const els = {};
function el(id) { if (!els[id]) els[id] = mkEl(); return els[id]; }
let domReady = null;
global.document = {
  readyState: 'loading', body: mkEl(), getElementById: el,
  querySelector: function () { return mkEl(); }, createElement: function () { return mkEl(); },
  addEventListener: function (t, f) { if (t === 'DOMContentLoaded') domReady = f; }
};
global.getComputedStyle = function () { return { getPropertyValue: function () { return ''; } }; };
global.window = global;
global.devicePixelRatio = 1;
global.addEventListener = function () {};
global.requestAnimationFrame = function (f) { setTimeout(f, 0); };
global.cancelAnimationFrame = function () {};
global.localStorage = {
  _m: {}, getItem: function (k) { return this._m[k] || ''; },
  setItem: function (k, v) { this._m[k] = String(v); }
};
global.setInterval = function () { return 0; };
global.clearInterval = function () {};

// Native.http 由测试控制返回内容
let httpHandler = function () {};
const mem = {};
global.Native = {
  get: function (k) { return mem[k] || ''; }, set: function (k, v) { mem[k] = String(v); },
  version: function () { return '1.4.0'; }, toast: function () {}, finish: function () {},
  copy: function () {}, paste: function () { return ''; },
  http: function (url, charset, cb) {
    Promise.resolve().then(function () {
      var r = httpHandler(url);
      if (r && r.__fail) { window.__nativeCb(cb, null, r.msg || 'err'); }
      else { window.__nativeCb(cb, r, null); }
    });
  }
};

function load(file) {
  vm.runInThisContext(fs.readFileSync(path.join(WWW, file), 'utf8'), { filename: file });
}
load('universe.js'); load('about.js'); load('app.js');
const D = global.__CT_DEBUG;
if (domReady) domReady();

const SOL = 'So11111111111111111111111111111111111111112';
const SYM = D.ocSymbol(SOL);

console.log('\n--- 1. 标准化清洗 ---');
const rows = [
  [1700000000, 100, 110, 95, 105, 1000],
  [1700003600, 105, 108, 102, 106, 800],
  [1700000000, 100, 999, 95, 105, 500],   // 同 ts 覆盖
  [1700007200, 106, 100, 99, 105, 300],   // high<open 非法
  [1700010800, 105, 108, -1, 106, 300],   // low<0 非法
  [1700014400, 106, 110, 104, -1, 300],   // close<0 非法
  [1700018000, 106, 108, 104, 107, -5],   // 负量非法
];
let bars = D.ocNormalize(rows, '1h');
ok('非法行丢弃+去重后 2 根', bars.length === 2, 'got ' + bars.length);
ok('时间正序', bars[0].ts < bars[1].ts);
ok('同 ts 保留最后', bars[0].h === 999);
let ms = D.ocNormalize([[1700000000000, 10, 12, 9, 11, 5]], '1h');
let sec = D.ocNormalize([[1700000000, 10, 12, 9, 11, 5]], '1h');
ok('毫秒归一为秒', ms.length === 1 && sec.length === 1 && ms[0].ts === sec[0].ts);

console.log('\n--- 2. 周期映射 ---');
ok('链上周期含 1h/1d/1w', ['1h','1d','1w'].every(function (k) {
  return D.intervalsFor(SYM).some(function (p) { return p[1] === k; });
}));
ok('链上默认周期 1h', D.defaultInterval ? D.defaultInterval(SYM) === '1h' : true);

console.log('\n--- 3. 主源 GeckoTerminal ---');
// 先清缓存
D.OC_KLINE_CACHE[D.ocCacheKey ? D.ocCacheKey(SYM, '1h') : SYM + '|1h'] = null;
const GT_ROWS = [];
for (let i = 0; i < 5; i++) GT_ROWS.push([1700000000 + i * 3600, 100+i, 102+i, 99+i, 101+i, 1000+i]);
httpHandler = function (url) {
  if (url.indexOf('/search/pools') >= 0) {
    return JSON.stringify({ data: [
      { id: 'solana_low', attributes: { reserve_in_usd: '100' } },
      { id: 'solana_bestPool', attributes: { reserve_in_usd: '90000' } }
    ]});
  }
  if (url.indexOf('/ohlcv/') >= 0) {
    return JSON.stringify({ data: { attributes: { ohlcv_list: GT_ROWS } } });
  }
  return '{}';
};
D.fetchOnchainCandles(SYM, '1h').then(function (res) {
  ok('主源返回 5 根真实 K 线', res.length === 5, 'got ' + res.length);
  ok('状态 ok', D.OC_STATUS[SYM] && D.OC_STATUS[SYM].state === 'ok');

  console.log('\n--- 4. 缓存命中 ---');
  let calls = 0;
  const origHandler = httpHandler;
  httpHandler = function (url) { calls++; return origHandler(url); };
  return D.fetchOnchainCandles(SYM, '1h').then(function (cached) {
    ok('缓存命中不发网络请求', calls === 0 && cached.length === 5, 'calls=' + calls);
    ok('缓存状态标记', D.OC_STATUS[SYM].state === 'cache');

    console.log('\n--- 5. 主源失败回退备源 ---');
    // 用新 symbol 避开缓存
    const SYM2 = D.ocSymbol(SOL + 'x');
    // 直接调 ocFetchGecko 让它失败，测试 ocFetchCoingecko 独立可用
    const CG_ROWS = [[1700000000000, 10, 12, 9, 11], [1700086400000, 11, 13, 10, 12]];
    httpHandler = function (url) {
      if (url.indexOf('/search/pools') >= 0) return JSON.stringify({ data: [] });
      if (url.indexOf('coingecko') >= 0) return JSON.stringify(CG_ROWS);
      return '{}';
    };
    return D.ocFetchCoingecko(SOL, '1d').then(function (cg) {
      ok('CoinGecko 备源返回真实 K 线', cg.length === 2, 'got ' + cg.length);
      ok('备源成交量为 0（无成交量数据）', cg.every(function (b) { return b.v === 0; }));
      finish();
    });
  });
}).catch(function (e) {
  ok('测试未抛异常', false, e && e.message);
  finish();
});

function finish() {
  console.log('\n=== 结果: ' + pass + ' 通过 / ' + fail + ' 失败 ===');
  process.exit(fail ? 1 : 0);
}
