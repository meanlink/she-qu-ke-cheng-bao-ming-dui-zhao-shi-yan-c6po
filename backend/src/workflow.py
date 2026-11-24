import hashlib
import json
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from psycopg.errors import UniqueViolation

from .control_records import (
    delivered_dates, enforce_analysis_ready, enforce_cleared_roster,
    enforce_observation_after_delivery, latest_clearance,
)
from .contracts import Outcome, Phase
from .session_policy import ensure_manual_workflow, find_session, require_handoff
from .db import audit, connect

SITE_TIMEZONE = ZoneInfo('Asia/Shanghai')
BALANCE_MESSAGE = '有效样本低于每组下限，或任一组超出 45%–55% 的比例范围'


def load_plan(conn, code, lock=False):
    suffix = ' FOR UPDATE' if lock else ''
    plan = conn.execute('SELECT * FROM experiment_plan WHERE code = %s' + suffix, (code,)).fetchone()
    if not plan:
        raise HTTPException(404, '找不到该实验方案')
    return plan


def in_phase(plan, *allowed):
    if plan['state'] not in allowed:
        raise HTTPException(409, '当前阶段无法执行此操作，请刷新后核对状态')


def set_phase(conn, plan, phase):
    conn.execute('UPDATE experiment_plan SET state = %s WHERE id = %s', (phase, plan['id']))


def assignments(conn, plan):
    return conn.execute(
        'SELECT * FROM participant_assignment WHERE plan_id = %s ORDER BY arm, participant_code', (plan['id'],),
    ).fetchall()


def counts(rows):
    groups = {arm: dict(assigned=0, eligible=0, recorded=0, signup=0, attendance=0) for arm in ('A', 'B')}
    for row in rows:
        group = groups[row['arm']]
        group['assigned'] += 1
        if row['exclusion_reason']:
            continue
        group['eligible'] += 1
        group['recorded'] += row['outcome'] is not None
        group['signup'] += row['outcome'] is not None and row['outcome'] != Outcome.NO_SIGNUP
        group['attendance'] += row['outcome'] == 'attended'
    return groups


def balanced(plan, groups):
    a, b = (groups[arm]['eligible'] for arm in ('A', 'B'))
    return min(a, b) >= plan['min_per_arm'] and 45 * (a + b) <= 100 * a <= 55 * (a + b)


def plan_list(instructor_email=None):
    with connect() as conn:
        if instructor_email:
            return conn.execute(
                'SELECT p.* FROM experiment_plan p JOIN course_session s ON s.plan_id = p.id'
                ' WHERE s.instructor_email = %s ORDER BY p.id DESC', (instructor_email,),
            ).fetchall()
        return conn.execute('SELECT * FROM experiment_plan ORDER BY id DESC').fetchall()


def dossier(code, instructor_email=None):
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        plan = load_plan(conn, code)
        session = find_session(conn, plan)
        if instructor_email and (not session or session['instructor_email'] != instructor_email):
            raise HTTPException(403, '讲师仅可查阅自己的场次')
        rows = assignments(conn, plan)
        review = conn.execute('SELECT * FROM result_review WHERE plan_id = %s', (plan['id'],)).fetchone()
        events = conn.execute(
            'SELECT actor, event, detail, occurred_at FROM audit_event WHERE plan_id = %s ORDER BY id DESC LIMIT 12',
            (plan['id'],),
        ).fetchall()
        clearance = latest_clearance(conn, plan)
        pending_corrections = 0
        if clearance:
            deliveries = delivered_dates(conn, plan)
            for row in rows:
                row['delivered_on'] = deliveries.get(row['participant_code'])
            pending_corrections = conn.execute(
                "SELECT count(*) AS total FROM observation_correction WHERE plan_id = %s AND status = 'pending'", (plan['id'],),
            ).fetchone()['total']
        return {'plan': plan, 'assignments': rows, 'groups': counts(rows), 'review': review, 'events': events,
                'clearance_status': clearance['status'] if clearance else None, 'pending_corrections': pending_corrections,
                'has_session': session is not None}


def insert_plan(conn, item, actor):
    saved = conn.execute(
        '''INSERT INTO experiment_plan
           (code, title, question, site, control_invite, variant_invite, window_start, window_end,
            primary_metric, min_per_arm, author)
           VALUES (%(code)s, %(title)s, %(question)s, %(site)s, %(control_invite)s, %(variant_invite)s,
                   %(window_start)s, %(window_end)s, %(primary_metric)s, %(min_per_arm)s, %(author)s)
           RETURNING *''', {**item.model_dump(), 'author': actor},
    ).fetchone()
    audit(conn, saved['id'], actor, 'drafted', '建立课程实验方案')
    return saved


