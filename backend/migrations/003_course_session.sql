ALTER TABLE staff DROP CONSTRAINT IF EXISTS staff_role_check;
ALTER TABLE staff ADD CONSTRAINT staff_role_check CHECK (role IN ('organizer', 'observer', 'reviewer', 'instructor'));

CREATE TABLE IF NOT EXISTS instructor_capacity (
    email text PRIMARY KEY REFERENCES staff(email),
    teaching_limit integer NOT NULL CHECK (teaching_limit BETWEEN 1 AND 500)
);

CREATE TABLE IF NOT EXISTS course_session (
    plan_id bigint PRIMARY KEY REFERENCES experiment_plan(id),
    instructor_email text NOT NULL REFERENCES instructor_capacity(email),
    starts_at timestamp NOT NULL,
    ends_at timestamp NOT NULL CHECK (ends_at > starts_at AND ends_at::date = starts_at::date),
    room_limit integer NOT NULL CHECK (room_limit BETWEEN 1 AND 500),
    seat_limit integer NOT NULL CHECK (seat_limit BETWEEN 1 AND room_limit),
    schedule_ref text NOT NULL,
    booked_by text NOT NULL REFERENCES staff(email),
    booked_at timestamptz NOT NULL DEFAULT now(),
    locked_at timestamptz
);

CREATE INDEX IF NOT EXISTS course_session_instructor_time ON course_session (instructor_email, starts_at, ends_at);
