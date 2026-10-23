-- Evaluation v2 — status model 3.0.0 (upgrade, additive, idempotent)
-- STATUS: DRAFT. NOT APPLIED to production.
--
-- Purpose: allow the four new result states (pending / assessed / not_applicable /
-- insufficient_evidence) without deleting or rewriting existing rows.
--
-- Safety notes:
--   * no table or row is dropped; legacy rows stay readable for audit;
--   * constraints are added NOT VALID, so rows written by earlier drafts are not
--     rejected retroactively (they are still excluded from scoring in code);
--   * the script can be re-run: constraints are dropped-if-exists first.

alter table evaluation.parameter_evaluations
    drop constraint if exists parameter_evaluations_status_check;
alter table evaluation.parameter_evaluations
    drop constraint if exists evaluated_requires_value;
alter table evaluation.parameter_evaluations
    drop constraint if exists assessed_requires_value;
alter table evaluation.parameter_evaluations
    drop constraint if exists assessed_requires_explanation;

alter table evaluation.parameter_evaluations
    add constraint parameter_evaluations_status_check
    check (status in ('pending', 'assessed', 'not_applicable',
                      'insufficient_evidence', 'stale',
                      'evaluated', 'not_researched', 'contradictory_evidence'))
    not valid;

-- Only an assessed result carries a score, and the score is one of 0/25/50/75/100.
alter table evaluation.parameter_evaluations
    add constraint assessed_requires_value check (
        (status = 'assessed' and value is not null and value in (0, 25, 50, 75, 100))
        -- legacy rows keep their historical number; the engine never scores them
        or (status = 'evaluated' and value is not null)
        or (status not in ('assessed', 'evaluated') and value is null)
    ) not valid;

-- An assessed result must carry an explanation and references to stored evidence.
alter table evaluation.parameter_evaluations
    add constraint assessed_requires_explanation check (
        status <> 'assessed'
        or (length(btrim(rationale)) > 0 and jsonb_array_length(evidence_ids) > 0)
    ) not valid;

-- The final score is a plain arithmetic mean of allowed levels, so it may be
-- fractional (e.g. 62.5 or 58.33) and must not be coerced to int.
alter table evaluation.snapshots
    alter column total type numeric(5, 2) using total::numeric(5, 2);
