import {escape, facts, manualOutcomes, notice, options, outcomes} from './view.js';

export function observationPage(data, user) {
  const {plan, assignments, groups} = data;
  const rows = assignments.filter(row => !row.exclusion_reason);
  const managed = !!data.clearance_status;
  const edit = plan.state === 'observing' && user.role === 'observer';
  const pending = rows.filter(row => !row.outcome).length;
  const canEnter = row => edit && !data.has_session && (!managed || (row.delivered_on && !row.outcome));
  const ready = rows.length > 0 && pending === 0;
  const table = `<div class="table-wrap" tabindex="0" aria-label="居民观测表"><table><thead><tr><th>居民编号</th><th>分组</th><th>报名与到课</th><th>登记凭证</th>${managed ? '<th>邀请送达</th>' : ''}</tr></thead><tbody>
    ${rows.map(row => `<tr><td class="code">${escape(row.participant_code)}</td><td>${row.arm}</td><td>${canEnter(row) ? `<select aria-label="${escape(row.participant_code)} 的观测结果" name="outcome" data-member="${escape(row.participant_code)}" data-original="${escape(row.outcome)}">${options({'': '待登记', ...manualOutcomes}, row.outcome || '')}</select>` : escape(outcomes[row.outcome] ?? '待登记')}</td>
    <td>${escape(row.source_ref || '—')}</td>${managed ? `<td>${escape(row.delivered_on || '待回执')}</td>` : ''}</tr>`).join('')}</tbody></table></div>`;
  return `<div class="observation-layout"><section class="panel"><h2>报名与到课登记</h2>
    ${data.has_session ? `<p>本实验的结果来自<a href="#/${escape(plan.code)}/attendance">签到交接</a>。</p>` : ''}
    ${managed && edit && !data.has_session ? `<p><a href="#/${escape(plan.code)}/delivery">查阅邀请回执</a>。已登记结果如有差错，请<a href="#/${escape(plan.code)}/correction">提交观测更正</a>。</p>` : ''}
    ${rows.length ? (rows.some(canEnter) ? `<form data-action="observe" class="stack"><div class="fields"><label>观测日期<input required type="date" name="observed_on" min="${plan.window_start}" max="${plan.window_end}" value="${plan.window_end}"></label><label>登记凭证<input required name="source_ref" placeholder="例：拓印课签到簿_1120.csv" maxlength="100"></label></div>
      ${table}<div class="actions"><button>保存更改过的观测</button></div></form>` : table) : `<div class="empty">分组完成后，这里会出现可登记的有效居民名单。</div>`}
  </section><section class="panel"><h3>封存前核对</h3>
    ${facts(['A', 'B'].map(arm => [`${arm} 组`, `${groups[arm].recorded}/${groups[arm].eligible} 人已登记 · ${groups[arm].signup} 人报名 · ${groups[arm].attendance} 人到课`]))}
    ${rows.length && !ready ? notice(`仍缺 ${pending} 条观测`, data.has_session ? '请先完成签到交接。' : '请逐位核对签到簿。未报名是有效结果；待登记表示缺失。') : ''}
    ${edit && data.pending_corrections ? notice(`${data.pending_corrections} 单更正待复核`, '请督导处理观测更正后再封存。') : ''}
    ${ready && edit && !data.pending_corrections ? `<p>名单已齐。观测窗口结束后可封存并提交两比例检验。</p><form data-action="analysis"><button>封存并提交检验</button></form>` : ''}
    ${!edit && ['queued', 'review', 'approved', 'frozen', 'rejected'].includes(plan.state) ? notice('观测已锁定', '查阅分析或异常原因，请前往复盘审批。') : ''}
    </section></div>`;
}
