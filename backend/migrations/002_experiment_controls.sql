CREATE TABLE IF NOT EXISTS roster_clearance (
    plan_id bigint NOT NULL REFERENCES experiment_plan(id),
    version integer NOT NULL CHECK (version > 0),
    codes text[] NOT NULL CHECK (cardinality(codes) BETWEEN 24 AND 1000),
    source_ref text NOT NULL,
    submitted_by text NOT NULL REFERENCES staff(email),
    submitted_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'returned')),
    decision_note text,
    decided_by text REFERENCES staff(email) CHECK (decided_by <> submitted_by),
    decided_at timestamptz,
    PRIMARY KEY (plan_id, version),
    CHECK ((status = 'pending') = (decided_by IS NULL)),
    CHECK ((decided_by IS NULL) = (decided_at IS NULL) AND (decided_by IS NULL) = (decision_note IS NULL))
);

CREATE TABLE IF NOT EXISTS invitation_attempt (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id bigint NOT NULL,
    participant_code text NOT NULL,
    delivered_on date NOT NULL,
    channel text NOT NULL CHECK (channel IN ('sms', 'phone', 'desk')),
    status text NOT NULL CHECK (status IN ('delivered', 'failed')),
    source_ref text NOT NULL,
    recorded_by text NOT NULL REFERENCES staff(email),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (plan_id, participant_code) REFERENCES participant_assignment(plan_id, participant_code),
    UNIQUE (plan_id, participant_code, source_ref)
);

CREATE UNIQUE INDEX IF NOT EXISTS invitation_delivered_once
    ON invitation_attempt (plan_id, participant_code) WHERE status = 'delivered';

CREATE TABLE IF NOT EXISTS observation_correction (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id bigint NOT NULL,
    participant_code text NOT NULL,
    original_outcome text NOT NULL CHECK (original_outcome IN ('no_signup', 'absent', 'attended')),
    original_observed_on date NOT NULL,
    original_source_ref text NOT NULL,
    original_observed_by text NOT NULL REFERENCES staff(email),
    proposed_outcome text NOT NULL CHECK (proposed_outcome IN ('no_signup', 'absent', 'attended') AND proposed_outcome <> original_outcome),
    proposed_observed_on date NOT NULL,
    proposed_source_ref text NOT NULL,
    reason text NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'returned')),
    submitted_by text NOT NULL REFERENCES staff(email),
    submitted_at timestamptz NOT NULL DEFAULT now(),
    decision_note text,
    decided_by text REFERENCES staff(email) CHECK (decided_by <> submitted_by),
    decided_at timestamptz,
    FOREIGN KEY (plan_id, participant_code) REFERENCES participant_assignment(plan_id, participant_code),
    CHECK ((status = 'pending') = (decided_by IS NULL)),
    CHECK ((decided_by IS NULL) = (decided_at IS NULL) AND (decided_by IS NULL) = (decision_note IS NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS observation_correction_pending_once
    ON observation_correction (plan_id, participant_code) WHERE status = 'pending';
