import json
import math
from pathlib import Path

from fastapi import HTTPException

from .contracts import Phase
from .db import audit, connect
from .statistics import two_proportion
from .storage import analysis_dir
from .workflow import analysis_input, assignments, counts, load_plan

METRIC_KEYS = ('a_success', 'a_n', 'a_rate', 'b_success', 'b_n', 'b_rate', 'difference', 'z', 'p',
               'ci_low', 'ci_high', 'cohen_h')
TALLY_KEYS = ('assigned', 'eligible', 'recorded', 'signup', 'attendance')
SIGNATURE_MISMATCH = '封存观测复验与签字记录对不上'


def snapshot_path(digest):
    return analysis_dir() / f'{digest}.json'


def _close(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-12)
    return left == right


def _stats_match(stored, expected):
    return expected is not None and isinstance(stored, dict) and all(
        key in stored and _close(stored[key], expected[key]) for key in METRIC_KEYS
    )


def _tallies_match(stored, expected):
    if not isinstance(stored, dict):
        return False
    for arm in ('A', 'B'):
        group = stored.get(arm)
        if not isinstance(group, dict):
            return False
        if not all(key in group and _close(group[key], expected[arm][key]) for key in TALLY_KEYS):
            return False
    return True


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.tmp')
    pending.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    pending.replace(path)


def _review(conn, plan):
    return conn.execute('SELECT * FROM result_review WHERE plan_id = %s', (plan['id'],)).fetchone()


def _supplements(conn, plan):
    return conn.execute('SELECT * FROM snapshot_supplement WHERE plan_id = %s ORDER BY id DESC',
                        (plan['id'],)).fetchall()


def replay(plan, rows):
    """Re-derive the sealed observations and reproduce the signed statistics."""
    groups = counts(rows)
    digest = analysis_input(plan, rows)
    try:
        result = two_proportion(
            groups['A'][plan['primary_metric']], groups['A']['eligible'],
            groups['B'][plan['primary_metric']], groups['B']['eligible'],
        )
    except ValueError as exc:
        return groups, digest, None, f'封存观测无法重新计算检验：{exc}'
    return groups, digest, result, None


def _file_problem(payload, plan, groups, digest, result):
    if not isinstance(payload, dict):
        return '结果快照文件无法解析，可能混入了同名错件'
    if payload.get('code') != plan['code']:
        return '结果快照的实验编号与档案不符'
    if payload.get('primary_metric') != plan['primary_metric']:
        return '结果快照的主指标与方案不符'
    if payload.get('input_digest') != digest:
        return '结果快照的原输入摘要与签字记录不符'
    if not _tallies_match(payload.get('groups'), groups):
        return '结果快照的各组人数与封存观测不符'
    if not _stats_match(payload.get('statistics'), result):
        return '结果快照的检验值与签字记录不符'
    return None


def _signature_problem(review, computed_digest, replay_result, replay_problem):
    if review['input_digest'] != computed_digest:
        return '封存观测复验与原输入摘要不符'
    if replay_problem:
        return replay_problem
    if not _stats_match(review['result'], replay_result):
        return '封存观测重算的检验值与原签字记录不符'
    return None


def _payload(plan, review, groups, digest, result):
    return {'code': plan['code'], 'primary_metric': plan['primary_metric'], 'groups': groups,
            'statistics': result, 'input_digest': digest}


def inspect(conn, plan, review=None):
    """Blend the signed conclusion, the sealed observations and the on-disk archive."""
    review = _review(conn, plan) if review is None else review
    groups, computed_digest, replay_result, replay_problem = replay(plan, assignments(conn, plan))
    supplements = _supplements(conn, plan)
    report = {'code': plan['code'], 'primary_metric': plan['primary_metric'], 'groups': groups,
              'statistics': review['result'] if review else None, 'digest': review['input_digest'] if review else None,
              'computed_digest': computed_digest, 'supplements': supplements, 'state': None, 'reason': None,
              'replay_result': replay_result}
    pending = next((row for row in supplements if row['status'] == 'pending'), None)
    if review is None or review['status'] != 'approved':
        state, reason = 'not_ready', '复核通过后才能导出实验快照'
    else:
        problem = _signature_problem(review, computed_digest, replay_result, replay_problem)
        if problem:
            state, reason = 'manual', f'{problem}，已转人工查档'
        elif pending:
            state, reason = 'pending', '补档单已写好但尚未登记生效，恢复后接着办，补档记录生效才开放下载'
        else:
            path = snapshot_path(review['input_digest'])
            if not path.is_file():
                state, reason = 'missing', '结果快照缺失，请督导凭补档单恢复快照'
            else:
                file_problem = _file_problem(_read(path), plan, groups, review['input_digest'], replay_result)
                state, reason = ('mismatch', f'{file_problem}，请督导凭补档单恢复快照') if file_problem else ('verified', None)
    report['state'], report['reason'] = state, reason
    return report


