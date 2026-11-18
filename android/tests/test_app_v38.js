/* v38 手机端回归：列表顶部随滚动折叠 / 展开 + 图表工具条精简。
 *
 * 运行：node android/tests/test_app_v38.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const WWW = path.join(__dirname, '..', 'assets', 'www');
const ANDROID = path.join(__dirname, '..');
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
  version: function () { return '1.2.1'; },
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

function read(p) { return fs.readFileSync(p, 'utf8'); }
const html = read(path.join(WWW, 'index.html'));
const css = read(path.join(WWW, 'style.css'));
const js = read(path.join(WWW, 'app.js'));
const listSeg = html.slice(html.indexOf('id="pageList"'),
                           html.indexOf('id="pageSearch"'));

console.log('=== v38 · 手机端列表折叠 / 图表工具条回归 ===\n');

// ---------- 1. DOM 结构 ----------
ok('1. 市场 / 子页 / 搜索框被包进 #listHead',
  listSeg.indexOf('<div id="listHead" class="list-head">') >= 0 &&
  listSeg.indexOf('id="markets"') > listSeg.indexOf('id="listHead"') &&
  listSeg.indexOf('id="btnSortMenu"') > listSeg.indexOf('id="listHead"') &&
  listSeg.indexOf('class="section-head"') > listSeg.indexOf('id="btnSortMenu"'));
ok('2. 折叠区在 .section-head 之前，列表滚动容器仍是 #list',
  listSeg.indexOf('id="listHead"') < listSeg.indexOf('class="section-head"') &&
  listSeg.indexOf('<div id="list" class="list"></div>') >
    listSeg.indexOf('class="section-head"'));
ok('3. 图表页只有一个 .chart-tools，且不再有放大 / 缩小按钮',
  (html.match(/class="chart-tools"/g) || []).length === 1 &&
  html.indexOf('data-act="zoomin"') < 0 && html.indexOf('data-act="zoomout"') < 0 &&
  html.indexOf('＋ 放大') < 0 && html.indexOf('－ 缩小') < 0);
ok('4. 保留「最新 / 详情 / 指标」三个紧凑按钮',
  html.indexOf('id="btnReset"') >= 0 && html.indexOf('id="btnDetail"') >= 0 &&
  html.indexOf('id="btnIndicators"') >= 0);

// ---------- 2. CSS 动画与紧凑布局 ----------
ok('5. .list-head 有 max-height / opacity / transform 缓动过渡',
  /\.list-head\s*\{[^}]*overflow:\s*hidden[^}]*\}/s.test(css) &&
  css.indexOf('transition: max-height .28s cubic-bezier(.22,.61,.36,1)') >= 0 &&
  css.indexOf('opacity .2s ease') >= 0);
ok('6. 隐藏态规则存在（透明度 / 上移 / 禁用点击）',
  /#pageList\.head-hidden \.list-head\s*\{[^}]*opacity: 0[^}]*pointer-events: none[^}]*\}/s.test(css));
ok('7. 列表关闭滚动锚定，避免折叠时 scrollTop 回弹抖动',
  /\.list\s*\{[^}]*overflow-anchor:\s*none/s.test(css));
ok('8. 工具按钮视觉高度收紧到 36px，周期按钮也收紧',
  /\.chart-tools button\s*\{[^}]*min-height:\s*36px/s.test(css) &&
  /\.intervals button\s*\{[^}]*min-height:\s*36px/s.test(css));
ok('9. 用 ::after 把触摸热区扩回 44px，不牺牲手感',
  /\.chart-tools button::after\s*\{[^}]*top:\s*-4px[^}]*bottom:\s*-4px/s.test(css));
ok('10. 图表头部 / 备注间距同步收紧',
  /\.chart-head\s*\{[^}]*padding:\s*6px 10px/s.test(css) &&
  /\.chart-note\s*\{[^}]*padding:\s*0 12px 4px/s.test(css));

// ---------- 3. 滚动状态机 ----------
ok('11. 调试接口导出折叠状态机',
  typeof D.headOnScroll === 'function' &&
  typeof D.setHeadHidden === 'function' &&
  typeof D.resetHead === 'function' &&
  typeof D.measureHead === 'function' &&
  typeof D.headState === 'function');
ok('12. 当前页是列表，初始为展开态',
  D.page() === 'list' && D.headState().hidden === false);
D.resetHead();
D.headOnScroll(30);
D.headOnScroll(40);
ok('13. 小幅上滑（累计 <56px）不会误收起',
  D.headState().hidden === false);
D.headOnScroll(60);
ok('14. 上滑累计达阈值后收起',
  D.headState().hidden === true &&
  String(el('pageList').className).indexOf('head-hidden') >= 0);
ok('15. 收起时写精确 0px 高度 + 透明 + 禁用点击',
  el('listHead').style.maxHeight === '0px' &&
  el('listHead').style.opacity === '0' &&
  el('listHead').style.pointerEvents === 'none' &&
  el('listHead').style.transform === 'translateY(-10px)');
D.headOnScroll(140);
ok('16. 继续上滑不重复触发动画',
  D.headState().hidden === true);
D.headOnScroll(132);
ok('17. 下滑不足 20px 不展开（滞回防抖）',
  D.headState().hidden === true);
D.headOnScroll(105);
ok('18. 下滑累计超阈值立即展开',
  D.headState().hidden === false &&
  String(el('pageList').className).indexOf('head-hidden') < 0);
ok('19. 展开后恢复实测 / 兜底高度与不透明',
  el('listHead').style.maxHeight !== '0px' &&
  el('listHead').style.opacity === '1' &&
  el('listHead').style.pointerEvents === '');
D.setHeadHidden(true);
D.headOnScroll(10);
ok('20. 回到列表顶部强制展开，搜索框始终可达',
  D.headState().hidden === false && D.headState().acc === 0);
D.resetHead();
let flickered = false, top = 0;
for (let i = 0; i < 12; i++) {
  top += 40; D.headOnScroll(top);   // 上滑 40（单方向未达 56）
  if (D.headState().hidden) flickered = true;
  top -= 10; D.headOnScroll(top);   // 下滑 10 → 方向变化清零累计
  if (D.headState().hidden) flickered = true;
}
ok('21. 快速上下抖动 12 轮不会让头部来回跳',
  flickered === false && D.headState().hidden === false);
D.setHeadHidden(true);
D.resetHead();
ok('22. resetHead() 可强制恢复展开并清零累计',
  D.headState().hidden === false && D.headState().acc === 0);

// ---------- 4. 事件接线与缩放能力保留 ----------
ok('23. 列表 scroll 事件已接入折叠逻辑',
  js.indexOf('headOnScroll(el.scrollTop)') >= 0 &&
  (el('list')._listeners.scroll || []).length >= 1);
ok('24. 输入框聚焦 / 点顶栏 / 尺寸变化都会恢复工具区',
  js.indexOf("$('search').addEventListener('focus'") >= 0 &&
  js.indexOf("$('topbar').addEventListener('click'") >= 0 &&
  js.indexOf("window.addEventListener('resize', measureHead)") >= 0);
ok('25. 切回列表页强制展开，切换市场 / 子页重置方向累计',
  js.indexOf("if (page === 'list')") >= 0 &&
  js.indexOf('resetHead(); renderList(); requestWindow();') >= 0 &&
  js.indexOf('headAcc = 0; headLastTop = list.scrollTop || 0;') >= 0);
ok('26. 缩放按钮逻辑已删，双指捏合 zoomBy 仍保留',
  js.indexOf("act === 'zoomin'") < 0 &&
  js.indexOf("act === 'zoomout'") < 0 &&
  js.indexOf('zoomBy(d > lastDist)') >= 0 &&
  js.indexOf("$('btnReset').addEventListener('click'") >= 0);
ok('27. 「最新」只复位平移，不改用户调好的缩放倍数',
  /btnReset'\)\.addEventListener\('click', function \(\) \{\s*VIEW\.pan = 0; saveView\(\); drawChart\(\);/s.test(js));

console.log('\n=== ' + pass + '/' + (pass + fail) + ' 通过 ===');
process.exit(fail ? 1 : 0);
