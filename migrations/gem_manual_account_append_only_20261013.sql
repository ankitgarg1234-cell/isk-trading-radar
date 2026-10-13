-- Additive only. Isolated Neon GEM project; never touch DM tables.
-- Manual user-entered events are not broker execution confirmations.
-- Apply with an authorized GEM database migration identity.
CREATE TABLE IF NOT EXISTS gem_manual_entry (
    entry_id text PRIMARY KEY,
    experiment_id text NOT NULL REFERENCES gem_experiment(experiment_id)
        CHECK (experiment_id = 'gem-v1-forward-2026-10'),
    event_kind text NOT NULL CHECK (event_kind IN (
        'FILL', 'DIVIDEND', 'CASH_DEPOSIT', 'CASH_WITHDRAWAL',
        'SPLIT', 'SPINOFF', 'MERGER_CASH'
    )),
    trade_date date NOT NULL,
    payload_sha256 char(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    prior_sha256 char(64) NOT NULL CHECK (prior_sha256 ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (payload->>'source' IS DISTINCT FROM 'BROKER_API')
);
CREATE INDEX IF NOT EXISTS gem_manual_entry_experiment_order_idx
    ON gem_manual_entry (experiment_id, trade_date, created_at, entry_id);
-- Separately append human-imported statements; equality is not proof of
-- independent statement authenticity, only recorded reconciliation evidence.
CREATE TABLE IF NOT EXISTS gem_manual_statement (
    statement_id text PRIMARY KEY,
    experiment_id text NOT NULL REFERENCES gem_experiment(experiment_id)
        CHECK (experiment_id = 'gem-v1-forward-2026-10'),
    statement_as_of date NOT NULL,
    source_sha256 char(64) NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    ledger_head_sha256 char(64) NOT NULL CHECK (ledger_head_sha256 ~ '^[0-9a-f]{64}$'),
    statement_payload jsonb NOT NULL,
    reconciliation text NOT NULL CHECK (reconciliation IN (
        'USER_STATEMENT_RECONCILED', 'STATEMENT_MISMATCH_HOLD'
    )),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS gem_manual_statement_experiment_idx
    ON gem_manual_statement (experiment_id, statement_as_of DESC, created_at DESC);
-- Intentionally do not GRANT access to any Render service writer here.
-- Future manual-only app credentials may receive SELECT, INSERT solely on
-- these tables. The existing GEM/DM write permissions are unchanged.
