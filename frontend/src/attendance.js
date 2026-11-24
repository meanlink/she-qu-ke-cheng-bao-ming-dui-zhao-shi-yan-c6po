import {classTime, sourceField, stageLabels} from './session-actions.js';
import {escape, facts, notice, options, outcomes} from './view.js';

function signForm(confirmed) {
  return `<form class="stack" data-action="session-sign">${sourceField('签到簿凭证', '例：育苗课签到_1120.csv')}
    ${confirmed.length ? `<div class="table-wrap" tabindex="0" aria-label="确认席位签到表"><table><thead><tr><th>居民</th><th>原组</th><th>签到结果</th></tr></thead><tbody>
    ${confirmed.map(row => `<tr><td class="code">${escape(row.participant_code)}</td><td>${row.arm}</td><td><select required
      aria-label="${escape(row.participant_code)} 的签到结果" data-roll-member="${escape(row.participant_code)}">
      ${options({'': '选择结果', attended: '到课', absent: '缺席'})}</select></td></tr>`).join('')}
    </tbody></table></div>` : '<p>本场没有确认席位。签署空表后，观测员仍需交接候补、撤回及未报名记录。</p>'}
    <div class="actions"><button>签署签到表</button></div></form>`;
}

function handoffTable(rows) {
  return `<div class="table-wrap" tabindex="0" aria-label="交接结果预览"><table>
    <thead><tr><th>居民</th><th>原组</th><th>观测结果</th></tr></thead><tbody>
    ${rows.map(row => `<tr><td class="code">${escape(row.participant_code)}</td><td>${row.arm}</td><td>${outcomes[row.outcome]}</td></tr>`).join('')}
    </tbody></table></div>`;
}

export function attendancePage(data, user, ledger) {
  const {plan} = data;
  const {session, seats, roll, outcomes: preview} = ledger;
  if (!session) return notice('尚无签到名册', '课程统筹安排场次后，讲师可在开课时锁定确认名单。');
  const confirmed = seats.filter(row => row.status === 'confirmed');
  const signing = user.role === 'instructor' && user.email === session.instructor_email;
  const reconciled = session.stage === 'reconciled';
  const reviewLink = `#/${escape(plan.code)}/observation`;
  return `<div class="split"><section class="panel"><div class="inline"><h2>签到与观测交接</h2><span class="badge">${stageLabels[session.stage]}</span></div>
    <p>${session.locked_at ? '确认名单已锁定。' : '开课后由本场讲师锁定确认名单。'} 共 ${confirmed.length} 个确认席位。</p>
    ${signing && session.may_lock ? '<form data-action="session-lock"><button>锁定签到名册</button></form>' : ''}
    ${signing && session.may_submit ? signForm(confirmed) : ''}
    ${session.stage === 'locked' && !session.may_submit && plan.state === 'observing' ? notice('等待下课', '签到名单已锁定，下课后方可签署。') : ''}
    ${roll ? handoffTable(preview) : ''}</section>
    <div><section class="panel"><h3>场次签到凭证</h3>
    ${facts([['本场讲师', session.instructor_name], ['结束时间', `${classTime(session.ends_at)} · 北京时间`],
      ['签到簿', roll?.source_ref || '待讲师签署'], ['交接单', roll?.reconcile_ref || '待观测员交接']])}
    ${roll ? `<ul class="handoff-tally">${Object.entries(outcomes).map(([value, label]) =>
      `<li><span>${label}</span><strong>${preview.filter(row => row.outcome === value).length}</strong></li>`).join('')}</ul>` : ''}
    ${roll && !reconciled && user.role === 'observer' && plan.state === 'observing' ? `<form class="stack spaced" data-action="session-reconcile">
      ${sourceField('交接凭证', '例：育苗课观测交接_1120.csv')}<div class="actions"><button>核对并写入观测</button></div></form>` : ''}
    ${reconciled && !signing ? `<p><a href="${reviewLink}">查看已登记观测 →</a></p>` : ''}</section></div></div>`;
}
