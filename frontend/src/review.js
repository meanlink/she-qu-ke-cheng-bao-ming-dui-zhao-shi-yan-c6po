import {escape, facts, metrics, notice, pct, points, recordLog} from './view.js';

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

export function reviewPage(data, user) {
  const {plan, review, events, groups} = data;
  const deciding = user.role === 'reviewer' && ['review', 'frozen'].includes(plan.state);
  const signature = deciding ? `<form class="panel stack" data-action="decision"><h3>复核签署</h3>
    <label>结论依据<textarea required minlength="4" maxlength="300" rows="3" name="note" placeholder="记录发布决定或驳回依据"></textarea></label>
    <div class="actions">${plan.state === 'review' ? '<button name="decision" value="approved">批准结果</button>' : ''}<button class="danger" name="decision" value="rejected">驳回分析</button></div></form>` : '';
  return `<div class="split"><div>
   ${review?.result ? report(review.result, plan) : `<section class="panel"><h2>两比例检验档案</h2>${review?.freeze_reason ? notice('冻结原因', review.freeze_reason, true) : `<div class="empty">${plan.state === 'queued' ? '工作进程正在计算，可刷新查看。' : '有效名单全部登记并封存后，检验结果会出现在这里。'}</div>`}
   ${plan.state === 'queued' ? '<form class="spaced" data-action="refresh"><button class="secondary">刷新检验状态</button></form>' : ''}</section>`}
   ${recordLog(events)}
  </div><div>${signature}<section class="panel ${deciding ? 'spaced' : ''}"><h3>复核依据</h3>
  ${facts([['主指标', metrics[plan.primary_metric]], ['有效样本', `A 组 ${groups.A.eligible} 人 · B 组 ${groups.B.eligible} 人`], ['发起人', review?.requested_by || '—'], ['签署人', review?.decided_by || '—'], ['输入摘要', review?.input_digest || '—']])}
  ${review?.decision_note ? notice('签署说明', review.decision_note, plan.state === 'rejected') : ''}
  ${plan.state === 'approved' ? '<form class="spaced" data-action="download"><button class="secondary">下载复核快照</button></form>' : ''}
  </section></div></div>`;
}
