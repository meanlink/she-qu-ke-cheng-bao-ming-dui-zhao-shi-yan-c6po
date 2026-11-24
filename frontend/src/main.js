import {api, experiment, session, state} from './api.js';
import {attendancePage} from './attendance.js';
import {capacityPage} from './capacity.js';
import {changeInvitationArm, clearancePage, correctionPage, invitationPage} from './controls.js';
import {observationPage} from './observations.js';
import {planForm, planPage} from './plan.js';
import {reviewPage} from './review.js';
import {rosterPage} from './roster.js';
import {sessionAction} from './session-actions.js';
import {badge, escape, roles} from './view.js';
import {waitlistPage} from './waitlist.js';

const root = document.querySelector('#app');
const tabs = {
  plan: ['课程方案', planPage], clearance: ['资格预审', clearancePage, '/controls'], roster: ['随机分组', rosterPage],
  delivery: ['邀请送达', invitationPage, '/controls'],
  capacity: ['场次容量', capacityPage, '/session'], waitlist: ['席位候补', waitlistPage, '/session'],
  attendance: ['签到交接', attendancePage, '/session'], observation: ['报名观测', observationPage],
  correction: ['观测更正', correctionPage, '/controls'], review: ['复盘审批', reviewPage, '/snapshot/status'],
};
const instructorTabs = new Set(['capacity', 'waitlist', 'attendance']);
const demo = {organizer: 'lin@community.demo', observer: 'zhou@community.demo', reviewer: 'lu@community.demo', instructor: 'tang@community.demo'};
let requestNumber = 0;
let flash = '';

function route() {
  const [, code, tab] = location.hash.split('/');
  return {code: code || null, tab: Object.hasOwn(tabs, tab) ? tab : 'plan'};
}

const href = (code, tab = 'plan') => `#/${encodeURIComponent(code)}/${tab}`;

function loginPage() {
  root.innerHTML = `<main class="login-page">
    <section class="login-feature"><div class="brand"><span class="mark">邻</span><span class="eyebrow">祥和里社区教育合作社</span></div>
    <div><h1>邻里课程<br>试验簿</h1><p>比较两种课程邀请方式，从原始分组追溯每一份报名与到课结果。</p></div>
    <span class="eyebrow">课程方案　/　随机分组　/　报名观测　/　复盘审批</span></section>
    <section class="login-content"><h2>登录实验档案</h2><p class="muted">使用你的岗位账号进入工作台。</p>
    <form class="stack" data-action="login"><label>邮箱<input required type="email" name="email" autocomplete="username"></label>
    <label>密码<input required type="password" name="password" autocomplete="current-password"></label>
    <div class="form-status" role="alert"></div><div class="actions"><button>登录</button></div></form>
    <div class="spaced"><small>演示账号 · 点击填入登录信息</small><div class="demo-roles">${Object.keys(demo).map(key => `<button class="secondary" data-demo="${key}">${roles[key]} · ${demo[key]}</button>`).join('')}</div></div>
    </section></main>`;
}

function shell(content, code, tab) {
  const user = state.user;
  const dossier = state.dossier;
  root.innerHTML = `<header class="masthead"><div class="mast-inner"><div class="brand"><span class="mark">邻</span><strong>邻里课程试验簿</strong></div>
    <div class="account"><span>${escape(user.display_name)} · ${roles[user.role]}</span><button id="logout" class="secondary">切换岗位</button></div></div></header>
    <div class="workspace"><aside class="ledger"><header><strong>实验档案</strong>${user.role === 'organizer' ? '<a href="#/new/plan">＋ 新建</a>' : ''}</header><ul class="ledger-list">
    ${state.plans.map(plan => `<li><a href="${href(plan.code, tab)}" aria-current="${code === plan.code}"><span class="code">${escape(plan.code)}</span><strong>${escape(plan.title)}</strong>${badge(plan.state)}</a></li>`).join('')}
    </ul></aside>
    <main class="workarea">
    ${dossier ? `<div class="titlebar"><div><div class="eyebrow code">${escape(code)}　·　${escape(dossier.plan.site)}</div><h1>${escape(dossier.plan.title)}</h1><p>${escape(dossier.plan.question)}</p></div>${badge(dossier.plan.state)}</div>
    <nav class="tabs" aria-label="实验工作流程">${Object.entries(tabs).filter(([key]) => user.role !== 'instructor' || instructorTabs.has(key)).map(([key, [label]]) => `<a ${key === tab ? 'aria-current="page"' : ''} href="${href(code, key)}">${label}</a>`).join('')}</nav>` : ''}
    <div class="form-status" id="workspace-status" role="status">${flash ? `<div class="field-note">${escape(flash)}</div>` : ''}</div>${content}</main></div>`;
  flash = '';
}

