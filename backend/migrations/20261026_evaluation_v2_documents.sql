-- Evaluation v2 — shared source documents (upgrade, additive, idempotent)
-- STATUS: DRAFT. NOT APPLIED to production.
--
-- Stores the text of downloaded pages once per (composition, url). A research
-- session fetches each page once and answers several parameters from the same
-- documents; later sessions reuse the stored text instead of downloading again.
-- Evidence quotes are validated against this text, not against model output.

create table if not exists evaluation.source_documents (
    id             bigserial primary key,
    composition_id bigint      not null references evaluation.product_compositions (id) on delete cascade,
    url            text        not null,
    title          text        not null default '',
    text           text        not null,
    content_hash   text        not null default '',
    retrieved_at   timestamptz,
    provenance     text        not null default 'fetched'
                   check (provenance in ('fetched', 'synthetic', 'unknown')),
    created_at     timestamptz not null default now(),
    unique (composition_id, url)
);

create index if not exists idx_source_documents_composition
    on evaluation.source_documents (composition_id);

alter table evaluation.source_documents enable row level security;
