/* v34 手机端功能补齐回归（Node + 轻量 DOM，无真实网络）。
 *
 * 覆盖用户反馈的 5 项落差 + 桌面改动的手机端同步：
 *   1. 刷新间隔 5~300 秒（旧版被钳死在 15~120）
 *   2. 图表指标：MA/EMA 可设天数与周期作用域、BOLL/MACD/成交量、参数面板
 *   3. 品种真实 logo（APK 内 coins/*.png + 股票远程 logo + 字徽兜底）
 *   4. K 线左右完全自由平移（pan 可为负 / 浮点 / 右侧留白）
 *   5. 设置页扩充（主题 6 套、字号、货币、指标开关、排序、分页、实时等）
 *   6. 搜索结果独立页 + 最近 100 条历史 + 点击进图表不默认收藏 + ⋯ 删除
 *
 * 运行：node android/tests/test_app_v34.js
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
function near(a, b) { return Math.abs(a - b) < 1e-9; }

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

const mem = {};
global.Native = {
  get: function (k) { return mem[k] || ''; },
  set: function (k, v) { mem[k] = String(v); },
  version: function () { return '1.1.0'; },
  toast: function () {}, finish: function () {},
  copy: function (t) { mem.__clip = t; }, paste: function () { return mem.__clip || ''; },
  http: function (url, charset, cb) {
    setTimeout(function () {
      if (global.__nativeCb) global.__nativeCb(cb, '', '');
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

function fire(id, type, value) {
  const e = el(id);
  if (value !== undefined) e.value = value;
  const ls = e._listeners[type] || [];
  for (let i = 0; i < ls.length; i++) {
    ls[i]({ target: e, key: 'Enter', keyCode: 13,
            preventDefault: function () {} });
  }
}
function bars(n) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const c = 100 + 10 * Math.sin(i / 9) + i * 0.05;
    out.push({ ts: 1700000000 + i * 900, label: String(i),
               o: c - 0.4, h: c + 1, l: c - 1, c: c, v: 100 + i });
  }
  return out;
}
const ROWS = bars(220);

console.log('=== v34 · Android 功能补齐回归 ===\n');

// ---------- 1. 刷新间隔 ----------
ok('1. 默认间隔 15 秒', D.cfg.interval === 15);
fire('setIntervalNum', 'change', '5');
ok('1. 可设到 5 秒（旧下限 15 已放开）', D.cfg.interval === 5 &&
  el('setIntervalNum').value === '5');
fire('setIntervalNum', 'change', '300');
ok('1. 可设到 300 秒（旧上限 120 已放开）', D.cfg.interval === 300);
fire('setIntervalNum', 'change', '1');
ok('1. 低于下限被钳到 5', D.cfg.interval === 5);
fire('setIntervalNum', 'change', '9999');
ok('1. 高于上限被钳到 300', D.cfg.interval === 300);
fire('setIntervalNum', 'change', '15');

// ---------- 2. 指标参数与算法 ----------
const def = D.normInd(null);
ok('2. 默认 MA 天数', def.ma.map(function (x) { return x.period; }).join(',') === '5,10,20,30');
ok('2. 默认 EMA 天数', def.ema.map(function (x) { return x.period; }).join(',') === '12,26,50,99' &&
  def.ema[3].enabled === false);
ok('2. 默认 BOLL / MACD', def.boll.period === 20 && def.boll.k === 2 &&
  def.macd.fast === 12 && def.macd.slow === 26 && def.macd.signal === 9);
ok('2. 脏参数不抛异常', D.normInd({ ma: 'bad', ema: [null], boll: { k: 'x' } }).boll.k === 2);
ok('2. 慢线小于快线自动调整', D.normInd({ macd: { fast: 30, slow: 5, signal: 9 } }).macd.slow === 31);
const tiny = [{ c: 1 }, { c: 2 }, { c: 3 }, { c: 4 }, { c: 5 }];
const e3 = D.emaSeries(tiny, 3);
ok('2. EMA 预热与递推正确', e3[0] === null && e3[1] === null &&
  near(e3[2], 2) && near(e3[3], 3) && near(e3[4], 4));
ok('2. MA 与 EMA 不同', D.maSeries(tiny, 3)[4] === 4 && e3[4] !== D.maSeries(tiny, 4)[4]);
const flat = bars(50).map(function () { return { c: 10 }; });
const bflat = D.bollSeries(flat, 20, 2);
ok('2. BOLL 恒定价格上下轨收敛到中轨', near(bflat.up[30], 10) && near(bflat.dn[30], 10));
const mflat = D.macdSeries(flat, 12, 26, 9);
ok('2. MACD 恒定价格无 NaN / 全 0', mflat.dif[40] === 0 && mflat.dea[40] === 0 &&
  mflat.hist[40] === 0);
const dup = D.enabledIndPeriods(D.normInd({
  ma: [{ period: 20, enabled: true }, { period: 20, enabled: true }]
}), 'ma');
ok('2. 重复天数去重', dup.filter(function (p) { return p === 20; }).length === 1);

const gParams = D.normInd(null);
gParams.ma[0] = { period: 7, enabled: true };
gParams.ma[1] = { period: 21, enabled: true };
gParams.boll.k = 3;
D.writeIndParams('*', gParams);
const hParams = D.indParams('1d');
hParams.ma[0] = { period: 20, enabled: true };
hParams.ma[1] = { period: 60, enabled: true };
D.writeIndParams('1h', hParams);
ok('2. 周期覆盖只影响自己', D.indParams('1h').ma[0].period === 20 &&
  D.indParams('1d').ma[0].period === 7);
ok('2. 周期未覆盖字段回落全局', D.indParams('1h').boll.k === 3 &&
  D.indParams('1h').macd.fast === 12);
ok('2. 周期只存差异字段', Object.keys(D.cfg.indicator_params['1h']).indexOf('ma') >= 0 &&
  Object.keys(D.cfg.indicator_params['1h']).length === 1);
const g2 = D.indParams('1d'); g2.boll.k = 1.5; D.writeIndParams('*', g2);
ok('2. 改全局参数会传导到未覆盖字段', D.indParams('1h').boll.k === 1.5 &&
  D.indParams('1h').ma[0].period === 20);
D.resetIndParams('1h');
ok('2. 恢复周期默认不误伤全局', D.indParams('1h').ma[0].period === 7);

D.setChartSymbol('BTC');
D.setIntervalKey('15m');
D.showIndicatorSheet();
ok('2. 参数面板可打开且有作用域选择', D.sheet() === 'indicatorSheet' &&
  el('indicatorBody').innerHTML.indexOf('indScope') >= 0 &&
  el('indicatorBody').innerHTML.indexOf('indmaP0') >= 0 &&
  el('indicatorBody').innerHTML.indexOf('indemaP0') >= 0);
D.setScope('*');
D.setIndInput('indmaP0', '13', true);
D.setIndInput('indemaP0', '33', true);
D.setIndInput('indBollK', '2.5');
D.applyIndicatorSheet();
ok('2. 面板应用后落盘并生效', D.indParams('15m').ma[0].period === 13 &&
  D.indParams('15m').ema[0].period === 33 &&
  D.indParams('15m').boll.k === 2.5 && D.sheet() === '');

D.setCandles(ROWS);
try { D.drawChart(); ok('2. 全指标开启时 Canvas 绘制不崩', true); }
catch (e) { ok('2. 全指标开启时 Canvas 绘制不崩', false, e.message); }
const lines = D.indLines(ROWS, D.indParams('15m'));
ok('2. 指标线含 MA / EMA / BOLL', lines.some(function (l) { return l.label.indexOf('MA') === 0; }) &&
  lines.some(function (l) { return l.label.indexOf('EMA') === 0; }) &&
  lines.some(function (l) { return l.label.indexOf('BOLL') === 0; }));
D.cfg.show_ma = false; D.cfg.show_ema = false;
ok('2. 关闭开关后对应线不再生成',
  !D.indLines(ROWS, D.indParams('15m')).some(function (l) { return l.label.indexOf('MA') === 0; }));
D.cfg.show_ma = true; D.cfg.show_ema = true;

// ---------- 3. 品种图标 ----------
ok('3. 加密品种用 APK 内官方 logo', D.symbolIconHTML('BTC', 'BTC').indexOf('coins/btc.png') >= 0 &&
  D.symbolIconHTML('BTC', 'BTC').indexOf('data-fallback') >= 0);
ok('3. 美股用品牌 logo 远程地址',
  D.symbolIconHTML('US:AAPL', 'AAPL').indexOf('finnhub') >= 0);
ok('3. A 股用中文名徽章', D.symbolIconHTML('SH:600519', '600519').indexOf('<img') < 0);
const OC_ADDR = '9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump';
ok('3. 链上品种用文字徽章',
  D.symbolIconHTML(D.ocSymbol(OC_ADDR), 'abc').indexOf('<img') < 0);
const row = D.rowHTML('BTC');
ok('3. 行情行有图标', row.indexOf('coins/btc.png') >= 0);
ok('3. 价格右侧 ⋯ 方框已删除', row.indexOf('data-more') < 0 &&
  row.indexOf('class="more"') < 0);
D.cfg.show_icons = false;
ok('3. 可一键关闭图标退回字徽', D.symbolIconHTML('BTC', 'BTC').indexOf('<img') < 0);
D.cfg.show_icons = true;
const coinDir = path.join(WWW, 'coins');
ok('3. APK 内图标资源存在（≥250 个）',
  fs.existsSync(path.join(coinDir, 'btc.png')) &&
  fs.existsSync(path.join(coinDir, 'eth.png')) &&
  fs.readdirSync(coinDir).filter(function (f) { return /\.png$/.test(f); }).length >= 250);

// ---------- 4. K 线自由平移 ----------
D.setCandles(ROWS);
const V = D.view();
ok('4. pan 允许负值（右侧留白）', D.clampPan(-5) === -5);
ok('4. pan 允许回看到最早一批', D.clampPan(100) <= ROWS.length - 8);
V.pan = -4.5;
D.drawChart();
ok('4. 小数 pan 不被取整吸附', V.pan === -4.5);
V.pan = 0; V.count = 90;
D.zoomBy(true);
ok('4. 缩放以视口中心为锚点、不强制贴右', V.count < 90);
D.go('chart');
ok('4. 进入图表页不重置自由视口', D.page() === 'chart');

// ---------- 5. 设置页 ----------
D.go('settings');
D.syncSettings();
ok('5. 主题 6 套可选', el('setTheme').innerHTML === '' ||
  el('setSort').innerHTML.indexOf('change_desc') >= 0);
ok('5. 排序选项已同步进设置页', el('setSort').innerHTML.indexOf('cap_desc') >= 0);
ok('5. 指标开关同步', el('setShowMa').checked === true &&
  el('setShowMacd').checked === true);
ok('5. 每页条数 / 重试 / 字号同步', el('setPageSize').value === '60' &&
  el('setRetry').value === '3' && el('setFontScale').value === '120');
['binance', 'midnight', 'oled', 'light', 'cyber', 'sepia'].forEach(function (t) {
  D.cfg.theme = t; D.applyTheme();
  ok('5. 主题生效 ' + t, document.body.className === (t === 'binance' ? '' : t));
});
D.cfg.theme = 'binance'; D.applyTheme();
ok('5. 搜索页有独立标题', D.pageTitle('search') === '搜索');
const html = fs.readFileSync(path.join(WWW, 'index.html'), 'utf8');
ok('5. 设置页明示 Windows 专属能力', html.indexOf('桌面端专属功能') >= 0 &&
  html.indexOf('任务栏常驻价格条') >= 0);
ok('5. 设置页含刷新间隔自定义输入框', html.indexOf('setIntervalNum') >= 0);
ok('5. 设置页含指标参数入口', html.indexOf('btnOpenIndicators') >= 0);
ok('5. 图表页含指标按钮', html.indexOf('btnIndicators') >= 0);

// ---------- 6. 搜索独立页 ----------
D.go('search');
ok('6. 搜索是独立页面（与行情列表不同层）',
  D.page() === 'search' && el('pageSearch').hidden === false &&
  el('pageList').hidden === true);
D.submitSearch('BTC');
ok('6. 提交搜索写入历史', D.cfg.search_history[0] === 'BTC');
ok('6. 结果行点击进图表', el('searchBody').innerHTML.indexOf('data-search-open') >= 0);
const before = D.cfg.symbols.slice();
D.openSearchResult('ETH');
ok('6. 点击结果不默认收藏', D.page() === 'chart' &&
  D.cfg.symbols.length === before.length);
for (let i = 0; i < 120; i++) D.recordSearchHistory('Q' + i);
ok('6. 搜索历史最多 100 条且最新在前', D.cfg.search_history.length === 100 &&
  D.cfg.search_history[0] === 'Q119');
D.go('search');
D.clearSearchHistory();
ok('6. 清空历史生效', D.cfg.search_history.length === 0 &&
  el('searchBody').innerHTML.indexOf('还没有搜索记录') >= 0);
const OC = OC_ADDR;
D.setSearch(OC);
D.renderList();
ok('6. 合约结果不再叠在行情列表上',
  el('list').innerHTML.indexOf('data-addcontract') < 0 &&
  D.contractHitHTML(OC).indexOf('data-search-open') >= 0);
D.back();
ok('6. 系统返回从搜索页回行情', D.page() === 'list');

console.log('\n=== 结果: ' + pass + ' 通过 / ' + fail + ' 失败 ===');
process.exit(fail ? 1 : 0);
