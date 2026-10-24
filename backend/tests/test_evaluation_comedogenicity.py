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
        self.assertEqual(result["total_count"], 2)
        self.assertEqual(result["known_count"], 0)
        self.assertEqual(result["coverage"], 0.0)

    def test_one_flagged_ingredient_is_reported_without_product_diagnosis(self):
        rows = {"Aqua": lookup(1), "Glycerin": lookup(4)}
        result = assess_comedogenicity(
            {"name": "Cream", "category": "Крем"},
            {"inci_raw": "Aqua, Glycerin"},
            ingredient_lookup=rows.get,
        )
        self.assertEqual(result["status"], "assessed")
        self.assertEqual(result["level"], "high")
        self.assertEqual(result["verdict"], "caution")
        self.assertEqual(result["ingredients"][0]["name"], "Glycerin")
        self.assertEqual(result["ingredients"][0]["rating"], 4)
        self.assertIsNone(result["score"])
        self.assertIn("не доказательство", result["risk"].casefold())
        self.assertNotIn("доказанно", result["risk"].casefold())

    def test_two_flagged_ingredients_are_listed_together_without_score(self):
        rows = {"Aqua": lookup(1), "Glycerin": lookup(4), "Shea Butter": lookup(3)}
        result = assess_comedogenicity(
            {"name": "Rich Cream", "category": "Крем"},
            {"inci_raw": "Aqua, Glycerin, Shea Butter"},
            ingredient_lookup=rows.get,
            composition_status="active",
        )
        self.assertEqual(result["status"], "assessed")
        self.assertEqual(result["level"], "high")
        self.assertEqual(result["max_rating"], 4)
        self.assertEqual([item["name"] for item in result["ingredients"]], ["Glycerin", "Shea Butter", "Aqua"])
        self.assertIsNone(result["score"])
        self.assertTrue(result["risk"])
        self.assertTrue(result["recommendation"])
        self.assertNotIn("каждый день", result["recommendation"].casefold())

    def test_low_verified_ingredients_are_low_but_not_zero(self):
        rows = {"Aqua": lookup(0), "Glycerin": lookup(0), "Water": lookup(0)}
        result = assess_comedogenicity(
            {"name": "Light Gel", "category": "Крем"},
            {"inci_raw": "Aqua, Glycerin, Water"},
            ingredient_lookup=rows.get,
        )
        self.assertEqual(result["status"], "assessed")
        self.assertEqual(result["level"], "low")
        self.assertIsNone(result["score"])
        self.assertEqual(result["known_count"], 3)
        self.assertEqual(result["coverage"], 1.0)

    def test_zero_only_records_are_not_a_user_facing_comedo_block(self):
        rows = {
            "Water": lookup(0),
            "Glycerin": lookup(0),
            "Unknown One": None,
            "Unknown Two": None,
        }
        result = assess_comedogenicity(
            {"name": "Gel", "category": "Крем"},
            {"inci_raw": "Water, Glycerin, Unknown One, Unknown Two"},
            ingredient_lookup=rows.get,
        )
        self.assertEqual(result["status"], "assessed")
        self.assertEqual(result["level"], "low")
        self.assertEqual(result["verdict"], "positive")
        self.assertEqual(result["known_count"], 2)
        self.assertEqual(result["flagged_count"], 0)
        self.assertEqual(result["ingredients"], [])
        self.assertEqual(result["coverage"], 0.5)

    def test_low_inci_coverage_does_not_hide_a_confirmed_rating(self):
        # 39 tokens, only one confirmed positive rating: the old 60% coverage
        # gate used to hide exactly this evidence.
        inci = ", ".join(["Aqua"] + [f"Unknown {i}" for i in range(38)] + ["Cocos Nucifera Oil"])
        rows = {"Cocos Nucifera Oil": lookup(4, "high", 0.9)}
        result = assess_comedogenicity(
            {"name": "Rich balm", "category": "Крем"},
            {"inci_raw": inci},
            ingredient_lookup=rows.get,
        )
        self.assertEqual(result["status"], "assessed")
        self.assertEqual(result["level"], "high")
        self.assertEqual(result["flagged_count"], 1)
        self.assertLess(result["coverage"], 0.1)
        self.assertEqual(result["ingredients"][0]["name"], "Cocos Nucifera Oil")
        self.assertEqual(result["ingredients"][0]["rating_label"], "4/5")
        self.assertIn("4/5", result["basis"][0]["value"])
        self.assertIn("не доказывает", result["risk"].casefold())

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
            "verdict": "caution",
            "score": None,
            "reason": "Есть несколько компонентов для контекста.",
            "risk": "Теоретическая нагрузка.",
            "recommendation": "Проверьте переносимость.",
            "ingredients": [{"name": "Shea Butter", "rating": 3, "rating_label": "3/5"}],
            "max_rating": 3,
            "flagged_count": 1,
        }).user_report()
        self.assertEqual(without["overall"], with_comedo["overall"])
        self.assertEqual(without["primary_function"], with_comedo["primary_function"])
        self.assertEqual(with_comedo["personal_compatibility"][0]["verdict"], "positive")
        self.assertEqual(with_comedo["comedogenicity"]["level"], "medium")
        self.assertEqual(with_comedo["comedogenicity"]["ingredients"][0]["rating"], 3)
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

    def test_low_coverage_comedo_is_still_in_user_report(self):
        inci = ", ".join(["Aqua"] + [f"Unknown {i}" for i in range(38)] + ["Cocos Nucifera Oil"])
        assessed = assess_comedogenicity(
            {"name": "Rich balm", "category": "Крем"},
            {"inci_raw": inci},
            ingredient_lookup={"Cocos Nucifera Oil": lookup(4, "high", 0.9)}.get,
        )
        public = self._report(assessed).user_report()
        self.assertIn("comedogenicity", public)
        self.assertLess(public["comedogenicity"]["coverage"], 0.1)
        self.assertEqual(public["comedogenicity"]["ingredients"][0]["rating"], 4)
        self.assertEqual(public["comedogenicity"]["risk_label"], "Высокий потенциальный риск")

    def test_assessed_without_flagged_ratings_is_hidden(self):
        public = self._report({
            "status": "assessed",
            "applicable": True,
            "level": "low",
            "verdict": "positive",
            "score": None,
            "reason": "Подтверждённых рейтингов 1–5 нет.",
            "ingredients": [],
            "flagged_count": 0,
        }).user_report()
        self.assertNotIn("comedogenicity", public)

    def test_dedupe_removes_only_comedogenicity_and_keeps_irritation(self):
        from app.evaluation.comedo_dedupe import dedupe_comedogenicity_text, scrub_comedo_fields

        text = (
            "Кокосовое масло обладает комедогенностью 4/5, но может вызывать "
            "раздражение. Барьер кожи при этом не нарушен."
        )
        cleaned = dedupe_comedogenicity_text(text, ("Cocos Nucifera Oil",))
        self.assertNotIn("комедоген", cleaned.casefold())
        self.assertIn("раздражение", cleaned)
        self.assertIn("Барьер кожи", cleaned)

        item = scrub_comedo_fields({
            "cause": "Комедогенность 4/5 у кокосового масла.",
            "risk": "Кокосовое масло комедогенно, возможна аллергическая реакция.",
            "recommendation": "Учитывайте комедогенность кокосового масла.",
            "display_text": "Кокосовое масло может закупоривать поры.",
        }, ("Cocos Nucifera Oil",))
        self.assertNotIn("cause", item)
        self.assertNotIn("recommendation", item)
        self.assertIn("аллергическая реакция", item["risk"])
        self.assertNotIn("комедоген", item["risk"].casefold())
        self.assertEqual(item["display_text"], "")

    def test_user_report_does_not_repeat_comedo_ingredient_in_reason(self):
        report = self._report({
            "status": "assessed",
            "applicable": True,
            "level": "high",
            "verdict": "caution",
            "score": None,
            "reason": "Есть подтверждённый рейтинг.",
            "ingredients": [{"name": "Cocos Nucifera Oil", "rating": 4, "rating_label": "4/5"}],
            "max_rating": 4,
            "flagged_count": 1,
        })
        report.snapshot["parameters"][0]["summary"] = (
            "Кокосовое масло обладает комедогенностью 4/5, но может вызывать раздражение."
        )
        public = report.user_report()
        item = public["personal_compatibility"][0]
        self.assertIn("comedogenicity", public)
        self.assertNotIn("комедоген", item["reason"].casefold())
        self.assertIn("раздражение", item["reason"])
        self.assertIn("Cocos Nucifera Oil", public["comedogenicity"]["ingredients"][0]["name"])

    def test_insufficient_comedogenicity_is_hidden_but_retained_for_diagnostics(self):
        report = self._report({
            "status": "insufficient_evidence",
            "applicable": True,
            "level": "unknown",
            "score": None,
            "reason": "7 из 39: проверенных записей недостаточно.",
            "known_count": 7,
            "total_count": 39,
            "coverage": 0.179,
        })
        public = report.user_report()
        full = report.as_dict()
        self.assertNotIn("comedogenicity", public)
        self.assertEqual(full["comedogenicity"]["status"], "insufficient_evidence")
        self.assertEqual(full["comedogenicity"]["known_count"], 7)


if __name__ == "__main__":
    unittest.main()
