-- PostgreSQL / Railway. Apply explicitly before deploying the updated model.
-- No application import, automatic connection, or embedded connection details.
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE businesses
    ADD COLUMN IF NOT EXISTS is_quickgold BOOLEAN NOT NULL DEFAULT FALSE;
COMMIT;
-- Existing businesses remain NORMAL. Re-running does not reset assigned types.
-- To disable the feature, retire QuickGold through Super Admin; do not drop
-- this column while an application version referencing it is running.