def create_plan(item, actor):
    try:
        with connect() as conn:
            return insert_plan(conn, item, actor)
    except UniqueViolation as exc:
        raise HTTPException(409, '实验编号已存在') from exc


def edit_plan(code, item, actor):
    with connect() as conn:
        plan = load_plan(conn, code, lock=True)
        in_phase(plan, Phase.DRAFT)
        conn.execute(
            '''UPDATE experiment_plan SET title = %(title)s, question = %(question)s, site = %(site)s,
               control_invite = %(control_invite)s, variant_invite = %(variant_invite)s,
               window_start = %(window_start)s, window_end = %(window_end)s,
               primary_metric = %(primary_metric)s, min_per_arm = %(min_per_arm)s WHERE id = %(id)s''',
            {**item.model_dump(), 'id': plan['id']},
        )
        audit(conn, plan['id'], actor, 'edited', '更新方案及观测口径')


def mark_checked(conn, plan, actor):
    in_phase(plan, Phase.DRAFT)
    conn.execute('UPDATE experiment_plan SET state = %s, checked_by = %s, checked_at = now() WHERE id = %s',
                 (Phase.CHECKED, actor, plan['id']))
    audit(conn, plan['id'], actor, 'checked', '确认两种邀请、主指标、观测窗口与每组下限')


def check(code, actor):
    with connect() as conn:
        mark_checked(conn, load_plan(conn, code, lock=True), actor)


def allocate(conn, plan, roster, actor, seed):
    in_phase(plan, Phase.CHECKED)
    if len(roster) < 2 * plan['min_per_arm']:
        raise HTTPException(422, f"名单人数不足，至少需要 {2 * plan['min_per_arm']} 人")
    enforce_cleared_roster(conn, plan, roster)
    roster_digest = hashlib.sha256('\n'.join(sorted(roster)).encode()).hexdigest()
    ordered = sorted(roster, key=lambda code: (hashlib.sha256(f'{seed}:{code}'.encode()).digest(), code))
    rows = [(plan['id'], member, 'AB'[index % 2]) for index, member in enumerate(ordered)]
    with conn.cursor() as cur:
        cur.executemany('INSERT INTO participant_assignment (plan_id, participant_code, arm) VALUES (%s,%s,%s)', rows)
    conn.execute('UPDATE experiment_plan SET allocation_seed = %s, roster_digest = %s, state = %s WHERE id = %s',
                 (seed, roster_digest, Phase.OBSERVING, plan['id']))
    audit(conn, plan['id'], actor, 'allocated', f'固化 {len(rows)} 名居民的原始随机组别')


def assign(code, roster, actor):
    with connect() as conn:
        allocate(conn, load_plan(conn, code, lock=True), roster, actor, secrets.token_hex(16))


def freeze(conn, plan, actor, reason):
    conn.execute(
        '''INSERT INTO result_review (plan_id, status, requested_by, freeze_reason)
           VALUES (%s, 'frozen', COALESCE((SELECT requested_by FROM result_review WHERE plan_id = %s), %s), %s)
           ON CONFLICT (plan_id) DO UPDATE SET status = 'frozen', freeze_reason = excluded.freeze_reason,
               result = NULL, input_digest = NULL''', (plan['id'], plan['id'], actor, reason),
    )
    set_phase(conn, plan, Phase.FROZEN)
    audit(conn, plan['id'], actor, 'frozen', reason)


def exclude(code, resident, item, actor):
    with connect() as conn:
        plan = load_plan(conn, code, lock=True)
        in_phase(plan, Phase.OBSERVING)
        ensure_manual_workflow(conn, plan)
        rows = assignments(conn, plan)
        if any(row['outcome'] is not None for row in rows):
            raise HTTPException(409, '已开始观测，资格名单已锁定')
        updated = conn.execute(
            '''UPDATE participant_assignment SET exclusion_reason = %s, exclusion_ref = %s
               WHERE plan_id = %s AND participant_code = %s AND exclusion_reason IS NULL''',
            (item.reason, item.reference, plan['id'], resident),
        )
        if updated.rowcount != 1:
            raise HTTPException(409, '找不到该居民或该居民已做资格剔除')
        audit(conn, plan['id'], actor, 'excluded', f'{resident} · {item.reason} · {item.reference}')
        if not balanced(plan, counts(assignments(conn, plan))):
            freeze(conn, plan, actor, BALANCE_MESSAGE)


