CREATE TABLE IF NOT EXISTS staff (
    email text PRIMARY KEY,
    display_name text NOT NULL,
    password_hash text NOT NULL,
    role text NOT NULL CHECK (role IN ('organizer', 'observer', 'reviewer'))
);

CREATE TABLE IF NOT EXISTS experiment_plan (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE,
    title text NOT NULL,
    question text NOT NULL,
    site text NOT NULL,
    control_invite text NOT NULL,
    variant_invite text NOT NULL CHECK (variant_invite <> control_invite),
    window_start date NOT NULL,
    window_end date NOT NULL CHECK (window_end >= window_start),
    primary_metric text NOT NULL CHECK (primary_metric IN ('signup', 'attendance')),
    min_per_arm integer NOT NULL CHECK (min_per_arm BETWEEN 12 AND 500),
    state text NOT NULL DEFAULT 'draft' CHECK (state IN ('draft', 'checked', 'observing', 'queued', 'review', 'frozen', 'approved', 'rejected')),
    author text NOT NULL REFERENCES staff(email),
    checked_by text REFERENCES staff(email) CHECK (checked_by <> author),
    checked_at timestamptz,
    allocation_seed text,
    roster_digest text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((checked_by IS NULL) = (checked_at IS NULL)),
    CHECK ((allocation_seed IS NULL) = (roster_digest IS NULL))
);

CREATE TABLE IF NOT EXISTS participant_assignment (
    plan_id bigint NOT NULL REFERENCES experiment_plan(id),
    participant_code text NOT NULL,
    arm text NOT NULL CHECK (arm IN ('A', 'B')),
    outcome text CHECK (outcome IN ('no_signup', 'absent', 'attended')),
    source_ref text,
    observed_on date,
    observed_by text REFERENCES staff(email),
    exclusion_reason text CHECK (exclusion_reason IN ('duplicate', 'ineligible')),
    exclusion_ref text,
    reported_arm text CHECK (reported_arm IN ('A', 'B') AND reported_arm <> arm),
    deviation_ref text,
    PRIMARY KEY (plan_id, participant_code),
    CHECK ((outcome IS NULL) = (source_ref IS NULL) AND (outcome IS NULL) = (observed_on IS NULL) AND (outcome IS NULL) = (observed_by IS NULL)),
    CHECK ((exclusion_reason IS NULL) = (exclusion_ref IS NULL)),
    CHECK (exclusion_reason IS NULL OR outcome IS NULL),
    CHECK ((reported_arm IS NULL) = (deviation_ref IS NULL))
);

CREATE TABLE IF NOT EXISTS result_review (
    plan_id bigint PRIMARY KEY REFERENCES experiment_plan(id),
    status text NOT NULL CHECK (status IN ('queued', 'ready', 'frozen', 'approved', 'rejected')),
    requested_by text NOT NULL REFERENCES staff(email),
    requested_at timestamptz NOT NULL DEFAULT now(),
    input_digest text,
    result jsonb,
    freeze_reason text,
    decision_note text,
    decided_by text REFERENCES staff(email),
    decided_at timestamptz,
    CHECK (status NOT IN ('ready', 'approved') OR (input_digest IS NOT NULL AND result IS NOT NULL)),
    CHECK (status <> 'frozen' OR (freeze_reason IS NOT NULL AND result IS NULL)),
    CHECK (status NOT IN ('approved', 'rejected') OR (decided_by IS NOT NULL AND decision_note IS NOT NULL AND decided_at IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS audit_event (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id bigint NOT NULL REFERENCES experiment_plan(id),
    actor text NOT NULL,
    event text NOT NULL,
    detail text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now()
);
