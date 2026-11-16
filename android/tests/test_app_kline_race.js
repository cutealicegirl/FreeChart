/* 回归：K 线异步请求竞态（乱序返回不得覆盖当前品种/周期）。
 *
 * 场景：连续切换 10 个品种/周期，故意让旧请求晚于新请求返回。
 * 验收：最终 CANDLES 一定属于最后选中的品种和周期，chartNote 无残留错误。
 *
 * 运行：node android/tests/test_app_kline_race.js
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
    lineTo() {}, stroke() {}, fillRect() {}, fillText() {}, setLineDash() {}
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
global.document = {
  readyState: 'loading', body: mkEl('body'), getElementById: el,
  querySelector: function () { return mkEl('query'); },
  createElement: function () { return mkEl('new'); },
  addEventListener: function (t, f) { if (t === 'DOMContentLoaded') domReady = f; }
};
global.getComputedStyle = function () { return { getPropertyValue: function () { return ''; } }; };
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

// Native.http：记录每次请求的回调 id + URL，不立即回调（由测试手动乱序触发）
const pending = [];
global.Native = {
  get: function (k) { return mem[k] || ''; },
  set: function (k, v) { mem[k] = String(v); },
  version: function () { return '1.3.0'; },
  toast: function () {}, finish: function () {},
  copy: function () {}, paste: function () { return ''; },
  http: function (u, c, cb) { pending.push({ url: u, cb: cb }); }
};
const mem = {};
function load(file) {
  vm.runInThisContext(fs.readFileSync(path.join(WWW, file), 'utf8'), { filename: file });
}
load('universe.js');
load('about.js');
load('app.js');
const D = global.__CT_DEBUG;
if (domReady) domReady();

console.log('=== K 线异步竞态回归（乱序返回）===\n');

// 用 BINANCE_KLINE 特征串识别 crypto 请求；构造带唯一价格的 K 线文本
// 价格编码品种序号，便于断言最终显示的是哪个品种的数据。
function klineText(marker) {
  return JSON.stringify([
    [1700000000000, marker, marker + 1, marker - 1, marker + 0.5, 100]
  ]);
}
function urlMarker(url) {
  const m = /symbol=([A-Z]+)USDT/.exec(url);
  return m ? m[1] : '?';
}

// 依次切换 10 个品种（每次 loadChart 递增 seq 并挂起一个请求）
const symbols = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'AVAX', 'LINK', 'DOT'];
const seqBefore = D.loadSeq();
const pendingBase = pending.length;   // 排除 domReady 初始化时产生的请求
for (let i = 0; i < symbols.length; i++) {
  D.setChartSymbol(symbols[i]);
  D.setIntervalKey('m5');
  D.loadChart();
}
const mine = pending.slice(pendingBase);
ok('1. 每次 loadChart 递增请求序号（共 +10）',
  D.loadSeq() - seqBefore === symbols.length,
  'delta=' + (D.loadSeq() - seqBefore));
ok('2. 收集到 10 个在途 K 线请求', mine.length === symbols.length,
  'pending=' + mine.length);

function codeOf(marker) {
  let code = 0;
  for (let j = 0; j < marker.length; j++) code = code * 31 + marker.charCodeAt(j);
  return code;
}
// 冲刷微任务队列：Promise.then/catch 需在同步触发后等待其执行。
function flushMicrotasks() {
  return new Promise(function (resolve) { setImmediate(resolve); });
}

(async function run() {
  // 故意「倒序」返回：最先触发最后一个品种的请求，最后触发第一个（最旧）请求。
  // 每个请求回执携带的品种标记不同，若旧请求未被守卫，最终 CANDLES 会停在 BTC。
  for (let i = mine.length - 1; i >= 0; i--) {
    const req = mine[i];
    global.__nativeCb(req.cb, klineText(codeOf(urlMarker(req.url))), '');
  }
  await flushMicrotasks();

  // 最终选中的是最后一个品种 DOT；旧请求全部应被丢弃
  const finalCandles = D.candles();
  ok('3. 最终 CANDLES 来自最后选中的品种 DOT，而非最早的 BTC',
    finalCandles.length === 1 &&
    Math.round(finalCandles[0].o) === codeOf('DOT'),
    'o=' + (finalCandles[0] && finalCandles[0].o) + ' expect=' + codeOf('DOT'));

  // 再验证「失败回调」同样被守卫：制造一个旧请求的 error 回执，
  // 不得把当前界面的 chartNote 改成「加载失败」。
  D.setChartSymbol('ETH'); D.setIntervalKey('m15'); D.loadChart();
  const newestSeq = D.loadSeq();
  const base2 = pending.length;
  D.setChartSymbol('SOL'); D.setIntervalKey('m5'); D.loadChart();
  const oldReq = pending[base2 - 1];   // 上一个（已失效）ETH 请求
  global.__nativeCb(oldReq.cb, '', '模拟旧请求失败');
  await flushMicrotasks();
  ok('4. 旧请求失败回执不改写当前 chartNote',
    el('chartNote').textContent.indexOf('加载失败') < 0,
    'note=' + el('chartNote').textContent);
  ok('5. 当前请求序号未被旧回执影响', D.loadSeq() === newestSeq + 1);

  console.log('\n=== 结果: ' + pass + ' 通过 / ' + fail + ' 失败 ===');
  process.exit(fail ? 1 : 0);
})();
