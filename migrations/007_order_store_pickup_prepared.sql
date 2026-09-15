-- Manual review only. Apply before deploying code that reads picked_up_at.
-- PostgreSQL; does not change existing orders or delivered_at.
BEGIN;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS picked_up_at TIMESTAMPTZ;
COMMIT;
