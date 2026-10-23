// 端到端交互测试：node tools/test_browser.mjs [baseUrl]
import { Browser } from './lib/cdp.mjs';
import { readdirSync, rmSync } from 'node:fs';
const base = process.argv[2] || 'http://127.0.0.1:5188';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const pad = (n) => String(n).padStart(2, "0");
const TODAY = new Date();
const YMD = TODAY.getFullYear() + "-" + pad(TODAY.getMonth() + 1) + "-" + pad(TODAY.getDate());
const CN_DATE = TODAY.getFullYear() + "年" + (TODAY.getMonth() + 1) + "月" + TODAY.getDate() + "日";
const PAST = new Date(TODAY.getTime() - 86400000);
const PAST_YMD = PAST.getFullYear() + "-" + pad(PAST.getMonth() + 1) + "-" + pad(PAST.getDate());
const results = [];
// 测试会清空本地断语缓存（data/narratives），请勿在有真实 AI 断语时运行
function clearNarratives() {
  try { for (const f of readdirSync('data/narratives')) if (f.endsWith('.json')) rmSync('data/narratives/' + f); } catch (e) {}
}
clearNarratives();
const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail: detail === undefined ? '' : detail }); };

const b = await Browser.launch({ width: 1440, height: 900 });
const p = await b.newPage({ width: 1440, height: 900 });

// 1. 初始状态
await p.goto(base + '/', { settleMs: 1800 });
await p.eval(() => { localStorage.clear(); });
await p.goto(base + '/', { settleMs: 1800 });
let s = await p.eval(() => ({
  castHidden: document.querySelector('#cast-btn').hidden,
  readingHidden: document.querySelector('#reading').hidden,
  facts: document.querySelectorAll('#today-facts > div').length,
  dial: document.querySelectorAll('#dial .t24').length,
  tri: document.querySelectorAll('#dial .tri').length,
  hero: document.querySelector('#hero-title').textContent,
  date: document.querySelector('#date-greg').textContent,
}));
check('首屏：起卦按钮可见', !s.castHidden);
check('首屏：阅读区隐藏', s.readingHidden);
check('首屏：今日历 7 项', s.facts === 7, s.facts);
check('罗盘：二十四山 24 字', s.dial === 24, s.dial);
check('罗盘：八卦 8 个可点', s.tri === 8, s.tri);
check('首屏：标题与日期', s.hero === '今日一卦' && s.date === CN_DATE, s.hero + ' ' + s.date);

// 2. 点击八卦
await p.eval(() => document.querySelector('#dial .tri[data-num="1"]').dispatchEvent(new MouseEvent('click', { bubbles: true })));
const cap = await p.eval(() => document.querySelector('#dial-cap').textContent);
check('点八卦更新说明', /乾/.test(cap) && /西北/.test(cap), cap);

