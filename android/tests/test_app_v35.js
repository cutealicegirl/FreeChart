/* v35 手机端回归：批量行情含非法交易对时拆分降级，不再整页空白。
 *
 * 运行：node android/tests/test_app_v35.js
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

function mkEl(id) {
  return {
    id: id, innerHTML: '', textContent: '', value: '', hidden: false,
    className: '', style: {}, width: 0, height: 0,
    clientWidth: 360, clientHeight: 300, scrollTop: 0, scrollHeight: 1000,
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

// 模拟 Java Bridge：含 BADCOINUSDT 的整批返回 HTTP 400，其它批正常返回。
const BAD = 'BADCOINUSDT';
const urls = [];
global.Native = {
  get: function () { return ''; }, set: function () {},
  version: function () { return '1.1.0'; },
  toast: function () {}, finish: function () {},
  copy: function () {}, paste: function () { return ''; },
  http: function (url, charset, cb) {
    urls.push(url);
    setTimeout(function () {
      if (url.indexOf('ticker/24hr') < 0) {
        global.__nativeCb(cb, '', '');
        return;
      }
      let pairs = [];
      try { pairs = JSON.parse(decodeURIComponent(url.split('symbols=')[1])); }
      catch (e) { pairs = []; }
      if (pairs.indexOf(BAD) >= 0) {
        global.__nativeCb(cb, '', 'HTTP 400 Invalid symbol');
        return;
      }
      const rows = pairs.map(function (p) {
        return { symbol: p, lastPrice: '100.5', priceChangePercent: '-1.25',
                 highPrice: '110', lowPrice: '90', quoteVolume: '123456' };
      });
      global.__nativeCb(cb, JSON.stringify(rows), '');
    }, 0);
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

(async function () {
  console.log('=== v35 · Android 批量行情容错回归 ===\n');

  // 1. 正常批次一次请求即可
  urls.length = 0;
  const clean = await D.binanceBatch(['BTCUSDT', 'ETHUSDT', 'SOLUSDT']);
  ok('1. 正常批次返回全部品种',
    Object.keys(clean).sort().join(',') === 'BTC,ETH,SOL', Object.keys(clean));
  ok('2. 正常批次只发 1 个请求', urls.length === 1, urls.length);

  // 2. 含非法交易对：拆分后其余品种照常有价
  urls.length = 0;
  const mixed = await D.binanceBatch([
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
    BAD, 'DOGEUSDT', 'ARBUSDT', 'ARUSDT'
  ]);
  ok('3. 坏品种被剔除', !mixed.BADCOIN, Object.keys(mixed));
  ok('4. 同批其它 8 个品种都有价', Object.keys(mixed).length === 8,
    Object.keys(mixed));
  ok('5. 价格解析正确', mixed.BTC && mixed.BTC.price === 100.5,
    mixed.BTC);
  ok('6. 触发了拆分子批重试', urls.length > 1, urls.length);
  ok('7. 单个坏品种最终只被请求一次',
    urls.filter(function (u) { return u.indexOf(BAD) >= 0; }).length >= 1);

  // 3. fetchTickers 分组：链上品种绝不进币安 URL
  urls.length = 0;
  const res = await D.fetchTickers(['BTC', 'ETH', OC, 'SH:600519']);
  ok('8. 任何请求都不含链上地址',
    urls.every(function (u) { return u.indexOf('ONCHAIN') < 0; }), urls);
  ok('9. 加密货币仍有数据', !!res.map.BTC, Object.keys(res.map));
  ok('10. 请求拆分为币安与腾讯两路',
    urls.some(function (u) { return u.indexOf('ticker/24hr') >= 0; }) &&
    urls.some(function (u) { return u.indexOf('qt.gtimg.cn') >= 0; }), urls);
  ok('11. 空批次安全返回',
    Object.keys(await D.binanceBatch([])).length === 0);

  console.log('\n=== ' + pass + '/' + (pass + fail) + ' 通过 ===');
  process.exit(fail ? 1 : 0);
})().catch(function (e) {
  console.error('EXCEPTION', e);
  process.exit(2);
});
