"""LLM provider: extraction only from stored documents, honest failures."""
from __future__ import annotations

import json
import unittest

from app.evaluation.documents import SourceDocument
from app.evaluation.evidence import validate_candidates
from app.evaluation.llm_research import LlmResearchProvider
from app.evaluation.research import RESEARCH_PROVIDER_ERROR, RESEARCH_SOURCE_UNAVAILABLE, ResearchRequest

URL = "https://brand.example/serum"
TEXT = (
    "Formula: Aqua, Glycerin, Niacinamide. Glycerin helps keep the skin hydrated "
    "and supports the skin barrier. Apply twice daily."
)
QUOTE = "Glycerin helps keep the skin hydrated"


def document(text: str = TEXT) -> SourceDocument:
    return SourceDocument(
        url=URL,
        title="Serum",
        text=text,
        retrieved_at="2026-10-01T00:00:00+00:00",
        provenance="fetched",
    )


def request(documents=None) -> ResearchRequest:
    return ResearchRequest(
        product_id=7,
        product_name="Serum",
        composition_hash="a" * 64,
        ingredients=("Aqua", "Glycerin"),
        parameter_id="goal:hydration",
        parameter_label="Цель: увлажнение",
        method_version="research-1.0.0-draft",
        scale_anchors=((0, "нет"), (100, "полностью")),
        parameter_question="Соответствует ли состав задаче увлажнения?",
        parameter_definition="Увлажнение рогового слоя.",
        documents=tuple(documents if documents is not None else [document()]),
    )


def provider_response(**overrides) -> dict:
    payload = {
        "applicability": "applicable",
        "applicability_reason": "",
        "sufficient": True,
        "score": 75,
        "rationale": "Источник подтверждает увлажняющее свойство состава.",
        "limitations": [],
        "contradictions": [],
        "important_unknowns": [],
        "evidence": [
            {
                "url": URL,
                "quote": QUOTE,
                "claim": "Glycerin удерживает влагу",
                "direction": "supports",
                "strength": "moderate",
                "confidence": 0.8,
            }
        ],
    }
    payload.update(overrides)
    return payload


def fake_post(payload: dict, content: str | None = None, usage=(100, 50)):
    def post(_: dict) -> dict:
        return {
            "choices": [{"message": {"content": content or json.dumps(payload)}}],
            "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]},
        }

    return post


class LlmProviderTests(unittest.TestCase):
    def test_without_documents_nothing_is_invented(self):
        outcome = LlmResearchProvider(post=fake_post(provider_response())).research(
            request(documents=[])
        )
        self.assertEqual(outcome.status, RESEARCH_SOURCE_UNAVAILABLE)
        self.assertEqual(outcome.candidates, ())

    def test_without_api_key_the_provider_reports_an_error(self):
        outcome = LlmResearchProvider(api_key="").research(request())
        self.assertEqual(outcome.status, RESEARCH_PROVIDER_ERROR)
        self.assertIn("не настроен", outcome.error)

    def test_candidate_is_bound_to_the_stored_document(self):
        provider = LlmResearchProvider(post=fake_post(provider_response()))
        outcome = provider.research(request())
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(len(outcome.candidates), 1)
        candidate = outcome.candidates[0]
        self.assertEqual(candidate.source.url, URL)
        self.assertEqual(candidate.source.provenance, "fetched")
        self.assertEqual(candidate.source_text, document().text)
        self.assertEqual(outcome.proposal.score, 75)
        self.assertEqual(outcome.proposal.evidence_refs, (0,))
        self.assertEqual((outcome.tokens_in, outcome.tokens_out), (100, 50))

    def test_quote_from_the_document_is_confirmed(self):
        provider = LlmResearchProvider(post=fake_post(provider_response()))
        outcome = provider.research(request())
        evidence = validate_candidates(
            outcome.candidates,
            product_id=7,
            composition_hash="a" * 64,
            parameter_id="goal:hydration",
            documents=request().documents,
        )
        self.assertEqual(evidence[0].verification, "confirmed")
        self.assertEqual(evidence[0].provenance, "fetched")

    def test_hallucinated_quote_is_rejected(self):
        provider = LlmResearchProvider(
            post=fake_post(provider_response(evidence=[{"url": URL, "quote": "Glycerin cures eczema", "claim": "лечит"}]))
        )
        outcome = provider.research(request())
        evidence = validate_candidates(
            outcome.candidates,
            product_id=7,
            composition_hash="a" * 64,
            parameter_id="goal:hydration",
            documents=request().documents,
        )
        self.assertEqual(evidence[0].verification, "rejected")
        self.assertIn("не найдена", evidence[0].rejection_reason)

    def test_source_outside_the_downloaded_set_is_dropped(self):
        provider = LlmResearchProvider(
            post=fake_post(
                provider_response(
                    evidence=[{"url": "https://unknown.example/page", "quote": QUOTE}]
                )
            )
        )
        outcome = provider.research(request())
        self.assertEqual(outcome.status, "insufficient_evidence")
        self.assertIn("вне загруженного набора", " ".join(outcome.proposal.limitations))

    def test_not_json_is_a_provider_error(self):
        provider = LlmResearchProvider(post=fake_post({}, content="не JSON"))
        outcome = provider.research(request())
        self.assertEqual(outcome.status, RESEARCH_PROVIDER_ERROR)
        self.assertIn("не JSON", outcome.error)

    def test_invalid_applicability_is_a_provider_error(self):
        provider = LlmResearchProvider(
            post=fake_post(provider_response(applicability="maybe"))
        )
        outcome = provider.research(request())
        self.assertEqual(outcome.status, RESEARCH_PROVIDER_ERROR)

    def test_disallowed_score_is_not_silently_changed(self):
        provider = LlmResearchProvider(post=fake_post(provider_response(score=60)))
        outcome = provider.research(request())
        self.assertEqual(outcome.proposal.score, 60)  # assess() will reject it

    def test_transport_exception_is_a_provider_error(self):
        def post(_: dict) -> dict:
            raise RuntimeError("timeout")

        outcome = LlmResearchProvider(post=post).research(request())
        self.assertEqual(outcome.status, RESEARCH_PROVIDER_ERROR)
        self.assertIn("timeout", outcome.error)

    def test_usage_is_charged_at_the_configured_price(self):
        provider = LlmResearchProvider(
            post=fake_post(provider_response()), price_per_1k_tokens=0.002
        )
        outcome = provider.research(request())
        self.assertAlmostEqual(outcome.cost_usd, 0.0003, places=6)


if __name__ == "__main__":
    unittest.main()

