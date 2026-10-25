# Compatibility checks and shelf sets

This feature reuses the existing `AnalysisService`, Evaluation V2 snapshots and
the deterministic `compute_shelf_compatibility` engine. It does not introduce a
second Score Engine or regenerate reports when a saved result is opened.

## Persistence

Apply `migrations/20261027_compatibility_sets.sql` to PostgreSQL/Supabase. It
creates:

* `public.compatibility_sets` — automatically saved shelf sets;
* `public.compatibility_tasks` — durable individual/compatibility jobs;
* `public.user_notifications` — persistent in-app notifications;
* `public.shelf_products.shelf_status` — `using` / `want`.

SQLite creates the same compatibility tables lazily via
`app.compat_store.ensure_schema()`.

## Background worker

The application starts one durable worker per process on FastAPI startup. It
claims queued database rows atomically, so multiple gunicorn processes do not
process the same task. Set `AIDERMY_COMPAT_WORKER=0` to disable it in a
specialised deployment; otherwise leave the default enabled.

The worker:

1. reuses an actual current saved report when one exists;
2. runs the existing product analysis for stale/missing reports;
3. waits for all individual results before building the compatibility report;
4. records a safe error and notifies the user when an individual stage fails;
5. ignores a set that was deleted while its task was running.

## API

* `POST /api/v1/compatibility/tasks/individual`
* `GET /api/v1/compatibility/tasks/individual/{product_id}`
* `POST /api/v1/compatibility/tasks/compatibility`
* `GET /api/v1/compatibility/tasks/{task_id}`
* `GET /api/v1/compatibility/sets`
* `GET /api/v1/compatibility/sets/{set_id}`
* `DELETE /api/v1/compatibility/sets/{set_id}`
* `POST /api/v1/compatibility/sets/{set_id}/retry`
* `GET /api/v1/notifications`
* `POST /api/v1/notifications/{id}/read`
* `POST /api/v1/notifications/read-all`

All endpoints derive the owner from the authenticated session. The frontend
polls notifications and set statuses with visibility-aware intervals and stops
the timers on unmount.
