"""INCI-based checks for intolerance parameters and per-parameter applicability.

No network: compositions and evidence are fixtures. Fetched provenance is used
where a score is expected, because production scores require it.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.evaluation import (
    APPLICABLE,
    NOT_APPLICABLE,
    PARAMETERS,
    AssessmentProposal,
    ContractError,
    assess,
    candidate,
    validate_candidate,
)
from app.evaluation.assessment import as_parameter
from app.evaluation.inci import (
    NOT_LISTED,
    PRESENT,
    UNVERIFIABLE,
    check_intolerance,
    normalize_inci_name,
    split_inci,
)
from app.evaluation.parameters import ingredient_parameter

HASH = "a" * 64
NOW = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)
FRAGRANCE = "intolerance:fragrance_intolerance"
NIACINAMIDE = "intolerance:niacinamide_intolerance"
ESSENTIAL_OILS = "intolerance:essential_oil_intolerance"
ALCOHOL = "intolerance:alcohol_intolerance"
THERAPY = "therapy:tretinoin"
PROCEDURE = "procedure:recent_laser@<7"


def composition(inci: str, *, status: str = "active") -> dict:
    return {"composition_hash": HASH, "status": status, "inci_raw": inci}


ACTIVE = composition("Aqua, Glycerin, Parfum, Limonene")
CLEAN = composition("Aqua, Glycerin, Niacinamide")
UNVERIFIED = composition("Aqua, Glycerin, Parfum", status="unverified")
EMPTY = composition("")
TRUNCATED = composition("Aqua, Glycerin, ...")
SINGLE = composition("Aqua")


def fetched_evidence(parameter_id: str):
    return validate_candidate(
        candidate(
            parameter_id=parameter_id,
            claim="Источник описывает состав и свойства продукта",
            quote="Full ingredients and product description are provided",
            source_text="Full ingredients and product description are provided",
            provenance="fetched",
            confidence=1.0,
        ),
        product_id=7,
        composition_hash=HASH,
        parameter_id=parameter_id,
        now=NOW,
    )


class InciCheckTests(unittest.TestCase):
    def check(self, parameter_id, comp):
        return check_intolerance(as_parameter(parameter_id), comp)

    def test_present_ingredient_is_detected(self):
        result = self.check(FRAGRANCE, ACTIVE)
        self.assertEqual(result.status, PRESENT)
        self.assertEqual(result.matched, ("parfum",))
        self.assertTrue(result.verified)
        self.assertEqual(result.composition_hash, HASH)

    def test_parenthetical_synonym_is_normalised(self):
        result = self.check(FRAGRANCE, composition("Aqua, Parfum (Fragrance)"))
        self.assertEqual(result.status, PRESENT)
        self.assertEqual(normalize_inci_name("Parfum (Fragrance)"), "parfum")

    def test_fatty_alcohol_is_not_drying_alcohol(self):
        result = self.check(ALCOHOL, composition("Aqua, Cetyl Alcohol, Stearyl Alcohol"))
        self.assertEqual(result.status, NOT_LISTED)
        self.assertEqual(result.matched, ())

    def test_ethanol_is_detected(self):
        result = self.check(ALCOHOL, composition("Aqua, Alcohol Denat., Glycerin"))
        self.assertEqual(result.status, PRESENT)

    def test_unverified_composition_is_unverifiable(self):
        result = self.check(FRAGRANCE, UNVERIFIED)
        self.assertEqual(result.status, UNVERIFIABLE)
        self.assertIn("не подтверждён", result.reason)

    def test_empty_inci_is_unverifiable(self):
        result = self.check(FRAGRANCE, EMPTY)
        self.assertEqual(result.status, UNVERIFIABLE)
        self.assertIn("INCI пуст", result.reason)

    def test_truncated_inci_is_unverifiable(self):
        result = self.check(FRAGRANCE, TRUNCATED)
        self.assertEqual(result.status, UNVERIFIABLE)
        self.assertIn("неполным", result.reason)

    def test_single_token_is_unverifiable(self):
        result = self.check(FRAGRANCE, SINGLE)
        self.assertEqual(result.status, UNVERIFIABLE)

    def test_closed_category_absence_is_not_listed(self):
        result = self.check(FRAGRANCE, CLEAN)
        self.assertEqual(result.status, NOT_LISTED)
        self.assertIn("может быть неполным", result.reason)

    def test_open_category_absence_is_unverifiable(self):
        result = self.check(ESSENTIAL_OILS, CLEAN)
        self.assertEqual(result.status, UNVERIFIABLE)
        self.assertIn("словарь категории неполон", result.reason)

    def test_unknown_category_is_unverifiable(self):
        from app.evaluation.contracts import Parameter

        parameter = Parameter(
            id="intolerance:mystery_intolerance",
            label="Непереносимость: «Загадка»",
            definition="проверка",
            anchors=((0, "нет"), (100, "да")),
            section="intolerance",
            option_id="mystery_intolerance",
            direction="risk",
        )
        result = check_intolerance(parameter, ACTIVE)
        self.assertEqual(result.status, UNVERIFIABLE)
        self.assertIn("нет проверяемого словаря", result.reason)

    def test_specific_ingredient_is_matched_exactly(self):
        present = check_intolerance(ingredient_parameter("Niacinamide"), CLEAN)
        absent = check_intolerance(
            ingredient_parameter("Niacinamide"), composition("Aqua, Glycerin")
        )
        self.assertEqual(present.status, PRESENT)
        self.assertEqual(absent.status, NOT_LISTED)

    def test_cyrillic_ingredient_name_is_unverifiable(self):
        result = check_intolerance(
            ingredient_parameter("Ниацинамид"), CLEAN
        )
        self.assertEqual(result.status, UNVERIFIABLE)
        self.assertIn("нет словаря", result.reason)

    def test_non_intolerance_parameter_is_skipped(self):
        self.assertIsNone(self.check(THERAPY, ACTIVE))

    def test_split_inci_keeps_parenthetical_groups(self):
        self.assertEqual(
            split_inci("Aqua (Water, Eau), Glycerin"),
            ["Aqua (Water, Eau)", "Glycerin"],
        )


def run_assess(
    parameter: object,
    *,
    comp: dict | None = None,
    score: int | None = 75,
    applicability: str = APPLICABLE,
    sufficient: bool | None = None,
    reason: str = "",
    with_evidence: bool = True,
    allow_synthetic: bool = False,
):
    parameter_id = parameter.id if hasattr(parameter, "id") else str(parameter)
    items = [fetched_evidence(parameter_id)] if with_evidence else []
    ids = ["1"] if with_evidence else []
    if sufficient is None:
        sufficient = score is not None
    proposal = AssessmentProposal(
        parameter_id=parameter_id,
        applicability=applicability,
        applicability_reason=reason,
        sufficient=sufficient,
        score=score,
        rationale=(
            "Источник описывает состав и применимость продукта к требованию пункта."
        ),
        evidence_refs=(0,) if with_evidence else (),
    )
    return assess(
        parameter if hasattr(parameter, "id") else as_parameter(parameter),
        proposal,
        items,
        composition_hash=HASH,
        method_version="m",
        evaluated_at=NOW.isoformat(),
        evidence_ids=ids,
        composition=comp,
        allow_synthetic_evidence=allow_synthetic,
    )


class IntoleranceAssessmentTests(unittest.TestCase):
    def test_unverifiable_composition_never_scores(self):
        for comp in (UNVERIFIED, EMPTY, TRUNCATED):
            result = run_assess(FRAGRANCE, comp=comp, score=100)
            self.assertEqual(result.status, "insufficient_evidence", comp)
            self.assertIsNone(result.value)
            self.assertTrue(
                any("INCI:" in text for text in result.limitations), result.limitations
            )

    def test_present_ingredient_rejects_score_100(self):
        with self.assertRaises(ContractError):
            run_assess(FRAGRANCE, comp=ACTIVE, score=100)

    def test_present_ingredient_rejects_not_applicable(self):
        result = run_assess(
            FRAGRANCE,
            comp=ACTIVE,
            score=None,
            applicability=NOT_APPLICABLE,
            reason="Продукт для волос.",
        )
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIsNone(result.value)
        self.assertTrue(
            any("Неприменимость не принимается" in text for text in result.limitations)
        )

    def test_absent_in_closed_category_allows_assessment(self):
        result = run_assess(FRAGRANCE, comp=CLEAN, score=100)
        self.assertEqual(result.status, "assessed")
        self.assertEqual(result.value, 100)
        self.assertTrue(
            any("может быть неполным" in text for text in result.limitations)
        )

    def test_absent_in_open_category_is_insufficient(self):
        result = run_assess(ESSENTIAL_OILS, comp=CLEAN, score=100)
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIsNone(result.value)

    def test_specific_ingredient_absent_allows_assessment(self):
        result = run_assess(
            ingredient_parameter("Niacinamide"),
            comp=composition("Aqua, Glycerin"),
            score=100,
        )
        self.assertEqual(result.status, "assessed")
        self.assertEqual(result.value, 100)

    def test_specific_ingredient_present_rejects_score_100(self):
        with self.assertRaises(ContractError):
            run_assess(ingredient_parameter("Niacinamide"), comp=CLEAN, score=100)

    def test_present_ingredient_still_allows_a_lower_justified_score(self):
        # Presence forbids "fully meets", not a reasoned lower level.
        result = run_assess(FRAGRANCE, comp=ACTIVE, score=25)
        self.assertEqual(result.status, "assessed")
        self.assertEqual(result.value, 25)

    def test_not_applicable_and_insufficient_have_different_reasons(self):
        excluded = run_assess(
            THERAPY,
            comp=None,
            score=None,
            applicability=NOT_APPLICABLE,
            reason="Продукт не наносится на зону лечения.",
        )
        insufficient = run_assess(THERAPY, comp=None, score=None, sufficient=False)
        self.assertEqual(excluded.status, "not_applicable")
        self.assertEqual(insufficient.status, "insufficient_evidence")
        self.assertIn("не наносится", excluded.rationale)
        self.assertNotIn("не наносится", insufficient.rationale)
        self.assertTrue(
            any("недостаточно" in text for text in insufficient.limitations)
        )



class SectionApplicabilityTests(unittest.TestCase):
    """Therapy / procedure: no category ban, but evidence is required."""

    def test_therapy_not_applicable_with_reason_and_source(self):
        result = run_assess(
            THERAPY,
            score=None,
            applicability=NOT_APPLICABLE,
            reason="Средство смывается и не контактирует с зоной лечения.",
        )
        self.assertEqual(result.status, "not_applicable")
        self.assertIsNone(result.value)

    def test_therapy_not_applicable_without_source_is_insufficient(self):
        result = run_assess(
            THERAPY,
            score=None,
            applicability=NOT_APPLICABLE,
            reason="Не нашли данных.",
            with_evidence=False,
        )
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIsNone(result.value)

    def test_therapy_assessed_with_fetched_evidence(self):
        result = run_assess(THERAPY, comp=None, score=25)
        self.assertEqual(result.status, "assessed")
        self.assertEqual(result.value, 25)

    def test_procedure_not_applicable_with_reason_and_source(self):
        result = run_assess(
            PROCEDURE,
            score=None,
            applicability=NOT_APPLICABLE,
            reason="Продукт не предназначен для лица после процедуры.",
        )
        self.assertEqual(result.status, "not_applicable")
        self.assertIsNone(result.value)

    def test_procedure_without_sources_is_insufficient(self):
        result = run_assess(
            PROCEDURE,
            score=None,
            sufficient=False,
            with_evidence=False,
        )
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIsNone(result.value)
        self.assertTrue(
            any("недостаточно" in text for text in result.limitations)
        )

    def test_procedure_assessed_with_fetched_evidence(self):
        result = run_assess(PROCEDURE, comp=None, score=75)
        self.assertEqual(result.status, "assessed")
        self.assertEqual(result.value, 75)

