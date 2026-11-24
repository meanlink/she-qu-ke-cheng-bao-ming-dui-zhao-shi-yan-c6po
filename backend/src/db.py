import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from redis import Redis

QUEUE = 'course-analysis-wakeup'


def connect():
    return psycopg.connect('', connect_timeout=5, row_factory=dict_row)


def redis_client():
    return Redis.from_url(os.environ['REDIS_URL'], socket_connect_timeout=2, socket_timeout=4)


def migrate():
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(1043)')
        for path in sorted(Path('migrations').glob('*.sql')):
            conn.execute(path.read_text())


def audit(conn, plan_id, actor, event, detail):
    conn.execute(
        'INSERT INTO audit_event (plan_id, actor, event, detail) VALUES (%s,%s,%s,%s)',
        (plan_id, actor, event, detail),
    )
