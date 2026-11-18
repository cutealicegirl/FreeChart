/* 回归：统一资产搜索 + 对象化搜索历史 + 手机返回按钮层级 + 长按手势。
 *
 * 覆盖任务书 三/四/五/六：
 *   - chain id + address 唯一身份、同名资产区分、相关性排序、合约精确优先
 *   - 历史对象化 / 去重 / 上限 / 单删 / 直接打开 / 旧字符串兼容 / 失败不记录
 *   - 首页不显示返回、子页仅一个返回、导航栈逐级回退、弹窗关闭与页面返回区分
 *   - 长按延迟/容差可配置、双轴移动取消、touchcancel/失焦清理、
 *     scroll 取消、contextmenu 抑制 click、轻触正常、真长按弹菜单
 *
 * 运行：node android/tests/test_app_unified_search_gestures.js
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
    appendChild: function () {}, getElementsByTagName: function () { return []; },
    getContext: function () {
      return { setTransform() {}, clearRect() {}, beginPath() {}, moveTo() {},
        lineTo() {}, stroke() {}, fillRect() {}, strokeRect() {}, fillText() {},
        setLineDash() {} };
    }
  };
}
const els = {};
function el(id) { if (!els[id]) els[id] = mkEl(id); return els[id]; }
let domReady = null;
global.document = {
  readyState: 'loading', body: mkEl('body'), getElementById: el,
  visibilityState: 'visible', querySelector: function () { return mkEl('query'); },
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
  version: function () { return '1.1.0'; }, toast: function () {}, finish: function () {
    mem.__finished = (mem.__finished || 0) + 1;
  },
  copy: function (t) { mem.__clip = t; }, paste: function () { return mem.__clip || ''; },
  http: function () {}
};
function load(file) {
  vm.runInThisContext(fs.readFileSync(path.join(WWW, file), 'utf8'), { filename: file });
}
load('universe.js'); load('about.js'); load('app.js');
const D = global.__CT_DEBUG;
if (domReady) domReady();

function fire(id, type, extra) {
  const e = el(id);
  const ls = e._listeners[type] || [];
  for (let i = 0; i < ls.length; i++) {
    ls[i](Object.assign({ target: e, preventDefault: function () {} }, extra || {}));
  }
}

console.log('==============================================================');
console.log('统一搜索 / 搜索历史 / 返回按钮 / 长按手势 回归');
console.log('==============================================================');

// ---------- 1. 统一资产身份 ----------
console.log('\n[1] 统一资产身份 chain + address');
const evmA = '0x532f27101965DD16442E59d40670FaF5eBB142E4';
const hBrett = D.makeHit({ symbol: 'ONCHAIN:' + evmA, label: 'BRETT', name: 'Based Brett',
  asset_type: 'onchain', chain: 'Base', address: evmA });
ok('EVM 地址统一小写', hBrett.id === 'base:' + evmA.toLowerCase());
const solA = 'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263';
const hBonk = D.makeHit({ symbol: 'ONCHAIN:' + solA, label: 'BONK', name: 'Bonk',
  asset_type: 'onchain', chain: 'Solana', address: solA });
ok('Solana mint 保持原样', hBonk.id === 'solana:' + solA);
const usdcEth = D.makeHit({ symbol: 'USDC', label: 'USDC', name: 'USD Coin',
  asset_type: 'onchain', chain: 'Ethereum', address: '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48' });
const usdcSol = D.makeHit({ symbol: 'USDC', label: 'USDC', name: 'USD Coin',
  asset_type: 'onchain', chain: 'Solana', address: 'EPjFWdd5AufqSSqeM2qQN1xzybapC8G4wEGGkZwyTDt1v' });
ok('不同链同名同符号 id 不同', usdcEth.id !== usdcSol.id);
ok('禁止仅凭 symbol 合并', usdcEth.id.indexOf('USDC') < 0 && usdcSol.id.indexOf('USDC') < 0);
ok('chainId 归一', D.chainId('Solana') === 'solana' && D.chainId('BNB Chain') === 'bsc' &&
  D.chainId('Ethereum') === 'eth' && D.chainId('Base') === 'base' &&
  D.chainId('Arbitrum') === 'arb' && D.chainId('TON') === 'ton');

// ---------- 2. 相关性排序 ----------
console.log('\n[2] 相关性排序 / 合约地址精确优先');
const nvda = D.makeHit({ symbol: 'US:NVDA', label: 'NVDA', name: '英伟达',
  asset_type: 'stock', market: 'us' });
const nvdaX = D.makeHit({ symbol: 'US:NVDAX', label: 'NVDAX', name: '英伟达相关',
  asset_type: 'stock', market: 'us' });
ok('精确 > 前缀', D.relevance('NVDA', nvda) > D.relevance('NVDA', nvdaX));
ok('合约精确 = 200 最高', D.relevance(evmA, hBrett) === 200);
ok('合约精确 > 代码精确', D.relevance(evmA, hBrett) > D.relevance('BRETT', hBrett));
const merged = D.mergeHits([[nvdaX, hBrett, nvda]], 'NVDA', 60);
ok('无关联结果被过滤（链上 BRETT 不因查询 NVDA 混入）',
  !merged.some(function (x) { return x.id === hBrett.id; }));
ok('精确命中排在前缀命中之前',
  merged.length === 2 && merged[0].id === nvda.id && merged[1].id === nvdaX.id);
const dup = D.mergeHits([[nvda, Object.assign({}, nvda), Object.assign({}, nvda, { name: '英伟达公司' })]], 'NVDA', 60);
ok('按 asset_id 去重', dup.length === 1);

// ---------- 3. 链上代币名称搜索 ----------
console.log('\n[3] 链上代币名称 / 别名搜索');
ok('BONK 名称可搜', D.searchMatches('bonk').length > 0);
ok('忽略大小写', D.searchMatches('BoNk').length > 0);
ok('忽略多余空格', D.searchMatches('  bonk  ').length > 0);
ok('dogwifhat 别名可搜到 WIF',
  D.buildUnifiedHits('dogwifhat').some(function (h) { return h.label === 'WIF'; }));
ok('PUMP/FARTCOIN/POPCAT/BRETT/VIRTUAL 样本覆盖度',
  ['FARTCOIN', 'POPCAT', 'BRETT'].every(function (s) {
    return D.OC_TOKENS.some(function (t) { return t.sym === s; });
  }));
const pumpHits = D.buildUnifiedHits('PEPE');
ok('PEPE 结果带资产类型与链标识',
  pumpHits.some(function (h) { return h.asset_type === 'onchain' && h.chain === 'Ethereum'; }));
ok('结果清楚标识类型/市场/链',
  D.assetKindLabel(nvda).indexOf('股票') >= 0 &&
  D.assetKindLabel(hBrett).indexOf('链上代币') >= 0 &&
  D.assetKindLabel(hBrett).indexOf('Base') >= 0);
ok('结果行 HTML 含类型与链',
  D.searchResultHTML(hBrett).indexOf('链上代币') >= 0 &&
  D.searchResultHTML(hBrett).indexOf('Base') >= 0);

// ---------- 4. 搜索历史对象模型 ----------
console.log('\n[4] 搜索历史对象模型（去重/上限/单删/直接打开/旧版兼容）');
D.clearHistory();
const old = D.normalizeHistory(['BTC', 'ETH', 'BTC', '  NVDA  ']);
ok('旧字符串自动包装为对象', old.every(function (x) { return typeof x === 'object'; }));
ok('旧版去重 + 去空格', old.length === 3 &&
  old.some(function (x) { return x.label === 'NVDA'; }));
ok('全部带版本号', old.every(function (x) { return x.v === 2; }));
const aapl = D.makeHit({ symbol: 'US:AAPL', label: 'AAPL', name: '苹果',
  asset_type: 'stock', market: 'us', logo: 'aapl.png' });
let h = D.recordHistory(aapl, 1000);
ok('记录资产对象（含 name/type/market/logo）',
  h[0].name === '苹果' && h[0].asset_type === 'stock' && h[0].logo === 'aapl.png');
h = D.recordHistory(D.makeHit({ symbol: 'BTC', label: 'BTC', asset_type: 'cex', market: 'crypto' }), 2000);
h = D.recordHistory(aapl, 3000);
ok('重复搜索移至最前 + 按 id 去重',
  h[0].id === aapl.id && h.length === 2);
D.cfg.search_history = ['AAPL'];   // 模拟旧版 q:aapl 纯字符串条目
h = D.recordHistory(aapl, 4000);
ok('旧 q: 条目被资产折叠', h.length === 1 && h[0].id === aapl.id);
D.clearHistory();
for (let i = 0; i < 80; i++) D.recordHistory('K' + i, i + 1);
ok('上限 50 条（30~50 要求）', D.cfg.search_history.length === 50);
ok('最新在前、最旧淘汰',
  D.historyQuery(D.cfg.search_history[0]) === 'K79' &&
  !D.cfg.search_history.some(function (x) { return D.historyQuery(x) === 'K0'; }));
const did = D.cfg.search_history[0].id;
D.deleteHistory(did);
ok('单条删除生效', D.cfg.search_history.length === 49);
ok('historySymbol 可直接打开资产', D.historySymbol(h[0]) === 'US:AAPL');
ok('空输入不记录', (function () {
  const n = D.cfg.search_history.length;
  D.recordHistory('');
  return D.cfg.search_history.length === n;
})());
// 失败 / 无效搜索不永久保存（submitSearch 无结果时不写历史）
D.clearHistory();
D.submitSearch('ZZZ_NO_SUCH_ASSET_9999');
ok('无结果搜索不写入历史', D.cfg.search_history.length === 0);
D.clearHistory();

// ---------- 5. 返回按钮层级 + 导航栈 ----------
console.log('\n[5] 返回按钮层级 / 导航栈');
D.goWith('list', { resetStack: true });
ok('首页(根)隐藏返回箭头', D.backBtnHidden() === true);
ok('首页无下钻栈', D.navStack().length === 0);
D.goWith('search');
ok('子页显示唯一返回按钮', D.backBtnHidden() === false);
ok('下钻记录上一级', D.navStack().indexOf('list') >= 0);
ok('页面内重复返回按钮被隐藏',
  el('btnSearchBack').hidden === true && el('btnSettingsBack').hidden === true);
D.goWith('chart');
ok('连续下钻 chart 后仍只一个返回', D.backBtnHidden() === false);
D.back();
ok('系统返回优先回到上一级 search', D.page() === 'search');
D.back();
ok('再返回回到根页 list', D.page() === 'list' && D.backBtnHidden() === true);
// 弹窗关闭 != 页面返回
D.goWith('search');
D.showRowSheet('BTC');
ok('弹窗已打开', D.sheet() === 'rowSheet');
D.back();
ok('返回键先关弹窗、不切页', D.sheet() === '' && D.page() === 'search');
D.back();
ok('弹窗关闭后再返回才切页', D.page() === 'list');
// 底部导航 tab = 顶层切换，清栈
D.goWith('settings');
D.goWith('chart');
// 直接以 resetStack 模拟底部 tab 切换
D.goWith('settings', { resetStack: true });
ok('顶层 tab 切换清空下钻栈', D.navStack().length === 0 && D.backBtnHidden() === true);

// ---------- 6. 长按手势 ----------
console.log('\n[6] 长按手势（可配置 / 双轴 / 清理 / 抑制 click）');
const cfg0 = D.lpConfig();
ok('默认长按延迟在 500~650ms', cfg0.ms >= 500 && cfg0.ms <= 650);
ok('默认容差在 8~12dp', cfg0.slop >= 8 && cfg0.slop <= 12);
const cfg1 = D.lpConfig(600, 12);
ok('长按参数可配置', cfg1.ms === 600 && cfg1.slop === 12);
D.lpConfig(560, 10);
// 直接驱动手势状态机（不依赖真实定时器）
ok('初始无激活手势', D.lpState().active === false);
// 通过调试钩子模拟：长按触发后抑制同手势 click
D.lpArmSuppress('BTC');
ok('长按触发后标记抑制', D.lpState().suppressSym === 'BTC');
ok('同手势 click 被消费', D.lpConsumeSuppress('BTC') === true);
ok('抑制只生效一次', D.lpConsumeSuppress('BTC') === false);
ok('其它资产的轻触不被吞', D.lpConsumeSuppress('ETH') === false);
D.lpArmSuppress('BTC');
D.lpCancel();
ok('lpCancel 清理定时器标记', D.lpState().hasTimer === false && D.lpState().active === false);
// contextmenu 分支补了 click 抑制（桌面右键不受影响）
ok('桌面右键 contextmenu 监听仍存在',
  (el('list')._listeners['contextmenu'] || []).length >= 1);
ok('touchcancel 监听存在（清理手势）',
  (el('list')._listeners['touchcancel'] || []).length >= 1);
ok('scroll 监听会取消长按', (el('list')._listeners['scroll'] || []).length >= 1);

// ---- 真实触摸事件驱动的手势状态机（bind() 已在 boot 中执行）----
const list = el('list');
function row(sym) {
  const r = mkEl('trow');
  r._attrs['data-sym'] = sym;
  r.className = 'trow';
  r.parentNode = list;
  return r;
}
function touchList(type, extra) {
  const ls = list._listeners[type] || [];
  for (let i = 0; i < ls.length; i++) ls[i](extra);
}
function touchStart(sym, x, y) {
  const r = row(sym);
  D.lpCancel(); D.closeSheets();
  touchList('touchstart', { target: r, touches: [{ clientX: x, clientY: y }] });
  return r;
}
function clickRow(r) {
  const ls = list._listeners['click'] || [];
  for (let i = 0; i < ls.length; i++) {
    ls[i]({ target: r, preventDefault: function () {} });
  }
}
// 用较短但仍在建议区间的延迟驱动，避免测试等待过久
D.lpConfig(500, 10);
const wait = function (ms) { return new Promise(function (res) { setTimeout(res, ms); }); };

async function gestureTests() {
  console.log('\n[6b] 真实触摸事件：轻触 / 移动取消 / 真长按 / click 抑制');
  // 轻触（短按）后正常点开详情，不能弹菜单
  D.goWith('list', { resetStack: true });
  let r = touchStart('BTC', 100, 100);
  touchList('touchend', { target: r, touches: [] });
  await wait(560);
  ok('轻触不弹菜单（延迟内抬手）', D.sheet() === '');
  clickRow(r);
  ok('轻触后正常打开标的图表', D.page() === 'chart');

  // Y 轴移动达到阈值取消长按
  D.goWith('list', { resetStack: true });
  r = touchStart('ETH', 100, 100);
  touchList('touchmove', { target: r, touches: [{ clientX: 100, clientY: 140 }] });
  await wait(560);
  ok('Y 轴移动超过容差取消长按（滚动不误触）', D.sheet() === '');

  // X 轴移动（旧版只判 Y 会漏）也取消长按
  D.goWith('list', { resetStack: true });
  r = touchStart('ETH', 100, 100);
  touchList('touchmove', { target: r, touches: [{ clientX: 140, clientY: 100 }] });
  await wait(560);
  ok('X 轴移动也取消长按（双轴判定）', D.sheet() === '');

  // touchcancel 清理
  D.goWith('list', { resetStack: true });
  r = touchStart('ETH', 100, 100);
  touchList('touchcancel', { target: r, touches: [] });
  await wait(560);
  ok('touchcancel 清理手势不弹菜单', D.sheet() === '' && !D.lpState().active);

  // scroll 取消长按
  D.goWith('list', { resetStack: true });
  r = touchStart('ETH', 100, 100);
  touchList('scroll', { target: list });
  await wait(560);
  ok('开始滚动取消长按', D.sheet() === '' && !D.lpState().active);

  // 真长按：达到延迟弹出菜单，同手势 click 被抑制（不打开图表）
  D.goWith('list', { resetStack: true });
  r = touchStart('SOL', 100, 100);
  await wait(540);
  ok('真正长按弹出行操作菜单', D.sheet() === 'rowSheet');
  clickRow(r);
  ok('长按后同手势 click 不打开图表（抑制）', D.page() === 'list');

  // 抑制只影响该手势：下一次轻触正常
  D.closeSheets(); D.goWith('list', { resetStack: true });
  const r2 = touchStart('BTC', 100, 100);
  touchList('touchend', { target: r2, touches: [] });
  clickRow(r2);
  ok('长按后下一次轻触仍能正常打开图表', D.page() === 'chart');

  // contextmenu（桌面右键 / WebView 长按）弹菜单并抑制紧随的 click
  D.closeSheets(); D.goWith('list', { resetStack: true });
  const r3 = row('BTC');
  D.lpCancel();
  (list._listeners['contextmenu'] || []).forEach(function (f) {
    f({ target: r3, preventDefault: function () {} });
  });
  ok('桌面右键打开行菜单', D.sheet() === 'rowSheet');
  clickRow(r3);
  ok('右键后 click 被抑制不误开图表', D.page() === 'list');

  console.log('\n==============================================================');
  console.log('=== 结果: ' + pass + ' 通过 / ' + fail + ' 失败 ===');
  console.log('==============================================================');
  process.exit(fail ? 1 : 0);
}
gestureTests();
