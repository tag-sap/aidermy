-- Durable compatibility sets, background tasks and in-app notifications.
-- Mirrors backend/app/compat_store.py. Apply before enabling the worker in
-- production; the compatibility endpoints fail closed until this migration runs.

CREATE TABLE IF NOT EXISTS public.compatibility_sets (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT '',
    product_ids TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'queued',
    report_json TEXT,
    profile_json TEXT NOT NULL DEFAULT '{}',
    profile_updated_at TEXT NOT NULL DEFAULT '',
    context_key TEXT NOT NULL DEFAULT '',
    task_id BIGINT,
    cost INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    checked_at TIMESTAMP,
    deleted_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.compatibility_tasks (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    product_ids TEXT NOT NULL DEFAULT '[]',
    set_id BIGINT,
    profile_json TEXT NOT NULL DEFAULT '{}',
    profile_updated_at TEXT NOT NULL DEFAULT '',
    context_key TEXT NOT NULL DEFAULT '',
    active_key TEXT,
    result_snapshot_id TEXT,
    cost INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.user_notifications (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    event_key TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    target_type TEXT NOT NULL DEFAULT '',
    target_id BIGINT,
    read_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_compat_tasks_active_key
    ON public.compatibility_tasks (active_key);
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_notifications_event
    ON public.user_notifications (user_id, event_key);
CREATE INDEX IF NOT EXISTS idx_compat_tasks_status
    ON public.compatibility_tasks (status, id);
CREATE INDEX IF NOT EXISTS idx_compat_sets_user
    ON public.compatibility_sets (user_id, created_at);

-- Preserve the two shelf states across existing installations. Older rows are
-- treated as "currently using"; a scan/wishlist add may store "want".
ALTER TABLE public.shelf_products
    ADD COLUMN IF NOT EXISTS shelf_status TEXT NOT NULL DEFAULT 'using';
