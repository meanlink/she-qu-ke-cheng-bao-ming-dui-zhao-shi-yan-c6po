import {escape, facts, manualOutcomes, notice, options, outcomes} from './view.js';

const statuses = {pending: '待复核', approved: '已通过', returned: '已退回'};
const deliveryStatuses = {delivered: '已送达', failed: '未送达'};
const channels = {sms: '短信', phone: '电话', desk: '服务台当面通知'};

function reviewButtons(action, id, noun) {
  return `<form class="stack spaced" data-action="${action}" data-id="${id}">
    <label>复核意见<textarea name="note" required minlength="4" maxlength="300" rows="2"></textarea></label>
    <div class="actions"><button value="approved">批准${noun}</button><button class="secondary" value="returned">退回${noun}</button></div>
  </form>`;
}

function signature(record) {
  return record.decision_note ? `<p class="control-note">${escape(record.decision_note)}<small>${escape(record.decided_by)}</small></p>` : '';
}

export function clearancePage(data, user, controls) {
  const {plan} = data;
  const [latest, ...earlier] = controls.clearances;
  const checked = plan.state === 'checked';
  const canSubmit = checked && user.role === 'organizer' && (!latest || latest.status === 'returned');
  const canReview = checked && user.role === 'reviewer' && latest?.status === 'pending';
  const canAssign = checked && user.role === 'organizer' && latest?.status === 'approved';
  return `<div class="split"><section class="panel"><h2>分组前资格预审</h2>
    ${latest ? `${facts([['当前版本', `第 ${latest.version} 版 · ${statuses[latest.status]}`], ['资格凭证', latest.source_ref], ['提交人', latest.submitted_by], ['待分组人数', `${latest.codes.length} 人`]])}
      ${signature(latest)}<details><summary>查阅第 ${latest.version} 版匿名名单</summary><p class="code wrap-code">${escape(latest.codes.join('　'))}</p></details>`
    : '<p>方案检查通过后，课程统筹可提交资格名单及核对凭证，开启资格、送达和更正复核。</p>'}
    ${canReview ? reviewButtons('clearance-decision', latest.version, '名单') : ''}
    ${canAssign ? `<form class="actions spaced" data-action="assign"><textarea hidden name="codes">${escape(latest.codes.join('\n'))}</textarea><button>按获批名单分组</button></form>` : ''}
    ${canSubmit ? `<form class="spaced stack" data-action="clearance-submit">
      <label>资格核对凭证<input name="source_ref" required minlength="2" maxlength="100" placeholder="例：花圃课资格核对_1114.csv"></label>
      <label>居民编号，每行一位<textarea name="codes" rows="6" required placeholder="YC-001&#10;YC-002">${escape(latest?.codes.join('\n'))}</textarea></label>
      <div class="actions"><button>${latest ? '提交修订版' : '提交资格名单'}</button></div>
    </form>` : ''}
    </section><section class="panel"><h3>抽签前要核对什么</h3><p>至少 ${2 * plan.min_per_arm} 名资格有效且编号唯一的居民。督导确认凭证后，系统只接受获批版本中的居民。</p>
    ${earlier.length ? `<h3 class="spaced">历史版本</h3><ul class="log">${earlier.map(record => `<li><details><summary>第 ${record.version} 版 · ${statuses[record.status]} · ${record.codes.length} 人</summary><p>${escape(record.source_ref)} · ${escape(record.submitted_by)}</p>${signature(record)}<p class="code wrap-code">${escape(record.codes.join('　'))}</p></details></li>`).join('')}</ul>` : ''}
    </section></div>`;
}

function deliveryForm(plan, candidates) {
  const arm = candidates[0].arm;
  const armChoices = Object.fromEntries(['A', 'B'].filter(group => candidates.some(row => row.arm === group)).map(group => [group, `${group} 组 · ${group === 'A' ? plan.control_invite : plan.variant_invite}`]));
  return `<form class="stack spaced" data-action="invitation-record">
    <label>实际邀请组<select name="arm">${options(armChoices, arm)}</select></label>
    <div class="fields"><label>尝试日期<input type="date" name="delivered_on" required min="${plan.window_start}" max="${plan.window_end}"></label>
    <label>渠道<select name="channel">${options(channels, 'sms')}</select></label>
    <label>回执结果<select name="status">${options(deliveryStatuses, 'delivered')}</select></label>
    <label>回执凭证<input required name="source_ref" minlength="2" maxlength="100" placeholder="例：短信回执_A_1114.csv"></label></div>
    <fieldset class="delivery-members"><legend>本批居民</legend>
      <button class="secondary" type="button" data-select-invites>选择当前组全部</button>
      <div class="member-options spaced">${candidates.map(row => `<label data-invite-arm="${row.arm}"${row.arm === arm ? '' : ' hidden'}><input type="checkbox" name="resident" value="${escape(row.participant_code)}"${row.arm === arm ? '' : ' disabled'}> ${escape(row.participant_code)}</label>`).join('')}</div>
    </fieldset><div class="actions"><button>登记邀请回执</button></div>
  </form>`;
}

