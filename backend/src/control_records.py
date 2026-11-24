from fastapi import HTTPException

from .control_contracts import ControlStatus
from .db import audit


def latest_clearance(conn, plan):
    return conn.execute(
        'SELECT * FROM roster_clearance WHERE plan_id = %s ORDER BY version DESC LIMIT 1', (plan['id'],),
    ).fetchone()


def add_clearance(conn, plan, item, version, actor):
    conn.execute(
        'INSERT INTO roster_clearance (plan_id, version, codes, source_ref, submitted_by) VALUES (%s,%s,%s,%s,%s)',
        (plan['id'], version, sorted(item.codes), item.source_ref, actor),
    )
    audit(conn, plan['id'], actor, 'clearance_submitted', f'第 {version} 版 · {len(item.codes)} 人 · {item.source_ref}')


def enforce_cleared_roster(conn, plan, roster):
    clearance = latest_clearance(conn, plan)
    if clearance is None:
        return
    if clearance['status'] != ControlStatus.APPROVED:
        raise HTTPException(409, '请等待最新一版资格名单审批通过，再进行随机分组')
    if sorted(roster) != clearance['codes']:
        raise HTTPException(409, '分组名单必须与获批资格名单完全一致')


def delivered_dates(conn, plan):
    rows = conn.execute(
        "SELECT participant_code, delivered_on FROM invitation_attempt WHERE plan_id = %s AND status = 'delivered'",
        (plan['id'],),
    ).fetchall()
    return {row['participant_code']: row['delivered_on'] for row in rows}


def enforce_observation_after_delivery(code, observed_on, deliveries):
    date = deliveries.get(code)
    if date is None:
        raise HTTPException(409, f'{code} 尚无送达回执，请先核对邀请送达')
    if observed_on < date:
        raise HTTPException(422, f'{code} 的观测日期早于邀请送达日期')


def enforce_analysis_ready(conn, plan, rows):
    if latest_clearance(conn, plan) is None:
        return
    if conn.execute(
        "SELECT 1 FROM observation_correction WHERE plan_id = %s AND status = 'pending' LIMIT 1", (plan['id'],),
    ).fetchone():
        raise HTTPException(409, '仍有待复核的观测更正，处理完毕后才能封存')
    deliveries = delivered_dates(conn, plan)
    if any(row['participant_code'] not in deliveries for row in rows if not row['exclusion_reason']):
        raise HTTPException(409, '有效名单仍有未送达邀请，请完成送达核对后再封存')
