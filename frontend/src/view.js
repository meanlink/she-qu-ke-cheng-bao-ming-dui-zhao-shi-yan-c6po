export const roles = {organizer: '课程统筹', observer: '观测员', reviewer: '督导复核', instructor: '带班讲师'};
export const phases = {draft: '方案草拟', checked: '检查通过', observing: '观测中', queued: '待计算', review: '待复核', frozen: '已冻结', approved: '复核通过', rejected: '已驳回'};
export const manualOutcomes = {no_signup: '未报名', absent: '已报名未到课', attended: '已到课'};
export const outcomes = {...manualOutcomes, waitlisted: '候补未获席', withdrawn: '报名后撤回'};
export const metrics = {signup: '居民报名率', attendance: '居民到课率'};
export const events = {drafted: '建档', edited: '修改方案', checked: '通过方案检查', allocated: '固化分组', excluded: '剔除名单', observed: '保存观测', queued: '封存观测', frozen: '冻结分析', computed: '完成检验', approved: '批准结果', rejected: '驳回结果', clearance_submitted: '提交资格名单', clearance_approved: '批准资格名单', clearance_returned: '退回资格名单', invitation_recorded: '登记邀请回执', correction_submitted: '提交观测更正', correction_approved: '批准观测更正', correction_returned: '退回观测更正', session_booked: '安排场次', capacity_revised: '调整席位', seat_requested: '登记席位申请', seat_confirmed: '确认席位', seat_withdrawn: '撤回报名', roll_locked: '锁定签到名册', roll_signed: '讲师签署签到', roll_reconciled: '完成签到交接', supplement_requested: '提交补档单', supplement_restored: '快照补档恢复', supplement_manual: '转人工查档'};

export const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
export const pct = value => `${(value * 100).toFixed(1)}%`;
export const points = value => `${value > 0 ? '+' : ''}${(value * 100).toFixed(1)}`;
export const badge = phase => `<span class="badge ${escape(phase)}">${escape(phases[phase] ?? phase)}</span>`;
export const notice = (title, message, warn = false) => `<div class="field-note ${warn ? 'warn' : ''}"><h3>${escape(title)}</h3><p>${escape(message)}</p></div>`;
export const options = (items, selected) => Object.entries(items).map(([value, label]) => `<option value="${escape(value)}"${value === selected ? ' selected' : ''}>${escape(label)}</option>`).join('');
export const facts = rows => `<dl class="facts">${rows.map(([label, value]) => `<div><dt>${escape(label)}</dt><dd>${escape(value)}</dd></div>`).join('')}</dl>`;

export function arms(data) {
  const {plan, groups} = data;
  return `<div class="arm-grid">${['A', 'B'].map(arm => {
    const group = groups[arm];
    return `<div class="arm"><small>${arm === 'A' ? 'A · 对照组' : 'B · 实验组'}</small><strong>${escape(arm === 'A' ? plan.control_invite : plan.variant_invite)}</strong><span>${group.eligible} 人有效 · ${group.recorded} 人已登记</span></div>`;
  }).join('')}</div>`;
}

export function recordLog(rows) {
  return `<section class="panel spaced"><h3>档案流水</h3><ul class="log">${rows.map(row => `<li><strong>${escape(events[row.event] || row.event)}</strong> · ${escape(row.detail)}<small>${escape(row.actor)} · ${escape(new Date(row.occurred_at).toLocaleString('zh-CN', {hour12: false}))}</small></li>`).join('')}</ul></section>`;
}
