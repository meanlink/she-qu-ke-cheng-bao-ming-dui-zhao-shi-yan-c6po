from datetime import datetime

from fastapi import HTTPException

from . import workflow
from .session_policy import ensure_manual_workflow, find_session
from .control_contracts import ControlStatus
from .control_records import add_clearance, delivered_dates, enforce_observation_after_delivery, latest_clearance
from .contracts import Phase
from .db import audit, connect


def details(code):
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        plan = workflow.load_plan(conn, code)
        params = (plan['id'],)
        return {
            'clearances': conn.execute('SELECT * FROM roster_clearance WHERE plan_id = %s ORDER BY version DESC', params).fetchall(),
            'invitations': conn.execute('SELECT * FROM invitation_attempt WHERE plan_id = %s ORDER BY id DESC', params).fetchall(),
            'corrections': conn.execute('SELECT * FROM observation_correction WHERE plan_id = %s ORDER BY id DESC', params).fetchall(),
        }


def submit_clearance(code, item, actor):
    with connect() as conn:
        plan = workflow.load_plan(conn, code, lock=True)
        workflow.in_phase(plan, Phase.CHECKED)
        previous = latest_clearance(conn, plan)
        if previous and previous['status'] != ControlStatus.RETURNED:
            raise HTTPException(409, '只有退回的名单可以修订，待审及获批的版本均已锁定')
        minimum = 2 * plan['min_per_arm']
        if len(item.codes) < minimum:
            raise HTTPException(422, f'资格名单至少需要 {minimum} 人')
        add_clearance(conn, plan, item, previous['version'] + 1 if previous else 1, actor)


def decide_clearance(code, version, item, actor):
    with connect() as conn:
        plan = workflow.load_plan(conn, code, lock=True)
        workflow.in_phase(plan, Phase.CHECKED)
        record = latest_clearance(conn, plan)
        if not record or record['version'] != version or record['status'] != ControlStatus.PENDING:
            raise HTTPException(409, '只有最新一版待审核的资格名单可以签署')
        if record['submitted_by'] == actor:
            raise HTTPException(409, '提交人不能签署自己的资格名单')
        conn.execute(
            '''UPDATE roster_clearance SET status = %s, decision_note = %s, decided_by = %s, decided_at = now()
               WHERE plan_id = %s AND version = %s''', (item.decision, item.note, actor, plan['id'], version),
        )
        audit(conn, plan['id'], actor, f'clearance_{item.decision}', f'第 {version} 版 · {item.note}')


def require_controlled(conn, plan):
    if not latest_clearance(conn, plan):
        raise HTTPException(409, '此组未启用资格预审，请继续使用原有报名观测流程')


def require_window(plan, observed_on, message):
    if not plan['window_start'] <= observed_on <= min(plan['window_end'], datetime.now(workflow.SITE_TIMEZONE).date()):
        raise HTTPException(422, message)


