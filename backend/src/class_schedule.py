from fastapi import HTTPException

from .contracts import Phase
from .control_records import delivered_dates
from .db import audit, connect
from .session_policy import ensure_enrolling, find_session, require_session
from .seat_queue import promote
from .workflow import in_phase, load_plan


def can_book(conn, plan):
    if plan['state'] != Phase.OBSERVING:
        return False
    return not conn.execute(
        'SELECT 1 FROM participant_assignment WHERE plan_id = %s AND outcome IS NOT NULL LIMIT 1', (plan['id'],),
    ).fetchone()


def validate_limit(seats, room, teaching):
    if seats > min(room, teaching):
        raise HTTPException(422, f'开放席位不得超过教室上限 {room} 或讲师带班上限 {teaching}')


def book(code, item, actor):
    with connect() as conn:
        plan = load_plan(conn, code, lock=True)
        if find_session(conn, plan):
            raise HTTPException(409, '该实验已有课程场次，请在容量页调整开放席位')
        if not can_book(conn, plan):
            raise HTTPException(409, '仅可在完成随机分组后、登记首条观测前安排场次')
        if not plan['window_start'] <= item.starts_at.date() <= plan['window_end']:
            raise HTTPException(422, '上课日期须位于实验观测窗口内')
        if any(day > item.starts_at.date() for day in delivered_dates(conn, plan).values()):
            raise HTTPException(422, '上课日期不能早于已登记的邀请送达日期')
        instructor = conn.execute(
            '''SELECT i.teaching_limit FROM instructor_capacity i JOIN staff s ON s.email = i.email
               WHERE i.email = %s AND s.role = 'instructor' FOR UPDATE OF i''', (item.instructor_email,),
        ).fetchone()
        if not instructor:
            raise HTTPException(422, '请选择有带班额度的讲师')
        validate_limit(item.seat_limit, item.room_limit, instructor['teaching_limit'])
        conflict = conn.execute(
            '''SELECT 1 FROM course_session WHERE instructor_email = %s
               AND starts_at < %s AND ends_at > %s LIMIT 1''',
            (item.instructor_email, item.ends_at, item.starts_at),
        ).fetchone()
        if conflict:
            raise HTTPException(409, '讲师在该时段已排课，请调整时段或选择其他讲师')
        conn.execute(
            '''INSERT INTO course_session (plan_id, instructor_email, starts_at, ends_at, room_limit, seat_limit,
               schedule_ref, booked_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
            (plan['id'], item.instructor_email, item.starts_at, item.ends_at, item.room_limit, item.seat_limit,
             item.source_ref, actor),
        )
        audit(conn, plan['id'], actor, 'session_booked', f'{item.starts_at:%m-%d %H:%M} · {item.seat_limit} 席 · {item.source_ref}')


def revise_capacity(code, item, actor):
    with connect() as conn:
        plan = load_plan(conn, code, lock=True)
        in_phase(plan, Phase.OBSERVING)
        session = require_session(conn, plan)
        ensure_enrolling(session)
        validate_limit(item.seat_limit, session['room_limit'], session['teaching_limit'])
        confirmed = conn.execute(
            '''SELECT count(*) AS total FROM seat_request WHERE plan_id = %s
               AND confirmed_at IS NOT NULL AND withdrawn_on IS NULL''', (plan['id'],),
        ).fetchone()['total']
        if item.seat_limit < confirmed:
            raise HTTPException(409, f'已有 {confirmed} 个确认席位，不可调低至该人数以下')
        old_limit = session['seat_limit']
        if item.seat_limit == old_limit:
            raise HTTPException(409, '开放席位数未变更')
        conn.execute('UPDATE course_session SET seat_limit = %s WHERE plan_id = %s', (item.seat_limit, plan['id']))
        audit(conn, plan['id'], actor, 'capacity_revised', f'{old_limit} → {item.seat_limit} 席 · {item.source_ref}')
        promote(conn, plan, item.seat_limit, actor)
