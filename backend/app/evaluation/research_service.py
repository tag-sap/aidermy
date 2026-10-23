"""Research orchestration: plan -> deduplicated jobs -> provider -> evidence -> evaluation.

Design boundaries:
  * the provider only supplies candidates (claim + quote + source reference);
  * pages are downloaded once per run (``documents.py``) and shared by all
    parameters of that run; stored documents are reused by later runs;
  * validation (evidence.py) and value mapping (assessment.py) are deterministic;
  * a job is processed at most once per attempt, guarded by a DB-level claim;
  * an existing *confirmed* evaluation (``assessed`` / ``not_applicable``) means
    no provider call happens at all;
  * missing / stale / insufficient results become research gaps; repeated attempts
    are bounded by ``max_attempts``;
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
from .documents import (
    MAX_DOCUMENTS_PER_SESSION,
    DocumentFetcher,
    DocumentLibrary,
    DocumentUnavailable,
    SourceDocument,
    collect_source_urls,
)
from .evidence import Evidence, validate_candidates
from .freshness import DEFAULT_REVIEW_AFTER_DAYS
from .gaps import KnowledgeScan, ParameterGap, scan_parameters
from ..catalog_taxonomy import classify_product
from ..category_knowledge import get_category_knowledge
from .parameters import PARAMETERS, resolve_parameters
from .primary_function import build_primary_function
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
from .websearch import (
    RESULTS_PER_QUERY,
    SourceSearch,
    build_research_queries,
    prioritize_candidates,
)

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
    gaps: tuple[ParameterGap, ...] = ()
    source_urls: tuple[str, ...] = ()
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
    documents_fetched: int = 0
    documents_reused: int = 0
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    blocked: bool = False
    notes: tuple[str, ...] = ()

    def summary(self) -> dict:
        """Machine-readable view used by the analysis status (no secrets)."""
        return {
            "failed": list(self.failed),
            "deferred": list(self.deferred),
            "exhausted": list(self.exhausted),
            "documents_fetched": self.documents_fetched,
            "documents_reused": self.documents_reused,
            "notes": list(self.notes),
        }


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
        fetcher: DocumentFetcher | None = None,
        max_documents: int = MAX_DOCUMENTS_PER_SESSION,
        search: SourceSearch | None = None,
        max_queries: int = 4,
        results_per_query: int = RESULTS_PER_QUERY,
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
        self.fetcher = fetcher
        self.max_documents = max_documents
        self.search = search
        self.max_queries = max_queries
        self.results_per_query = results_per_query

    # -- planning -----------------------------------------------------------
    def plan(
        self,
        *,
        product: Mapping,
        composition: Mapping,
        profile: Mapping | None,
        now: datetime | None = None,
        source_urls: Sequence[str] = (),
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
        # ONE pass over every relevant parameter: the whole gap set is known
        # before a single research job is created.
        scan: KnowledgeScan = scan_parameters(
            evaluations=stored,
            profile=profile,
            composition_hash=composition_hash,
            method_version=self.method_version,
            now=now,
            max_age_days=self.max_age_days,
            review_after_days=self.review_after_days,
        )
        notes = list(scan.notes)
        urls = collect_source_urls(
            product, composition, extra=tuple(source_urls)
        )

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
                current=scan.current,
                needed=(),
                stale=scan.stale,
                parameters=resolved.parameters,
                gaps=scan.gaps,
                source_urls=urls,
                blocked=True,
                notes=tuple(notes),
            )

        return ResearchPlan(
            composition=record,
            current=scan.current,
            needed=scan.needed,
            stale=scan.stale,
            parameters=resolved.parameters,
            gaps=scan.gaps,
            source_urls=urls,
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
        source_urls: Sequence[str] = (),
    ) -> ResearchRunReport:
        plan = self.plan(
            product=product,
            composition=composition,
            profile=profile,
            now=now,
            source_urls=source_urls,
        )
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
        notes: list[str] = list(plan.notes)

        for parameter_id in plan.needed:
            attempts = self._max_attempts_used(composition_id, parameter_id)
            if attempts >= self.max_attempts:
                exhausted.append(parameter_id)
                notes.append(
                    f"{parameter_id}: достигнут лимит попыток ({attempts}/{self.max_attempts}); "
                    "сохранённый результат переиспользуется"
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

        if not plan.needed:
            # Nothing to research: do not download pages for an empty plan.
            return ResearchRunReport(
                enqueued=tuple(enqueued),
                skipped=tuple(skipped),
                exhausted=tuple(exhausted),
                notes=tuple(notes),
            )

        if not enqueued and not self._pending_parameters(composition_id):
            # Every gap already exhausted its attempts: reuse stored results and
            # do not spend money on downloads.
            return ResearchRunReport(
                enqueued=(),
                skipped=tuple(skipped),
                exhausted=tuple(exhausted),
                notes=tuple(notes),
            )

        # Shared research session: fetch every candidate page ONCE, then answer
        # every unknown parameter from the same documents. Documents stored by an
        # earlier run are reused instead of being downloaded again.
        library, documents_fetched, documents_reused, document_notes = self._prepare_documents(
            composition_id=composition_id,
            product=product,
            composition=plan.composition,
            source_urls=plan.source_urls,
            parameter_labels=tuple(
                parameters[pid].label
                for pid in plan.needed
                if pid in parameters
            )[: self.max_queries],
        )
        notes.extend(document_notes)

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
            outcome, cost, tin, tout, new_documents = self._process_job(
                job,
                product=product,
                composition=plan.composition,
                parameter=parameter,
                documents=library.documents(),
            )
            if new_documents:
                stored = self.store.save_documents(composition_id, new_documents)
                added = library.extend(new_documents)
                documents_fetched += added
                notes.append(
                    f"провайдер вернул {len(stored)} документ(ов): они доступны "
                    "остальным параметрам этой сессии"
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
            documents_fetched=documents_fetched,
            documents_reused=documents_reused,
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

    def _prepare_documents(
        self,
        *,
        composition_id: int,
        product: Mapping,
        composition: Mapping,
        source_urls: Sequence[str] = (),
        parameter_labels: Sequence[str] = (),
    ) -> tuple[DocumentLibrary, int, int, list[str]]:
        """Load stored documents, discover missing pages, fetch each page once."""
        notes: list[str] = []
        stored = self.store.documents_for(composition_id)
        library = DocumentLibrary(
            [
                SourceDocument(
                    url=str(row["url"]),
                    text=str(row["text"]),
                    title=str(row.get("title") or ""),
                    retrieved_at=str(row.get("retrieved_at") or ""),
                    provenance=str(row.get("provenance") or "unknown"),
                    content_hash=str(row.get("content_hash") or ""),
                )
                for row in stored
            ]
        )
        reused = len(library)
        if reused:
            notes.append(f"переиспользовано сохранённых источников: {reused}")
        if self.fetcher is None or len(library) >= self.max_documents:
            return library, 0, reused, notes

        candidates: list[str] = list(
            collect_source_urls(product, composition, extra=tuple(source_urls))
        )

        # Discover additional pages with the project's existing search, only when
        # the known URLs are not enough to cover the gap set.
        if self.search is not None and len(library) < self.max_documents:
            queries = build_research_queries(
                product=product,
                composition=composition,
                parameter_labels=parameter_labels,
                limit=self.max_queries,
            )
            discovered: list[str] = []
            for query in queries:
                if len(library) + len(discovered) >= self.max_documents:
                    break
                try:
                    found = self.search.search(query, limit=self.results_per_query)
                except Exception as exc:  # noqa: BLE001 - search failures are data
                    notes.append(f"поиск «{query}» не выполнен ({type(exc).__name__})")
                    continue
                if found:
                    notes.append(f"поиск «{query}»: найдено {len(found)} URL")
                discovered.extend(found)
            candidates.extend(prioritize_candidates(discovered, product))

        fetched = 0
        attempts = 0
        max_attempts = max(1, self.max_documents * 2)
        for url in dict.fromkeys(candidates):
            if url in library:
                continue
            if len(library) >= self.max_documents:
                notes.append(f"достигнут лимит источников на сессию ({self.max_documents})")
                break
            if attempts >= max_attempts:
                notes.append(f"достигнут лимит попыток загрузки ({max_attempts})")
                break
            attempts += 1
            try:
                document = self.fetcher.fetch(url)
            except DocumentUnavailable as exc:
                notes.append(f"источник недоступен: {exc.reason}")
                continue
            except Exception as exc:  # noqa: BLE001 - a fetcher failure is data
                notes.append(f"источник не загружен ({type(exc).__name__})")
                continue
            self.store.save_documents(composition_id, [document])
            library.add(document)
            fetched += 1
        return library, fetched, reused, notes

    def _request(
        self,
        job: Mapping,
        *,
        product: Mapping,
        composition: Mapping,
        parameter: Parameter,
        documents: Sequence[SourceDocument] = (),
        source_urls: Sequence[str] = (),
    ) -> ResearchRequest:
        classification = classify_product(dict(product))
        canonical = str(classification.get("canonical_category") or "").strip()
        category = get_category_knowledge(canonical)
        primary = build_primary_function(
            product,
            {**composition, "inci_raw": composition.get("inci_raw") or ""},
            composition_status=str(composition.get("status") or "active"),
        )
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
            product_type=canonical,
            primary_function=str(primary.get("label") or ""),
            category_purpose=str(category.get("intended_purpose") or ""),
            category_guidance=str(category.get("report_guidance") or ""),
            documents=tuple(documents),
            source_urls=tuple(source_urls),
        )

    def _process_job(
        self,
        job: Mapping,
        *,
        product: Mapping,
        composition: Mapping,
        parameter: Parameter,
        documents: Sequence[SourceDocument] = (),
    ) -> tuple[str, float, int, int, tuple[SourceDocument, ...]]:
        parameter_id = str(job["parameter_id"])
        request = self._request(
            job,
            product=product,
            composition=composition,
            parameter=parameter,
            documents=documents,
            source_urls=(),
        )
        try:
            outcome: ResearchOutcome = self.provider.research(request)
        except Exception as exc:  # noqa: BLE001 - provider failures are data, not crashes
            self.store.fail_job(job["id"], f"provider exception: {exc!r}")
            return "failed", 0.0, 0, 0, ()

        cost = float(outcome.cost_usd)
        if cost > self.max_cost_per_job:
            self.store.fail_job(
                job["id"],
                f"превышен лимит стоимости задачи: {cost:.4f} > {self.max_cost_per_job:.4f} USD",
                tokens_in=outcome.tokens_in,
                tokens_out=outcome.tokens_out,
                cost_usd=cost,
            )
            return "failed", cost, outcome.tokens_in, outcome.tokens_out, ()

        if outcome.status == RESEARCH_PROVIDER_ERROR:
            self.store.fail_job(
                job["id"],
                f"ошибка провайдера: {outcome.error or 'без описания'}",
                tokens_in=outcome.tokens_in,
                tokens_out=outcome.tokens_out,
                cost_usd=cost,
            )
            return "failed", cost, outcome.tokens_in, outcome.tokens_out, ()

        if outcome.status == RESEARCH_SOURCE_UNAVAILABLE:
            self.store.fail_job(
                job["id"],
                f"источник недоступен: {outcome.error or 'без описания'}",
                tokens_in=outcome.tokens_in,
                tokens_out=outcome.tokens_out,
                cost_usd=cost,
            )
            return "failed", cost, outcome.tokens_in, outcome.tokens_out, ()

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
            return "insufficient", cost, outcome.tokens_in, outcome.tokens_out, ()

        if outcome.status != RESEARCH_OK:
            self.store.fail_job(job["id"], f"неизвестный статус провайдера: {outcome.status}")
            return "failed", cost, outcome.tokens_in, outcome.tokens_out, ()

        evidence: list[Evidence] = validate_candidates(
            outcome.candidates,
            product_id=int(product["id"]),
            composition_hash=composition_hash,
            parameter_id=parameter_id,
            documents=tuple(documents) or None,
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
            return "failed", cost, outcome.tokens_in, outcome.tokens_out, ()

        self.store.save_evaluation(composition_id, evaluation)
        self.store.complete_job(
            job["id"],
            tokens_in=outcome.tokens_in,
            tokens_out=outcome.tokens_out,
            cost_usd=cost,
        )
        if evaluation.status == STATUS_ASSESSED:
            return "researched", cost, outcome.tokens_in, outcome.tokens_out, outcome.documents
        if evaluation.status == STATUS_NOT_APPLICABLE:
            return "not_applicable", cost, outcome.tokens_in, outcome.tokens_out, outcome.documents
        return "insufficient", cost, outcome.tokens_in, outcome.tokens_out, ()
