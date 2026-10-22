-- Evaluation v2 — schema draft (2026-10-23)
-- STATUS: DRAFT. NOT APPLIED anywhere. Requires approval + staging test.
-- Target: Supabase / PostgreSQL 17. Independent from legacy tables: this schema
-- does not read or write public.analysis / product_knowledge / kie.*.
-- Rollback: drop schema evaluation cascade; (only after a verified backup)

create schema if not exists evaluation;

-- 1. Product composition versions (append-only)
create table if not exists evaluation.product_compositions (
    id                bigserial primary key,
    product_id        bigint      not null,
    inci_raw          text        not null,
    inci_normalized   jsonb       not null default '[]'::jsonb,
    composition_hash  text        not null,
    source            text        not null default '',
    verified_at       timestamptz,
    status            text        not null default 'active'
                      check (status in ('active', 'superseded', 'unverified')),
    created_at        timestamptz not null default now(),
    unique (product_id, composition_hash)
);
create index if not exists idx_compositions_product
    on evaluation.product_compositions (product_id, created_at desc);

-- 2. Parameter registry (mirror of the code registry, versioned for audit)
create table if not exists evaluation.parameter_registry (
    parameter_id   text        not null,
    method_version text        not null,
    label          text        not null,
    definition     text        not null,
    anchors        jsonb       not null,
    direction      text        not null check (direction in ('benefit', 'risk')),
    created_at     timestamptz not null default now(),
    primary key (parameter_id, method_version)
);

-- 3. Research jobs (idempotent, resumable, cost-observable)
create table if not exists evaluation.research_jobs (
    id               bigserial primary key,
    composition_id   bigint      not null references evaluation.product_compositions (id) on delete cascade,
    parameter_id     text        not null,
    method_version   text        not null,
    status           text        not null default 'pending'
                     check (status in ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    attempts         int         not null default 0,
    locked_until     timestamptz,
    worker_id        text        not null default '',
    last_error       text        not null default '',
    tokens_in        int         not null default 0,
    tokens_out       int         not null default 0,
    cost_usd         numeric(12, 6) not null default 0,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);
-- one active job per (composition, parameter, method): prevents duplicate AI spend
create unique index if not exists uq_research_jobs_active
    on evaluation.research_jobs (composition_id, parameter_id, method_version)
    where status in ('pending', 'processing');
create index if not exists idx_research_jobs_queue
    on evaluation.research_jobs (status, created_at);

-- 4. Sources and evidence (a fact without a source is not a fact)
create table if not exists evaluation.sources (
    id            bigserial primary key,
    url           text        not null,
    title         text        not null default '',
    publisher     text        not null default '',
    source_type   text        not null default 'unknown'
                  check (source_type in ('official', 'regulator', 'peer_reviewed',
                                         'database', 'retailer', 'unknown')),
    retrieved_at  timestamptz,
    content_hash  text        not null default '',
    unique (url, content_hash)
);

create table if not exists evaluation.evidence (
    id             bigserial primary key,
    source_id      bigint      not null references evaluation.sources (id) on delete restrict,
    fact_type      text        not null,
    value          text        not null,
    quote          text        not null,
    verification   text        not null default 'unverified'
                   check (verification in ('confirmed', 'unverified', 'contradicted')),
    created_at     timestamptz not null default now()
);

-- 5. Parameter evaluations (current row + append-only history)
create table if not exists evaluation.parameter_evaluations (
    id               bigserial primary key,
    composition_id   bigint      not null references evaluation.product_compositions (id) on delete cascade,
    parameter_id     text        not null,
    method_version   text        not null,
    status           text        not null
                     check (status in ('evaluated', 'insufficient_evidence',
                                       'contradictory_evidence', 'not_researched', 'stale')),
    value            numeric(5, 2)
                     check (value is null or (value >= 0 and value <= 100)),
    confidence       numeric(4, 3)
                     check (confidence is null or (confidence >= 0 and confidence <= 1)),
    rationale        text        not null default '',
    limitations      jsonb       not null default '[]'::jsonb,
    evidence_ids     jsonb       not null default '[]'::jsonb,
    input_hash       text        not null,
    evaluated_at     timestamptz not null default now(),
    valid_until      timestamptz,
    superseded_by    bigint      references evaluation.parameter_evaluations (id),
    constraint evaluated_requires_value check (
        (status = 'evaluated' and value is not null)
        or (status <> 'evaluated' and value is null)
    )
);
create unique index if not exists uq_parameter_evaluations_current
    on evaluation.parameter_evaluations (composition_id, parameter_id, method_version)
    where superseded_by is null;
create index if not exists idx_parameter_evaluations_lookup
    on evaluation.parameter_evaluations (composition_id, parameter_id);

-- 6. Rule versions (immutable; calibrated flag gates verdicts)
create table if not exists evaluation.rule_versions (
    version       text        primary key,
    aggregation   text        not null check (aggregation = 'weighted_mean'),
    rules         jsonb       not null,
    rules_hash    text        not null,
    calibrated    boolean     not null default false,
    status        text        not null default 'draft'
                  check (status in ('draft', 'approved', 'retired')),
    notes         text        not null default '',
    created_at    timestamptz not null default now(),
    created_by    text        not null default ''
);

-- 7. Snapshots (immutable; single source of truth for UI and report)
create table if not exists evaluation.snapshots (
    snapshot_id         text        primary key,
    snapshot_hash       text        not null,
    schema_version      text        not null,
    user_id             bigint,
    product_id          bigint      not null,
    composition_id      bigint      not null references evaluation.product_compositions (id) on delete restrict,
    profile_fingerprint jsonb       not null,
    rule_version        text        not null references evaluation.rule_versions (version) on delete restrict,
    engine_version      text        not null,
    engine_input_hash   text        not null,
    parameters          jsonb       not null,
    total               int         check (total is null or (total >= 0 and total <= 100)),
    verdict             text,
    completeness        numeric(4, 3) not null check (completeness >= 0 and completeness <= 1),
    limitations         jsonb       not null default '[]'::jsonb,
    created_at          timestamptz not null default now()
);
create index if not exists idx_snapshots_user_product
    on evaluation.snapshots (user_id, product_id, created_at desc);
create unique index if not exists uq_snapshots_input
    on evaluation.snapshots (user_id, product_id, composition_id, rule_version, engine_input_hash);

create or replace function evaluation.reject_snapshot_mutation() returns trigger as $$
begin
    raise exception 'evaluation.snapshots is append-only';
end;
$$ language plpgsql;

drop trigger if exists trg_snapshots_immutable on evaluation.snapshots;
create trigger trg_snapshots_immutable
    before update or delete on evaluation.snapshots
    for each row execute function evaluation.reject_snapshot_mutation();

-- 8. Access control
-- The backend connects as owner/service role (bypasses RLS). RLS is enabled so
-- accidental anon/authenticated access is denied by default; an owner-read
-- policy is added for future direct-client use.
alter table evaluation.snapshots enable row level security;
alter table evaluation.parameter_evaluations enable row level security;
alter table evaluation.product_compositions enable row level security;
alter table evaluation.research_jobs enable row level security;

drop policy if exists snapshots_owner_read on evaluation.snapshots;
create policy snapshots_owner_read on evaluation.snapshots
    for select to authenticated
    using (user_id::text = auth.uid()::text);