def report_transfer(code, resident, item, actor):
    with connect() as conn:
        plan = load_plan(conn, code, lock=True)
        in_phase(plan, Phase.OBSERVING, Phase.QUEUED, Phase.REVIEW)
        row = conn.execute(
            '''UPDATE participant_assignment SET reported_arm = %s, deviation_ref = %s
               WHERE plan_id = %s AND participant_code = %s AND arm <> %s AND exclusion_reason IS NULL
               RETURNING arm''', (item.reported_arm, item.reference, plan['id'], resident, item.reported_arm),
        ).fetchone()
        if not row:
            raise HTTPException(422, '请选择有效居民和与原组不同的实际邀请组')
        freeze(conn, plan, actor, f'{resident} 中途改组：原组 {row["arm"]}，实际收到 {item.reported_arm} 组邀请。{item.reference}')


def observe(code, batch, actor):
    with connect() as conn:
        plan = load_plan(conn, code, lock=True)
        in_phase(plan, Phase.OBSERVING)
        ensure_manual_workflow(conn, plan)
        if not plan['window_start'] <= batch.observed_on <= min(plan['window_end'], datetime.now(SITE_TIMEZONE).date()):
            raise HTTPException(422, '观测日期必须位于锁定窗口内，且不可登记未来观测')
        eligible = {row['participant_code']: row for row in assignments(conn, plan) if not row['exclusion_reason']}
        if any(entry.code not in eligible for entry in batch.entries):
            raise HTTPException(422, '批次包含名单外或已剔除的居民，整批未保存')
        if latest_clearance(conn, plan):
            deliveries = delivered_dates(conn, plan)
            for entry in batch.entries:
                if eligible[entry.code]['outcome'] is not None:
                    raise HTTPException(409, f'{entry.code} 已登记观测，请提交更正单；整批未保存')
                enforce_observation_after_delivery(entry.code, batch.observed_on, deliveries)
        with conn.cursor() as cur:
            cur.executemany(
                '''UPDATE participant_assignment SET outcome = %s, source_ref = %s, observed_on = %s, observed_by = %s
                   WHERE plan_id = %s AND participant_code = %s''',
                [(entry.outcome, batch.source_ref, batch.observed_on, actor, plan['id'], entry.code) for entry in batch.entries],
            )
        audit(conn, plan['id'], actor, 'observed', f'{len(batch.entries)} 人 · {batch.observed_on} · {batch.source_ref}')


def queue_analysis(code, actor):
    with connect() as conn:
        plan = load_plan(conn, code, lock=True)
        in_phase(plan, Phase.OBSERVING)
        if datetime.now(SITE_TIMEZONE).date() < plan['window_end']:
            raise HTTPException(409, '观测窗口尚未结束')
        rows = assignments(conn, plan)
        groups = counts(rows)
        if not balanced(plan, groups):
            freeze(conn, plan, actor, BALANCE_MESSAGE)
            return False
        require_handoff(conn, plan)
        enforce_analysis_ready(conn, plan, rows)
        if any(group['recorded'] != group['eligible'] for group in groups.values()):
            raise HTTPException(409, '有效名单还有未登记的结果，必须区分未报名与缺失记录')
        conn.execute('INSERT INTO result_review (plan_id, status, requested_by) VALUES (%s,%s,%s)',
                     (plan['id'], 'queued', actor))
        set_phase(conn, plan, Phase.QUEUED)
        audit(conn, plan['id'], actor, 'queued', '封存报名与到课结果，等待计算')
        return True


def decide(code, item, actor):
    with connect() as conn:
        plan = load_plan(conn, code, lock=True)
        in_phase(plan, Phase.REVIEW, Phase.FROZEN)
        if plan['state'] == Phase.FROZEN and item.decision == Phase.APPROVED:
            raise HTTPException(409, '冻结分析只能驳回，原始分组与观测保留')
        updated = conn.execute(
            '''UPDATE result_review SET status = %s, decision_note = %s, decided_by = %s, decided_at = now()
               WHERE plan_id = %s AND status IN ('ready','frozen') AND requested_by <> %s''',
            (item.decision, item.note, actor, plan['id'], actor),
        )
        if updated.rowcount != 1:
            raise HTTPException(409, '复核单状态已变化或提交人不能签署自己的结果')
        set_phase(conn, plan, item.decision)
        audit(conn, plan['id'], actor, item.decision, item.note)


def analysis_input(plan, rows):
    fields = ('participant_code', 'arm', 'outcome', 'source_ref', 'observed_on', 'exclusion_reason', 'exclusion_ref')
    payload = dict(code=plan['code'], metric=plan['primary_metric'], allocation=plan['roster_digest'],
                   assignments=[{key: row[key] for key in fields} for row in rows])
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
