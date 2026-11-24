from fastapi import HTTPException

from .attendance_handoff import find_roll, outcomes
from .class_schedule import can_book
from .contracts import Phase, Role
from .db import connect
from .seat_queue import records
from .session_policy import find_session, local_now, stage
from .workflow import load_plan


def read_ledger(code, user):
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        plan = load_plan(conn, code)
        session = find_session(conn, plan)
        if user['role'] == Role.INSTRUCTOR and (not session or session['instructor_email'] != user['email']):
            raise HTTPException(403, '讲师仅可查阅自己的场次')
        roll = find_roll(conn, plan) if session else None
        may_book = not session and user['role'] == Role.ORGANIZER and can_book(conn, plan)
        instructors = conn.execute(
            '''SELECT s.email, s.display_name, i.teaching_limit FROM instructor_capacity i
               JOIN staff s USING (email) WHERE s.role = 'instructor' ORDER BY s.display_name, s.email''',
        ).fetchall() if may_book else []
        now = local_now()
        if session:
            session['stage'] = stage(session, roll)
            session['last_received_on'] = min(session['starts_at'].date(), now.date())
            active = plan['state'] == Phase.OBSERVING
            session['may_lock'] = active and not session['locked_at'] and now >= session['starts_at']
            session['may_submit'] = active and bool(session['locked_at']) and not roll and now >= session['ends_at']
        return {'session': session, 'instructors': instructors, 'may_book': may_book,
                'seats': records(conn, plan) if session else [], 'roll': roll,
                'outcomes': outcomes(conn, plan) if roll else []}
