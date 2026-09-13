-- PREPARED ONLY. Apply manually before deploying this branch.
-- Commercial availability is independent of platform authorization (is_active).
-- TRUE preserves the existing behavior for current businesses.
BEGIN;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS is_open BOOLEAN NOT NULL DEFAULT TRUE;
COMMIT;
