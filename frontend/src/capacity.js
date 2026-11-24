import {classTime, isEnrolling, sourceField, stageLabels} from './session-actions.js';
import {escape, facts, notice, options, recordLog} from './view.js';

function bookingForm(plan, instructors) {
  const choices = Object.fromEntries(instructors.map(row => [row.email, `${row.display_name} · 带班上限 ${row.teaching_limit} 人`]));
  return `<section class="panel"><h2>安排课程场次</h2><p>所选讲师须有空档。开放席位由讲师带班额度和教室容量共同约束。</p>
    <form class="stack" data-action="session-book">
      <label>讲师<select name="instructor_email" required>${options({'': '选择讲师', ...choices})}</select></label>
      <div class="fields"><label>开课时间<input type="datetime-local" name="starts_at" required value="${plan.window_end}T09:00"></label>
      <label>下课时间<input type="datetime-local" name="ends_at" required value="${plan.window_end}T10:30"></label></div>
      <div class="fields"><label>教室上限<input type="number" min="1" max="500" name="room_limit" required></label>
      <label>开放席位<input type="number" min="1" max="500" name="seat_limit" required></label></div>
      ${sourceField('排课凭证', '例：花圃教室排课单_1120.csv')}
      <div class="actions"><button>确认排课</button></div>
    </form></section>`;
}

export function capacityPage(data, user, ledger) {
  const {plan, events} = data;
  const {session, instructors, seats, may_book: canBook} = ledger;
  if (!session) {
    const content = canBook && instructors.length ? bookingForm(plan, instructors) : notice('尚无课程场次',
      canBook ? '没有可排课的讲师，请先配置带班额度。' : '课程统筹可在随机分组完成后、登记首条观测前安排场次。');
    return `<div class="split">${content}<section class="panel"><h3>排课条件</h3>
      ${facts([['地点', plan.site], ['观测窗口', `${plan.window_start} 至 ${plan.window_end}`], ['本地时区', '北京时间']])}</section></div>`;
  }
  const confirmed = seats.filter(row => row.status === 'confirmed').length;
  const waiting = seats.filter(row => row.status === 'waitlisted').length;
  const upper = Math.min(session.room_limit, session.teaching_limit);
  return `<div class="split"><div><section class="panel"><div class="inline"><h2>讲师与场次容量</h2><span class="badge">${stageLabels[session.stage]}</span></div>
    ${facts([['带班讲师', session.instructor_name], ['上课时间', `${classTime(session.starts_at)}–${classTime(session.ends_at).slice(11)} · 北京时间`], ['排课凭证', session.schedule_ref]])}
    <dl class="session-tally"><div><dt>教室上限</dt><dd>${session.room_limit}</dd></div><div><dt>讲师上限</dt><dd>${session.teaching_limit}</dd></div>
    <div><dt>开放席位</dt><dd>${session.seat_limit}</dd></div></dl>
    <p>${confirmed} 个确认席位 · ${waiting} 人候补</p><a href="#/${escape(plan.code)}/waitlist">查看席位与候补 →</a></section>
    ${recordLog(events.filter(row => ['session_booked', 'capacity_revised'].includes(row.event)))}</div>
    <section class="panel"><h3>开放席位调整</h3>
    ${isEnrolling(plan, user, session) ? `<p>调高席位数会按登记顺序递补。当前可调整范围为 ${Math.max(confirmed, 1)}–${upper} 席。</p>
      <form class="stack" data-action="session-capacity"><label>新开放席位<input type="number" required min="${Math.max(confirmed, 1)}" max="${upper}" name="seat_limit" value="${session.seat_limit}"></label>
      ${sourceField('变更凭证', '例：追加种植操作台_1120.csv')}<div class="actions"><button>保存席位调整</button></div></form>` :
      '<p>课程统筹可在签到名册锁定前调整席位。</p>'}</section></div>`;
}
