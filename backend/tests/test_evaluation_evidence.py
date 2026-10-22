"""Evidence contract and deterministic assessment tests (no network, no AI)."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.evaluation import (
    PARAMETERS,
    EvidenceError,
    Source,
    assess,
    candidate,
    net_score,
    normalize_text,
    validate_candidate,
    value_for_net,
)

COMPOSITION = "a" * 64
PRODUCT_ID = 7
METHOD = "research-1.0.0-draft"
NOW = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)


def make(**overrides):
    base = dict(
        parameter_id="goal:hydration",
        claim="Glycerin удерживает влагу в роговом слое",
        quote="Glycerin helps keep the skin hydrated",
        source_text="Formula: Aqua, Glycerin. Glycerin helps keep the skin hydrated.",
        url="https://brand.example/serum",
    )
    base.update(overrides)
    return candidate(**base)


def confirmed(**overrides):
    item = make(**overrides)
    return validate_candidate(
        item,
        product_id=PRODUCT_ID,
        composition_hash=COMPOSITION,
        parameter_id=item.parameter_id,
        now=NOW,
    )


class EvidenceContractTests(unittest.TestCase):
    def test_valid_candidate_is_confirmed_and_bound(self):
        evidence = confirmed()
        self.assertEqual(evidence.verification, "confirmed")
        self.assertTrue(evidence.usable)
        self.assertEqual(evidence.product_id, PRODUCT_ID)
        self.assertEqual(evidence.composition_hash, COMPOSITION)
        self.assertEqual(evidence.parameter_id, "goal:hydration")
        self.assertEqual(evidence.source.host, "brand.example")

    def test_quote_must_exist_in_source_text(self):
        evidence = confirmed(quote="Glycerin cures eczema completely")
        self.assertEqual(evidence.verification, "rejected")
        self.assertIn("не найдена", evidence.rejection_reason)
        self.assertFalse(evidence.usable)

    def test_missing_quote_is_rejected(self):
        evidence = confirmed(quote="")
        self.assertEqual(evidence.verification, "rejected")
        self.assertIn("цитата отсутствует", evidence.rejection_reason)

    def test_missing_source_text_is_rejected(self):
        evidence = confirmed(source_text="")
        self.assertEqual(evidence.verification, "rejected")
        self.assertIn("источник недоступен", evidence.rejection_reason)

    def test_wrong_parameter_is_rejected(self):
        item = make(parameter_id="skin_type:dry")
        evidence = validate_candidate(
            item,
            product_id=PRODUCT_ID,
            composition_hash=COMPOSITION,
            parameter_id="goal:hydration",
            now=NOW,
        )
        self.assertEqual(evidence.verification, "rejected")
        self.assertIn("не совпадает", evidence.rejection_reason)

    def test_missing_retrieval_date_is_rejected(self):
        evidence = confirmed(retrieved_at="")
        self.assertEqual(evidence.verification, "rejected")
        self.assertIn("дата получения", evidence.rejection_reason)

    def test_future_retrieval_date_is_rejected(self):
        future = (NOW + timedelta(days=1)).isoformat()
        evidence = confirmed(retrieved_at=future)
        self.assertEqual(evidence.verification, "rejected")
        self.assertIn("в будущем", evidence.rejection_reason)

    def test_non_http_source_is_rejected_at_construction(self):
        with self.assertRaises(EvidenceError):
            Source(url="file:///etc/passwd", source_type="official")

    def test_quote_matching_ignores_case_and_punctuation(self):
        evidence = confirmed(
            quote='"GLYCERIN — helps keep the skin hydrated!"',
            source_text="glycerin helps keep the skin hydrated",
        )
        self.assertEqual(evidence.verification, "confirmed")
        self.assertEqual(normalize_text("A,  B!"), "a b")


class AssessmentTests(unittest.TestCase):
    def _evaluate(self, *evidence):
        return assess(
            "goal:hydration",
            list(evidence),
            composition_hash=COMPOSITION,
            method_version=METHOD,
            evaluated_at=NOW.isoformat(),
            evidence_ids=(1, 2),
        )

    def test_no_evidence_means_insufficient_not_zero(self):
        result = self._evaluate()
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIsNone(result.value)
        self.assertTrue(any("Подтверждённых доказательств нет" in t for t in result.limitations))

    def test_neutral_only_is_insufficient_not_harm(self):
        result = self._evaluate(confirmed(direction="neutral"))
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIsNone(result.value)
        self.assertTrue(any("отсутствия эффекта" in t for t in result.limitations))

    def test_strong_support_gives_high_band(self):
        result = self._evaluate(confirmed(strength="strong", confidence=1.0))
        self.assertEqual(result.status, "evaluated")
        self.assertEqual(result.value, 80)

    def test_moderate_support_gives_middle_band(self):
        result = self._evaluate(confirmed(strength="moderate", confidence=1.0))
        self.assertEqual(result.value, 70)

    def test_weak_support_gives_lower_band(self):
        result = self._evaluate(confirmed(strength="weak", confidence=0.8))
        self.assertEqual(result.value, 60)

    def test_strong_contradiction_gives_low_band(self):
        result = self._evaluate(
            confirmed(direction="contradicts", strength="strong", confidence=1.0)
        )
        self.assertEqual(result.value, 20)

    def test_balanced_evidence_is_contradictory_not_midpoint(self):
        # A midpoint would hide the contradiction and pretend the value is known.
        result = self._evaluate(
            confirmed(direction="supports", strength="strong", confidence=1.0),
            confirmed(direction="contradicts", strength="strong", confidence=1.0),
        )
        self.assertEqual(result.status, "contradictory_evidence")
        self.assertIsNone(result.value)
        self.assertTrue(any("сопоставимы" in t for t in result.limitations))
        self.assertIn("противоречат", result.rationale)

    def test_explanation_answers_the_parameter_question(self):
        result = self._evaluate(confirmed(strength="strong", confidence=1.0))
        parameter = PARAMETERS["goal:hydration"]
        self.assertIn(parameter.label, result.rationale)
        self.assertIn(parameter.question, result.rationale)
        self.assertIn("Оценка 80/100", result.rationale)
        # Only confirmed claim + quote, never the model's rejected text.
        self.assertIn("Glycerin удерживает влагу", result.rationale)
        self.assertIn("brand.example", result.rationale)
        self.assertNotIn("https://", result.rationale)

    def test_explanation_has_no_unsupported_medical_claims(self):
        result = self._evaluate(confirmed(strength="strong", confidence=1.0))
        generated = result.rationale.replace(confirmed().claim, "")
        for forbidden in ("лечит", "гарантирует", "безопасен", "вреден", "излечивает"):
            self.assertNotIn(forbidden, generated.lower())
        self.assertIn("не клиническую пригодность", " ".join(result.limitations))

    def test_explanation_distinguishes_absence_from_harm(self):
        absent = self._evaluate()
        harmful = self._evaluate(
            confirmed(direction="contradicts", strength="strong", confidence=1.0)
        )
        self.assertIsNone(absent.value)
        self.assertEqual(absent.status, "insufficient_evidence")
        self.assertIn("не является доказательством вреда", " ".join(absent.limitations))
        self.assertEqual(harmful.value, 20)
        self.assertIn("против требования", harmful.rationale.lower())

    def test_confidence_changes_weight_not_direction(self):
        low = net_score([confirmed(direction="supports", strength="strong", confidence=0.2)])
        high = net_score([confirmed(direction="supports", strength="strong", confidence=1.0)])
        self.assertLess(low, high)
        self.assertEqual(value_for_net(high), 80)

    def test_rationale_uses_only_confirmed_claims(self):
        good = confirmed(claim="Глицерин удерживает влагу")
        bad = confirmed(
            claim="Продукт лечит экзему",
            quote="cures eczema",
            source_text="Formula: Aqua, Glycerin.",
        )
        result = self._evaluate(good, bad)
        self.assertIn("Глицерин удерживает влагу", result.rationale)
        self.assertNotIn("лечит экзему", result.rationale)
        self.assertTrue(any("Отклонено кандидатов" in t for t in result.limitations))

    def test_evidence_ids_are_attached(self):
        result = self._evaluate(confirmed())
        self.assertEqual(result.evidence_ids, ("1", "2"))

    def test_rejected_evidence_alone_gives_no_value(self):
        result = self._evaluate(confirmed(quote="cures eczema"))
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIsNone(result.value)


if __name__ == "__main__":
    unittest.main()
