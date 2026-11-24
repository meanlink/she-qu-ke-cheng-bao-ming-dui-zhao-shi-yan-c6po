import {arms, escape, facts, notice} from './view.js';

export function rosterPage(data, user) {
  const {plan, assignments: rows, groups} = data;
  const canExclude = !data.has_session && plan.state === 'observing' && user.role === 'organizer' && !groups.A.recorded && !groups.B.recorded;
  const canTransfer = ['observing', 'queued', 'review'].includes(plan.state) && user.role === 'observer';
  const eligible = rows.filter(row => !row.exclusion_reason);
  const residentOptions = eligible.map(row => `<option value="${escape(row.participant_code)}">${escape(row.participant_code)} · ${row.arm} 组</option>`).join('');
  const list = rows.length ? `<div class="table-wrap" tabindex="0" aria-label="原始分组名单"><table><thead><tr><th>居民编号</th><th>原组</th><th>资格</th><th>改组记录</th></tr></thead><tbody>
    ${rows.map(row => `<tr><td class="code">${escape(row.participant_code)}</td><td>${row.arm}</td><td>${row.exclusion_reason ? escape(`${row.exclusion_reason === 'duplicate' ? '重复登记' : '资格误录'} · ${row.exclusion_ref}`) : '有效'}</td>
    <td>${row.reported_arm ? escape(`实际 ${row.reported_arm} 组 · ${row.deviation_ref}`) : '—'}</td></tr>`).join('')}</tbody></table></div>` : '';
  return `<div class="split"><section class="panel"><h2>居民名单与原始分配</h2>
    ${rows.length ? arms(data) + list : `<p>方案检查通过后导入已校验资格的匿名居民编号。系统随机分组并保留名单摘要。</p>`}
    ${plan.state === 'checked' && data.clearance_status ? `<p>资格预审已启用。<a href="#/${escape(plan.code)}/clearance">前往资格预审核对并分组</a>。</p>` : ''}
    ${plan.state === 'checked' && !data.clearance_status && user.role === 'organizer' ? `<form class="stack spaced" data-action="assign"><label>居民编号，每行一位<textarea required rows="8" name="codes" placeholder="ZH-001&#10;ZH-002"></textarea></label>
    <div class="actions"><button>随机分组并锁定</button></div></form>` : ''}
  </section><div><section class="panel"><h3>分组保护规则</h3>
    ${facts([['随机分配', 'A / B 约 1:1'], ['比例门槛', '各组 45%–55%'], ['每组下限', `${plan.min_per_arm} 人`], ['名单摘要', plan.roster_digest || '分组后生成']])}
    ${plan.allocation_seed ? `<details><summary>查看随机种子</summary><p class="code">${escape(plan.allocation_seed)}</p></details>` : ''}
    ${notice('保留原组', '确认名单误录只可在第一条观测前登记；记录中途改组会立即冻结分析。')}
  </section>
  ${canExclude ? `<form class="panel stack spaced" data-action="exclude"><h3>更正资格误录</h3><label>居民<select name="resident">${residentOptions}</select></label>
    <label>原因<select name="reason"><option value="duplicate">重复登记</option><option value="ineligible">资格不符</option></select></label><label>核对凭证<input required name="reference" minlength="4" maxlength="300"></label>
    <div class="actions"><button class="secondary">登记资格剔除</button></div></form>` : ''}
  ${canTransfer ? `<form class="panel stack spaced" data-action="transfer"><h3>登记中途改组</h3><label>居民<select name="resident">${residentOptions}</select></label>
    <label>实际收到的邀请组<select name="reported_arm"><option value="A">A · 对照组</option><option value="B">B · 实验组</option></select></label><label>改组凭证<input required name="reference" minlength="4" maxlength="300"></label>
    <div class="actions"><button class="danger">登记改组并冻结</button></div></form>` : ''}</div></div>`;
}
