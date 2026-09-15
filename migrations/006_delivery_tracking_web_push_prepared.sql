-- PREPARED ONLY. Apply manually after review; never run by app startup.
BEGIN;
CREATE TABLE IF NOT EXISTS order_delivery_locations (
    order_id INTEGER PRIMARY KEY REFERENCES orders(id),
    driver_id INTEGER NOT NULL REFERENCES users(id),
    latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    accuracy DOUBLE PRECISION NOT NULL CHECK (accuracy BETWEEN 0 AND 100000),
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS web_push_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint_hash VARCHAR(64) NOT NULL UNIQUE,
    endpoint VARCHAR(2048) NOT NULL,
    p256dh VARCHAR(128) NOT NULL,
    auth VARCHAR(32) NOT NULL,
    visible_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_web_push_subscriptions_user_id ON web_push_subscriptions(user_id);
COMMIT;
