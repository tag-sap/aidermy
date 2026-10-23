"""Typed evidence contract.

An LLM answer is NOT evidence. A candidate becomes evidence only when:

  * it is bound to the requested product composition and parameter;
  * it carries a verbatim quote that actually occurs in the source text;
  * the source is a resolvable http(s) URL with a retrieval timestamp;
  * direction, strength and confidence stay inside the declared enums.

Anything else is stored as ``rejected`` with a reason and can never move a score.
Absence of benefit evidence is NOT evidence of harm: it yields
``insufficient_evidence``, never a low value.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlparse

DIRECTIONS = ("supports", "contradicts", "neutral")
STRENGTHS = ("weak", "moderate", "strong")
SOURCE_TYPES = ("official", "regulator", "peer_reviewed", "database", "retailer", "unknown")
VERIFICATIONS = ("confirmed", "unverified", "rejected")
# How the source text reached the provider. ``synthetic`` is test-only data,
# ``unknown`` means the provider did not declare it. Only ``fetched`` may back a
# production score (see assessment.assess).
PROVENANCES = ("fetched", "synthetic", "unknown")

MIN_QUOTE_CHARS = 8
_NORMALIZE_RE = re.compile(r"[^\w\s]+", re.UNICODE)


class EvidenceError(ValueError):
    """Raised when a candidate cannot even be represented as evidence."""


def normalize_text(value: str) -> str:
    """Case/whitespace/punctuation-insensitive form used for quote matching."""
    cleaned = _NORMALIZE_RE.sub(" ", str(value or ""))
    return " ".join(cleaned.casefold().split())


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@dataclass(frozen=True)
class Source:
    url: str
    title: str = ""
    publisher: str = ""
    source_type: str = "unknown"
    retrieved_at: str = ""
    content_hash: str = ""
    # ``fetched`` — provider declares it downloaded the page; ``synthetic`` —
    # test fixture; ``unknown`` — not declared. Validation cannot verify the claim.
    provenance: str = "unknown"

    def __post_init__(self) -> None:
        parsed = urlparse(str(self.url or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise EvidenceError(f"source url must be http(s): {self.url!r}")
        if self.source_type not in SOURCE_TYPES:
            raise EvidenceError(f"unknown source_type: {self.source_type}")
        if self.provenance not in PROVENANCES:
            raise EvidenceError(f"unknown provenance: {self.provenance}")

    @property
    def host(self) -> str:
        return urlparse(self.url).netloc.lower()


@dataclass(frozen=True)
class EvidenceCandidate:
    """Raw provider output. It is a claim about a source, not yet a fact."""

    parameter_id: str
    claim: str
    quote: str
    source: Source
    source_text: str = ""
    direction: str = "supports"
    strength: str = "moderate"
    confidence: float = 0.0
    extraction_method: str = "unspecified"

    def __post_init__(self) -> None:
        if self.direction not in DIRECTIONS:
            raise EvidenceError(f"unknown direction: {self.direction}")
        if self.strength not in STRENGTHS:
            raise EvidenceError(f"unknown strength: {self.strength}")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise EvidenceError(f"confidence out of 0..1: {self.confidence}")
        if not str(self.claim).strip():
            raise EvidenceError("claim must not be empty")


@dataclass(frozen=True)
class Evidence:
    """Validated evidence bound to one product composition and parameter."""

    parameter_id: str
    claim: str
    quote: str
    direction: str
    strength: str
    confidence: float
    source: Source
    verification: str
    product_id: int
    composition_hash: str
    extraction_method: str
    retrieved_at: str
    rejection_reason: str = ""
    provenance: str = "unknown"

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCES:
            raise EvidenceError(f"unknown provenance: {self.provenance}")

    @property
    def usable(self) -> bool:
        return self.verification == "confirmed"

    @property
    def fetched(self) -> bool:
        """True only when the provider explicitly declared a page download."""
        return self.provenance == "fetched"

    def as_dict(self) -> dict:
        return {
            "parameter_id": self.parameter_id,
            "claim": self.claim,
            "quote": self.quote,
            "direction": self.direction,
            "strength": self.strength,
            "confidence": self.confidence,
            "source": {
                "url": self.source.url,
                "title": self.source.title,
                "publisher": self.source.publisher,
                "source_type": self.source.source_type,
                "retrieved_at": self.source.retrieved_at,
                "content_hash": self.source.content_hash,
                "provenance": self.source.provenance,
            },
            "verification": self.verification,
            "product_id": self.product_id,
            "composition_hash": self.composition_hash,
            "extraction_method": self.extraction_method,
            "retrieved_at": self.retrieved_at,
            "rejection_reason": self.rejection_reason,
            "provenance": self.provenance,
        }


def _reject(
    candidate: EvidenceCandidate,
    *,
    product_id: int,
    composition_hash: str,
    reason: str,
) -> Evidence:
    return Evidence(
        parameter_id=candidate.parameter_id,
        claim=candidate.claim,
        quote=candidate.quote,
        direction=candidate.direction,
        strength=candidate.strength,
        confidence=candidate.confidence,
        source=candidate.source,
        verification="rejected",
        product_id=product_id,
        composition_hash=composition_hash,
        extraction_method=candidate.extraction_method,
        retrieved_at=candidate.source.retrieved_at,
        rejection_reason=reason,
        provenance=candidate.source.provenance,
    )


def validate_candidate(
    candidate: EvidenceCandidate,
    *,
    product_id: int,
    composition_hash: str,
    parameter_id: str,
    now: datetime | None = None,
) -> Evidence:
    """Validate one candidate against the request it belongs to.

    Returns ``Evidence`` with verification ``confirmed`` or ``rejected``; the
    latter is kept for audit but never used for scoring.
    """
    if candidate.parameter_id != parameter_id:
        return _reject(
            candidate,
            product_id=product_id,
            composition_hash=composition_hash,
            reason=f"параметр {candidate.parameter_id!r} не совпадает с запросом {parameter_id!r}",
        )
    if not str(candidate.quote).strip():
        return _reject(candidate, product_id=product_id, composition_hash=composition_hash,
                       reason="цитата отсутствует")
    if len(normalize_text(candidate.quote)) < MIN_QUOTE_CHARS:
        return _reject(candidate, product_id=product_id, composition_hash=composition_hash,
                       reason="цитата слишком короткая для проверки")
    if not str(candidate.source_text).strip():
        return _reject(
            candidate,
            product_id=product_id,
            composition_hash=composition_hash,
            reason="источник недоступен: нет текста для проверки цитаты",
        )
    if normalize_text(candidate.quote) not in normalize_text(candidate.source_text):
        return _reject(
            candidate,
            product_id=product_id,
            composition_hash=composition_hash,
            reason="цитата не найдена в тексте источника",
        )
    retrieved = parse_timestamp(candidate.source.retrieved_at)
    if retrieved is None:
        return _reject(candidate, product_id=product_id, composition_hash=composition_hash,
                       reason="не указана или некорректна дата получения источника")
    current = now or datetime.now(timezone.utc)
    if retrieved > current:
        return _reject(candidate, product_id=product_id, composition_hash=composition_hash,
                       reason="дата получения источника в будущем")

    return Evidence(
        parameter_id=candidate.parameter_id,
        claim=str(candidate.claim).strip(),
        quote=str(candidate.quote).strip(),
        direction=candidate.direction,
        strength=candidate.strength,
        confidence=float(candidate.confidence),
        source=candidate.source,
        verification="confirmed",
        product_id=product_id,
        composition_hash=composition_hash,
        extraction_method=candidate.extraction_method,
        retrieved_at=candidate.source.retrieved_at,
        provenance=candidate.source.provenance,
    )


def validate_candidates(
    candidates: Iterable[EvidenceCandidate],
    *,
    product_id: int,
    composition_hash: str,
    parameter_id: str,
    now: datetime | None = None,
) -> list[Evidence]:
    return [
        validate_candidate(
            candidate,
            product_id=product_id,
            composition_hash=composition_hash,
            parameter_id=parameter_id,
            now=now,
        )
        for candidate in candidates
    ]