def record_invitations(code, item, actor):
    with connect() as conn:
        plan = workflow.load_plan(conn, code, lock=True)
        workflow.in_phase(plan, Phase.OBSERVING)
        require_controlled(conn, plan)
        require_window(plan, item.delivered_on, '邀请日期必须位于观测窗口内且不能晚于今天')
        session = find_session(conn, plan)
        if session and item.delivered_on > session['starts_at'].date():
            raise HTTPException(422, '课程邀请回执日期不能晚于上课日期')
        codes = set(item.codes)
        allowed = {row['participant_code'] for row in workflow.assignments(conn, plan)
                   if not row['exclusion_reason'] and row['arm'] == item.arm}
        if not codes <= allowed:
            raise HTTPException(422, '回执批次包含无效居民或实际使用的邀请组与原分组不符，整批未保存')
        previous = conn.execute(
            '''SELECT participant_code, source_ref, status, delivered_on FROM invitation_attempt
               WHERE plan_id = %s AND participant_code = ANY(%s)''', (plan['id'], item.codes),
        ).fetchall()
        if any(row['status'] == 'delivered' for row in previous):
            raise HTTPException(409, '批次包含已送达居民，送达回执已锁定')
        if any(row['source_ref'] == item.source_ref for row in previous):
            raise HTTPException(409, '存在已经登记的回执凭证，请核对后重试')
        if any(row['delivered_on'] > item.delivered_on for row in previous):
            raise HTTPException(422, '本次尝试日期不能早于已登记的邀请尝试')
        with conn.cursor() as cur:
            cur.executemany(
                '''INSERT INTO invitation_attempt (plan_id, participant_code, delivered_on, channel, status, source_ref, recorded_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                [(plan['id'], resident, item.delivered_on, item.channel, item.status, item.source_ref, actor)
                 for resident in item.codes],
            )
        label = '送达' if item.status == 'delivered' else '未送达'
        audit(conn, plan['id'], actor, 'invitation_recorded', f'{item.arm} 组 · {len(codes)} 人{label} · {item.source_ref}')


def submit_correction(code, item, actor):
    with connect() as conn:
        plan = workflow.load_plan(conn, code, lock=True)
        workflow.in_phase(plan, Phase.OBSERVING)
        require_controlled(conn, plan)
        ensure_manual_workflow(conn, plan)
        require_window(plan, item.proposed_observed_on, '更正后的观测日期必须位于观测窗口内且不能晚于今天')
        current = conn.execute(
            'SELECT * FROM participant_assignment WHERE plan_id = %s AND participant_code = %s',
            (plan['id'], item.participant_code),
        ).fetchone()
        if not current or not current['outcome']:
            raise HTTPException(422, '只有已经登记观测结果的居民可以发起更正')
        enforce_observation_after_delivery(item.participant_code, item.proposed_observed_on, delivered_dates(conn, plan))
        if current['outcome'] == item.proposed_outcome:
            raise HTTPException(422, '更正后的观测结果必须与原结果不同')
        if conn.execute(
            "SELECT 1 FROM observation_correction WHERE plan_id = %s AND participant_code = %s AND status = 'pending'",
            (plan['id'], item.participant_code),
        ).fetchone():
            raise HTTPException(409, '该居民已有待复核的更正单')
        conn.execute(
            '''INSERT INTO observation_correction
               (plan_id, participant_code, original_outcome, original_observed_on, original_source_ref,
                original_observed_by, proposed_outcome, proposed_observed_on, proposed_source_ref, reason, submitted_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (plan['id'], item.participant_code, current['outcome'], current['observed_on'], current['source_ref'],
             current['observed_by'], item.proposed_outcome, item.proposed_observed_on, item.proposed_source_ref, item.reason, actor),
        )
        audit(conn, plan['id'], actor, 'correction_submitted', f'{item.participant_code} · {item.proposed_source_ref}')


def decide_correction(code, correction_id, item, actor):
    with connect() as conn:
        plan = workflow.load_plan(conn, code, lock=True)
        workflow.in_phase(plan, Phase.OBSERVING)
        record = conn.execute(
            'SELECT * FROM observation_correction WHERE plan_id = %s AND id = %s', (plan['id'], correction_id),
        ).fetchone()
        if not record or record['status'] != ControlStatus.PENDING:
            raise HTTPException(409, '只有该实验待复核的更正单可以签署')
        if record['submitted_by'] == actor:
            raise HTTPException(409, '提交人不能签署自己的观测更正单')
        if item.decision == ControlStatus.APPROVED:
            updated = conn.execute(
                '''UPDATE participant_assignment SET outcome = %(proposed_outcome)s, source_ref = %(proposed_source_ref)s,
                   observed_on = %(proposed_observed_on)s, observed_by = %(submitted_by)s
                   WHERE plan_id = %(plan_id)s AND participant_code = %(participant_code)s AND outcome = %(original_outcome)s
                     AND observed_on = %(original_observed_on)s AND source_ref = %(original_source_ref)s
                     AND observed_by = %(original_observed_by)s''', record,
            )
            if updated.rowcount != 1:
                raise HTTPException(409, '原观测已变化，请核对相关记录')
        conn.execute(
            '''UPDATE observation_correction SET status = %s, decision_note = %s, decided_by = %s, decided_at = now()
               WHERE id = %s''', (item.decision, item.note, actor, correction_id),
        )
        audit(conn, plan['id'], actor, f'correction_{item.decision}', f'{record["participant_code"]} · {item.note}')
