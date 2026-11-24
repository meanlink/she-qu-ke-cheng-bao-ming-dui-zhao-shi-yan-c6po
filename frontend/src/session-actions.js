import {experiment} from './api.js';
import {escape, options} from './view.js';

export const seatLabels = {confirmed: '已确认', waitlisted: '候补', withdrawn: '已撤回'};
export const stageLabels = {enrolling: '席位受理中', locked: '名册已锁定', submitted: '签到待交接', reconciled: '交接完成'};
export const classTime = timestamp => timestamp.replace('T', ' ').slice(0, 16);
export const isEnrolling = (plan, user, session) =>
  plan.state === 'observing' && user.role === 'organizer' && session?.stage === 'enrolling';
export const sourceField = (label, placeholder) =>
  `<label>${escape(label)}<input required name="source_ref" minlength="2" maxlength="100" placeholder="${escape(placeholder)}"></label>`;
export const seatOptions = rows => options(Object.fromEntries(rows.map(row =>
  [row.participant_code, `${row.participant_code} · ${row.arm} 组`])));

const commands = {
  'session-book': ['', 'POST', '课程场次已建立。'],
  'session-capacity': ['/capacity', 'PATCH', '开放席位已调整，候补顺序已更新。'],
  'session-seat': ['/seats', 'POST', '已登记席位申请。'],
  'session-withdraw': [values => `/seats/${encodeURIComponent(values.participant_code)}/withdraw`, 'POST', '已保留撤回凭证并核对候补递补。'],
  'session-lock': ['/attendance/lock', 'POST', '签到名册已锁定。'],
  'session-sign': ['/attendance', 'POST', '签到表已签署。'],
  'session-reconcile': ['/attendance/reconcile', 'POST', '签到交接完成，观测已登记。'],
};

export async function sessionAction(action, code, form) {
  const values = Object.fromEntries(new FormData(form));
  let [path, method, message] = commands[action];
  if (typeof path === 'function') {
    path = path(values);
    delete values.participant_code;
  }
  for (const key of ['room_limit', 'seat_limit']) {
    if (key in values) values[key] = Number(values[key]);
  }
  if (action === 'session-sign') {
    values.entries = [...form.querySelectorAll('select[data-roll-member]')].map(select =>
      ({participant_code: select.dataset.rollMember, status: select.value}));
  }
  await experiment(code, `/session${path}`, {method, body: values});
  return message;
}
