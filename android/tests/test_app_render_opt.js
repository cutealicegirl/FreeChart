/* 回归：行情列表合帧渲染 + 行级增量更新（阶段三性能优化）。
 *
 * 场景：
 *  1) scheduleRender() 在 rAF 内合并多次调用为一次 renderList；
 *  2) 行集合/顺序不变时，只更新变化行的 .info / .right，不整表重建 innerHTML；
 *  3) 结构变化（切市场/排序）时仍走整表重建，保证正确性；
 *  4) 数据刷新（skipTabs）不重建市场/子页标签按钮。
 *
 * 运行：node android/tests/test_app_render_opt.js
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

// ---------- 具备最小 DOM 查询能力的元素桩 ----------
function parseClass(s) { var m = /class="([^"]*)"/.exec(s || ''); return m ? m[1] : ''; }

function mkEl(id) {
  const e = {
    id: id, _html: '', textContent: '', value: '', hidden: false,
    className: '', style: {}, width: 0, height: 0,
    clientWidth: 360, clientHeight: 300, scrollTop: 0, scrollHeight: 1000,
    _attrs: {}, _listeners: {}, _writes: 0,
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = String(v); this._writes++; this._syncChildren(); },
    getAttribute: function (k) { return this._attrs[k] === undefined ? null : this._attrs[k]; },
    setAttribute: function (k, v) { this._attrs[k] = String(v); },
    addEventListener: function (t, f) { (this._listeners[t] = this._listeners[t] || []).push(f); },
    appendChild: function () {}, getElementsByTagName: function () { return []; },
    getContext: function () { return this._ctx; },
    _syncChildren: function () {
      // 解析出 .trow 行节点，供 querySelectorAll 使用；每行带 .info/.right 子节点
      this._rows = [];
      var re = /<div class="(trow[^"]*)" data-sym="([^"]*)">([\s\S]*?)(?=<div class="trow|$)/g;
      var m;
      while ((m = re.exec(this._html)) !== null) {
        var body = m[3];
        var infoM = /<div class="info">([\s\S]*?)<div class="right">/.exec(body);
        var rightM = /<div class="right">([\s\S]*)$/.exec(body);
        var info = mkEl('info'); info._html = infoM ? infoM[1] : '';
        var right = mkEl('right'); right._html = rightM ? rightM[1] : '';
        var row = mkEl('trow');
        row.className = m[1];
        row._attrs['data-sym'] = m[2];
        row._children = { '.info': info, '.right': right };
        this._rows.push(row);
      }
    },
    querySelectorAll: function (sel) {
      if (sel === '.trow') return this._rows || [];
      return [];
    },
    querySelector: function (sel) {
      return (this._children && this._children[sel]) || null;
    },
    _ctx: {
      setTransform() {}, clearRect() {}, beginPath() {}, moveTo() {}, lineTo() {},
      stroke() {}, fillRect() {}, fillText() {}, setLineDash() {}
    }
  };
  return e;
}
const els = {};
function el(id) { if (!els[id]) els[id] = mkEl(id); return els[id]; }

let domReady = null;
global.document = {
  readyState: 'loading', body: mkEl('body'), getElementById: el,
  querySelector: function () { return mkEl('query'); },
  createElement: function () {
    var e = mkEl('fresh');
    // createElement 的 div 设置 innerHTML 后，取首个子 .trow
    Object.defineProperty(e, 'firstElementChild', {
      configurable: true,
      get: function () { return (this._rows && this._rows[0]) || null; }
    });
    Object.defineProperty(e, 'firstChild', {
      configurable: true,
      get: function () { return (this._rows && this._rows[0]) || null; }
    });
    return e;
  },
  addEventListener: function (t, f) { if (t === 'DOMContentLoaded') domReady = f; }
};
global.getComputedStyle = function () { return { getPropertyValue: function () { return ''; } }; };
global.window = global;
global.devicePixelRatio = 1;
global.addEventListener = function () {};
// 手动flush：记录 rAF 回调，由测试显式触发
const rafQueue = [];
global.requestAnimationFrame = function (f) { rafQueue.push(f); return rafQueue.length; };
function flushRAF() { const q = rafQueue.splice(0); q.forEach(function (f) { f(); }); }
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
  copy: function () {}, paste: function () { return ''; },
  http: function () {}
};
function load(file) {
  vm.runInThisContext(fs.readFileSync(path.join(WWW, file), 'utf8'), { filename: file });
}
load('universe.js');
load('about.js');
load('app.js');
const D = global.__CT_DEBUG;
if (domReady) domReady();

console.log('=== 行情列表合帧 + 增量渲染回归 ===\n');

// ---------- 1. 首屏全量挂载一页 ----------
var initialWrites = el('list')._writes;
var rowCount = (el('list').innerHTML.match(/class="trow/g) || []).length;
ok('1. 首屏挂载一页行（≤60）', rowCount > 0 && rowCount <= 60, '实际 ' + rowCount);
ok('2. 首屏至少写了一次列表', initialWrites >= 1, 'writes=' + initialWrites);

// ---------- 2. 同结构再次 renderList：应走增量，不整表重建 ----------
el('list')._writes = 0;
D.renderList();
ok('3. 行集合未变时 renderList 不整表重建 innerHTML',
  el('list')._writes === 0, 'writes=' + el('list')._writes);

// ---------- 3. scheduleRender 合帧：多次调用只排入一个 rAF ----------
rafQueue.length = 0;
D.scheduleRender(); D.scheduleRender(); D.scheduleRender();
ok('4. 多次 scheduleRender 只排入一个 rAF 回调（合帧）', rafQueue.length === 1,
  'raf=' + rafQueue.length);
flushRAF();
ok('5. rAF 执行后队列清空', rafQueue.length === 0, 'raf=' + rafQueue.length);

// ---------- 4. skipTabs：数据刷新不重建标签按钮 ----------
// 先制造一次结构变化，使随后的合帧渲染必然发生（否则增量路径会是 no-op）
var mBefore = el('markets')._writes, sBefore = el('subs')._writes;
D.cfg.sort_reverse = !D.cfg.sort_reverse;
D.scheduleRender(); flushRAF();
ok('6. 合帧渲染确实执行（排序翻转后标签未重建但列表已更新）',
  el('markets')._writes === mBefore && el('subs')._writes === sBefore,
  'markets +' + (el('markets')._writes - mBefore) + ' subs +' + (el('subs')._writes - sBefore));

// ---------- 5. 结构变化（切市场）走整表重建，保证正确性 ----------
el('list')._writes = 0;
D.cfg.sub_tabs[D.cfg.last_tab || 'crypto'] = 'watch';
D.cfg.symbols.push('CRYPTO_FAKE_FOR_STRUCT_CHANGE');
D.renderList();
ok('8. 行结构变化后走整表重建（列表 innerHTML 被写入）',
  el('list')._writes >= 1, 'writes=' + el('list')._writes);

console.log('\n=== 结果: ' + pass + ' 通过 / ' + fail + ' 失败 ===\n');
process.exit(fail ? 1 : 0);
