import {escape, facts, metrics, notice, pct, points, recordLog} from './view.js';

const archiveStates = {
  not_ready: ['快照未就绪', '复核通过后才能导出实验快照。', false],
  missing: ['快照缺失', '下载前核对实验编号、各组人数、原输入摘要和检验值，请督导凭补档单恢复快照。', true],
  pending: ['补档待登记', '补档单已写好但尚未登记生效，恢复后接着办，补档记录生效才开放下载。', true],
  mismatch: ['快照错件', '下载前核对实验编号、各组人数、原输入摘要和检验值，请督导凭补档单恢复快照。', true],
  manual: ['转人工查档', '封存观测复验对不上，已转人工查档，暂不开放下载。', true],
  verified: ['快照已核验', '实验编号、各组人数、原输入摘要和检验值均与签字记录一致，可下载。', false],
};

const supplementStates = {pending: '待登记', restored: '已恢复', manual: '转人工'};

function archivePanel(data, user, archive) {
  const {plan} = data;
  const [title, message, warn] = archiveStates[archive.state];
  const reviewer = user.role === 'reviewer' && plan.state === 'approved';
  const canSupplement = reviewer && ['missing', 'mismatch', 'pending'].includes(archive.state);
  const pending = archive.supplements.find(row => row.status === 'pending');
  const resuming = Boolean(pending);
  return `<section class="panel spaced"><div class="inline"><h3>快照归档</h3><span class="badge ${warn ? 'frozen' : 'approved'}">${title}</span></div>
    ${notice(title, message, warn)}
    ${archive.reason && archive.state !== 'verified' ? `<p class="muted">${escape(archive.reason)}</p>` : ''}
    ${canSupplement ? `<form class="stack spaced" data-action="snapshot-supplement">
      <label>补档单编号<input required name="source_ref" minlength="2" maxlength="100" ${resuming ? `value="${escape(pending.source_ref)}" readonly` : 'placeholder="例：补档单_1124-01"'}></label>
      <label>补档说明<textarea required name="note" minlength="4" maxlength="300" rows="2" placeholder="记录补档原因与来源">${resuming ? '恢复后接着办，沿用原签字' : ''}</textarea></label>
      <div class="actions"><button>${resuming ? '接着办理未登记的补档' : '凭补档单恢复快照'}</button></div></form>` : ''}
    ${plan.state === 'approved' && archive.state === 'verified' ? '<form class="spaced" data-action="download"><button class="secondary">下载复核快照</button></form>' : ''}
    ${archive.supplements.length ? `<h3 class="spaced">补档记录</h3><ul class="log">${archive.supplements.map(row => `<li><strong>${escape(row.source_ref)}</strong> · ${supplementStates[row.status]}<small>${escape(row.requested_by)} · ${escape(new Date(row.requested_at).toLocaleString('zh-CN', {hour12: false}))}${row.mismatch_reason ? ` · ${escape(row.mismatch_reason)}` : ''}</small></li>`).join('')}</ul>` : ''}
  </section>`;
}

function report(result, plan) {
  const {a_rate: a, b_rate: b, difference, p, ci_low, ci_high, cohen_h, significant} = result;
  return `<section class="panel"><div class="eyebrow">${metrics[plan.primary_metric]} · 双侧两比例 Z 检验</div><h2>邀请方式的观察结果</h2>
    <div class="bars" aria-label="按原始分组比较主指标">
    ${[[a, 'A · 对照组', result.a_success, result.a_n], [b, 'B · 实验组', result.b_success, result.b_n]].map(([value, label, success, n]) =>
      `<div class="bar-line"><strong>${label}</strong><div class="track" role="meter" aria-label="${label}" aria-valuenow="${value * 100}" aria-valuemin="0" aria-valuemax="100"><i style="width:${value * 100}%"></i></div><span>${pct(value)}</span><small class="span">${success}/${n} 位有效居民</small></div>`).join('')}
    </div><div class="metrics"><div><small>B − A（百分点）</small><strong>${points(difference)}</strong></div><div><small>双侧 p 值</small><strong>${p < .0001 ? '<0.0001' : p.toFixed(4)}</strong></div><div><small>Cohen’s h</small><strong>${cohen_h.toFixed(3)}</strong></div></div>
    ${notice(significant ? '达到预设 0.05 显著性阈值' : '未达到预设 0.05 显著性阈值', `差值的 95% 区间为 ${points(ci_low)} 至 ${points(ci_high)} 个百分点。请结合课程组织成本与区间宽度评估后续安排。`)}
    </section>`;
}

export function reviewPage(data, user, archive) {
  const {plan, review, events, groups} = data;
  const deciding = user.role === 'reviewer' && ['review', 'frozen'].includes(plan.state);
  const signature = deciding ? `<form class="panel stack" data-action="decision"><h3>复核签署</h3>
    <label>结论依据<textarea required minlength="4" maxlength="300" rows="3" name="note" placeholder="记录发布决定或驳回依据"></textarea></label>
    <div class="actions">${plan.state === 'review' ? '<button name="decision" value="approved">批准结果</button>' : ''}<button class="danger" name="decision" value="rejected">驳回分析</button></div></form>` : '';
  return `<div class="split"><div>
   ${review?.result ? report(review.result, plan) : `<section class="panel"><h2>两比例检验档案</h2>${review?.freeze_reason ? notice('冻结原因', review.freeze_reason, true) : `<div class="empty">${plan.state === 'queued' ? '工作进程正在计算，可刷新查看。' : '有效名单全部登记并封存后，检验结果会出现在这里。'}</div>`}
   ${plan.state === 'queued' ? '<form class="spaced" data-action="refresh"><button class="secondary">刷新检验状态</button></form>' : ''}</section>`}
   ${recordLog(events)}
  </div><div>${signature}${archive && plan.state === 'approved' ? archivePanel(data, user, archive) : ''}<section class="panel ${deciding ? 'spaced' : ''}"><h3>复核依据</h3>
  ${facts([['主指标', metrics[plan.primary_metric]], ['有效样本', `A 组 ${groups.A.eligible} 人 · B 组 ${groups.B.eligible} 人`], ['发起人', review?.requested_by || '—'], ['签署人', review?.decided_by || '—'], ['原输入摘要', review?.input_digest || '—']])}
  ${review?.decision_note ? notice('签署说明', review.decision_note, plan.state === 'rejected') : ''}
  </section></div></div>`;
}
