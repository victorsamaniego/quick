-- PREPARED ONLY. Apply manually after review; NEVER run by app startup or automatic deploy.
-- Migration 008: Business Cash Register (Gestión de Caja Opcional por Negocio)
-- Target Database: PostgreSQL (QuickGo Production / Staging)
-- Safe, transactional, and idempotent.

BEGIN;

-- 1. Agregar columna cash_register_enabled en businesses (desactivada por defecto)
ALTER TABLE businesses 
ADD COLUMN IF NOT EXISTS cash_register_enabled BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. Crear tabla cash_sessions (sesiones de apertura y cierre de caja)
CREATE TABLE IF NOT EXISTS cash_sessions (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    opened_by_user_id INTEGER NOT NULL REFERENCES users(id),
    opened_at TIMESTAMPTZ NOT NULL,
    opening_amount NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    closed_by_user_id INTEGER REFERENCES users(id),
    closed_at TIMESTAMPTZ,
    declared_cash NUMERIC(15, 2),
    expected_cash_at_close NUMERIC(15, 2),
    difference_at_close NUMERIC(15, 2),
    cash_sales_total NUMERIC(15, 2) DEFAULT 0.00,
    qr_sales_total NUMERIC(15, 2) DEFAULT 0.00,
    transfer_sales_total NUMERIC(15, 2) DEFAULT 0.00,
    card_sales_total NUMERIC(15, 2) DEFAULT 0.00,
    other_sales_total NUMERIC(15, 2) DEFAULT 0.00,
    manual_income_total NUMERIC(15, 2) DEFAULT 0.00,
    expense_total NUMERIC(15, 2) DEFAULT 0.00,
    withdrawal_total NUMERIC(15, 2) DEFAULT 0.00,
    total_sales NUMERIC(15, 2) DEFAULT 0.00
);

-- Índices de consulta para cash_sessions
CREATE INDEX IF NOT EXISTS ix_cash_sessions_business_id ON cash_sessions(business_id);
CREATE INDEX IF NOT EXISTS ix_cash_sessions_opened_at ON cash_sessions(opened_at);
CREATE INDEX IF NOT EXISTS ix_cash_sessions_closed_at ON cash_sessions(closed_at);

-- Restricción estricta de unicidad: Una única sesión abierta (closed_at IS NULL) por negocio
CREATE UNIQUE INDEX IF NOT EXISTS uq_open_cash_session_per_business 
ON cash_sessions (business_id) 
WHERE closed_at IS NULL;

-- 3. Crear tabla cash_movements (movimientos manuales de efectivo: ingreso, gasto, retiro)
CREATE TABLE IF NOT EXISTS cash_movements (
    id SERIAL PRIMARY KEY,
    cash_session_id INTEGER NOT NULL REFERENCES cash_sessions(id),
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    created_by_user_id INTEGER NOT NULL REFERENCES users(id),
    type VARCHAR(30) NOT NULL,
    amount NUMERIC(15, 2) NOT NULL,
    description VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

-- Índices para cash_movements
CREATE INDEX IF NOT EXISTS ix_cash_movements_cash_session_id ON cash_movements(cash_session_id);
CREATE INDEX IF NOT EXISTS ix_cash_movements_business_id ON cash_movements(business_id);
CREATE INDEX IF NOT EXISTS ix_cash_movements_created_at ON cash_movements(created_at);

-- 4. Metodo de pago de pedidos
-- orders.payment_method ya existe en QuickGo y se conserva sin cambios.
-- La migracion 008 no modifica ni completa metodos de pago historicos.


COMMIT;


