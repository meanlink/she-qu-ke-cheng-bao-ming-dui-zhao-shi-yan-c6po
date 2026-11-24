ALTER TABLE participant_assignment DROP CONSTRAINT IF EXISTS participant_assignment_outcome_check;
ALTER TABLE participant_assignment ADD CONSTRAINT participant_assignment_outcome_check
    CHECK (outcome IN ('no_signup', 'absent', 'attended', 'waitlisted', 'withdrawn'));

CREATE TABLE IF NOT EXISTS attendance_roll (
    plan_id bigint PRIMARY KEY REFERENCES course_session(plan_id),
    source_ref text NOT NULL,
    submitted_by text NOT NULL REFERENCES staff(email),
    submitted_at timestamptz NOT NULL DEFAULT now(),
    reconciled_by text REFERENCES staff(email) CHECK (reconciled_by <> submitted_by),
    reconciled_at timestamptz,
    reconcile_ref text,
    CHECK ((reconciled_by IS NULL) = (reconciled_at IS NULL)
       AND (reconciled_by IS NULL) = (reconcile_ref IS NULL))
);

CREATE TABLE IF NOT EXISTS attendance_mark (
    plan_id bigint NOT NULL REFERENCES attendance_roll(plan_id),
    participant_code text NOT NULL,
    status text NOT NULL CHECK (status IN ('attended', 'absent')),
    PRIMARY KEY (plan_id, participant_code),
    FOREIGN KEY (plan_id, participant_code) REFERENCES seat_request(plan_id, participant_code)
);
