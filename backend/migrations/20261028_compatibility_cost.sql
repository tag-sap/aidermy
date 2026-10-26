-- Fixed compatibility-set price, stored with the durable task and set.
-- Additive only: existing rows keep their data and default to zero until the
-- next check is created.

ALTER TABLE public.compatibility_sets
    ADD COLUMN IF NOT EXISTS cost INTEGER NOT NULL DEFAULT 0;

ALTER TABLE public.compatibility_tasks
    ADD COLUMN IF NOT EXISTS cost INTEGER NOT NULL DEFAULT 0;
