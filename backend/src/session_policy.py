from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from .session_contracts import SessionStage

SITE_TIMEZONE = ZoneInfo('Asia/Shanghai')


def local_now():
    return datetime.now(SITE_TIMEZONE).replace(tzinfo=None)


def find_session(conn, plan):
    return conn.execute(
        '''SELECT s.*, staff.display_name AS instructor_name, i.teaching_limit FROM course_session s
           JOIN instructor_capacity i ON i.email = s.instructor_email JOIN staff ON staff.email = i.email
           WHERE s.plan_id = %s''', (plan['id'],),
    ).fetchone()


def require_session(conn, plan):
    session = find_session(conn, plan)
    if not session:
        raise HTTPException(409, '请先安排课程场次')
    return session


def ensure_enrolling(session):
    if session['locked_at']:
        raise HTTPException(409, '签到名册已锁定，不能变更席位或候补名单')


def stage(session, roll):
    if roll:
        return SessionStage.RECONCILED if roll['reconciled_at'] else SessionStage.SUBMITTED
    return SessionStage.LOCKED if session['locked_at'] else SessionStage.ENROLLING


def ensure_manual_workflow(conn, plan):
    if find_session(conn, plan):
        raise HTTPException(409, '课程场次已建立，请通过签到交接登记结果；原始资格名单已锁定')


def require_handoff(conn, plan):
    if find_session(conn, plan) and not conn.execute(
        'SELECT 1 FROM attendance_roll WHERE plan_id = %s AND reconciled_at IS NOT NULL', (plan['id'],),
    ).fetchone():
        raise HTTPException(409, '请先完成签到交接，再封存实验')
