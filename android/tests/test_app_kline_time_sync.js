/* 回归：Android K 线时间同步、周期边界、实时预览与自动刷新。
 *
 * 覆盖跨日 23:45→00:00→04:00、UTC/A股/美股 DST、checked_bucket 缓存、
 * 乱序合并、实时报价预览不伪造成交量、后台切回刷新。
 *
 * 运行：node android/tests/test_app_kline_time_sync.js
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
    setTransform() {}, clearRect() {}, beginPath() {}, moveTo() {},
    lineTo() {}, stroke() {}, fillRect() {}, strokeRect() {}, fillText() {}, setLineDash() {}
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
    appendChild: function () {}, getElementsByTagName: function () { return []; },
    getContext: function () { return this._ctx; }
  };
}
const els = {};
function el(id) { if (!els[id]) els[id] = mkEl(id); return els[id]; }
let domReady = null;
let visHandler = null;
global.document = {
  readyState: 'loading', body: mkEl('body'), getElementById: el,
  visibilityState: 'visible',
  querySelector: function () { return mkEl('query'); },
  createElement: function () { return mkEl('new'); },
  addEventListener: function (t, f) {
    if (t === 'DOMContentLoaded') domReady = f;
    if (t === 'visibilitychange') visHandler = f;
  }
};
global.getComputedStyle = function () { return { getPropertyValue: function () { return ''; } }; };
global.window = global;
global.devicePixelRatio = 1;
global.addEventListener = function () {};
global.requestAnimationFrame = function (f) { setTimeout(f, 0); };
global.localStorage = {
  _m: {}, getItem: function (k) { return this._m[k] || ''; },
  setItem: function (k, v) { this._m[k] = String(v); }
};
const intervals = [];
global.setInterval = function (f, ms) { intervals.push({ f: f, ms: ms }); return intervals.length; };
global.clearInterval = function () {};
const pending = [];
const mem = {};
global.Native = {
  get: function (k) { return mem[k] || ''; },
  set: function (k, v) { mem[k] = String(v); },
  version: function () { return '1.6.0'; },
  toast: function () {}, finish: function () {},
  copy: function () {}, paste: function () { return ''; },
  http: function (u, c, cb) { pending.push({ url: u, cb: cb }); }
};
function load(file) {
  vm.runInThisContext(fs.readFileSync(path.join(WWW, file), 'utf8'), { filename: file });
}
load('universe.js');
load('about.js');
load('app.js');
const D = global.__CT_DEBUG;
if (domReady) domReady();

console.log('=== Android K 线时间同步专项回归 ===\n');
const U = (y, mo, d, h, mi) => Date.UTC(y, mo - 1, d, h || 0, mi || 0) / 1000;
const B = (t) => D.klineBucketStart(t, '15m', 'BTC');

// ---- 1. 周期边界 ----
ok('1. 23:45/23:59 同属 15m 桶，00:00 开新桶',
  B(U(2026, 11, 17, 23, 45)) === U(2026, 11, 17, 23, 45) &&
  B(U(2026, 11, 17, 23, 59)) === U(2026, 11, 17, 23, 45) &&
  B(U(2026, 11, 18, 0, 0)) === U(2026, 11, 18, 0, 0));
ok('2. 1h: 23:59->23:00, 00:00->00:00',
  D.klineBucketStart(U(2026, 11, 17, 23, 59), '1h', 'BTC') === U(2026, 11, 17, 23, 0) &&
  D.klineBucketStart(U(2026, 11, 18, 0, 0), '1h', 'BTC') === U(2026, 11, 18, 0, 0));
ok('3. 4h: 03:59 仍属 00:00，04:00 切桶',
  D.klineBucketStart(U(2026, 11, 18, 3, 59), '4h', 'BTC') === U(2026, 11, 18, 0, 0) &&
  D.klineBucketStart(U(2026, 11, 18, 4, 0), '4h', 'BTC') === U(2026, 11, 18, 4, 0));
ok('4. 2h/6h/12h 均按 UTC 自然刻线切桶',
  D.klineBucketStart(U(2026, 11, 18, 1, 0), '2h', 'BTC') === U(2026, 11, 18, 0, 0) &&
  D.klineBucketStart(U(2026, 11, 18, 4, 0), '6h', 'BTC') === U(2026, 11, 18, 0, 0) &&
  D.klineBucketStart(U(2026, 11, 18, 12, 0), '12h', 'BTC') === U(2026, 11, 18, 12, 0));
ok('5. 日/周/月跨边界按 UTC 自然日历',
  D.klineBucketStart(U(2026, 11, 17, 23, 59), '1d', 'BTC') === U(2026, 11, 17, 0, 0) &&
  D.klineBucketStart(U(2026, 11, 23, 0, 0), '1w', 'BTC') === U(2026, 11, 23, 0, 0) &&
  D.klineBucketStart(U(2026, 12, 1, 0, 0), '1M', 'BTC') === U(2026, 12, 1, 0, 0));
ok('6. 自然月不是固定 30 天块（1/31 -> 2/1）',
  D.klineBucketStart(U(2026, 1, 31, 23, 59), '1M', 'BTC') === U(2026, 1, 1, 0, 0) &&
  D.klineBucketStart(U(2026, 2, 1, 0, 0), '1M', 'BTC') === U(2026, 2, 1, 0, 0));

// ---- 2. 市场时区 / DST ----
ok('7. A股日线按北京 00:00 切桶',
  D.klineBucketStart(U(2026, 11, 17, 15, 59), 'day', 'SH:600519') === U(2026, 11, 16, 16, 0) &&
  D.klineBucketStart(U(2026, 11, 18, 0, 1), 'day', 'SH:600519') === U(2026, 11, 17, 16, 0),
  '注意 UTC 表示：北京 00:00 = 前一日 16:00 UTC');
ok('8. 美股 DST：7 月 -4h，1 月 -5h',
  D.klineOffsetMs('US:AAPL', U(2026, 7, 1) * 1000) === -4 * 3600000 &&
  D.klineOffsetMs('US:AAPL', U(2026, 1, 1) * 1000) === -5 * 3600000);
ok('9. 美股日线桶按美东当地午夜',
  D.klineBucketStart(D.klineBucketStart(U(2026, 7, 1, 19, 59), 'day', 'US:AAPL'), 'day', 'US:AAPL') ===
  D.klineBucketStart(U(2026, 7, 1, 4, 0), 'day', 'US:AAPL'));

// ---- 3. 刷新频率 / 缓存边界 ----
ok('10. 自动刷新分档与桌面一致',
  D.refreshSeconds('15m') === 10 && D.refreshSeconds('1h') === 30 &&
  D.refreshSeconds('6h') === 30 && D.refreshSeconds('1d') === 60);
const cacheSym = 'TESTCACHE', cacheKey = cacheSym + '|1h';
D.KLINE_CACHE[cacheKey] = {
  bars: [{ ts: U(2026, 11, 17, 23), o: 1, h: 1, l: 1, c: 1, v: 1 }],
  checkedBucket: 0, ts: Date.now()
};
D.setNowMs(U(2026, 11, 18, 0, 5) * 1000);
ok('11. 跨到 00:00 桶后缓存立即失效（不再等 15 分钟）',
  D.klineCacheFresh(cacheSym, '1h') === false);
D.KLINE_CACHE[cacheKey].checkedBucket = U(2026, 11, 18, 0, 0);
ok('12. 源确认本桶无新根后 TTL 内不再打源',
  D.klineCacheFresh(cacheSym, '1h') === true);
D.setNowMs(null);

// ---- 4. 实时预览（不伪造数据） ----
const t00 = U(2026, 11, 18, 0, 0);
D.setNowMs(U(2026, 11, 18, 0, 1) * 1000);
const f = D.klinePreviewFields('BTC', '1h', 42000.5, U(2026, 11, 18, 0, 1));
ok('13. 跨周期预览落在当前桶，OHLC 来自真实报价，volume=0',
  f && f.ts === t00 && f.preview === true && f.v === 0 &&
  f.o === 42000.5 && f.h === 42000.5 && f.l === 42000.5 && f.c === 42000.5);
ok('14. 无效报价不生成预览',
  D.klinePreviewFields('BTC', '1h', 0, U(2026, 11, 18, 0, 1)) === null);

D.setPage('chart');
D.setChartSymbol('BTC');
D.setIntervalKey('1h');
D.setCandles([{ ts: U(2026, 11, 17, 23), label: '23:00', o: 1, h: 2, l: 1, c: 2, v: 10 }]);
D.applyChartQuote(3.5, U(2026, 11, 18, 0, 1));
let cs = D.candles();
ok('15. 服务端仍停在 23:00 时，00:01 创建 00:00 预览根',
  cs.length === 2 && cs[1].ts === t00 && cs[1].preview === true &&
  cs[1].c === 3.5 && cs[1].v === 0,
  JSON.stringify(cs));
ok('16. 预览不写入 K 线缓存',
  !D.KLINE_CACHE['BTC|1h'] ||
  !D.KLINE_CACHE['BTC|1h'].bars.some(function (b) { return !!b.preview; }));
const merged = D.mergeCandles(cs, [
  { ts: t00, label: '00:00', o: 3, h: 4, l: 2, c: 3.8, v: 99 }
]);
ok('17. 真实 K 线到达后覆盖同 ts 预览（根数不增加）',
  merged.length === 2 && merged[1].v === 99 && !merged[1].preview);

// ---- 5. 自动刷新与后台切回 ----
intervals.length = 0;
D.restartKlineTimer();
const klineTimer = intervals.filter(function (x) { return x.ms === 30000; });
ok('18. 1h 图表注册 30 秒 K 线刷新定时器', klineTimer.length >= 1,
  'intervals=' + JSON.stringify(intervals.map(function (x) { return x.ms; })));
ok('19. 切到日线后定时器改为 60 秒档',
  (function () {
    D.setIntervalKey('1d');
    intervals.length = 0;
    D.restartKlineTimer();
    return intervals.some(function (x) { return x.ms === 60000; });
  })());
ok('20. visibilitychange 回到图表会触发一次边界校验',
  typeof visHandler === 'function' && (function () {
    const before = D.loadSeq();
    visHandler();
    return D.loadSeq() > before;
  })());
D.setNowMs(null);

console.log('\n=== 结果: ' + pass + ' 通过 / ' + fail + ' 失败 ===');
process.exit(fail ? 1 : 0);
