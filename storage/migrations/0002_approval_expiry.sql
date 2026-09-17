-- Approvals now carry an expiry: an L3-L5 request left undecided past
-- expires_at is treated as expired, not silently re-approvable later.
-- See docs/04-safety-model.md and policy/engine.py.

ALTER TABLE approvals ADD COLUMN expires_at TEXT;
