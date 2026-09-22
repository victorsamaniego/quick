-- PREPARED ONLY. Review and back up before applying manually. Never run on import.
BEGIN;
ALTER TABLE businesses
    ADD COLUMN approval_status VARCHAR(20) NOT NULL DEFAULT 'approved',
    ADD COLUMN approved_at TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN approved_by_user_id INTEGER REFERENCES users(id),
    ADD COLUMN rejected_at TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN rejected_by_user_id INTEGER REFERENCES users(id),
    ADD COLUMN rejection_reason VARCHAR(300),
    ADD CONSTRAINT ck_business_approval_status CHECK (approval_status IN ('pending', 'approved', 'rejected'));
-- All legacy businesses (including inactive ones) retain is_active, subscriptions,
-- QuickGold and coverage. Audit fields remain NULL: no fabricated historical approval.
CREATE INDEX ix_businesses_approval_status ON businesses (approval_status);
ALTER TABLE users
    ADD COLUMN legal_accepted_at TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN legal_version VARCHAR(20);
-- NULL for legacy users: do not fabricate prior consent.
COMMIT;
