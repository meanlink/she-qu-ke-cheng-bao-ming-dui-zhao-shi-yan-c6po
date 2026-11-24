import json
import logging
import time
from pathlib import Path

from redis.exceptions import RedisError

from .contracts import Phase
from .db import QUEUE, audit, connect, redis_client
from .statistics import two_proportion
from .workflow import analysis_input, assignments, balanced, counts, freeze, set_phase

HEARTBEAT = Path('/tmp/worker-heartbeat')


def step():
    with connect() as conn:
        plan = conn.execute(
            '''SELECT p.* FROM experiment_plan p JOIN result_review r ON p.id = r.plan_id
               WHERE p.state = 'queued' AND r.status = 'queued'
               ORDER BY r.requested_at, p.id LIMIT 1 FOR UPDATE OF p SKIP LOCKED''',
        ).fetchone()
        if not plan:
            return False
        rows = assignments(conn, plan)
        groups = counts(rows)
        try:
            if not balanced(plan, groups) or any(row['reported_arm'] for row in rows):
                raise ValueError('计算前校验发现有效样本失衡或中途改组')
            if any(row['recorded'] != row['eligible'] for row in groups.values()):
                raise ValueError('计算前校验发现有效样本有缺失观测')
            a, b = groups['A'], groups['B']
            metric = plan['primary_metric']
            result = two_proportion(a[metric], a['eligible'], b[metric], b['eligible'])
        except ValueError as exc:
            freeze(conn, plan, 'worker', str(exc))
            return True
        digest = analysis_input(plan, rows)
        report = dict(code=plan['code'], primary_metric=metric, groups=groups, statistics=result, input_digest=digest)
        target = Path('/analysis') / f'{digest}.json'
        pending = target.with_suffix('.tmp')
        pending.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        pending.replace(target)
        conn.execute("UPDATE result_review SET status = 'ready', result = %s::jsonb, input_digest = %s WHERE plan_id = %s",
                     (json.dumps(result), digest, plan['id']))
        set_phase(conn, plan, Phase.REVIEW)
        audit(conn, plan['id'], 'worker', 'computed', f'两比例检验完成 · {digest[:12]}')
        logging.info('Computed %s', plan['code'])
        return True


def run():
    logging.basicConfig(level=logging.INFO)
    redis = redis_client()
    while True:
        try:
            worked = step()
            HEARTBEAT.touch()
            if not worked:
                try:
                    redis.blpop(QUEUE, timeout=2)
                except RedisError:
                    time.sleep(2)
        except Exception:
            logging.exception('持久任务保留，下次轮询重试')
            time.sleep(2)


if __name__ == '__main__':
    run()
