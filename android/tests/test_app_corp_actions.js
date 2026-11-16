/* Android 公司行为复权回归测试。
 * 与桌面端 tests/test_corporate_actions.py 同口径，验证 app.js 的复权引擎：
 * 拆股 / 反向拆股 / 已复权跳过 / 成交量口径 / 多周期聚合 / 无事件标的。
 *
 * 运行：node android/tests/test_app_corp_actions.js
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

// ---------- 轻量 DOM / Native（与 kline_race 测试一致） ----------
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
const mem = {};
global.Native = {
  get: function (k) { return mem[k] || ''; }, set: function (k, v) { mem[k] = String(v); },
  version: function () { return '1.3.0'; }, toast: function () {}, finish: function () {},
  copy: function () {}, paste: function () { return ''; },
  http: function () {}
};
const pending = [];
function load(file) {
  vm.runInThisContext(fs.readFileSync(path.join(WWW, file), 'utf8'), { filename: file });
}
load('universe.js'); load('about.js'); load('app.js');
const D = global.__CT_DEBUG;
if (domReady) domReady();

console.log('=== Android 公司行为复权回归 ===\n');

// candle 场：{ts,label,o,h,l,c,v}
function mk(dateStr, c, v) {
  const [Y, M, Dd] = dateStr.split('-').map(Number);
  return { ts: new Date(Y, M - 1, Dd).getTime() / 1000, label: dateStr,
    o: c, h: c, l: c, c: c, v: v };
}

// [1] 登记库真实性
console.log('[1] 已核实事件登记库');
ok('AAPL 2020 1拆4 已登记', (D.corporateActions['US:AAPL'] || []).some(a => a.d === '2020-08-31' && a.r === 4));
ok('TSLA 2022 1拆3 已登记', (D.corporateActions['US:TSLA'] || []).some(a => a.d === '2022-08-25' && a.r === 3));
ok('NVDA 2024 1拆10 已登记', (D.corporateActions['US:NVDA'] || []).some(a => a.d === '2024-06-10' && a.r === 10));

// [2] AAPL 拆股前复权
console.log('[2] AAPL 2020 1拆4');
const aaplActs = D.corporateActions['US:AAPL'];
const unadj = [mk('2020-08-27', 500, 100), mk('2020-08-28', 500, 100),
  mk('2020-08-31', 125, 400), mk('2020-09-01', 126, 410)];
const eff = D.detectUnadjustedEvents(unadj, aaplActs);
ok('识别到未复权事件', eff.length === 1, 'len=' + eff.length);
const adj = D.applyAdjustment(unadj, aaplActs);
ok('除权前价 /4 -> 125', Math.abs(adj[1].c - 125) < 1e-6, 'c=' + adj[1].c);
ok('除权前量 ×4 -> 400', Math.abs(adj[1].v - 400) < 1e-6, 'v=' + adj[1].v);
ok('除权日价不变', Math.abs(adj[2].c - 125) < 1e-6);
ok('OHLC 同比例', Math.abs(adj[1].o - 500 / 4) < 1e-6 && Math.abs(adj[1].h - 125) < 1e-6);

// [3] 反向拆股 10合1
console.log('[3] 反向拆股 10合1');
const rev = [{ d: '2023-05-10', r: 0.1, k: 'reverse_split' }];
const rc = [mk('2023-05-09', 5, 1000), mk('2023-05-10', 50, 100), mk('2023-05-11', 51, 110)];
const radj = D.applyAdjustment(rc, rev);
ok('反向拆股前价 5/0.1 -> 50', Math.abs(radj[0].c - 50) < 1e-6, 'c=' + radj[0].c);
ok('反向拆股前量 ×0.1 -> 100', Math.abs(radj[0].v - 100) < 1e-6, 'v=' + radj[0].v);

// [4] 多次拆股累积
console.log('[4] 多次拆股累积');
const multi = [mk('2014-06-06', 645, 100), mk('2014-06-09', 92, 700),
  mk('2020-08-28', 500, 400), mk('2020-08-31', 125, 1600)];
const mAdj = D.applyAdjustment(multi, aaplActs);
ok('2014前累积 /28', Math.abs(mAdj[0].c - 645 / 28) < 1e-3, 'c=' + mAdj[0].c);
ok('中间段仅 /4', Math.abs(mAdj[2].c - 125) < 1e-6, 'c=' + mAdj[2].c);

// [5] 已复权跳过 / 无事件不变
console.log('[5] 幂等与保守');
const already = [mk('2020-08-28', 125, 400), mk('2020-08-31', 125, 100), mk('2020-09-01', 126, 110)];
ok('已复权数据不二次复权', D.detectUnadjustedEvents(already, aaplActs).length === 0);
ok('无事件标的不变', D.applyAdjustment(unadj, undefined)[1].c === 500);
ok('qfq成交量补齐：AAPL无分红登记时不误改量', D.adjustVolumeOnly(unadj, 'US:AAPL')[1].v === 400);

// [6] 多周期聚合用复权后日线
console.log('[6] 多周期聚合');
const week = D.aggregateKlines([mk('2024-01-01', 10, 100), mk('2024-01-02', 12, 110),
  mk('2024-01-03', 11, 105), mk('2024-01-08', 13, 120)], 'week', 'day');
ok('周K 聚合 high=12', week.length === 2 && Math.abs(week[0].h - 12) < 1e-9, 'h=' + (week[0] && week[0].h));
ok('周K 聚合 volume=315', Math.abs(week[0].v - 315) < 1e-9, 'v=' + week[0].v);

console.log('\n=== 结果: ' + pass + ' 通过 / ' + fail + ' 失败 ===');
process.exit(fail === 0 ? 0 : 1);