async function render() {
  const rendering = ++requestNumber;
  if (!state.token) {
    loginPage();
    return;
  }
  try {
    const user = state.user || await api('/auth/me');
    const plans = await api('/experiments');
    if (rendering !== requestNumber) return;
    state.user = user;
    state.plans = plans;
    state.dossier = null;
    let {code, tab} = route();
    if (code === 'new' && user.role === 'organizer') {
      shell(planForm(), null, tab);
      return;
    }
    if (user.role === 'instructor') {
      if (!instructorTabs.has(tab)) tab = 'attendance';
      if (!plans.some(plan => plan.code === code)) code = null;
    }
    code = (code === 'new' ? null : code) || plans[0]?.code;
    if (!code) {
      shell(user.role === 'instructor' ? '<div class="empty">当前没有分配给你的课程场次。</div>' :
        '<div class="empty">目前没有实验。由课程统筹新建方案后，其他岗位即可查阅。</div>', null, tab);
      return;
    }
    const [, page, resource] = tabs[tab];
    const [data, extra] = await Promise.all([experiment(code), resource ? experiment(code, resource) : null]);
    if (rendering !== requestNumber) return;
    state.dossier = data;
    shell(page(data, user, extra), code, tab);
  } catch (error) {
    if (rendering !== requestNumber) return;
    state.dossier = null;
    if (state.user) shell(`<div class="field-note warn" role="alert">${escape(error.message)}</div><form data-action="recover"><button>重新载入档案</button></form>`, null, 'plan');
    else if (!state.token) loginPage();
    else root.innerHTML = `<main class="login-content"><h2>暂时无法打开档案</h2><p role="alert">${escape(error.message)}</p><form data-action="refresh"><button>重试</button></form></main>`;
  }
}

const post = body => ({method: 'POST', body});
const put = body => ({method: 'PUT', body});

