-- PREPARADA, NO EJECUTADA. No cambia solicitudes ni asignaciones existentes.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
CREATE TABLE IF NOT EXISTS delivery_request_candidates (
    id BIGSERIAL PRIMARY KEY,
    delivery_request_id INTEGER NOT NULL REFERENCES delivery_requests(id),
    driver_id INTEGER NOT NULL REFERENCES users(id),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'rejected', 'expired', 'cancelled')),
    notified_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMPTZ,
    approximate_distance_km INTEGER NOT NULL CHECK (approximate_distance_km >= 0),
    UNIQUE (delivery_request_id, driver_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_candidate_one_winner
    ON delivery_request_candidates(delivery_request_id) WHERE status = 'accepted';
COMMIT;
-- No backfill por vecinos actuales: no equivalen a destinatarios históricos notificados.
-- Rollback conservador: desactivar nuevo despacho; conservar filas para auditoría.
