from datetime import date

from src.auth import password_hash
from src.contracts import PlanCreate
from src.workflow import allocate, insert_plan, load_plan, mark_checked

INSTRUCTORS = (
    ('chen@community.demo', '陈珂', 10),
    ('tang@community.demo', '唐雯', 16),
)
COURSE_CODE = 'CC-1122'


def prepare_course_session(conn, password, organizer, reviewer):
    for email, name, teaching_limit in INSTRUCTORS:
        conn.execute("INSERT INTO staff VALUES (%s,%s,%s,'instructor') ON CONFLICT (email) DO NOTHING",
                     (email, name, password_hash(password)))
        conn.execute('INSERT INTO instructor_capacity VALUES (%s,%s) ON CONFLICT (email) DO NOTHING',
                     (email, teaching_limit))
    if conn.execute('SELECT 1 FROM experiment_plan WHERE code = %s', (COURSE_CODE,)).fetchone():
        return
    plan = PlanCreate(code=COURSE_CODE, title='冬日阳台育苗课', site='祥和里花圃教室',
                      question='邀请附上两种育苗方式，能否提高居民实际到课率？', control_invite='常规开课短信',
                      variant_invite='短信附水培与土培示例', window_start=date(2026, 11, 14),
                      window_end=date(2026, 11, 20), min_per_arm=12, primary_metric='attendance')
    saved = insert_plan(conn, plan, organizer)
    mark_checked(conn, saved, reviewer)
    allocate(conn, load_plan(conn, COURSE_CODE), [f'YM-{index:03d}' for index in range(1, 33)], organizer,
             'cbb76be9baad4cb48240f990019b1043')