export function invitationPage(data, user, controls) {
  const {plan, clearance_status: managed} = data;
  const {invitations} = controls;
  const delivered = new Set(invitations.filter(row => row.status === 'delivered').map(row => row.participant_code));
  const eligible = data.assignments.filter(row => !row.exclusion_reason);
  const candidates = eligible.filter(row => !delivered.has(row.participant_code));
  const rollup = ['A', 'B'].map(arm => {
    const group = eligible.filter(row => row.arm === arm);
    return [`${arm} 组送达`, `${group.filter(row => delivered.has(row.participant_code)).length} / ${group.length} 人`];
  });
  return `<div class="split"><section class="panel"><h2>课程邀请送达核对</h2>
    ${managed ? facts([...rollup, ['未送达历史', `${invitations.filter(row => row.status === 'failed').length} 次尝试`]]) : notice('按原流程观测', '该实验未提交资格预审。新的受控实验在资格名单获批并分组后，可以在这里登记回执。')}
    ${plan.state === 'observing' && managed && user.role === 'organizer' && candidates.length ? deliveryForm(plan, candidates) : ''}
    ${managed && eligible.length && !candidates.length ? notice('邀请回执已齐', '观测员可以根据报名和到课凭证登记结果。') : ''}
    </section><section class="panel"><h3>回执历史</h3><p>未送达可重试，历史仍保留。已经送达的回执进入实验档案，作为观测日期的下限。</p>
    ${invitations.length ? `<div class="table-wrap" tabindex="0" aria-label="邀请回执历史"><table><thead><tr><th>居民</th><th>回执</th></tr></thead><tbody>${invitations.map(row => `<tr><td class="code">${escape(row.participant_code)}</td><td><strong>${deliveryStatuses[row.status]}</strong> · ${channels[row.channel]}<small class="source-line">${escape(row.delivered_on)} · ${escape(row.source_ref)}</small></td></tr>`).join('')}</tbody></table></div>` : '<p class="empty">暂无回执。</p>'}
    </section></div>`;
}

function correctionForm(plan, residents) {
  return `<form class="stack spaced" data-action="correction-submit">
    <label>已登记居民<select name="participant_code">${options(Object.fromEntries(residents.map(row => [row.participant_code, `${row.participant_code} · ${row.arm} 组 · ${outcomes[row.outcome]}`])))}</select></label>
    <div class="fields"><label>更正为<select name="proposed_outcome">${options(manualOutcomes)}</select></label>
    <label>更正后观测日期<input type="date" required name="proposed_observed_on" min="${plan.window_start}" max="${plan.window_end}" value="${plan.window_end}"></label>
    <label class="span">更正凭证<input required name="proposed_source_ref" minlength="2" maxlength="100" placeholder="例：签到簿复核_1120.csv"></label></div>
    <label>更正原因<textarea name="reason" required minlength="4" maxlength="300" rows="2"></textarea></label>
    <div class="actions"><button>提交观测更正</button></div>
  </form>`;
}

export function correctionPage(data, user, controls) {
  const {plan, clearance_status: managed} = data;
  const pending = new Set(controls.corrections.filter(row => row.status === 'pending').map(row => row.participant_code));
  const candidates = data.assignments.filter(row => row.outcome && !pending.has(row.participant_code));
  const canSubmit = managed && !data.has_session && plan.state === 'observing' && user.role === 'observer' && candidates.length;
  const canReview = plan.state === 'observing' && user.role === 'reviewer';
  const ordered = [...controls.corrections].sort((a, b) => Number(b.status === 'pending') - Number(a.status === 'pending'));
  return `<div class="split"><section class="panel"><h2>报名观测更正复核</h2>
    <p>${managed ? '观测员可用新的签到或报名凭证发起更正。待复核期间保留原结果，实验暂缓封存。' : '该实验沿用原有观测登记方式。启用资格预审的实验会在这里保留观测更正和签署记录。'}</p>
    ${canSubmit ? correctionForm(plan, candidates) : ''}
    ${managed && pending.size ? notice(`${pending.size} 单待复核`, plan.state === 'observing' ? '督导签署后，当前报名表才会更新。' : '实验已离开观测阶段，待复核记录随实验归档。') : ''}
    </section><section class="panel"><h3>更正单</h3>
    ${ordered.length ? `<ul class="log correction-list">${ordered.map(row => `<li><div class="inline"><strong class="code">${escape(row.participant_code)}</strong><span class="badge ${row.status === 'returned' ? 'rejected' : row.status}">${statuses[row.status]}</span></div>
      ${facts([['原记录', `${outcomes[row.original_outcome]} · ${row.original_observed_on} · ${row.original_source_ref}`], ['更正为', `${outcomes[row.proposed_outcome]} · ${row.proposed_observed_on} · ${row.proposed_source_ref}`], ['更正依据', row.reason]])}
      <small>提交人 ${escape(row.submitted_by)}</small>${signature(row)}
      ${canReview && row.status === 'pending' ? reviewButtons('correction-decision', row.id, '更正') : ''}</li>`).join('')}</ul>` : '<p class="empty">暂无更正单。</p>'}
    </section></div>`;
}

export function changeInvitationArm(form) {
  for (const member of form.querySelectorAll('[data-invite-arm]')) {
    const checkbox = member.querySelector('input');
    member.hidden = checkbox.disabled = member.dataset.inviteArm !== form.elements.arm.value;
    if (checkbox.disabled) checkbox.checked = false;
  }
}
