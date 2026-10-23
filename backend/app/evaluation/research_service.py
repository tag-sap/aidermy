"""Research orchestration: plan -> deduplicated jobs -> provider -> evidence -> evaluation.

Design boundaries:
  * the provider only supplies candidates (claim + quote + source text);
  * validation (evidence.py) and value mapping (assessment.py) are deterministic;
  * a job is processed at most once per attempt, guarded by a DB-level claim;
  * an existing *current* evaluation means no provider call happens at all;
  * a stale evaluation (composition/method/TTL) triggers a new research;
  * provider failures never leave a "success" state behind.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping, Sequence

from .assessment import assess
from .contracts import (
    STATUS_ASSESSED,
    STATUS_NOT_APPLICABLE,
    ContractError,
    Parameter,
    ParameterEvaluation,
)
from .evidence import Evidence, validate_candidates
from .freshness import DEFAULT_REVIEW_AFTER_DAYS, select_current
from .parameters import PARAMETERS, resolve_parameters
from .research import (
    RESEARCH_INSUFFICIENT,
    RESEARCH_OK,
    RESEARCH_PROVIDER_ERROR,
    RESEARCH_SOURCE_UNAVAILABLE,
    ResearchOutcome,
    ResearchProvider,
    ResearchRequest,
)
from .service import DEFAULT_METHOD_VERSION
from .store import EvaluationStore, StoreError

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MAX_COST_PER_JOB = 0.50
DEFAULT_MAX_COST_PER_RUN = 5.00

COMPOSITION_ACTIVE = "active"


@dataclass(frozen=True)
class ResearchPlan:
    composition: dict
    current: tuple[ParameterEvaluation, ...]
    needed: tuple[str, ...]
    stale: tuple[str, ...]
    parameters: tuple[Parameter, ...] = ()
    blocked: bool = False
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResearchRunReport:
    enqueued: tuple[str, ...] = ()
    researched: tuple[str, ...] = ()
    insufficient: tuple[str, ...] = ()
    not_applicable: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    exhausted: tuple[str, ...] = ()
    deferred: tuple[str, ...] = ()
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    blocked: bool = False
    notes: tuple[str, ...] = ()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _split_inci(raw: str) -> tuple[str, ...]:
    parts = [part.strip() for part in str(raw or "").replace(";", ",").split(",")]
    return tuple(part for part in parts if part)


class ResearchService:
    def __init__(
        self,
        store: EvaluationStore,
        provider: ResearchProvider,
        *,
        method_version: str = DEFAULT_METHOD_VERSION,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        max_cost_per_job: float = DEFAULT_MAX_COST_PER_JOB,
        max_cost_per_run: float = DEFAULT_MAX_COST_PER_RUN,
        max_age_days: int | None = None,
        review_after_days: int | None = DEFAULT_REVIEW_AFTER_DAYS,
        allow_synthetic_evidence: bool = False,
    ) -> None:
        self.store = store
        self.provider = provider
        self.method_version = method_version
        self.max_attempts = max_attempts
        self.max_cost_per_job = max_cost_per_job
        self.max_cost_per_run = max_cost_per_run
        self.max_age_days = max_age_days
        self.review_after_days = review_after_days
        self.allow_synthetic_evidence = allow_synthetic_evidence

    # -- planning -----------------------------------------------------------
    def plan(
        self,
        *,
        product: Mapping,
        composition: Mapping,
        profile: Mapping | None,
        now: datetime | None = None,
    ) -> ResearchPlan:
        composition_hash = str(composition.get("composition_hash") or "")
        if not composition_hash:
            raise StoreError("composition_hash is required")
        record = self.store.get_composition(int(product["id"]), composition_hash)
        if record is None:
            record = self.store.upsert_composition(
                {
                    "product_id": int(product["id"]),
                    "composition_hash": composition_hash,
                    "inci_raw": composition.get("inci_raw") or "",
                    "source": composition.get("source") or "",
                    "verified_at": composition.get("verified_at") or "",
                }
            )

        resolved = resolve_parameters(profile)
        stored = self.store.current_evaluations(record["id"], self.method_version)
        current, stale = select_current(
            stored,
            composition_hash=composition_hash,
            method_version=self.method_version,
            now=now,
            max_age_days=self.max_age_days,
            review_after_days=self.review_after_days,
        )
        notes = list(resolved.notes)

        status = str(record.get("status") or "unverified")
        if status != COMPOSITION_ACTIVE:
            # An unverified INCI may not even be the real formula: researching it
            # would spend money on shared knowledge nobody can rely on.
            notes.append(
                f"Состав не подтверждён (status={status}): исследование не запускается, "
                "пока состав не проверен (verified_at/source или verify_composition)."
            )
            return ResearchPlan(
                composition=record,
                current=tuple(current),
                needed=(),
                stale=tuple(sorted(stale)),
                parameters=resolved.parameters,
                blocked=True,
                notes=tuple(notes),
            )

        researched = {item.parameter_id for item in current}
        needed = tuple(sorted(item.id for item in resolved.parameters if item.id not in researched))
        return ResearchPlan(
            composition=record,
            current=tuple(current),
            needed=needed,
            stale=tuple(sorted(stale)),
            parameters=resolved.parameters,
            notes=tuple(notes),
        )

    # -- execution ----------------------------------------------------------
    def research_missing(
        self,
        *,
        product: Mapping,
        composition: Mapping,
        profile: Mapping | None,
        worker_id: str = "worker",
        process: bool = True,
        now: datetime | None = None,
    ) -> ResearchRunReport:
        plan = self.plan(product=product, composition=composition, profile=profile, now=now)
        if plan.blocked:
            return ResearchRunReport(blocked=True, notes=plan.notes)
        composition_id = int(plan.composition["id"])
        # A job may belong to a parameter selected by another user's profile, so the
        # request is built from the catalog (plus dynamic ingredient parameters),
        # never from this profile's relevant set.
        parameters = dict(PARAMETERS)
        parameters.update({item.id: item for item in plan.parameters})

        enqueued: list[str] = []
        skipped: list[str] = []
        exhausted: list[str] = []
        notes: list[str] = []

        for parameter_id in plan.needed:
            attempts = self._max_attempts_used(composition_id, parameter_id)
            if attempts >= self.max_attempts:
                exhausted.append(parameter_id)
                notes.append(
                    f"{parameter_id}: достигнут лимит попыток ({attempts}/{self.max_attempts})"
                )
                continue
            if self.store.enqueue_research(composition_id, parameter_id, self.method_version):
                enqueued.append(parameter_id)
            else:
                skipped.append(parameter_id)

        if not process:
            return ResearchRunReport(
                enqueued=tuple(enqueued),
                skipped=tuple(skipped),
                exhausted=tuple(exhausted),
                notes=tuple(notes),
            )

        researched: list[str] = []
        insufficient: list[str] = []
        not_applicable: list[str] = []
        failed: list[str] = []
        deferred: list[str] = []
        run_cost = 0.0
        tokens_in = 0
        tokens_out = 0

        while True:
            if run_cost >= self.max_cost_per_run:
                deferred.extend(self._pending_parameters(composition_id))
                notes.append(f"остановлено по лимиту стоимости прогона ({run_cost:.4f} USD)")
                break
            job = self.store.claim_job(worker_id, composition_id=composition_id)
            if job is None:
                break
            parameter = parameters.get(str(job["parameter_id"]))
            if parameter is None:
                self.store.fail_job(
                    job["id"],
                    f"параметр {job['parameter_id']} отсутствует в каталоге анкеты",
                )
                failed.append(job["parameter_id"])
                continue
            outcome, cost, tin, tout = self._process_job(
                job, product=product, composition=plan.composition, parameter=parameter
            )
            run_cost += cost
            tokens_in += tin
            tokens_out += tout
            if outcome == "researched":
                researched.append(job["parameter_id"])
            elif outcome == "not_applicable":
                not_applicable.append(job["parameter_id"])
            elif outcome == "insufficient":
                insufficient.append(job["parameter_id"])
            else:
                failed.append(job["parameter_id"])

        return ResearchRunReport(
            enqueued=tuple(enqueued),
            researched=tuple(researched),
            insufficient=tuple(insufficient),
            not_applicable=tuple(not_applicable),
            failed=tuple(failed),
            skipped=tuple(skipped),
            exhausted=tuple(exhausted),
            deferred=tuple(deferred),
            cost_usd=round(run_cost, 6),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            notes=tuple(notes),
        )

    # -- internals ----------------------------------------------------------
    def _max_attempts_used(self, composition_id: int, parameter_id: str) -> int:
        jobs = self.store.jobs_for(composition_id, parameter_id, self.method_version)
        return max((int(job.get("attempts") or 0) for job in jobs), default=0)

    def _pending_parameters(self, composition_id: int) -> list[str]:
        return list(self.store.pending_parameters(composition_id, self.method_version))

    def _request(
        self,
        job: Mapping,
        *,
        product: Mapping,
        composition: Mapping,
        parameter: Parameter,
    ) -> ResearchRequest:
        return ResearchRequest(
            product_id=int(product["id"]),
            product_name=str(product.get("name") or ""),
            composition_hash=str(composition["composition_hash"]),
            ingredients=_split_inci(composition.get("inci_raw") or ""),
            parameter_id=parameter.id,
            parameter_label=parameter.label,
            method_version=self.method_version,
            scale_anchors=tuple(parameter.anchors),
            parameter_question=parameter.question,
            parameter_definition=parameter.definition,
        )

    def _process_job(
        self,
        job: Mapping,
        *,
        product: Mapping,
        composition: Mapping,
        parameter: Parameter,
    ) -> tuple[str, float, int, int]:
        parameter_id = str(job["parameter_id"])
        request = self._request(
            job, product=product, composition=composition, parameter=parameter
        )
        try:
            outcome: ResearchOutcome = self.provider.research(request)
        except Exception as exc:  # noqa: BLE001 - provider failures are data, not crashes
            self.store.fail_job(job["id"], f"provider exception: {exc!r}")
            return "failed", 0.0, 0, 0

        cost = float(outcome.cost_usd)
        if cost > self.max_cost_per_job:
            self.store.fail_job(
                job["id"],
                f"превышен лимит стоимости задачи: {cost:.4f} > {self.max_cost_per_job:.4f} USD",
                tokens_in=outcome.tokens_in,
                tokens_out=outcome.tokens_out,
                cost_usd=cost,
            )
            return "failed", cost, outcome.tokens_in, outcome.tokens_out

        if outcome.status == RESEARCH_PROVIDER_ERROR:
            self.store.fail_job(
                job["id"],
                f"ошибка провайдера: {outcome.error or 'без описания'}",
                tokens_in=outcome.tokens_in,
                tokens_out=outcome.tokens_out,
                cost_usd=cost,
            )
            return "failed", cost, outcome.tokens_in, outcome.tokens_out

        if outcome.status == RESEARCH_SOURCE_UNAVAILABLE:
            self.store.fail_job(
                job["id"],
                f"источник недоступен: {outcome.error or 'без описания'}",
                tokens_in=outcome.tokens_in,
                tokens_out=outcome.tokens_out,
                cost_usd=cost,
            )
            return "failed", cost, outcome.tokens_in, outcome.tokens_out

        composition_id = int(job["composition_id"])
        composition_hash = str(composition["composition_hash"])

        if outcome.status == RESEARCH_INSUFFICIENT:
            evaluation = assess(
                parameter,
                None,
                composition_hash=composition_hash,
                method_version=self.method_version,
                evaluated_at=_now_iso(),
                composition=composition,
                allow_synthetic_evidence=self.allow_synthetic_evidence,
            )
            self.store.save_evaluation(composition_id, evaluation)
            self.store.complete_job(
                job["id"],
                tokens_in=outcome.tokens_in,
                tokens_out=outcome.tokens_out,
                cost_usd=cost,
            )
            return "insufficient", cost, outcome.tokens_in, outcome.tokens_out

        if outcome.status != RESEARCH_OK:
            self.store.fail_job(job["id"], f"неизвестный статус провайдера: {outcome.status}")
            return "failed", cost, outcome.tokens_in, outcome.tokens_out

        evidence: list[Evidence] = validate_candidates(
            outcome.candidates,
            product_id=int(product["id"]),
            composition_hash=composition_hash,
            parameter_id=parameter_id,
        )
        ids = self.store.save_evidence(composition_id, evidence)

        try:
            evaluation = assess(
                parameter,
                outcome.proposal,
                evidence,
                composition_hash=composition_hash,
                method_version=self.method_version,
                evaluated_at=_now_iso(),
                evidence_ids=ids,
                composition=composition,
                allow_synthetic_evidence=self.allow_synthetic_evidence,
            )
        except ContractError as exc:
            # A protocol/validation error is NOT "not applicable" and NOT
            # "insufficient evidence": the job fails and can be retried.
            reasons = sorted(
                {item.rejection_reason for item in evidence if item.rejection_reason}
            )
            self.store.fail_job(
                job["id"],
                f"некорректный результат оценки: {exc}"
                + (f" (отклонено: {'; '.join(reasons[:3])})" if reasons else ""),
                tokens_in=outcome.tokens_in,
                tokens_out=outcome.tokens_out,
                cost_usd=cost,
            )
            return "failed", cost, outcome.tokens_in, outcome.tokens_out

        self.store.save_evaluation(composition_id, evaluation)
        self.store.complete_job(
            job["id"],
            tokens_in=outcome.tokens_in,
            tokens_out=outcome.tokens_out,
            cost_usd=cost,
        )
        if evaluation.status == STATUS_ASSESSED:
            return "researched", cost, outcome.tokens_in, outcome.tokens_out
        if evaluation.status == STATUS_NOT_APPLICABLE:
            return "not_applicable", cost, outcome.tokens_in, outcome.tokens_out
        return "insufficient", cost, outcome.tokens_in, outcome.tokens_out
