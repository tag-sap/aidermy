"""Research provider contract and a deterministic fake for tests.

The provider is the ONLY component allowed to talk to the outside world (search,
fetch, LLM). It returns *candidates* — claims plus quotes plus source text —
never scores. Validation and scoring happen downstream and are deterministic.

No real network calls happen in this module: ``FakeResearchProvider`` is used by
all tests, so the suite never spends money.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Protocol

from .evidence import EvidenceCandidate, EvidenceError, Source

RESEARCH_OK = "ok"
RESEARCH_INSUFFICIENT = "insufficient_evidence"
RESEARCH_SOURCE_UNAVAILABLE = "source_unavailable"
RESEARCH_PROVIDER_ERROR = "provider_error"
RESEARCH_STATUSES = (
    RESEARCH_OK,
    RESEARCH_INSUFFICIENT,
    RESEARCH_SOURCE_UNAVAILABLE,
    RESEARCH_PROVIDER_ERROR,
)


@dataclass(frozen=True)
class ResearchRequest:
    product_id: int
    product_name: str
    composition_hash: str
    ingredients: tuple[str, ...]
    parameter_id: str
    parameter_label: str
    method_version: str
    scale_anchors: tuple[tuple[int, str], ...] = ()

    def as_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "composition_hash": self.composition_hash,
            "ingredients": list(self.ingredients),
            "parameter_id": self.parameter_id,
            "parameter_label": self.parameter_label,
            "method_version": self.method_version,
        }


@dataclass(frozen=True)
class ResearchOutcome:
    status: str
    candidates: tuple[EvidenceCandidate, ...] = ()
    error: str = ""
    provider: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.status not in RESEARCH_STATUSES:
            raise EvidenceError(f"unknown research status: {self.status}")
        if self.cost_usd < 0:
            raise EvidenceError("cost_usd must not be negative")
        if self.status == RESEARCH_OK and not self.candidates:
            raise EvidenceError("status=ok requires at least one candidate")


class ResearchProvider(Protocol):
    name: str

    def research(self, request: ResearchRequest) -> ResearchOutcome: ...


Response = ResearchOutcome | Callable[[ResearchRequest], ResearchOutcome]


class FakeResearchProvider:
    """Deterministic provider for tests: no network, no cost, full call log."""

    name = "fake"

    def __init__(
        self,
        responses: Mapping[object, Response] | None = None,
        *,
        default: Response | None = None,
    ) -> None:
        self._responses: dict = dict(responses or {})
        self._default = default
        self.calls: list[ResearchRequest] = []
        self.total_cost = 0.0

    def set_response(self, key: object, response: Response) -> None:
        self._responses[key] = response

    def call_count(self, parameter_id: str | None = None) -> int:
        if parameter_id is None:
            return len(self.calls)
        return sum(1 for call in self.calls if call.parameter_id == parameter_id)

    def research(self, request: ResearchRequest) -> ResearchOutcome:
        self.calls.append(request)
        response = self._lookup(request)
        if response is None:
            outcome = ResearchOutcome(status=RESEARCH_INSUFFICIENT, provider=self.name)
        elif callable(response):
            outcome = response(request)
        else:
            outcome = response
        self.total_cost += float(outcome.cost_usd)
        return outcome

    def _lookup(self, request: ResearchRequest) -> Response | None:
        keys = (
            (request.product_id, request.composition_hash, request.parameter_id),
            (request.composition_hash, request.parameter_id),
            request.parameter_id,
        )
        for key in keys:
            if key in self._responses:
                return self._responses[key]
        return self._default


def candidate(
    *,
    parameter_id: str,
    claim: str,
    quote: str,
    url: str = "https://example.org/product",
    source_text: str | None = None,
    retrieved_at: str = "2026-10-01T00:00:00+00:00",
    direction: str = "supports",
    strength: str = "moderate",
    confidence: float = 0.8,
    source_type: str = "official",
    title: str = "Product page",
    extraction_method: str = "quote_extraction_v1",
) -> EvidenceCandidate:
    """Convenience builder for tests (source text defaults to the quote itself)."""
    return EvidenceCandidate(
        parameter_id=parameter_id,
        claim=claim,
        quote=quote,
        source=Source(
            url=url,
            title=title,
            source_type=source_type,
            retrieved_at=retrieved_at,
        ),
        source_text=quote if source_text is None else source_text,
        direction=direction,
        strength=strength,
        confidence=confidence,
        extraction_method=extraction_method,
    )


def ok(
    *candidates: EvidenceCandidate,
    cost_usd: float = 0.0,
    tokens: tuple[int, int] = (0, 0),
) -> ResearchOutcome:
    return ResearchOutcome(
        status=RESEARCH_OK,
        candidates=tuple(candidates),
        provider="fake",
        tokens_in=tokens[0],
        tokens_out=tokens[1],
        cost_usd=cost_usd,
    )


def insufficient(reason: str = "источники не найдены") -> ResearchOutcome:
    return ResearchOutcome(status=RESEARCH_INSUFFICIENT, error=reason, provider="fake")


def provider_error(reason: str = "provider timeout") -> ResearchOutcome:
    return ResearchOutcome(status=RESEARCH_PROVIDER_ERROR, error=reason, provider="fake")


def source_unavailable(reason: str = "источник недоступен") -> ResearchOutcome:
    return ResearchOutcome(status=RESEARCH_SOURCE_UNAVAILABLE, error=reason, provider="fake")
