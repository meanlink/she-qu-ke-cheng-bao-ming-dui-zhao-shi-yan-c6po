import json
from datetime import date

from scripts.seed_course_session import prepare_course_session
from src.auth import password_hash
from src.control_contracts import ClearanceSubmission
from src.control_records import add_clearance
from src.contracts import PlanCreate
from src.db import audit, connect
from src.workflow import allocate, insert_plan, load_plan, mark_checked

ORGANIZER = 'lin@community.demo'
OBSERVER = 'zhou@community.demo'
REVIEWER = 'lu@community.demo'
PASSWORD = 'ClassDemo26!'

EXPERIMENTS = [
    ('CC-1119', '居民香草栽培课', '祥和里花圃教室', '附香草习性卡的邀请，能否提高居民报名率？', '常规活动短信', '短信附香草习性卡', 'signup'),
    ('CC-1121', '周末植物拓印', '祥和里社区活动室', '邀请中附加材料清单，能否提高居民报名率？', '常规课程短信', '短信附三项材料清单', 'signup'),
    ('CC-1120', '手机摄影散步', '梧桐公园南门', '邀请注明集合点后，能否提高居民到课率？', '常规地点提示', '地址和集合点地图', 'attendance'),
    ('CC-1118', '便民缝补入门', '向阳里共享教室', '加入工具借用说明，能否提高居民报名率？', '简版课程通知', '附工具借用说明', 'signup'),
]


def seed():
    staff = [(ORGANIZER, '林嘉', 'organizer'), (OBSERVER, '周葵', 'observer'), (REVIEWER, '陆宁', 'reviewer')]
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(10430)')
        for email, name, role in staff:
            conn.execute('INSERT INTO staff VALUES (%s,%s,%s,%s) ON CONFLICT (email) DO NOTHING',
                         (email, name, password_hash(PASSWORD), role))
        for code, title, site, question, control, variant, metric in EXPERIMENTS:
            exists = conn.execute('SELECT 1 FROM experiment_plan WHERE code = %s', (code,)).fetchone()
            if exists:
                continue
            plan = PlanCreate(code=code, title=title, site=site, question=question, control_invite=control,
                              variant_invite=variant, window_start=date(2026, 11, 14), window_end=date(2026, 11, 20),
                              min_per_arm=12, primary_metric=metric)
            saved = insert_plan(conn, plan, ORGANIZER)
            if code == 'CC-1118':
                continue
            mark_checked(conn, saved, REVIEWER)
            if code == 'CC-1119':
                item = ClearanceSubmission(codes=[f'YC-{number:03d}' for number in range(1, 25)],
                                           source_ref='花圃课资格核对_1114.csv')
                add_clearance(conn, saved, item, 1, ORGANIZER)
                continue
            if code == 'CC-1120':
                continue
            roster = [f'ZH-{number:03d}' for number in range(1, 49)]
            allocate(conn, load_plan(conn, code), roster, ORGANIZER, 'd19e3df65ea81296a6244a82ef4d1043')
            for arm, attended, absent, no_signup in [('A', 5, 3, 8), ('B', 9, 5, 2)]:
                rows = conn.execute('SELECT participant_code FROM participant_assignment WHERE plan_id = %s AND arm = %s ORDER BY participant_code',
                                    (saved['id'], arm)).fetchall()
                outcomes = ['attended'] * attended + ['absent'] * absent + ['no_signup'] * no_signup
                with conn.cursor() as cur:
                    cur.executemany('''UPDATE participant_assignment SET outcome = %s, source_ref = %s,
                                       observed_on = %s, observed_by = %s WHERE plan_id = %s AND participant_code = %s''',
                                    [(outcome, '拓印课签到簿_1120.csv', plan.window_end, OBSERVER, saved['id'], row['participant_code'])
                                     for outcome, row in zip(outcomes, rows)])
            audit(conn, saved['id'], OBSERVER, 'observed', '32 人 · 2026-11-20 · 拓印课签到簿_1120.csv')
        prepare_course_session(conn, PASSWORD, ORGANIZER, REVIEWER)
        tables = ('staff', 'experiment_plan', 'participant_assignment', 'result_review', 'audit_event',
                  'roster_clearance', 'invitation_attempt', 'observation_correction', 'instructor_capacity',
                  'course_session', 'seat_request', 'attendance_roll', 'attendance_mark')
        return {table: conn.execute(f'SELECT count(*) AS total FROM {table}').fetchone()['total'] for table in tables}


if __name__ == '__main__':
    print(json.dumps(seed(), sort_keys=True))
