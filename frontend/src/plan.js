import {arms, escape, facts, metrics, notice, options, recordLog} from './view.js';

export const planFields = ['title', 'question', 'site', 'control_invite', 'variant_invite', 'window_start', 'window_end', 'primary_metric', 'min_per_arm'];

function input(name, label, type, value, extra = '') {
  return `<label>${label}<input required type="${type}" name="${name}" value="${escape(value)}" ${extra}></label>`;
}

export function planForm(plan = {}) {
  const editing = Boolean(plan.code);
  return `<form class="panel stack" data-action="${editing ? 'edit' : 'create'}">
    <h2>${editing ? '编辑方案草稿' : '新建课程方案'}</h2>
    <div class="fields">
      ${editing ? '' : input('code', '实验编号', 'text', '', 'maxlength="24" placeholder="CC-1125"')}
      ${input('title', '课程名称', 'text', plan.title, 'maxlength="100"')}
      ${input('site', '授课地点', 'text', plan.site, 'maxlength="100"')}
      <label class="span">实验问题<textarea required name="question" minlength="4" maxlength="300" rows="2">${escape(plan.question)}</textarea></label>
      ${input('control_invite', 'A 组 · 现行邀请', 'text', plan.control_invite, 'maxlength="100"')}
      ${input('variant_invite', 'B 组 · 新版邀请', 'text', plan.variant_invite, 'maxlength="100"')}
      ${input('window_start', '观测开始', 'date', plan.window_start)}
      ${input('window_end', '观测结束', 'date', plan.window_end)}
      <label>主指标<select name="primary_metric">${options(metrics, plan.primary_metric)}</select></label>
      ${input('min_per_arm', '每组最少有效居民', 'number', plan.min_per_arm ?? 12, 'min="12" max="500"')}
    </div>
    <div class="actions"><button type="submit">${editing ? '保存方案修改' : '建立方案档案'}</button></div>
  </form>`;
}

export function planPage(data, user) {
  const {plan, events} = data;
  const draft = plan.state === 'draft';
  return `<div class="split"><div>
    <section class="panel"><div class="eyebrow">研究设计</div><h2>邀请方案与观察口径</h2>
    ${facts([['课程地点', plan.site], ['观察窗口', `${plan.window_start} 至 ${plan.window_end}`], ['主要指标', metrics[plan.primary_metric]], ['样本下限', `每组至少 ${plan.min_per_arm} 位居民`], ['方案检查', plan.checked_by || '等待督导检查']])}
    ${arms(data)}
    ${draft && user.role === 'reviewer' ? `<form class="spaced" data-action="check"><button>通过方案检查</button></form>` : ''}
    </section>
    ${draft && user.role === 'organizer' ? `<div class="spaced">${planForm(plan)}</div>` : ''}
  </div><div>
    <section class="panel"><h3>指标分母</h3><p>每组全部有效的原始分配居民。明确未报名的居民也计入分母。</p>
    ${notice('锁定时点', '督导通过检查后，邀请文案、主指标及观测窗口随方案锁定。课程统筹随后导入居民编号并随机分组。')}
    </section>${recordLog(events)}
  </div></div>`;
}
