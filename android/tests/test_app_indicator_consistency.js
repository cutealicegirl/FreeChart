/* 指标一致性回归（Android H5）：app.js 指标函数对黄金数据集。
 *
 * 与 python tests/test_indicator_consistency.py 共用
 * tests/fixtures/indicator_golden.json，证明 Python / JavaScript
 * 两端 MA / EMA / BOLL / MACD 公式在容差内逐点一致。
 *
 * 运行：node android/tests/test_app_indicator_consistency.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const WWW = path.join(__dirname, '..', 'assets', 'www');
const GOLDEN = JSON.parse(fs.readFileSync(
  path.join(__dirname, '..', '..', 'tests', 'fixtures', 'indicator_golden.json'), 'utf8'));
let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('  PASS ' + name); }
  else { fail++; console.log('  FAIL ' + name + (extra ? '  ' + extra : '')); }
}

// ---------- 最小 DOM 桩 ----------
function mkCtx() {
  return { setTransform() {}, clearRect() {}, beginPath() {}, moveTo() {},
    lineTo() {}, stroke() {}, fillRect() {}, fillText() {}, setLineDash() {} };
}
function mkEl(id) {
  return { id: id, innerHTML: '', textContent: '', value: '', hidden: false,
    className: '', style: {}, width: 0, height: 0,
    clientWidth: 360, clientHeight: 300, scrollTop: 0, scrollHeight: 1000,
    _attrs: {}, _listeners: {}, _ctx: mkCtx(),
    getAttribute: function (k) { return this._attrs[k] === undefined ? null : this._attrs[k]; },
    setAttribute: function (k, v) { this._attrs[k] = String(v); },
    addEventListener: function (t, f) { (this._listeners[t] = this._listeners[t] || []).push(f); },
    appendChild: function () {}, getElementsByTagName: function () { return []; },
    getContext: function () { return this._ctx; } };
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
const mem = {};
global.Native = {
  get: function (k) { return mem[k] || ''; }, set: function (k, v) { mem[k] = String(v); },
  version: function () { return '1.3.0'; }, toast: function () {}, finish: function () {},
  copy: function () {}, paste: function () { return ''; }, http: function () {}
};
function load(file) {
  vm.runInThisContext(fs.readFileSync(path.join(WWW, file), 'utf8'), { filename: file });
}
load('universe.js');
load('about.js');
load('app.js');
const D = global.__CT_DEBUG;
if (domReady) domReady();

console.log('=== 指标一致性回归 · Android H5 (app.js) ===\n');

const CLOSES = GOLDEN.closes, P = GOLDEN.params, EXP = GOLDEN.expected;
const TOL = 1e-4;
const rows = CLOSES.map(function (c) { return { c: c }; });

function seqClose(actual, expected, name) {
  ok(name + ' 长度一致', actual.length === expected.length,
    'got ' + actual.length + ' want ' + expected.length);
  const diffs = [];
  for (let i = 0; i < Math.min(actual.length, expected.length); i++) {
    const a = actual[i], e = expected[i];
    if ((a === null) !== (e === null)) diffs.push('i=' + i + ' 空值不一致 ' + a + '/' + e);
    else if (a !== null && Math.abs(a - e) > TOL) diffs.push('i=' + i + ' ' + a + '!=' + e);
  }
  ok(name + ' 全部数值在容差内', diffs.length === 0, diffs.slice(0, 3).join('; '));
}

seqClose(D.maSeries(rows, P.ma), EXP.ma5, 'MA(5)');
seqClose(D.emaSeries(rows, P.ema), EXP.ema5, 'EMA(5)');
const b = D.bollSeries(rows, P.boll_n, P.boll_k);
seqClose(b.up, EXP.boll_up, 'BOLL 上轨');
seqClose(b.mid, EXP.boll_mid, 'BOLL 中轨');
seqClose(b.dn, EXP.boll_dn, 'BOLL 下轨');
const m = D.macdSeries(rows, P.macd_fast, P.macd_slow, P.macd_signal);
seqClose(m.dif, EXP.macd_dif, 'MACD DIF');
seqClose(m.dea, EXP.macd_dea, 'MACD DEA');
seqClose(m.hist, EXP.macd_hist, 'MACD HIST');

console.log('\n=== 结果: ' + pass + ' 通过 / ' + fail + ' 失败 ===\n');
process.exit(fail ? 1 : 0);
