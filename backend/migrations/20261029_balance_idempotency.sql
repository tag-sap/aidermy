-- Idempotent balance operations for compatibility-set charging and retries.
-- Additive only: existing balance rows are preserved.

ALTER TABLE public.balance_transactions
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_balance_tx_idempotency
    ON public.balance_transactions (idempotency_key)
    WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';