// 3. 起卦
const t0 = Date.now();
await p.eval(() => document.querySelector('#cast-btn').click());
await sleep(120);
const casting = await p.eval(() => document.querySelector('#dial').classList.contains('is-casting'));
check('起卦：罗盘进入旋转状态', casting);
await sleep(4200);
s = await p.eval((ymd) => ({
  open: document.querySelector('#reading').classList.contains('is-open'),
  hidden: document.querySelector('#reading').hidden,
  title: document.querySelector('#reading-title').textContent,
  sub: document.querySelector('#hex-sub').textContent,
  stamp: document.querySelector('#score-stamp .stamp-score').textContent,
  areas: document.querySelectorAll('#areas li').length,
  hours: document.querySelectorAll('#hours li').length,
  cast: JSON.parse(localStorage.getItem('yigua.cast.' + ymd) || 'null'),
  history: JSON.parse(localStorage.getItem('yigua.history') || '[]'),
  dialHex: document.querySelectorAll('#dial .hex-group .line-group').length,
  badge: document.querySelector('#source-badge').textContent,
  badgeHidden: document.querySelector('#source-badge').hidden,
  status: document.querySelector('#reading-status').textContent,
  readText: document.querySelector('#reading-text').textContent.length,
  scrollY: Math.round(window.scrollY),
}), YMD);
check('起卦：阅读区展开', s.open && !s.hidden, JSON.stringify({ open: s.open, hidden: s.hidden }));
check('起卦：卦名有值', s.title.length >= 2 && s.title !== '—', s.title + ' / ' + s.sub);
check('起卦：印章分数', /^\d+$/.test(s.stamp), s.stamp);
check('起卦：六事 6 条', s.areas === 6, s.areas);
check('起卦：十二时辰 12 条', s.hours === 12, s.hours);
check('起卦：卦象记入本机', typeof s.cast === 'string' && s.cast.includes('T'), s.cast);
check('起卦：历史 +1', s.history.length === 1 && s.history[0].name === s.title, JSON.stringify(s.history[0] || null));
check('起卦：盘心画出六爻', s.dialHex === 6, s.dialHex);
check('无 API：显示本地断语', s.badgeHidden === false && /本地断语/.test(s.badge), s.badge + ' / ' + s.status.slice(0, 20));
check('无 API：正文非空', s.readText > 60, s.readText);
check('起卦后自动滚到阅读区', s.scrollY > 300, s.scrollY);
check('起卦耗时合理', Date.now() - t0 < 15000, Date.now() - t0);

// 4. 设置里测试连接 + 保存 API
await p.eval(() => document.querySelector('.nav-btn[data-view="settings"]').click());
await sleep(400);
await p.eval(() => {
  document.querySelector('#api-base').value = 'http://127.0.0.1:5199/v1';
  document.querySelector('#api-key').value = 'test-key';
  document.querySelector('#api-model').value = 'mock-model';
  document.querySelector('#test-api').click();
});
await sleep(900);
const testStatus = await p.eval(() => ({ text: document.querySelector('#api-status').textContent, cls: document.querySelector('#api-status').className }));
check('设置：测试连接成功', /连接正常/.test(testStatus.text), testStatus.text + ' / ' + testStatus.cls);
await p.eval(() => document.querySelector('#save-settings').click());
await sleep(4500);
s = await p.eval(() => ({
  badge: document.querySelector('#source-badge').textContent,
  poem: document.querySelector('#poem').textContent,
  text: document.querySelector('#reading-text').textContent,
  status: document.querySelector('#reading-status').textContent,
  api: JSON.parse(localStorage.getItem('yigua.api') || '{}'),
  dialogOpen: document.querySelector('#settings').open,
}));
check('AI：徽标为 AI 解卦', s.badge === 'AI 解卦', s.badge);
check('AI：签诗来自模型', /炉中火候自分明/.test(s.poem), s.poem.slice(0, 30));
check('AI：解卦正文来自模型', /今日庚午，火气偏旺/.test(s.text), s.text.slice(0, 30));
check('AI：状态提示模型', /mock-model/.test(s.status), s.status.slice(0, 40));
check('设置：Key 存在 localStorage', s.api.key === 'test-key' && s.api.model === 'mock-model', JSON.stringify(s.api));
check('设置：保存后关闭', !s.dialogOpen);

// 5. 刷新后读缓存
await p.goto(base + '/?cast=08:12', { settleMs: 2600 });
await sleep(2500);
s = await p.eval(() => ({ badge: document.querySelector('#source-badge').textContent, poem: document.querySelector('#poem').textContent }));
check('刷新：AI 断语命中缓存', s.badge === 'AI 解卦' && /炉中火候/.test(s.poem), s.badge);

