"""Independent primary-function and compact user-report contracts."""
from __future__ import annotations

import re
import unittest

from app.evaluation import AnalysisReport, build_primary_function
from app.evaluation.gaps import AnalysisState

CREAM = {
    "id": 1176,
    "name": "ARAVIA Laboratories Hyaluron Filler Hydrating Cream",
    "category": "Крем",
    "subcategory": "Кремы",
    "ingredients": (
        "Aqua, Butyrospermum Parkii (Shea) Butter, Cetearyl Alcohol, Glycerin, "
        "Caprylic/Capric Triglyceride, Panthenol, Sodium Hyaluronate"
    ),
}


class PrimaryFunctionTests(unittest.TestCase):
    def test_cream_gets_an_independent_moisturising_score(self):
        result = build_primary_function(
            CREAM, {"inci_raw": CREAM["ingredients"], "source": "catalog"}
        )
        self.assertEqual(result["status"], "assessed")
        self.assertEqual(result["label"], "Увлажнение")
        self.assertIn(result["score"], (75, 100))
        self.assertIn("Увлажн", result["purpose"])
        self.assertNotIn("profile", result)
        self.assertNotIn("total", result)

    def test_score_does_not_change_with_a_different_personal_profile(self):
        # This function has no profile argument at all: primary function cannot
        # accidentally be mixed with personal compatibility.
        first = build_primary_function(CREAM, {"inci_raw": CREAM["ingredients"]})
        second = build_primary_function(CREAM, {"inci_raw": CREAM["ingredients"]})
        self.assertEqual(first["score"], second["score"])
        self.assertEqual(first["function_id"], second["function_id"])

    def test_sunscreen_without_uv_filter_has_no_invented_score(self):
        product = {
            "id": 2,
            "name": "SPF 50 Sunscreen",
            "category": "Солнцезащитный крем",
            "ingredients": "Aqua, Glycerin",
        }
        result = build_primary_function(
            product, {"inci_raw": product["ingredients"]}, composition_status="active"
        )
        self.assertEqual(result["label"], "Защита от солнца")
        self.assertIsNone(result["score"])
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertNotEqual(result["score"], 0)

    def test_sunscreen_with_a_confirmed_filter_is_assessed(self):
        product = {
            "id": 3,
            "name": "SPF 50 Sunscreen",
            "category": "Солнцезащитный крем",
            "ingredients": "Aqua, Zinc Oxide, Glycerin",
        }
        result = build_primary_function(
            product, {"inci_raw": product["ingredients"]}, composition_status="active"
        )
        self.assertEqual(result["score"], 100)
        self.assertIn("UV-фильтры", result["basis"][-1]["value"])

    def test_missing_or_unconfirmed_composition_has_no_invented_score(self):
        no_inci = {key: value for key, value in CREAM.items() if key != "ingredients"}
        for product, status, composition in (
            (CREAM, "active", {"inci_raw": "Aqua"}),
            (CREAM, "unverified", {"inci_raw": CREAM["ingredients"]}),
            (no_inci, "active", {}),
        ):
            result = build_primary_function(
                product, composition, composition_status=status
            )
            self.assertIsNone(result["score"], status)
            self.assertEqual(result["status"], "insufficient_evidence", status)

    def test_cleanser_is_assessed_by_its_own_function_not_by_acne_treatment(self):
        product = {
            "id": 5,
            "name": "Gentle Gel Cleanser",
            "category": "Очищение",
            "ingredients": "Aqua, Cocamidopropyl Betaine, Glycerin",
        }
        result = build_primary_function(
            product, {"inci_raw": product["ingredients"]}, composition_status="active"
        )
        self.assertEqual(result["label"], "Очищение")
        self.assertGreater(result["score"], 0)
        self.assertNotIn("акне", result["reason"].casefold())

    def test_unknown_category_has_no_invented_score(self):
        result = build_primary_function(
            {"id": 4, "name": "Неизвестный продукт XYZ", "category": "Другое"},
            {"inci_raw": "Aqua, Glycerin"},
        )
        self.assertIsNone(result["score"])
        self.assertEqual(result["status"], "insufficient_evidence")

    def test_primary_reason_is_at_most_two_sentences(self):
        result = build_primary_function(CREAM, {"inci_raw": CREAM["ingredients"]})
        sentences = [part for part in re.split(r"(?<=[.!?])\s+", result["reason"]) if part]
        self.assertLessEqual(len(sentences), 2)


class CompactUserReportTests(unittest.TestCase):
    def _report(self, primary: dict | None = None) -> AnalysisReport:
        primary = primary or build_primary_function(
            CREAM, {"inci_raw": CREAM["ingredients"]}
        )
        return AnalysisReport(
            product={"id": 1176, "name": CREAM["name"]},
            composition={"composition_hash": "a" * 64, "status": "active"},
            snapshot={
                "parameters": [
                    {
                        "parameter_id": "skin_type:dry",
                        "label": "Тип кожи: «Сухая»",
                        "value": 75,
                        "included": True,
                        "summary": "Состав соответствует сухой коже.",
                    },
                    {
                        "parameter_id": "problem:dryness",
                        "label": "Проблема: «Сухость»",
                        "value": None,
                        "included": False,
                        "summary": "",
                    },
                    {
                        "parameter_id": "goal:hydration",
                        "label": "Цель: «Увлажнение»",
                        "value": 100,
                        "included": True,
                        "summary": "Состав поддерживает увлажнение.",
                    },
                ],
                "total": 87.5,
                "analysis": {
                    "status": "incomplete",
                    "gaps": [{"parameter_id": "problem:dryness"}],
                },
            },
            analysis=AnalysisState(status="incomplete", is_final=False),
            evidence={
                "skin_type:dry": [{"id": 1, "quote": "Glycerin helps hydration"}],
            },
            primary_function=primary,
        )

    def test_user_report_has_only_two_sections_and_no_average(self):
        report = self._report()
        public = report.user_report()
        self.assertEqual(
            set(public),
            {"product_name", "primary_function", "personal_compatibility"},
        )
        self.assertNotIn("total", public)
        self.assertNotIn("average", public)
        self.assertNotIn("gaps", public)
        self.assertNotIn("analysis", public)
        self.assertNotIn("status", public["primary_function"])
        self.assertNotIn("limitations", public["primary_function"])
        self.assertEqual(len(public["personal_compatibility"]), 2)
        # Diagnostics and history remain available in the full backend payload.
        full = report.as_dict()
        self.assertEqual(full["analysis"]["status"], "incomplete")
        self.assertEqual(full["snapshot"]["total"], 87.5)
        self.assertTrue(full["snapshot"]["analysis"]["gaps"])

    def test_unassessed_parameter_is_not_rendered_and_primary_stays_separate(self):
        public = self._report().user_report()
        labels = [row["label"] for row in public["personal_compatibility"]]
        self.assertNotIn("Проблема: «Сухость»", labels)
        self.assertNotIn("total", public["personal_compatibility"][0])

    def test_short_reason_is_used_instead_of_the_long_audit_rationale(self):
        row = self._report().user_report()["personal_compatibility"][0]
        self.assertEqual(row["reason"], "Состав соответствует сухой коже.")
        self.assertNotIn("Оценка 87.5", row["reason"])