async function perform(action, form, button) {
  const code = state.dossier?.plan.code;
  if (action?.startsWith('session-')) {
    flash = await sessionAction(action, code, form);
    await render();
    return;
  }
  const values = Object.fromEntries(new FormData(form));
  if (action === 'login') {
    session(await api('/auth/login', post(values)));
    await render();
    return;
  }
  if (action === 'recover') {
    if (location.hash) location.hash = '';
    else await render();
    return;
  }
  if (action === 'refresh') {
    await render();
    return;
  }
  if (action === 'create' || action === 'edit') {
    values.min_per_arm = Number(values.min_per_arm);
    if (action === 'create') {
      const plan = await api('/experiments', post(values));
      flash = '方案草稿已建立。';
      location.hash = href(plan.code);
      return;
    }
    await experiment(code, '', put(values));
    flash = '方案草稿已更新。';
  }
  if (action === 'assign') {
    await experiment(code, '/assign', post({codes: values.codes.split(/\s+/).filter(Boolean)}));
    flash = '原始分配已锁定，可以开始登记观测。';
  }
  if (action === 'clearance-submit') {
    const codes = values.codes.split(/\s+/).filter(Boolean);
    await experiment(code, '/clearances', post({codes, source_ref: values.source_ref}));
    flash = '资格名单已提交。';
  }
  if (action === 'clearance-decision' || action === 'correction-decision') {
    const resource = action === 'clearance-decision' ? 'clearances' : 'corrections';
    await experiment(code, `/${resource}/${form.dataset.id}/decision`, post({...values, decision: button.value}));
    flash = button.value === 'approved' ? '复核已通过。' : '复核已退回。';
  }
  if (action === 'invitation-record') {
    const fields = new FormData(form);
    const codes = fields.getAll('resident');
    if (!codes.length) throw new Error('请至少选择一位居民');
    fields.delete('resident');
    await experiment(code, '/invitations', post({...Object.fromEntries(fields), codes}));
    flash = `已登记 ${codes.length} 条邀请回执。`;
  }
  if (action === 'correction-submit') {
    await experiment(code, '/corrections', post(values));
    flash = '观测更正已提交。';
  }
  if (action === 'check') {
    await experiment(code, '/check', post());
    flash = '方案检查通过，可以随机分组。';
  }
  if (action === 'exclude' || action === 'transfer') {
    const {resident, ...body} = values;
    const result = await experiment(code, `/roster/${encodeURIComponent(resident)}/${action}`, post(body));
    flash = result.plan.state === 'frozen' ? '已冻结分析。请到复盘审批查看原因。' : '资格剔除已记录。';
  }
  if (action === 'observe') {
    const entries = [...form.querySelectorAll('[data-member]')].filter(select => select.value && select.value !== select.dataset.original)
      .map(select => ({code: select.dataset.member, outcome: select.value}));
    if (!entries.length) throw new Error('请至少选择一条新的观测结果');
    await experiment(code, '/observations', put({observed_on: values.observed_on, source_ref: values.source_ref, entries}));
    flash = `已保存 ${entries.length} 条观测。`;
  }
  if (action === 'analysis') {
    await experiment(code, '/analysis', post());
    flash = '观测已封存。';
    location.hash = href(code, 'review');
    return;
  }
  if (action === 'decision') {
    await experiment(code, '/decision', post({...values, decision: button.value}));
    flash = button.value === 'approved' ? '复核已通过，快照可下载。' : '分析已驳回。';
  }
  if (action === 'snapshot-supplement') {
    const result = await experiment(code, '/snapshot/supplements', post(values));
    flash = {verified: '补档单已登记，快照恢复并沿用原签字。',
      pending: '补档单已写好但尚未登记生效，恢复后接着办。',
      manual: result.reason || '封存观测复验对不上，已转人工查档。'}[result.state] || '补档单已登记。';
  }
  if (action === 'download') {
    const blob = await experiment(code, '/snapshot', {download: true});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${code}-analysis.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return;
  }
  await render();
}

root.addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.target;
  const submitter = event.submitter || form.querySelector('button');
  if (!submitter || submitter.disabled) return;
  submitter.disabled = true;
  try {
    await perform(form.dataset.action, form, submitter);
  } catch (error) {
    const status = form.querySelector('.form-status') || root.querySelector('#workspace-status');
    if (status) {
      status.innerHTML = `<div class="field-note warn" role="alert">${escape(error.message)}</div>`;
      status.scrollIntoView({block: 'nearest'});
    }
  } finally {
    submitter.disabled = false;
  }
});

root.addEventListener('change', event => {
  const field = event.target;
  if (field.name === 'arm' && field.form?.dataset.action === 'invitation-record') changeInvitationArm(field.form);
});

root.addEventListener('click', event => {
  const button = event.target.closest('button');
  if (button?.hasAttribute('data-select-invites')) {
    for (const checkbox of button.form.querySelectorAll('input[name=resident]:enabled')) checkbox.checked = true;
  }
  if (button?.id === 'logout') {
    session(null);
    state.dossier = null;
    void render();
  }
  if (button?.dataset.demo) {
    const form = root.querySelector('[data-action="login"]');
    form.elements.email.value = demo[button.dataset.demo];
    form.elements.password.value = 'ClassDemo26!';
    form.querySelector('button').focus();
  }
});

window.addEventListener('hashchange', render);
window.addEventListener('sessionexpired', render);
void render();
