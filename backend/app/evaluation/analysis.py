"""End-to-end analysis: product knowledge -> gaps -> shared research -> report.

This is the mechanic the product needs, in one place:

  1. load the product and its composition (optionally from the Aidermy catalog);
  2. scan EVERY questionnaire parameter and collect the full gap set;
  3. research the gaps together: discover pages with the project's search, fetch
     each page once, answer each parameter from the same documents, keep each
     parameter's own result;
  4. assemble the report and state honestly whether it is final.

The service never invents a score and never marks an unfinished or failed analysis
as a finished report: that decision belongs to ``gaps.analysis_state``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from .gaps import AnalysisState, analysis_state, scan_parameters
from .documents import MAX_DOCUMENTS_PER_SESSION
from .freshness import DEFAULT_REVIEW_AFTER_DAYS
from .inci import NOT_LISTED, PRESENT, UNVERIFIABLE, check_intolerance
from .knowledge import (
    KnowledgeUnavailable,
    ProductKnowledge,
    ProductNotFound,
    assess_composition,
    load_product_knowledge,
)
from .parameters import PARAMETERS, ingredient_parameter
from .primary_function import build_primary_function, public_primary_function
from .research import ResearchProvider
from .snapshot import profile_fingerprint, verify_snapshot
from .timing import StageTimer
from .research_service import (
    DEFAULT_MAX_ATTEMPTS,
    ResearchPlan,
    ResearchRunReport,
    ResearchService,
)
from .rules import RuleSet, get_rules
from .service import DEFAULT_METHOD_VERSION, EvaluationService
from .store import COMPOSITION_ACTIVE, EvaluationStore
from .websearch import SourceSearch


logger = logging.getLogger(__name__)


class AnalysisUnavailable(RuntimeError):
    """The analysis cannot run (missing provider, catalog or composition)."""


_INTOLERANCE_LABELS = {
    PRESENT: "Обнаружен в составе",
    NOT_LISTED: "Не обнаружен в составе",
    UNVERIFIABLE: "Не удалось определить",
}
_INTOLERANCE_STATES = {
    PRESENT: "present",
    NOT_LISTED: "absent",
    UNVERIFIABLE: "unknown",
}


def _intolerance_status(parameter_id: str, composition: Mapping) -> dict | None:
    """Expose the authoritative INCI status without reinterpreting the score."""
    parameter = PARAMETERS.get(parameter_id)
    if parameter is None and parameter_id.startswith("intolerance:ingredient:"):
        name = parameter_id.split(":", 2)[2].replace("_", " ").strip()
        if not name:
            return None
        try:
            parameter = ingredient_parameter(name)
        except Exception:  # noqa: BLE001 - malformed legacy ids stay unknown
            return None
    if parameter is None or parameter.section != "intolerance":
        return None
    checked = check_intolerance(parameter, composition)
    if checked is None:
        return None
    return {
        "state": _INTOLERANCE_STATES.get(checked.status, "unknown"),
        "label": _INTOLERANCE_LABELS.get(checked.status, "Не удалось определить"),
        "status": checked.status,
        "reason": checked.reason,
        "matched": list(checked.matched),
    }


_CRITICAL_SECTIONS = {"skin_type", "problem", "therapy", "procedure", "intolerance"}
_VERDICT_ICONS = {"positive": "check", "neutral": "dash", "negative": "cross", "unknown": "dash"}


def _section(parameter_id: str) -> str:
    return parameter_id.split(":", 1)[0]


def _verdict_label(parameter_id: str, verdict: str, intolerance: Mapping | None = None) -> str:
    section = _section(parameter_id)
    if section == "intolerance" and intolerance is not None:
        return str(intolerance.get("label") or "Не удалось определить")
    if section == "therapy":
        return {
            "positive": "Совместимо с лечением",
            "neutral": "Совместимость неясна",
            "negative": "Конфликт с лечением",
            "unknown": "Не удалось определить",
        }[verdict]
    if section == "procedure":
        return {
            "positive": "Можно использовать в этот период",
            "neutral": "Нужна осторожность",
            "negative": "Не рекомендуется в этот период",
            "unknown": "Не удалось определить",
        }[verdict]
    if section == "goal":
        return {
            "positive": "Цель поддерживается",
            "neutral": "Влияние неясно",
            "negative": "Цель не подтверждена",
            "unknown": "Не удалось определить",
        }[verdict]
    if section == "skin_type":
        return {
            "positive": "Соответствует типу кожи",
            "neutral": "Смешанный результат",
            "negative": "Не соответствует типу кожи",
            "unknown": "Не удалось определить",
        }[verdict]
    if section == "problem":
        return {
            "positive": "Соответствует задаче",
            "neutral": "Смешанный результат",
            "negative": "Не соответствует задаче",
            "unknown": "Не удалось определить",
        }[verdict]
    return {
        "positive": "Подходит",
        "neutral": "Смешанный результат",
        "negative": "Не подходит",
        "unknown": "Не удалось определить",
    }[verdict]


def _item_verdict(parameter_id: str, score: object, intolerance: Mapping | None) -> str:
    if intolerance is not None:
        state = str(intolerance.get("state") or "unknown")
        if state == "present":
            return "negative"
        if state == "absent":
            return "positive"
        return "unknown"
    try:
        value = float(score)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "unknown"
    if value >= 75:
        return "positive"
    if value <= 25:
        return "negative"
    return "neutral"


def _gap_label(parameter_id: str) -> str:
    parameter = PARAMETERS.get(parameter_id)
    if parameter is not None:
        return parameter.label
    if parameter_id.startswith("intolerance:ingredient:"):
        name = parameter_id.split(":", 2)[2].replace("_", " ").strip()
        if name:
            try:
                return ingredient_parameter(name).label
            except Exception:  # noqa: BLE001
                return name
    return "Параметр профиля"


def _overall_verdict(items: Sequence[Mapping]) -> dict:
    """Aggregate conflicts by meaning, not by counting positive cards."""
    assessed = [
        item for item in items
        if item.get("verdict") in {"positive", "neutral", "negative"}
    ]
    unknown = sum(1 for item in items if item.get("verdict") == "unknown")
    positive = sum(1 for item in items if item.get("verdict") == "positive")
    neutral = sum(1 for item in items if item.get("verdict") == "neutral")
    negative = [item for item in items if item.get("verdict") == "negative"]
    critical = [
        item for item in negative
        if _section(str(item.get("parameter_id") or "")) in _CRITICAL_SECTIONS
    ]
    if critical:
        first = critical[0]
        verdict = "Не подходит"
        tone = "bad"
        summary = f"Есть критичный конфликт: {first.get('label')}. {first.get('verdict_label')}."
    elif not assessed and unknown:
        verdict = "Недостаточно данных"
        tone = "muted"
        summary = "Нет подтверждённых оценок; неизвестные данные не считаются положительными."
    elif not assessed:
        verdict = "Недостаточно данных"
        tone = "muted"
        summary = "Для вашего профиля нет проверенных пунктов."
    elif negative:
        verdict = "Подходит с оговорками"
        tone = "warn"
        summary = (
            f"Есть предупреждения: {len(negative)}. Это не критический конфликт, "
            "но продукт подходит не полностью."
        )
    elif neutral or unknown:
        verdict = "Подходит с оговорками"
        tone = "warn"
        summary = f"Есть оговорки: нейтральных — {neutral}, неизвестных — {unknown}."
    else:
        verdict = "Подходит"
        tone = "good"
        summary = f"Все {positive} проверенных пункта подтверждают совместимость."
    return {
        "verdict": verdict,
        "tone": tone,
        "summary": summary,
        "positive": positive,
        "neutral": neutral,
        "negative": len(negative),
        "unknown": unknown,
        "assessed": len(assessed),
    }


def _source_urls(items: Sequence[Mapping], primary: Mapping | None) -> list[str]:
    urls: list[str] = []

    def add(url: object) -> None:
        text = str(url or "").strip()
        if text.startswith(("http://", "https://")) and text not in urls:
            urls.append(text)

    for item in items:
        for row in item.get("evidence") or []:
            source = row.get("source") or {}
            add(source.get("url"))
    for row in (primary or {}).get("basis") or []:
        add(row.get("source"))
    return urls


@dataclass(frozen=True)
class AnalysisReport:
    product: dict
    composition: dict
    snapshot: dict
    analysis: AnalysisState
    research: ResearchRunReport | None = None
    plan: ResearchPlan | None = None
    knowledge: ProductKnowledge | None = None
    evidence: dict[str, list[dict]] = field(default_factory=dict)
    primary_function: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)

    @property
    def is_final(self) -> bool:
        return self.analysis.is_final

    def user_report(self) -> dict:
        """The compact, non-technical result rendered in the product drawer.

        Internal statuses, provider errors, the historical average and
        source-quote audit material stay in ``snapshot``/``analysis``/``evidence``.
        This projection contains the overall verdict, the checklist with
        explicit neutral/unknown states, and one source list.
        """
        personal = []
        seen: set[str] = set()
        for row in self.snapshot.get("parameters") or []:
            if not row.get("included") or row.get("value") is None:
                continue
            parameter_id = str(row.get("parameter_id") or "")
            intolerance = _intolerance_status(parameter_id, self.composition)
            verdict = _item_verdict(parameter_id, row.get("value"), intolerance)
            item = {
                "parameter_id": parameter_id,
                "label": str(row.get("label") or ""),
                "score": row.get("value"),
                "reason": str(row.get("summary") or row.get("reason") or ""),
                "evidence": list(self.evidence.get(parameter_id) or []),
                "section": _section(parameter_id),
                "verdict": verdict,
                "verdict_label": _verdict_label(parameter_id, verdict, intolerance),
                "verdict_icon": _VERDICT_ICONS[verdict],
            }
            if intolerance is not None:
                item["intolerance"] = intolerance
            personal.append(item)
            seen.add(parameter_id)

        # Unknown is not a positive result: show it explicitly with a neutral
        # dash, but never invent a score or a check.
        for gap in self.analysis.gaps:
            parameter_id = str(gap.parameter_id)
            if parameter_id in seen:
                continue
            personal.append({
                "parameter_id": parameter_id,
                "label": _gap_label(parameter_id),
                "score": None,
                "reason": gap.detail or "Нет подтверждённых данных для оценки.",
                "evidence": [],
                "section": _section(parameter_id),
                "verdict": "unknown",
                "verdict_label": "Не удалось определить",
                "verdict_icon": _VERDICT_ICONS["unknown"],
            })
            seen.add(parameter_id)

        primary = public_primary_function(self.primary_function)
        name = " ".join(str(self.product.get("name") or "").replace("\n", " ").split())
        return {
            "product_name": name,
            "primary_function": primary,
            "overall": _overall_verdict(personal),
            "personal_compatibility": personal,
            "sources": _source_urls(personal, primary),
        }

    def as_dict(self) -> dict:
        payload = {
            "product": dict(self.product),
            "composition": dict(self.composition),
            "composition_state": assess_composition(
                self.product,
                self.composition,
                status=str(self.composition.get("status") or ""),
            ).as_dict(),
            "snapshot": self.snapshot,
            "analysis": self.analysis.as_dict(),
            "evidence": self.evidence,
            "primary_function": self.primary_function,
            "user_report": self.user_report(),
            "timings": self.timings,
        }
        if self.plan is not None:
            payload["plan"] = {
                "needed": list(self.plan.needed),
                "stale": list(self.plan.stale),
                "gaps": [gap.as_dict() for gap in self.plan.gaps],
                "blocked": self.plan.blocked,
                "notes": list(self.plan.notes),
            }
        if self.research is not None:
            payload["research"] = {
                "researched": list(self.research.researched),
                "insufficient": list(self.research.insufficient),
                "not_applicable": list(self.research.not_applicable),
                "failed": list(self.research.failed),
                "skipped": list(self.research.skipped),
                "exhausted": list(self.research.exhausted),
                "deferred": list(self.research.deferred),
                "documents_fetched": self.research.documents_fetched,
                "documents_reused": self.research.documents_reused,
                "cost_usd": self.research.cost_usd,
                "tokens_in": self.research.tokens_in,
                "tokens_out": self.research.tokens_out,
                "blocked": self.research.blocked,
                "notes": list(self.research.notes),
            }
        return payload


class AnalysisService:
    """Runs the full analysis mechanic for one product composition."""

    def __init__(
        self,
        store: EvaluationStore,
        *,
        provider: ResearchProvider | None = None,
        fetcher=None,
        search: SourceSearch | None = None,
        rules: RuleSet | None = None,
        method_version: str = DEFAULT_METHOD_VERSION,
        max_age_days: int | None = None,
        review_after_days: int | None = DEFAULT_REVIEW_AFTER_DAYS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        max_documents: int = MAX_DOCUMENTS_PER_SESSION,
        max_cost_per_job: float = 0.50,
        max_cost_per_run: float = 5.00,
        max_concurrency: int = 4,
        allow_synthetic_evidence: bool = False,
    ) -> None:
        self.store = store
        self.provider = provider
        self.fetcher = fetcher
        self.search = search
        self.rules = rules or get_rules()
        self.method_version = method_version
        self.max_age_days = max_age_days
        self.review_after_days = review_after_days
        self.max_attempts = max_attempts
        self.max_documents = max_documents
        self.max_cost_per_job = max_cost_per_job
        self.max_cost_per_run = max_cost_per_run
        self.max_concurrency = max(1, min(int(max_concurrency), 8))
        self.allow_synthetic_evidence = allow_synthetic_evidence
        self._evaluation = EvaluationService(
            store,
            rules=self.rules,
            method_version=method_version,
            max_age_days=max_age_days,
            review_after_days=review_after_days,
            # The user-facing analysis has a primary-function score and
            # independent personal parameters; it must not calculate a mean
            # across heterogeneous questionnaire parameters.
            aggregate=False,
        )

    # -- public API ----------------------------------------------------------
    def analyze(
        self,
        *,
        product: Mapping[str, Any],
        composition: Mapping[str, Any],
        profile: Mapping[str, Any] | None,
        source_urls: Sequence[str] = (),
        allow_research: bool = True,
        process: bool = True,
        user_id: int | None = None,
        now: datetime | None = None,
        knowledge: ProductKnowledge | None = None,
        timer: StageTimer | None = None,
    ) -> AnalysisReport:
        """Scan all parameters, research the gaps, and assemble an honest report."""
        product_id = product.get("id")
        if product_id is None:
            raise AnalysisUnavailable("product.id is required")
        timer = timer or StageTimer(product_id=int(product_id), allow_research=allow_research)

        with timer.stage("composition"):
            record = self._evaluation.ensure_composition(int(product_id), composition)
        # An existing record may have been registered earlier as unverified (e.g.
        # by /status). An explicit verification must upgrade it, otherwise the
        # analysed composition stays blocked forever.
        if composition.get("verified_at") and str(record.get("status") or "") != COMPOSITION_ACTIVE:
            record = self.store.verify_composition(
                int(record["id"]),
                str(composition["verified_at"]),
                str(composition.get("source") or ""),
            )
        composition_hash = str(record["composition_hash"])
        blocked = str(record.get("status") or "") != COMPOSITION_ACTIVE

        research: ResearchRunReport | None = None
        plan: ResearchPlan | None = None

        if not blocked:
            service = self._research_service()
            with timer.stage("plan"):
                plan = service.plan(
                    product=product,
                    composition=composition,
                    profile=profile,
                    now=now,
                    source_urls=source_urls,
                    composition_record=record,
                )
            blocked = plan.blocked
            if plan.needed and allow_research:
                if self.provider is None:
                    raise AnalysisUnavailable(
                        "провайдер исследования не настроен: анализ недостающих "
                        "параметров невозможен"
                    )
                with timer.stage("research"):
                    research = service.research_missing(
                        product=product,
                        composition=composition,
                        profile=profile,
                        process=process,
                        now=now,
                        source_urls=source_urls,
                        plan=plan,
                    )
                blocked = research.blocked or blocked

        with timer.stage("snapshot"):
            built = self._evaluation.build(
                product=product,
                composition=composition,
                profile=profile,
                now=now,
                user_id=user_id,
                research_summary=research.summary() if research is not None else None,
                blocked=blocked,
                composition_record=record,
                stored_evaluations=plan.current if plan is not None and research is None else None,
            )

        extra_notes = list(knowledge.notes) if knowledge is not None else []
        state = built.analysis
        if extra_notes:
            state = analysis_state(
                scan=built.scan,
                research=research.summary() if research is not None else None,
                blocked=blocked,
                extra_notes=extra_notes,
            )

        logger.info(
            "[EVALUATION] product=%s composition=%s status=%s final=%s assessed=%d "
            "gaps=%d failed=%d docs_fetched=%d docs_reused=%d research=%s",
            product_id,
            composition_hash[:12],
            state.status,
            state.is_final,
            len(state.assessed_parameters),
            len(state.gaps),
            len(state.failed_parameters),
            state.documents_fetched,
            state.documents_reused,
            bool(research),
        )
        if state.gaps:
            logger.info(
                "[EVALUATION] gaps: %s",
                ", ".join(f"{gap.parameter_id}:{gap.reason}" for gap in state.gaps),
            )

        parameter_ids = (*state.assessed_parameters, *state.not_applicable_parameters)
        with timer.stage("evidence"):
            if parameter_ids and hasattr(self.store, "evidence_for_many"):
                evidence_by_parameter = self.store.evidence_for_many(
                    int(record["id"]), parameter_ids
                )
                evidence_by_parameter = {
                    parameter_id: [
                        row
                        for row in rows
                        if str(row.get("verification") or "") == "confirmed"
                    ]
                    for parameter_id, rows in evidence_by_parameter.items()
                }
                evidence_by_parameter = {
                    parameter_id: rows
                    for parameter_id, rows in evidence_by_parameter.items()
                    if rows
                }
            else:
                evidence_by_parameter = {}
                for parameter_id in parameter_ids:
                    rows = self.store.evidence_for(int(record["id"]), parameter_id)
                    confirmed = [
                        row
                        for row in rows
                        if str(row.get("verification") or "") == "confirmed"
                    ]
                    if confirmed:
                        evidence_by_parameter[parameter_id] = confirmed

        with timer.stage("primary_function"):
            primary_function = build_primary_function(
                product,
                {**record, "inci_raw": record.get("inci_raw") or composition.get("inci_raw") or ""},
                composition_status=str(record.get("status") or ""),
            )
        timings = timer.log(
            logger,
            assessed=len(state.assessed_parameters),
            gaps=len(state.gaps),
            failed=len(state.failed_parameters),
            needed=len(plan.needed) if plan is not None else 0,
            researched=len(research.researched) if research is not None else 0,
        )
        return AnalysisReport(
            product={
                "id": int(product_id),
                "name": str(product.get("name") or ""),
            },
            composition={
                "composition_hash": composition_hash,
                "inci_raw": record.get("inci_raw") or "",
                "source": record.get("source") or "",
                "verified_at": str(record.get("verified_at") or ""),
                "status": record.get("status") or "",
            },
            snapshot=built.snapshot,
            analysis=state,
            research=research,
            plan=plan,
            knowledge=knowledge,
            evidence=evidence_by_parameter,
            primary_function=primary_function,
            timings=timings,
        )


    def saved_report(
        self,
        *,
        product_id: int,
        profile: Mapping[str, Any] | None,
        user_id: int | None,
    ) -> AnalysisReport | None:
        """Read a complete, current snapshot without research or a new write.

        Reopening a product must not repeat the first analysis. This method only
        accepts a verified snapshot whose saved parameter values still match the
        current evaluations; stale/incomplete history falls back to ``None`` and
        the regular (reuse-first) analysis path remains available.
        """
        if user_id is None or not hasattr(self.store, "latest_snapshot"):
            return None
        try:
            # Saved-report reads do not need ingredient seed URLs; skip that
            # extra knowledge lookup on every drawer open.
            knowledge = load_product_knowledge(
                int(product_id), include_ingredient_sources=False
            )
            record = self.store.get_composition(
                int(product_id), knowledge.composition_hash
            )
        except (ProductNotFound, KnowledgeUnavailable):
            return None
        except Exception:  # noqa: BLE001 - a saved read must not break the drawer
            return None
        if record is None or str(record.get("status") or "") != COMPOSITION_ACTIVE:
            return None

        latest = self.store.latest_snapshot(
            product_id=int(product_id),
            composition_hash=str(record["composition_hash"]),
            user_id=int(user_id),
            profile_fingerprint=profile_fingerprint(profile),
        )
        if latest is None or not verify_snapshot(latest):
            return None
        saved_analysis = latest.get("analysis") or {}
        if not saved_analysis.get("is_final"):
            return None

        stored = self.store.current_evaluations(
            int(record["id"]), self.method_version
        )
        scan = scan_parameters(
            evaluations=stored,
            profile=profile,
            composition_hash=str(record["composition_hash"]),
            method_version=self.method_version,
            max_age_days=self.max_age_days,
            review_after_days=self.review_after_days,
        )
        if scan.needed or scan.stale:
            return None
        current_values = {
            item.parameter_id: item.value
            for item in scan.current
            if item.status == "assessed" and item.value is not None
        }
        saved_values = {
            str(row.get("parameter_id") or ""): row.get("value")
            for row in latest.get("parameters") or []
            if row.get("included") and row.get("value") is not None
        }
        if set(current_values) != set(saved_values):
            return None
        for parameter_id, value in current_values.items():
            try:
                if abs(float(value) - float(saved_values[parameter_id])) > 1e-9:
                    return None
            except (TypeError, ValueError):
                return None

        parameter_ids = tuple(saved_values)
        evidence: dict[str, list[dict]] = {}
        if parameter_ids:
            try:
                rows = self.store.evidence_for_many(int(record["id"]), parameter_ids)
            except AttributeError:
                rows = {
                    parameter_id: self.store.evidence_for(
                        int(record["id"]), parameter_id
                    )
                    for parameter_id in parameter_ids
                }
            for parameter_id, items in rows.items():
                confirmed = [
                    row
                    for row in items
                    if str(row.get("verification") or "") == "confirmed"
                ]
                if confirmed:
                    evidence[parameter_id] = confirmed
        primary = build_primary_function(
            knowledge.product,
            {**record, "inci_raw": record.get("inci_raw") or ""},
            composition_status=str(record.get("status") or ""),
        )
        state = analysis_state(scan=scan, blocked=False)
        return AnalysisReport(
            product=knowledge.product,
            composition={
                "composition_hash": str(record["composition_hash"]),
                "inci_raw": record.get("inci_raw") or "",
                "source": record.get("source") or "",
                "verified_at": str(record.get("verified_at") or ""),
                "status": record.get("status") or "",
            },
            snapshot=latest,
            analysis=state,
            knowledge=knowledge,
            evidence=evidence,
            primary_function=primary,
            timings={"saved": True},
        )

    def analyze_product(
        self,
        product_id: int,
        *,
        profile: Mapping[str, Any] | None,
        verified_at: str | None = None,
        composition_source: str | None = None,
        extra_sources: Sequence[str] = (),
        allow_research: bool = True,
        process: bool = True,
        user_id: int | None = None,
        now: datetime | None = None,
        product_loader: Callable[[int], Mapping | None] | None = None,
        repository=None,
        verify_catalog_inci: bool = False,
    ) -> AnalysisReport:
        """Analyze an existing Aidermy product (catalog + INCI + known sources).

        ``verify_catalog_inci`` is an explicit (admin) decision to treat the
        catalog INCI as the confirmed formula. It is refused when the record has
        no reliable INCI or no source URL, and it is recorded with its basis.
        """
        timer = StageTimer(product_id=int(product_id), allow_research=allow_research)
        try:
            with timer.stage("knowledge"):
                knowledge = load_product_knowledge(
                    product_id,
                    product_loader=product_loader,
                    repository=repository,
                    verified_at=verified_at,
                    composition_source=composition_source,
                    extra_sources=extra_sources,
                )
        except ProductNotFound:
            raise
        except KnowledgeUnavailable as exc:
            raise AnalysisUnavailable(str(exc)) from exc

        notes = list(knowledge.notes)
        composition = dict(knowledge.composition)
        readiness = assess_composition(knowledge.product, composition)
        if readiness.auto_verify and not composition.get("verified_at"):
            stamp = (now or datetime.now(timezone.utc)).isoformat()
            composition["verified_at"] = stamp
            notes.append(
                f"{readiness.message} Проверка происхождения зафиксирована в {stamp}."
            )
        if verify_catalog_inci and not composition.get("verified_at"):
            source = str(composition.get("source") or "")
            if not knowledge.product.get("has_reliable_inci"):
                raise AnalysisUnavailable(
                    "состав продукта нельзя подтвердить автоматически: в каталоге нет "
                    "надёжного INCI (нужно минимум два ингредиента)"
                )
            if not source.startswith(("http://", "https://")):
                raise AnalysisUnavailable(
                    "состав продукта нельзя подтвердить автоматически: у карточки нет "
                    "ссылки-источника состава"
                )
            stamp = (now or datetime.now(timezone.utc)).isoformat()
            composition["verified_at"] = stamp
            notes.append(
                f"Состав подтверждён администратором по данным каталога Aidermy "
                f"(источник: {source}) в {stamp}."
            )
        knowledge = ProductKnowledge(
            product=dict(knowledge.product),
            composition=composition,
            source_urls=knowledge.source_urls,
            notes=tuple(notes),
        )
        return self.analyze(
            product=knowledge.product,
            composition=knowledge.composition,
            profile=profile,
            source_urls=knowledge.source_urls,
            allow_research=allow_research,
            process=process,
            user_id=user_id,
            now=now,
            knowledge=knowledge,
            timer=timer,
        )

    # -- internals -----------------------------------------------------------
    def _research_service(self) -> ResearchService:
        return ResearchService(
            self.store,
            self.provider,
            method_version=self.method_version,
            max_attempts=self.max_attempts,
            max_age_days=self.max_age_days,
            review_after_days=self.review_after_days,
            allow_synthetic_evidence=self.allow_synthetic_evidence,
            fetcher=self.fetcher,
            search=self.search,
            max_documents=self.max_documents,
            max_cost_per_job=self.max_cost_per_job,
            max_cost_per_run=self.max_cost_per_run,
            max_concurrency=self.max_concurrency,
        )

