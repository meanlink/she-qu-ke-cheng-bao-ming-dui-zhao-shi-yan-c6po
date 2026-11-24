import {isEnrolling, seatLabels, seatOptions, sourceField} from './session-actions.js';
import {escape, notice} from './view.js';

const tally = (seats, status) => seats.filter(row => row.status === status).length;

export function waitlistPage(data, user, ledger) {
  const {plan, assignments} = data;
  const {session, seats} = ledger;
  if (!session) return notice('尚无席位账簿', '排课并确认开放席位后，即可登记报名申请。');
  const received = new Set(seats.map(row => row.participant_code));
  const candidates = assignments.filter(row => !row.exclusion_reason && !received.has(row.participant_code) &&
    (!data.clearance_status || row.delivered_on));
  const queue = seats.filter(row => row.status === 'waitlisted');
  const completed = seats.filter(row => row.status !== 'waitlisted');
  const active = seats.filter(row => row.status !== 'withdrawn');
  const editable = isEnrolling(plan, user, session);
  const lastDay = session.last_received_on;
  const dateField = `<label>受理日期<input type="date" name="received_on" required min="${plan.window_start}" max="${lastDay}" value="${lastDay}"></label>`;
  const table = seats.length ? `<div class="table-wrap" tabindex="0" aria-label="席位申请记录"><table>
    <thead><tr><th>居民</th><th>原组</th><th>席位状态</th><th>受理凭证</th></tr></thead><tbody>
    ${[...queue, ...completed].map(row => `<tr><td class="code">${escape(row.participant_code)}</td><td>${row.arm}</td>
      <td><span class="seat-status ${row.status}">${seatLabels[row.status]}${row.queue_position ? ` · 第 ${row.queue_position} 位` : ''}</span></td>
      <td>${escape(row.request_ref)}<small class="source-line">${row.requested_on}${row.withdrawn_on ? ` · 撤回 ${row.withdrawn_on} · ${escape(row.withdrawal_ref)}` : ''}</small></td></tr>`).join('')}
    </tbody></table></div>` : '<div class="empty">尚无报名。登记首条申请后会显示席位状态。</div>';
  return `<div class="split"><section class="panel"><h2>席位与候补</h2><p>满额后按受理登记顺序候补。确认席位释放时，最先登记且仍有效的候补将自动递补。待递补名单显示在最上方。</p>
    <dl class="session-tally"><div><dt>已确认 / 开放</dt><dd>${tally(seats, 'confirmed')} / ${session.seat_limit}</dd></div>
    <div><dt>等待递补</dt><dd>${tally(seats, 'waitlisted')}</dd></div><div><dt>已撤回</dt><dd>${tally(seats, 'withdrawn')}</dd></div></dl>${table}</section>
    <div>${editable && candidates.length ? `<section class="panel"><h3>登记报名申请</h3><form class="stack" data-action="session-seat">
      <label>居民<select name="participant_code">${seatOptions(candidates)}</select></label>${dateField}
      ${sourceField('报名凭证', '例：服务台报名_019')}<div class="actions"><button>登记报名</button></div></form></section>` : ''}
    ${editable && active.length ? `<section class="panel ${candidates.length ? 'spaced' : ''}"><h3>登记撤回</h3><form class="stack" data-action="session-withdraw">
      <label>居民<select name="participant_code">${seatOptions(active)}</select></label>${dateField}
      ${sourceField('撤回凭证', '例：来电撤回_014')}<div class="actions"><button class="secondary">确认撤回</button></div></form></section>` : ''}
    ${!editable ? notice('席位查阅', '席位变更由课程统筹处理，签到名册锁定后停止更改。') : ''}
    ${editable && !candidates.length && !active.length ? notice('暂无可登记居民', '请核对资格与邀请回执。') : ''}</div></div>`;
}