def status(code):
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        return inspect(conn, load_plan(conn, code))


def verified_payload(code):
    """Return the exact validated snapshot content for the approved experiment."""
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        plan = load_plan(conn, code)
        report = inspect(conn, plan)
        state = report['state']
        if state == 'not_ready':
            raise HTTPException(409, '复核通过后才能导出实验快照')
        if state == 'pending':
            raise HTTPException(409, '补档单已写好但尚未登记生效，暂不开放下载')
        if state == 'manual':
            raise HTTPException(409, report['reason'] or f'{SIGNATURE_MISMATCH}，已转人工查档，暂不开放下载')
        if state == 'missing':
            raise HTTPException(503, '结果快照缺失，请督导凭补档单恢复后再下载')
        if state == 'mismatch':
            raise HTTPException(409, f'{report["reason"]}，已阻止下载')
        # Re-read and revalidate this exact file so a swap between inspect and serve is caught.
        payload = _read(snapshot_path(report['digest']))
        if payload is None:
            raise HTTPException(503, '结果快照在下载前被移走或损坏，请督导凭补档单恢复')
        problem = _file_problem(payload, plan, report['groups'], report['digest'], report['replay_result'])
        if problem:
            raise HTTPException(409, f'{problem}，已阻止下载')
    return payload


def _register(conn, plan, review, item, actor):
    """Step one: register the slip as pending so an interrupted restore is resumable."""
    existing = conn.execute('SELECT * FROM snapshot_supplement WHERE plan_id = %s AND source_ref = %s',
                            (plan['id'], item.source_ref)).fetchone()
    if existing:
        return existing
    pending = conn.execute(
        "SELECT source_ref FROM snapshot_supplement WHERE plan_id = %s AND status = 'pending' LIMIT 1",
        (plan['id'],),
    ).fetchone()
    if pending:
        raise HTTPException(409, f'补档单 {pending["source_ref"]} 尚未登记生效，请沿用它恢复后接着办')
    inserted = conn.execute(
        '''INSERT INTO snapshot_supplement (plan_id, source_ref, input_digest, note, requested_by)
           VALUES (%s,%s,%s,%s,%s) ON CONFLICT (plan_id, source_ref) DO NOTHING''',
        (plan['id'], item.source_ref, review['input_digest'], item.note, actor),
    ).rowcount
    if inserted:
        audit(conn, plan['id'], actor, 'supplement_requested', f'{item.source_ref} · {item.note}')
    return conn.execute('SELECT * FROM snapshot_supplement WHERE plan_id = %s AND source_ref = %s',
                        (plan['id'], item.source_ref)).fetchone()


def _apply(conn, plan, review, record, item, actor):
    """Step two: verify against the sealed observations, then write and register the effect."""
    if record['status'] == 'manual':
        return
    groups, computed_digest, replay_result, replay_problem = replay(plan, assignments(conn, plan))
    problem = _signature_problem(review, computed_digest, replay_result, replay_problem)
    if problem:
        conn.execute('UPDATE snapshot_supplement SET status = %s, mismatch_reason = %s, applied_at = NULL WHERE id = %s',
                     ('manual', problem, record['id']))
        audit(conn, plan['id'], actor, 'supplement_manual', f'{item.source_ref} · {problem}')
        return
    # Rewriting is idempotent: a retry of a restored slip re-heals a lost file without re-accounting.
    _write(snapshot_path(computed_digest), _payload(plan, review, groups, computed_digest, replay_result))
    if record['status'] != 'restored':
        conn.execute('UPDATE snapshot_supplement SET status = %s, mismatch_reason = NULL, applied_at = now() WHERE id = %s',
                     ('restored', record['id']))
        audit(conn, plan['id'], actor, 'supplement_restored', f'{item.source_ref} · 沿用原签字 · {computed_digest[:12]}')


def submit(code, item, actor):
    with connect() as conn:
        plan = load_plan(conn, code, lock=True)
        review = _review(conn, plan)
        if plan['state'] != Phase.APPROVED or review is None or review['status'] != 'approved':
            raise HTTPException(409, '复核通过的实验才可以补档，原始签字保持不变')
        _register(conn, plan, review, item, actor)
    # The pending slip is committed before the archive is touched; a crash here leaves it resumable.
    with connect() as conn:
        plan = load_plan(conn, code, lock=True)
        review = _review(conn, plan)
        record = conn.execute(
            'SELECT * FROM snapshot_supplement WHERE plan_id = %s AND source_ref = %s FOR UPDATE',
            (plan['id'], item.source_ref),
        ).fetchone()
        if not record:
            raise HTTPException(409, '补档单状态已变化，请刷新后重试')
        _apply(conn, plan, review, record, item, actor)
        return inspect(conn, plan, review)
