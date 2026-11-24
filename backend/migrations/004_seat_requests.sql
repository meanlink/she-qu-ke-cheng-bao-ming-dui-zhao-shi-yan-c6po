CREATE TABLE IF NOT EXISTS seat_request (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id bigint NOT NULL REFERENCES course_session(plan_id),
    participant_code text NOT NULL,
    requested_on date NOT NULL,
    request_ref text NOT NULL,
    recorded_by text NOT NULL REFERENCES staff(email),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    confirmed_at timestamptz,
    withdrawn_on date CHECK (withdrawn_on >= requested_on),
    withdrawal_ref text,
    withdrawn_by text REFERENCES staff(email),
    withdrawn_at timestamptz,
    UNIQUE (plan_id, participant_code),
    FOREIGN KEY (plan_id, participant_code) REFERENCES participant_assignment(plan_id, participant_code),
    CHECK ((withdrawn_on IS NULL) = (withdrawal_ref IS NULL)
       AND (withdrawn_on IS NULL) = (withdrawn_by IS NULL)
       AND (withdrawn_on IS NULL) = (withdrawn_at IS NULL))
);

CREATE INDEX IF NOT EXISTS seat_request_waiting ON seat_request (plan_id, id)
    WHERE confirmed_at IS NULL AND withdrawn_on IS NULL;
