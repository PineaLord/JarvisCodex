-- Faza C: intent -> signal -> candidate initiative -> goal.
-- Like tasks/approvals/memory_candidates, these are projections derived
-- from events -- always reproducible from the event log alone.

CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    description TEXT NOT NULL,
    detected_from_event TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS initiatives (
    id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL,
    level TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    proposed_from_event TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    initiative_id TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_from_event TEXT NOT NULL
);
