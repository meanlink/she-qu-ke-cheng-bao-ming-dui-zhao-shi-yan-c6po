CREATE TABLE IF NOT EXISTS snapshot_supplement (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id bigint NOT NULL REFERENCES experiment_plan(id),
    source_ref text NOT NULL,
    input_digest text NOT NULL,
    note text NOT NULL DEFAULT '',
    mismatch_reason text,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'restored', 'manual')),
    requested_by text NOT NULL REFERENCES staff(email),
    requested_at timestamptz NOT NULL DEFAULT now(),
    applied_at timestamptz,
    UNIQUE (plan_id, source_ref),
    CHECK ((status = 'manual') = (mismatch_reason IS NOT NULL)),
    CHECK ((status = 'restored') = (applied_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS snapshot_supplement_plan ON snapshot_supplement (plan_id, id DESC);
