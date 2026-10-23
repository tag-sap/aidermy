-- Evaluation v2 — evidence provenance (upgrade, additive, idempotent)
-- STATUS: DRAFT. NOT APPLIED to production.
--
-- Records how the source text reached the research provider:
--   'fetched'   — the provider declares it downloaded the page;
--   'synthetic' — test fixture (FakeResearchProvider / candidate() helper);
--   'unknown'   — not declared (legacy rows and future providers that omit it).
--
-- Only 'fetched' evidence may back an ``assessed`` score or a ``not_applicable``
-- decision (see assessment.assess). Existing rows are preserved and default to
-- 'unknown'; the constraint is NOT VALID so old rows are not rejected.

alter table evaluation.evidence
    add column if not exists provenance text not null default 'unknown';

alter table evaluation.evidence
    drop constraint if exists evidence_provenance_check;

alter table evaluation.evidence
    add constraint evidence_provenance_check
    check (provenance in ('fetched', 'synthetic', 'unknown'))
    not valid;
