from fastapi import HTTPException

from .contracts import Outcome, Phase
from .control_records import delivered_dates, enforce_observation_after_delivery, latest_clearance
from .db import audit, connect
from .session_policy import find_session, local_now, require_session
from .workflow import assignments, in_phase, load_plan


def find_roll(conn, plan):
    return conn.execute('SELECT * FROM attendance_roll WHERE plan_id = %s', (plan['id'],)).fetchone()


def outcomes(conn, plan):
    return conn.execute(
        '''SELECT a.participant_code, a.arm, CASE
               WHEN r.id IS NULL THEN 'no_signup'
               WHEN r.withdrawn_on IS NOT NULL THEN 'withdrawn'
               WHEN r.confirmed_at IS NULL THEN 'waitlisted'
               ELSE m.status END AS outcome
           FROM participant_assignment a
           LEFT JOIN seat_request r USING (plan_id, participant_code)
           LEFT JOIN attendance_mark m USING (plan_id, participant_code)
           WHERE a.plan_id = %s AND a.exclusion_reason IS NULL ORDER BY a.arm, a.participant_code''',
        (plan['id'],),
    ).fetchall()


def instructor_session(conn, plan, actor):
    session = find_session(conn, plan)
    if not session or session['instructor_email'] != actor:
        raise HTTPException(403, '仅本场讲师可锁定名册和签署签到表')
    in_phase(plan, Phase.OBSERVING)
    return session


def lock_roll(code, actor):
    with connect() as conn:
        plan = load_plan(conn, code, lock=True)
        session = instructor_session(conn, plan, actor)
        if session['locked_at']:
            raise HTTPException(409, '签到名册已锁定')
        if local_now() < session['starts_at']:
            raise HTTPException(409, '到开课时间后方可锁定签到名册')
        conn.execute('UPDATE course_session SET locked_at = now() WHERE plan_id = %s', (plan['id'],))
        audit(conn, plan['id'], actor, 'roll_locked', '确认席位名单锁定')


def submit_roll(code, item, actor):
    with connect() as conn:
        plan = load_plan(conn, code, lock=True)
        session = instructor_session(conn, plan, actor)
        if not session['locked_at'] or local_now() < session['ends_at']:
            raise HTTPException(409, '须先锁定名册并等到下课，再签署签到表')
        if find_roll(conn, plan):
            raise HTTPException(409, '签到表已签署')
        confirmed = conn.execute(
            '''SELECT participant_code FROM seat_request WHERE plan_id = %s
               AND confirmed_at IS NOT NULL AND withdrawn_on IS NULL''', (plan['id'],),
        ).fetchall()
        if {row['participant_code'] for row in confirmed} != {entry.participant_code for entry in item.entries}:
            raise HTTPException(422, '签到表须覆盖全部确认席位，候补及撤回居民不得签到；整表未保存')
        conn.execute('INSERT INTO attendance_roll (plan_id, source_ref, submitted_by) VALUES (%s,%s,%s)',
                     (plan['id'], item.source_ref, actor))
        with conn.cursor() as cursor:
            cursor.executemany('INSERT INTO attendance_mark (plan_id, participant_code, status) VALUES (%s,%s,%s)',
                               [(plan['id'], entry.participant_code, entry.status) for entry in item.entries])
        audit(conn, plan['id'], actor, 'roll_signed', f'{len(confirmed)} 个确认席位 · {item.source_ref}')


def reconcile(code, item, actor):
    with connect() as conn:
        plan = load_plan(conn, code, lock=True)
        in_phase(plan, Phase.OBSERVING)
        session = require_session(conn, plan)
        roll = find_roll(conn, plan)
        if not roll or roll['reconciled_at']:
            raise HTTPException(409, '须有已签署且待交接的签到表')
        observed_on = session['starts_at'].date()
        controlled = latest_clearance(conn, plan)
        deliveries = delivered_dates(conn, plan) if controlled else {}
        if any(row['outcome'] for row in assignments(conn, plan)):
            raise HTTPException(409, '已存在独立观测，请核对后再交接')
        handoff = outcomes(conn, plan)
        for row in handoff:
            if controlled:
                enforce_observation_after_delivery(row['participant_code'], observed_on, deliveries)
        with conn.cursor() as cursor:
            cursor.executemany(
                '''UPDATE participant_assignment SET outcome = %s, source_ref = %s, observed_on = %s, observed_by = %s
                   WHERE plan_id = %s AND participant_code = %s''',
                [(row['outcome'], item.source_ref, observed_on, actor, plan['id'], row['participant_code']) for row in handoff],
            )
        conn.execute('UPDATE attendance_roll SET reconciled_by = %s, reconciled_at = now(), reconcile_ref = %s WHERE plan_id = %s',
                     (actor, item.source_ref, plan['id']))
        attended = sum(row['outcome'] == Outcome.ATTENDED for row in handoff)
        audit(conn, plan['id'], actor, 'roll_reconciled', f'{len(handoff)} 条观测 · {attended} 人到课 · {item.source_ref}')
