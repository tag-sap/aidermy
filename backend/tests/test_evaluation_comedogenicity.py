"""Comedogenicity is a separate product-level warning, never a compatibility score."""
from __future__ import annotations

import unittest

from app.evaluation.comedogenicity import assess_comedogenicity
from app.evaluation.analysis import AnalysisReport
from app.evaluation.gaps import AnalysisState


def lookup(rating: float, evidence: str = "moderate", confidence: float = 0.8):
    return {
        "comedogenicity": rating,
        "evidence_level": evidence,
        "knowledge_confidence": confidence,
    }


class ComedogenicityTests(unittest.TestCase):
    def test_missing_data_does_not_invent_a_score(self):
        result = assess_comedogenicity(
            {"name": "Cream", "category": "Крем"},
            {"inci_raw": "Aqua, Glycerin"},
            ingredient_lookup=lambda name: None,
        )
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIsNone(result["score"])

    def test_one_flagged_ingredient_does_not_make_whole_formula_negative(self):
        rows = {"Aqua": lookup(1), "Glycerin": lookup(4)}
        result = assess_comedogenicity(
            {"name": "Cream", "category": "Крем"},
            {"inci_raw": "Aqua, Glycerin"},
            ingredient_lookup=rows.get,
        )
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIsNone(result["score"])
        self.assertNotIn("risk", result.get("reason", "").casefold())

    def test_two_flagged_ingredients_give_contextual_warning_without_score(self):
        rows = {"Aqua": lookup(1), "Glycerin": lookup(4), "Shea Butter": lookup(3)}
        result = assess_comedogenicity(
            {"name": "Rich Cream", "category": "Крем"},
            {"inci_raw": "Aqua, Glycerin, Shea Butter"},
            ingredient_lookup=rows.get,
            composition_status="active",
        )
        self.assertEqual(result["status"], "assessed")
        self.assertEqual(result["level"], "medium")
        self.assertIsNone(result["score"])
        self.assertTrue(result["risk"])
        self.assertTrue(result["recommendation"])
        self.assertNotIn("каждый день", result["recommendation"].casefold())

    def test_low_verified_ingredients_are_low_but_not_zero(self):
        rows = {"Aqua": lookup(0), "Glycerin": lookup(0)}
        result = assess_comedogenicity(
            {"name": "Light Gel", "category": "Крем"},
            {"inci_raw": "Aqua, Glycerin"},
            ingredient_lookup=rows.get,
        )
        self.assertEqual(result["status"], "assessed")
        self.assertEqual(result["level"], "low")
        self.assertIsNone(result["score"])

    def test_fragrance_is_not_applicable_and_omitted(self):
        result = assess_comedogenicity(
            {"name": "Eau de Parfum", "category": "Парфюм"},
            {"inci_raw": "Alcohol, Parfum"},
            ingredient_lookup=lambda name: lookup(4),
        )
        self.assertEqual(result["status"], "not_applicable")
        self.assertFalse(result["applicable"])


class SeparateReportBlockTests(unittest.TestCase):
    def _report(self, comedo: dict | None) -> AnalysisReport:
        return AnalysisReport(
            product={"id": 1, "name": "Cleanser"},
            composition={"composition_hash": "a" * 64, "status": "active"},
            snapshot={
                "parameters": [{
                    "parameter_id": "problem:acne_general",
                    "label": "Проблема: «Высыпания»",
                    "value": 50,
                    "included": True,
                    "summary": "Не является лечением акне, но не подтверждает вред.",
                }],
            },
            analysis=AnalysisState(status="complete", is_final=True),
            primary_function={"label": "Очищение", "purpose": "", "score": 75, "reason": "", "basis": []},
            comedogenicity=comedo or {},
        )

    def test_comedogenicity_does_not_change_overall_or_primary_function(self):
        without = self._report(None).user_report()
        with_comedo = self._report({
            "status": "assessed",
            "applicable": True,
            "level": "medium",
            "score": None,
            "reason": "Есть несколько компонентов для контекста.",
            "risk": "Теоретическая нагрузка.",
            "recommendation": "Проверьте переносимость.",
        }).user_report()
        self.assertEqual(without["overall"], with_comedo["overall"])
        self.assertEqual(without["primary_function"], with_comedo["primary_function"])
        self.assertEqual(with_comedo["personal_compatibility"][0]["verdict"], "positive")
        self.assertEqual(with_comedo["comedogenicity"]["level"], "medium")
        self.assertIsNone(with_comedo["comedogenicity"]["score"])

    def test_not_applicable_comedogenicity_is_omitted_from_user_report(self):
        public = self._report({
            "status": "not_applicable",
            "applicable": False,
            "level": "unknown",
            "score": None,
            "reason": "Не относится к продукту.",
        }).user_report()
        self.assertNotIn("comedogenicity", public)


if __name__ == "__main__":
    unittest.main()
