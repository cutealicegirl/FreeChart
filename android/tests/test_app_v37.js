/* v37 手机端回归：Free Chart 品牌 + 发展历程 / 品种档案 / 行情里程碑。
 *
 * 运行：node android/tests/test_app_v37.js
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
  version: function () { return '1.2.0'; },
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
function read(p) { return fs.readFileSync(p, 'utf8'); }

console.log('=== v37 · 手机端品牌 / 发展历程 / 档案 / 里程碑回归 ===\n');

// ---------- 1. 品牌 ----------
ok('1. 品牌资料与桌面端同源导出',
  D.dbMeta.app_name === 'Free Chart' &&
  D.dbMeta.app_tagline.indexOf('自由缩放') >= 0 &&
  read(path.join(WWW, 'about.js')).indexOf('tools/export_profile_db.py') >= 0);
ok('2. HTML 标题 / 顶栏 / APK 应用名都改成 Free Chart',
  read(path.join(WWW, 'index.html')).indexOf('<span class="brand"') >= 0 &&
  read(path.join(WWW, 'index.html')).indexOf('>Free Chart</span>') >= 0 &&
  read(path.join(ANDROID, 'res', 'values', 'strings.xml'))
    .indexOf('<string name="app_name">Free Chart</string>') >= 0);
ok('3. APK 包名与版本号未破坏升级',
  read(path.join(ANDROID, 'AndroidManifest.xml'))
    .indexOf('package="com.cryptoticker.app"') >= 0 &&
  read(path.join(ANDROID, 'AndroidManifest.xml'))
    .indexOf('android:versionName="1.5.0"') >= 0);

// ---------- 2. 资料库内容 ----------
const DB = global.ABOUT_DB;
ok('4. 发展历程覆盖 40+ 品种 / 150+ 事件，核验日期可追溯',
  DB.meta.stats.symbols >= 40 && DB.meta.stats.events >= 150 &&
  DB.meta.verified_at === '2026-11-14');
ok('5. BTC / XRP 关键日期已联网核验且写入资料库',
  DB.timeline.BTC.some(function (e) { return e.date === '2009-01-03'; }) &&
  DB.timeline.BTC.some(function (e) { return e.date === '2024-01-10'; }) &&
  DB.timeline.XRP.some(function (e) { return e.date === '2025-08-07'; }));
ok('6. 每条里程碑都带来源，日期格式规范',
  Object.keys(DB.timeline).every(function (s) {
    return DB.timeline[s].every(function (e) {
      return /^\d{4}( 年代|-\d{2}(-\d{2})?)?$/.test(e.date) &&
        !!e.title && !!e.src;
    });
  }));
ok('7. 品种档案含可核对的上市日 / 交易所 / 官网',
  DB.archive['SH:600519'].listing_date === '2001-08-27' &&
  DB.archive['SH:600519'].exchange.indexOf('上海证券交易所') >= 0 &&
  !!DB.archive['US:NVDA'].website);

// ---------- 3. 详情新增分区 ----------
const tl = D.timelineHTML('BTC');
ok('8. 发展历程渲染时间线节点与来源',
  tl.indexOf('⑦ 发展历程') >= 0 &&
  tl.indexOf('2009-01-03') >= 0 &&
  tl.indexOf('创世区块') >= 0 &&
  tl.indexOf('来源：') >= 0 &&
  tl.indexOf('核验于 2026-11-14') >= 0);
ok('9. 未收录品种发展历程明确留白，不套用通用简介',
  D.timelineHTML('US:ZZZZ').indexOf(DB.meta.no_data) >= 0);
ok('10. 品种档案卡片填真实字段',
  D.archiveHTML('SH:600519').indexOf('2001-08-27') >= 0 &&
  D.archiveHTML('SH:600519').indexOf('上海证券交易所') >= 0);
ok('11. 未收录品种档案不拿同类品种数值填充',
  D.archiveHTML('US:ZZZZ').indexOf('资料库未收录') >= 0);
const dh = D.detailHTML('BTC');
ok('12. 详情在原有 6 分区之外新增 ⑦⑧⑨，且不破坏旧结构',
  ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨'].every(function (x) {
    return dh.indexOf(x) >= 0;
  }) && dh.indexOf('发展历程') >= 0 &&
  dh.indexOf('品种档案') >= 0 && dh.indexOf('行情里程碑') >= 0);
const oh = D.detailHTML(OC);
ok('13. 链上品种详情也补上三个新分区且发展历程留白',
  ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨'].every(function (x) {
    return oh.indexOf(x) >= 0;
  }) && oh.indexOf(DB.meta.no_data) >= 0);

// ---------- 4. 行情里程碑：真实数据、区间口径 ----------
const ms = D.computeMilestones([
  { ts: 1700000000, h: 110, l: 90, c: 100 },
  { ts: 1700100000, h: 130, l: 95, c: 120 },
  { ts: 1700200000, h: 125, l: 80, c: 90 }
], '测试源', '月 K', '区间说明');
ok('14. 区间最高 / 最低 / 涨跌 / 最大回撤计算正确',
  ms.ok && ms.high === 130 && ms.low === 80 &&
  Math.abs(ms.change_pct + 10) < 1e-6 &&
  Math.abs(ms.max_drawdown + 25) < 1e-6 && ms.bars === 3, JSON.stringify(ms));
ok('15. 样本不足不产出伪造极值',
  D.computeMilestones([{ ts: 1, h: 1, l: 1, c: 1 }], 'x', 'y', '').ok === false);
ok('16. 未取到历史数据时里程碑明确留白',
  D.milestoneHTML('BTC').indexOf('打开详情时会按需加载') >= 0 &&
  D.milestoneHTML('BTC').indexOf('— 暂无公开数据') >= 0);
D.milestones['BTC'] = ms;
const mh = D.milestoneHTML('BTC');
ok('17. 里程碑只叫「区间最高/最低」，不冒充历史高低',
  mh.indexOf('区间最高') >= 0 && mh.indexOf('区间最低') >= 0 &&
  mh.indexOf('不等同于上市以来全历史') >= 0 &&
  mh.indexOf('历史最高') < 0 && mh.indexOf('历史最低') < 0);
ok('18. 里程碑注明真实数据来源与样本根数',
  mh.indexOf('3 根') >= 0 && mh.indexOf('测试源') >= 0);
delete D.milestones['BTC'];

// ---------- 5. 链上币用本机真实采样算里程碑 ----------
D.recordOcSample(OC, 1700000000, 0.045);
D.recordOcSample(OC, 1700000300, 0.047);
D.loadMilestones(OC);
ok('19. 链上合约用真实报价采样算区间里程碑（非 K 线、非插值）',
  D.milestones[OC].ok === true &&
  D.milestones[OC].source.indexOf('本机真实报价采样') >= 0 &&
  D.milestones[OC].bars === 2, JSON.stringify(D.milestones[OC]));
ok('20. 时间线 / 档案 / 里程碑样式已随包提供',
  read(path.join(WWW, 'style.css')).indexOf('.tl-item') >= 0 &&
  read(path.join(WWW, 'style.css')).indexOf('.tl-date') >= 0);

console.log('\n=== ' + pass + '/' + (pass + fail) + ' 通过 ===');
process.exit(fail ? 1 : 0);
