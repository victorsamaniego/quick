-- PREPARADA, NO EJECUTADA. No activar recovery/revocación/2FA solo por crear tablas.
-- Requiere backup restaurable y validación PostgreSQL aislada antes de aplicación manual.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
-- Tabla aparte: no añade columnas obligatorias ni reescribe usuarios existentes.
CREATE TABLE IF NOT EXISTS user_security_state (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    auth_version INTEGER NOT NULL DEFAULT 0 CHECK (auth_version >= 0),
    password_changed_at TIMESTAMPTZ,
    force_password_change BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    token_hash CHAR(64) NOT NULL UNIQUE,
    password_fingerprint VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user ON password_reset_tokens(user_id);
-- No guardar secreto TOTP plano: ciphertext AEAD, clave fuera de DB, identificador de clave.
-- No escribir un secreto de ejemplo ni generar enrolamientos en esta migración.
CREATE TABLE IF NOT EXISTS user_totp_security (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    secret_ciphertext BYTEA NOT NULL,
    key_id VARCHAR(128) NOT NULL,
    confirmed_at TIMESTAMPTZ,
    last_accepted_counter BIGINT
);
CREATE TABLE IF NOT EXISTS user_recovery_codes (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    code_hash VARCHAR(255) NOT NULL,
    used_at TIMESTAMPTZ
);
COMMIT;
-- Rollback conservador: desactivar consumidores nuevos y conservar estas tablas.
-- No DROP/TRUNCATE: se preservan tokens consumidos, revocaciones y enrolamientos.
