"""End-to-end analysis: product knowledge -> gaps -> shared research -> report.

This is the mechanic the product needs, in one place:

  1. load the product and its composition (optionally from the Aidermy catalog);
  2. scan EVERY questionnaire parameter and collect the full gap set;
  3. research the gaps together: fetch pages once, answer each parameter from the
     same documents, keep each parameter's own result;
  4. assemble the report and state honestly whether it is final.

The service never invents a score and never marks an unfinished or failed analysis
as a finished report: that decision belongs to ``gaps.analysis_state``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

from .gaps import AnalysisState, analysis_state
from .freshness import DEFAULT_REVIEW_AFTER_DAYS
from .knowledge import (
    KnowledgeUnavailable,
    ProductKnowledge,
    ProductNotFound,
    load_product_knowledge,
)
from .research import ResearchProvider
from .research_service import (
    DEFAULT_MAX_ATTEMPTS,
    ResearchPlan,
    ResearchRunReport,
    ResearchService,
)
from .rules import RuleSet, get_rules
from .service import DEFAULT_METHOD_VERSION, EvaluationService
from .store import COMPOSITION_ACTIVE, EvaluationStore


class AnalysisUnavailable(RuntimeError):
    """The analysis cannot run (missing provider, catalog or composition)."""


@dataclass(frozen=True)
class AnalysisReport:
    product: dict
    composition: dict
    snapshot: dict
    analysis: AnalysisState
    research: ResearchRunReport | None = None
    plan: ResearchPlan | None = None
    knowledge: ProductKnowledge | None = None

    @property
    def is_final(self) -> bool:
        return self.analysis.is_final

    def as_dict(self) -> dict:
        payload = {
            "product": dict(self.product),
            "composition": dict(self.composition),
            "snapshot": self.snapshot,
            "analysis": self.analysis.as_dict(),
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
        rules: RuleSet | None = None,
        method_version: str = DEFAULT_METHOD_VERSION,
        max_age_days: int | None = None,
        review_after_days: int | None = DEFAULT_REVIEW_AFTER_DAYS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        allow_synthetic_evidence: bool = False,
    ) -> None:
        self.store = store
        self.provider = provider
        self.fetcher = fetcher
        self.rules = rules or get_rules()
        self.method_version = method_version
        self.max_age_days = max_age_days
        self.review_after_days = review_after_days
        self.max_attempts = max_attempts
        self.allow_synthetic_evidence = allow_synthetic_evidence
        self._evaluation = EvaluationService(
            store,
            rules=self.rules,
            method_version=method_version,
            max_age_days=max_age_days,
            review_after_days=review_after_days,
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
    ) -> AnalysisReport:
        """Scan all parameters, research the gaps, and assemble an honest report."""
        product_id = product.get("id")
        if product_id is None:
            raise AnalysisUnavailable("product.id is required")

        record = self._evaluation.ensure_composition(int(product_id), composition)
        composition_hash = str(record["composition_hash"])
        blocked = str(record.get("status") or "") != COMPOSITION_ACTIVE

        research: ResearchRunReport | None = None
        plan: ResearchPlan | None = None

        if not blocked:
            service = self._research_service()
            plan = service.plan(
                product=product,
                composition=composition,
                profile=profile,
                now=now,
                source_urls=source_urls,
            )
            blocked = plan.blocked
            if plan.needed and allow_research:
                if self.provider is None:
                    raise AnalysisUnavailable(
                        "провайдер исследования не настроен: анализ недостающих "
                        "параметров невозможен"
                    )
                research = service.research_missing(
                    product=product,
                    composition=composition,
                    profile=profile,
                    process=process,
                    now=now,
                    source_urls=source_urls,
                )
                blocked = research.blocked or blocked

        built = self._evaluation.build(
            product=product,
            composition=composition,
            profile=profile,
            now=now,
            user_id=user_id,
            research_summary=research.summary() if research is not None else None,
            blocked=blocked,
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
    ) -> AnalysisReport:
        """Analyze an existing Aidermy product (catalog + INCI + known sources)."""
        try:
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
        )

