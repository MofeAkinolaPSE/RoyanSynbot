-- Migration 151: Create the missing fin_budget_targets table
--
-- backend/src/routers/finance.py's budget-vs-actual variance feature
-- (GET/POST /finance/budget/targets, DELETE /finance/budget/targets/{id},
-- GET /finance/budget/variance) has referenced this table since it was
-- written, but no migration ever created it — every list/upsert/delete has
-- been failing with a caught exception, returning a 500 to the finance UI.

ROLLBACK;
BEGIN;

CREATE TABLE IF NOT EXISTS public.fin_budget_targets (
    id               bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    department       text        NOT NULL,
    category         text        NOT NULL DEFAULT 'general',
    period           text        NOT NULL CHECK (period ~ '^\d{4}-\d{2}$'),
    budgeted_amount  numeric(14,2) NOT NULL CHECK (budgeted_amount >= 0),
    note             text,
    created_by       text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (department, category, period)
);

COMMIT;