// 6. 历史回顾
await p.eval((past) => {
  const h = JSON.parse(localStorage.getItem('yigua.history') || '[]');
  h.unshift({ date: past, name: '地天泰', symbol: '䷊', score: 66, castAt: past + 'T09:10' });
  localStorage.setItem('yigua.history', JSON.stringify(h));
}, PAST_YMD);
await p.goto(base + '/', { settleMs: 2400 });
await p.eval(() => document.querySelectorAll('#history button')[0].click());
await sleep(1800);
s = await p.eval(() => ({
  bar: Boolean(document.querySelector('#reading .review-bar')),
  hero: document.querySelector('#hero-title').textContent,
  date: document.querySelector('#date-greg').textContent,
  castHidden: document.querySelector('#cast-btn').hidden,
  readVisible: !document.querySelector('#reading').hidden,
}));
check('回顾：出现回顾条', s.bar);
check('回顾：标题变往日一卦', s.hero === '往日一卦', s.hero);
check('回顾：日期为昨日', s.date === PAST.getFullYear() + "年" + (PAST.getMonth() + 1) + "月" + PAST.getDate() + "日", s.date);
check('回顾：不可起卦', s.castHidden);
check('回顾：阅读区可见', s.readVisible);

// 7. 移动端起卦
const b2 = await Browser.launch({ width: 390, height: 844 });
const m = await b2.newPage({ width: 390, height: 844, mobile: true });
await m.goto(base + '/', { settleMs: 1800 });
await m.eval(() => { localStorage.clear(); location.reload(); });
await sleep(2200);
await m.eval(() => document.querySelector('#cast-btn').click());
await sleep(3800);
const ms = await m.eval(() => ({
  open: !document.querySelector('#reading').hidden,
  title: document.querySelector('#reading-title').textContent,
  overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
  stampBox: document.querySelector('#score-stamp').getBoundingClientRect().toJSON(),
}));
check('移动端：起卦后阅读区展开', ms.open && ms.title.length > 1, ms.title);
check('移动端：无横向溢出', !ms.overflow);
check('移动端：印章在视口内', ms.stampBox.left >= 0 && ms.stampBox.right <= 390, JSON.stringify(ms.stampBox));
await b2.close();

// 8. API 出错时回落到本地断语
clearNarratives();
const b4 = await Browser.launch({ width: 1440, height: 900 });
const e = await b4.newPage({ width: 1440, height: 900 });
await e.goto(base + '/', { settleMs: 1800 });
await e.eval(() => { localStorage.clear(); localStorage.setItem('yigua.api', JSON.stringify({ base: 'http://127.0.0.1:5999/v1', key: 'x', model: 'm' })); });
await e.goto(base + '/', { settleMs: 2000 });
await e.eval(() => document.querySelector('#cast-btn').click());
await sleep(5000);
const es = await e.eval(() => ({
  badge: document.querySelector('#source-badge').textContent,
  status: document.querySelector('#reading-status').textContent,
  retry: Boolean(document.querySelector('#retry-ai')),
  text: document.querySelector('#reading-text').textContent.length,
}));
check('API 出错：回落本地断语', es.badge === '本地断语' && es.text > 60, es.badge + ' / ' + es.text);
check('API 出错：给出原因与重试', /连不上/.test(es.status) && es.retry, es.status.slice(0, 40));
await b4.close();

// 9. 减少动效
const b3 = await Browser.launch({ width: 1440, height: 900 });
const r = await b3.newPage({ width: 1440, height: 900, reducedMotion: true });
await r.goto(base + '/', { settleMs: 1600 });
await r.eval(() => { localStorage.clear(); location.reload(); });
await sleep(2000);
const t1 = Date.now();
await r.eval(() => document.querySelector('#cast-btn').click());
await sleep(800);
const rs = await r.eval(() => ({ open: !document.querySelector('#reading').hidden, title: document.querySelector('#reading-title').textContent }));
check('减少动效：800ms 内直接出卦', rs.open && rs.title.length > 1, Date.now() - t1 + 'ms ' + rs.title);
await b3.close();

await b.close();
const failed = results.filter((x) => !x.ok);
for (const x of results) console.log((x.ok ? 'PASS' : 'FAIL') + '  ' + x.name + (x.detail ? '  [' + x.detail + ']' : ''));
console.log('\n' + (results.length - failed.length) + '/' + results.length + ' passed');
process.exit(failed.length ? 1 : 0);
