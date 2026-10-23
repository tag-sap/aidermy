"""Evidence contract and deterministic assessment tests (no network, no AI)."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.evaluation import (
    APPLICABLE,
    NOT_APPLICABLE,
    PARAMETERS,
    AssessmentProposal,
    ContractError,
    EvidenceError,
    Source,
    assess,
    candidate,
    normalize_text,
    validate_candidate,
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
    """The model chooses the score; the deterministic layer validates it."""

    def proposal(self, **overrides) -> AssessmentProposal:
        defaults = dict(
            parameter_id="goal:hydration",
            applicability=APPLICABLE,
            sufficient=True,
            score=75,
            rationale=(
                "Подтверждённые источники описывают влагоудерживающие компоненты, "
                "соответствующие требованию пункта."
            ),
            evidence_refs=(0,),
        )
        defaults.update(overrides)
        return AssessmentProposal(**defaults)

    def evaluate(self, *evidence, proposal=None, parameter="goal:hydration", ids=None):
        items = list(evidence)
        evidence_ids = list(ids) if ids is not None else [
            str(index + 1) for index in range(len(items))
        ]
        return assess(
            parameter,
            self.proposal() if proposal is None else proposal,
            items,
            composition_hash=COMPOSITION,
            method_version=METHOD,
            evaluated_at=NOW.isoformat(),
            evidence_ids=evidence_ids,
            # Tests use synthetic candidates by default; production cannot.
            allow_synthetic_evidence=True,
        )

    def test_each_allowed_score_is_accepted(self):
        evidence = confirmed(strength="strong", confidence=1.0)
        for score in (0, 25, 50, 75, 100):
            result = self.evaluate(evidence, proposal=self.proposal(score=score))
            self.assertEqual(result.status, "assessed", score)
            self.assertEqual(result.value, score)
            self.assertTrue(result.evidence_ids)
            self.assertIn(f"Оценка {score}/100", result.rationale)

    def test_scores_outside_the_five_levels_are_rejected(self):
        evidence = confirmed()
        for score in (1, 30, 62, 101, -25):
            with self.assertRaises(ContractError, msg=f"score {score}"):
                self.evaluate(evidence, proposal=self.proposal(score=score))

    def test_assessed_without_explanation_is_rejected(self):
        evidence = confirmed()
        with self.assertRaises(ContractError):
            self.evaluate(evidence, proposal=self.proposal(rationale=""))
        with self.assertRaises(ContractError):
            self.evaluate(evidence, proposal=self.proposal(rationale="ок"))

    def test_assessed_without_evidence_reference_is_rejected(self):
        with self.assertRaises(ContractError):
            self.evaluate(confirmed(), proposal=self.proposal(evidence_refs=()))

    def test_reference_to_rejected_evidence_is_rejected(self):
        rejected = confirmed(quote="cures eczema completely")  # quote not in source
        self.assertFalse(rejected.usable)
        with self.assertRaises(ContractError):
            self.evaluate(rejected, proposal=self.proposal())

    def test_reference_out_of_range_is_rejected(self):
        with self.assertRaises(ContractError):
            self.evaluate(confirmed(), proposal=self.proposal(evidence_refs=(5,)))

    def test_parameter_mismatch_is_rejected(self):
        with self.assertRaises(ContractError):
            self.evaluate(
                confirmed(), proposal=self.proposal(parameter_id="problem:dryness")
            )

    def test_unknown_applicability_is_rejected(self):
        with self.assertRaises(ContractError):
            self.evaluate(confirmed(), proposal=self.proposal(applicability="maybe"))

    def test_score_requires_sufficient_decision(self):
        with self.assertRaises(ContractError):
            self.evaluate(confirmed(), proposal=self.proposal(sufficient=False))
        with self.assertRaises(ContractError):
            self.evaluate(confirmed(), proposal=self.proposal(sufficient=True, score=None))



    def test_insufficient_has_no_score_and_no_harm_conclusion(self):
        result = self.evaluate(
            confirmed(direction="neutral"),
            proposal=self.proposal(
                sufficient=False,
                score=None,
                rationale="Источники не описывают эффект по этому пункту.",
            ),
        )
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIsNone(result.value)
        self.assertTrue(
            any("не является доказательством вреда" in text for text in result.limitations)
        )

    def test_not_applicable_requires_reason_and_confirmed_source(self):
        grounded = self.evaluate(
            confirmed(),
            proposal=self.proposal(
                applicability=NOT_APPLICABLE,
                sufficient=False,
                score=None,
                applicability_reason="Продукт смывается и не остаётся на коже.",
            ),
        )
        self.assertEqual(grounded.status, "not_applicable")
        self.assertIsNone(grounded.value)

        ungrounded = self.evaluate(
            proposal=self.proposal(
                applicability=NOT_APPLICABLE,
                sufficient=False,
                score=None,
                applicability_reason="Информации о параметре не нашлось.",
                evidence_refs=(),
            )
        )
        self.assertEqual(ungrounded.status, "insufficient_evidence")
        self.assertIsNone(ungrounded.value)
        self.assertTrue(
            any("нельзя обосновать отсутствием данных" in text
                for text in ungrounded.limitations)
        )

    def test_not_applicable_is_allowed_for_safety_sections_with_a_source(self):
        # There is no category-level ban: the decision is checked per parameter.
        for section in ("therapy:tretinoin", "procedure:recent_laser@<7"):
            evidence = confirmed(parameter_id=section)
            result = assess(
                section,
                self.proposal(
                    parameter_id=section,
                    applicability=NOT_APPLICABLE,
                    sufficient=False,
                    score=None,
                    applicability_reason="Продукт не наносится на обрабатываемую зону.",
                ),
                [evidence],
                composition_hash=COMPOSITION,
                method_version=METHOD,
                evaluated_at=NOW.isoformat(),
                evidence_ids=["1"],
                allow_synthetic_evidence=True,
            )
            self.assertEqual(result.status, "not_applicable", section)
            self.assertIsNone(result.value)

    def test_not_applicable_for_safety_section_without_a_source_is_insufficient(self):
        result = assess(
            "therapy:tretinoin",
            self.proposal(
                parameter_id="therapy:tretinoin",
                applicability=NOT_APPLICABLE,
                sufficient=False,
                score=None,
                applicability_reason="Не нашли информации о совместимости.",
                evidence_refs=(),
            ),
            [],
            composition_hash=COMPOSITION,
            method_version=METHOD,
            evaluated_at=NOW.isoformat(),
            allow_synthetic_evidence=True,
        )
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIsNone(result.value)
        self.assertTrue(
            any("отсутствием данных" in text for text in result.limitations)
        )

    def test_provider_without_sources_is_insufficient_not_not_applicable(self):
        result = assess(
            "goal:hydration",
            None,
            [],
            composition_hash=COMPOSITION,
            method_version=METHOD,
            evaluated_at=NOW.isoformat(),
        )
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIsNone(result.value)
        self.assertIn("балл не выставляется", result.rationale)

    def test_treatment_claim_in_reasoning_is_rejected(self):
        with self.assertRaises(ContractError):
            self.evaluate(
                confirmed(),
                proposal=self.proposal(
                    rationale="Средство лечит сухость и гарантирует результат."
                ),
            )

    def test_treatment_claim_in_evidence_claim_is_rejected(self):
        claim = confirmed(claim="Продукт лечит экзему")
        with self.assertRaises(ContractError):
            self.evaluate(claim, proposal=self.proposal())

    def test_explanation_answers_the_parameter_question(self):
        result = self.evaluate(confirmed(claim="Глицерин удерживает влагу"))
        parameter = PARAMETERS["goal:hydration"]
        self.assertIn(parameter.label, result.rationale)
        self.assertIn(parameter.question, result.rationale)
        self.assertIn("Оценка 75/100", result.rationale)
        self.assertIn("Глицерин удерживает влагу", result.rationale)
        self.assertIn("brand.example", result.rationale)
        self.assertNotIn("https://", result.rationale)

    def test_score_is_not_derived_from_quote_count(self):
        one = self.evaluate(
            confirmed(), proposal=self.proposal(score=100, evidence_refs=(0,))
        )
        many = self.evaluate(
            confirmed(), confirmed(), confirmed(),
            proposal=self.proposal(score=25, evidence_refs=(0, 1, 2)),
        )
        self.assertEqual(one.value, 100)
        self.assertEqual(many.value, 25)

    def test_evidence_ids_referenced_by_the_assessment_are_stored(self):
        result = self.evaluate(
            confirmed(), confirmed(),
            proposal=self.proposal(evidence_refs=(1,)),
            ids=["11", "22"],
        )
        self.assertEqual(result.evidence_ids, ("22",))


class ProvenanceTests(unittest.TestCase):
    """Only evidence declared as fetched may back a score or an exclusion."""

    def _assess(self, evidence, proposal, **kwargs):
        return assess(
            "goal:hydration",
            proposal,
            [evidence],
            composition_hash=COMPOSITION,
            method_version=METHOD,
            evaluated_at=NOW.isoformat(),
            evidence_ids=["1"],
            **kwargs,
        )

    def proposal(self, **overrides) -> AssessmentProposal:
        defaults = dict(
            parameter_id="goal:hydration",
            applicability=APPLICABLE,
            sufficient=True,
            score=75,
            rationale=(
                "Подтверждённые источники описывают свойство, соответствующее "
                "требованию пункта."
            ),
            evidence_refs=(0,),
        )
        defaults.update(overrides)
        return AssessmentProposal(**defaults)

    def test_synthetic_evidence_cannot_back_a_score_by_default(self):
        result = self._assess(confirmed(), self.proposal())
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIsNone(result.value)
        self.assertTrue(
            any("provenance=synthetic" in text for text in result.limitations)
        )

    def test_unknown_provenance_cannot_back_a_score_by_default(self):
        evidence = confirmed(provenance="unknown")
        result = self._assess(evidence, self.proposal())
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIsNone(result.value)

    def test_fetched_evidence_can_back_a_score(self):
        evidence = confirmed(provenance="fetched")
        result = self._assess(evidence, self.proposal())
        self.assertEqual(result.status, "assessed")
        self.assertEqual(result.value, 75)
        self.assertTrue(
            any("загрузка страницы системой не выполнялась" in text
                for text in result.limitations)
        )

    def test_synthetic_evidence_cannot_back_not_applicable(self):
        result = self._assess(
            confirmed(),
            self.proposal(
                applicability=NOT_APPLICABLE,
                sufficient=False,
                score=None,
                applicability_reason="Продукт смывается.",
            ),
        )
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIsNone(result.value)

    def test_explicit_test_opt_in_allows_synthetic_evidence(self):
        result = self._assess(
            confirmed(), self.proposal(), allow_synthetic_evidence=True
        )
        self.assertEqual(result.status, "assessed")
        self.assertEqual(result.value, 75)

    def test_unknown_provenance_value_is_rejected(self):
        from app.evaluation.evidence import Evidence, EvidenceError

        with self.assertRaises(EvidenceError):
            confirmed(provenance="guessed")
        with self.assertRaises(EvidenceError):
            Evidence(
                parameter_id="goal:hydration",
                claim="claim",
                quote="quote",
                direction="supports",
                strength="moderate",
                confidence=0.5,
                source=confirmed().source,
                verification="confirmed",
                product_id=PRODUCT_ID,
                composition_hash=COMPOSITION,
                extraction_method="quote_extraction_v1",
                retrieved_at=NOW.isoformat(),
                provenance="guessed",
            )

    def test_fetched_property_reflects_declared_provenance(self):
        self.assertTrue(confirmed(provenance="fetched").fetched)
        self.assertFalse(confirmed().fetched)
        self.assertFalse(confirmed(provenance="unknown").fetched)


if __name__ == "__main__":
    unittest.main()
