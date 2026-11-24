from fastapi import HTTPException

from .contracts import Phase
from .control_records import delivered_dates, enforce_observation_after_delivery, latest_clearance
from .db import audit, connect
from .session_policy import ensure_enrolling, local_now, require_session
from .workflow import in_phase, load_plan


def records(conn, plan):
    rows = conn.execute(
        '''SELECT r.*, a.arm FROM seat_request r JOIN participant_assignment a USING (plan_id, participant_code)
           WHERE r.plan_id = %s ORDER BY r.id''', (plan['id'],),
    ).fetchall()
    position = 0
    for row in rows:
        row['queue_position'] = None
        if row['withdrawn_on']:
            row['status'] = 'withdrawn'
        elif row['confirmed_at']:
            row['status'] = 'confirmed'
        else:
            position += 1
            row['status'] = 'waitlisted'
            row['queue_position'] = position
    return rows


def promote(conn, plan, limit, actor):
    # Callers hold the experiment row lock, which serializes admissions and roll locking.
    promoted = conn.execute(
        '''WITH vacancies AS (
               SELECT %s - count(*) AS remaining FROM seat_request WHERE plan_id = %s
               AND confirmed_at IS NOT NULL AND withdrawn_on IS NULL
           ), next_up AS (
               SELECT id FROM seat_request WHERE plan_id = %s AND confirmed_at IS NULL AND withdrawn_on IS NULL
               ORDER BY id LIMIT (SELECT greatest(remaining, 0) FROM vacancies)
           )
           UPDATE seat_request SET confirmed_at = now() FROM next_up
           WHERE seat_request.id = next_up.id RETURNING seat_request.id, participant_code''',
        (limit, plan['id'], plan['id']),
    ).fetchall()
    if promoted:
        for row in sorted(promoted, key=lambda item: item['id']):
            audit(conn, plan['id'], actor, 'seat_confirmed', row['participant_code'])


def enrollment(conn, code, received_on):
    plan = load_plan(conn, code, lock=True)
    in_phase(plan, Phase.OBSERVING)
    session = require_session(conn, plan)
    ensure_enrolling(session)
    last_day = min(session['starts_at'].date(), local_now().date())
    if not plan['window_start'] <= received_on <= last_day:
        raise HTTPException(422, '受理日期须在观测起日与上课日期之间，且不能晚于今天')
    return plan, session


def request_seat(code, item, actor):
    with connect() as conn:
        plan, session = enrollment(conn, code, item.received_on)
        eligible = conn.execute(
            '''SELECT 1 FROM participant_assignment WHERE plan_id = %s AND participant_code = %s
               AND exclusion_reason IS NULL''', (plan['id'], item.participant_code),
        ).fetchone()
        if not eligible:
            raise HTTPException(422, '该居民不在有效随机分组名单内')
        if latest_clearance(conn, plan):
            enforce_observation_after_delivery(item.participant_code, item.received_on, delivered_dates(conn, plan))
        inserted = conn.execute(
            '''INSERT INTO seat_request (plan_id, participant_code, requested_on, request_ref, recorded_by)
               VALUES (%s,%s,%s,%s,%s) ON CONFLICT (plan_id, participant_code) DO NOTHING''',
            (plan['id'], item.participant_code, item.received_on, item.source_ref, actor),
        )
        if not inserted.rowcount:
            raise HTTPException(409, '该居民已有席位登记，含已撤回的记录')
        audit(conn, plan['id'], actor, 'seat_requested', f'{item.participant_code} · {item.received_on} · {item.source_ref}')
        promote(conn, plan, session['seat_limit'], actor)


def withdraw(code, resident, item, actor):
    with connect() as conn:
        plan, session = enrollment(conn, code, item.received_on)
        row = conn.execute(
            'SELECT * FROM seat_request WHERE plan_id = %s AND participant_code = %s', (plan['id'], resident),
        ).fetchone()
        if not row or row['withdrawn_on']:
            raise HTTPException(409, '未找到可撤回的席位登记')
        if item.received_on < row['requested_on']:
            raise HTTPException(422, '撤回日期不能早于报名日期')
        conn.execute(
            '''UPDATE seat_request SET withdrawn_on = %s, withdrawal_ref = %s, withdrawn_by = %s,
               withdrawn_at = now() WHERE id = %s''', (item.received_on, item.source_ref, actor, row['id']),
        )
        audit(conn, plan['id'], actor, 'seat_withdrawn', f'{resident} · {item.received_on} · {item.source_ref}')
        promote(conn, plan, session['seat_limit'], actor)
