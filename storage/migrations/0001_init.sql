-- Initial schema: immutable event ledger + materialized projections.
-- Projections (tasks, approvals, memory_candidates) are derived state:
-- they can always be dropped and rebuilt from `events` alone
-- (see storage/projections.py:rebuild_projections). Never write to them
-- directly outside of projection folding.

CREATE TABLE IF NOT EXISTS events (
    rowid_order INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    schema_version INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    type TEXT NOT NULL,
    source TEXT NOT NULL,
    parent_id TEXT,
    correlation_id TEXT,
    payload TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    created_from_event TEXT NOT NULL,
    updated_from_event TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    level TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_from_event TEXT NOT NULL,
    decided_from_event TEXT
);

CREATE TABLE IF NOT EXISTS memory_candidates (
    id TEXT PRIMARY KEY,
    statement TEXT NOT NULL,
    confidence REAL NOT NULL,
    source_event_ids TEXT NOT NULL,
    status TEXT NOT NULL,
    reviewed_at TEXT,
    retention_policy TEXT NOT NULL DEFAULT 'default'
);
