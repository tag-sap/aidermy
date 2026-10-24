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
        self.assertEqual(result["score"], 80)
        self.assertLess(result["score"], 100)
        self.assertEqual(result["score_kind"], "formula_support")
        self.assertIn("не подтверждает", result["score_note"])
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
        self.assertEqual(result["score"], 50)
        self.assertLess(result["score"], 100)
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
        self.assertLess(result["score"], 100)
        self.assertNotIn("акне", result["reason"].casefold())

    def test_cleanser_with_only_a_surfactant_is_not_maximally_effective(self):
        product = {
            "id": 1514,
            "name": "ROUND LAB 1025 Dokdo Cleanser",
            "category": "Очищение",
            "subcategory": "Очищение и демакияж",
            "ingredients": "Aqua, Sodium Cocoyl Isethionate",
        }
        result = build_primary_function(
            product, {"inci_raw": product["ingredients"]}, composition_status="active"
        )
        self.assertEqual(result["function_id"], "cleansing")
        self.assertEqual(result["score"], 50)
        self.assertLess(result["score"], 100)

    def test_cleanser_support_groups_do_not_inflate_primary_function(self):
        product = {
            "id": 1514,
            "name": "ROUND LAB 1025 Dokdo Cleanser",
            "category": "Очищение",
            "subcategory": "Очищение и демакияж",
            "ingredients": (
                "Aqua, Sodium Cocoyl Isethionate, Glycerin, Panthenol, Allantoin"
            ),
        }
        result = build_primary_function(
            product, {"inci_raw": product["ingredients"]}, composition_status="active"
        )
        self.assertEqual(result["score"], 50)
        self.assertLess(result["score"], 100)
        self.assertNotIn("100", str(result["score"]))

    def test_anti_acne_serum_keeps_its_catalog_function_when_name_says_hydrating(self):
        product = {
            "id": 4843,
            "name": "Увлажняющая сыворотка для лица",
            "category": "Сыворотка",
            "subcategory": "Сыворотки",
            "catalog_category": "Сыворотки и концентраты",
            "catalog_subcategory": "От акне и воспалений",
            "ingredients": "Aqua, Glycerin, Niacinamide, Salicylic Acid, Panthenol",
        }
        result = build_primary_function(
            product, {"inci_raw": product["ingredients"]}, composition_status="active"
        )
        self.assertEqual(result["function_id"], "anti_acne")
        self.assertEqual(result["label"], "Антиакне-уход")
        self.assertNotEqual(result["function_id"], "moisturizing")
        self.assertLess(result["score"], 100)

    def test_hydrating_serum_does_not_replace_anti_acne_purpose(self):
        product = {
            "id": 4843,
            "name": "Hydrating moisturizing serum",
            "catalog_category": "Сыворотки и концентраты",
            "catalog_subcategory": "От акне и воспалений",
            "ingredients": "Aqua, Glycerin",
        }
        result = build_primary_function(
            product, {"inci_raw": product["ingredients"]}, composition_status="active"
        )
        self.assertEqual(result["label"], "Антиакне-уход")
        self.assertIsNone(result["score"])

    def test_category_membership_or_one_ingredient_is_not_efficacy_proof(self):
        product = {
            "id": 999,
            "name": "Simple Hydrating Cream",
            "category": "Крем",
            "subcategory": "Кремы",
            "ingredients": "Aqua, Glycerin",
        }
        result = build_primary_function(
            product, {"inci_raw": product["ingredients"]}, composition_status="active"
        )
        self.assertEqual(result["label"], "Увлажнение")
        self.assertEqual(result["score"], 50)
        self.assertLess(result["score"], 100)
        self.assertIn("не подтверждает", result["score_note"])

    def test_explicit_sunscreen_keeps_sun_function_despite_conflicting_catalog(self):
        product = {
            "id": 4719,
            "name": "Capital Soleil Tinted Face Mineral Sunscreen SPF 60",
            "catalog_category": "Сыворотки и концентраты",
            "catalog_subcategory": "Антивозрастные",
            "ingredients": "Aqua, Zinc Oxide",
        }
        result = build_primary_function(
            product, {"inci_raw": product["ingredients"]}, composition_status="active"
        )
        self.assertEqual(result["function_id"], "sun_protection")
        self.assertEqual(result["label"], "Защита от солнца")

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


class CategoryFunctionRegressionTests(unittest.TestCase):
    def test_bioderma_cleansing_category_defines_function_without_marker_words(self):
        product = {
            "id": 4468,
            "name": "Créaline (Sensibio) Foaming Gel/ Gel Moussant",
            "category": "Очищение",
            "subcategory": "Очищение и демакияж",
            "taxonomy_category": "Уход для лица",
        }
        result = build_primary_function(
            product,
            {"inci_raw": "Aqua, Glycerin"},
            composition_status="active",
        )
        self.assertEqual(result["category"], "Очищение и демакияж")
        self.assertEqual(result["function_id"], "cleansing")
        self.assertEqual(result["label"], "Очищение")
        # The category defines the function; absence of a recognized marker
        # withholds the efficacy score, not the function itself.
        self.assertIsNone(result["score"])
        self.assertEqual(result["status"], "insufficient_evidence")

    def test_similar_cleansing_categories_keep_function_defined(self):
        for category, subcategory in (
            ("Очищение", "Гели и пенки"),
            ("Очищение", "Мицеллярная вода"),
            ("Очищение", "Молочко"),
            ("Очищение и демакияж", "Очищение и демакияж"),
        ):
            with self.subTest(category=category, subcategory=subcategory):
                result = build_primary_function(
                    {
                        "id": 999,
                        # No "cleanser"/"face wash" marker: only the catalog
                        # category/type can identify this function.
                        "name": "Bioderma Créaline Foaming Gel",
                        "category": category,
                        "subcategory": subcategory,
                    },
                    {"inci_raw": "Aqua, Glycerin"},
                    composition_status="active",
                )
                self.assertEqual(result["label"], "Очищение")
                self.assertEqual(result["function_id"], "cleansing")


class PublicFunctionPurposeTests(unittest.TestCase):
    def test_redundant_purpose_is_not_shown_for_multiple_categories(self):
        from app.evaluation.primary_function import public_primary_function

        products = (
            {"id": 1, "name": "SPF 50 Sunscreen", "category": "Солнцезащитный крем",
             "ingredients": "Aqua, Zinc Oxide"},
            {"id": 2, "name": "Gentle Cleanser", "category": "Очищение",
             "ingredients": "Aqua, Glycerin"},
            {"id": 3, "name": "Hydrating Cream", "category": "Крем",
             "ingredients": "Aqua, Glycerin"},
            {"id": 4, "name": "Anti-acne serum", "catalog_category": "Сыворотки и концентраты",
             "catalog_subcategory": "От акне и воспалений", "ingredients": "Aqua, Glycerin"},
            {"id": 5, "name": "Brightening essence", "catalog_category": "Сыворотки и концентраты",
             "catalog_subcategory": "Осветляющие", "ingredients": "Aqua, Glycerin"},
        )
        for product in products:
            with self.subTest(product=product["name"]):
                built = build_primary_function(
                    product, {"inci_raw": product["ingredients"]}, composition_status="active"
                )
                self.assertTrue(built["purpose"])
                public = public_primary_function(built)
                self.assertEqual(public["purpose"], "")
                self.assertTrue(public["label"])

    def test_extra_constraint_or_mechanism_is_preserved(self):
        from app.evaluation.primary_function import public_primary_function

        public = public_primary_function({
            "label": "Защита от солнца",
            "purpose": "Наносить только на открытые участки и обновлять после купания.",
        })
        self.assertIn("только", public["purpose"])
        self.assertIn("после купания", public["purpose"])


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
            {
                "product_name",
                "primary_function",
                "overall",
                "personal_compatibility",
                "sources",
            },
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

    def _intolerance_report(self, inci: str) -> AnalysisReport:
        primary = build_primary_function(CREAM, {"inci_raw": inci})
        return AnalysisReport(
            product={"id": 1176, "name": CREAM["name"]},
            composition={
                "composition_hash": "a" * 64,
                "status": "active",
                "inci_raw": inci,
            },
            snapshot={
                "parameters": [
                    {
                        "parameter_id": "intolerance:niacinamide_intolerance",
                        "label": "Наличие в составе: «Ниацинамид»",
                        "value": 75,
                        "included": True,
                        "summary": "Проверка подтверждённого INCI.",
                    }
                ],
                "total": 75,
                "analysis": {"status": "complete", "is_final": True},
            },
            analysis=AnalysisState(status="complete", is_final=True),
            primary_function=primary,
        )

    def test_niacinamide_intolerance_uses_confirmed_inci_status(self):
        present = self._intolerance_report("Aqua, Glycerin, Niacinamide")
        row = present.user_report()["personal_compatibility"][0]
        self.assertEqual(row["intolerance"]["state"], "present")
        self.assertEqual(row["intolerance"]["label"], "Обнаружен в составе")

        absent = self._intolerance_report("Aqua, Glycerin")
        row = absent.user_report()["personal_compatibility"][0]
        self.assertEqual(row["intolerance"]["state"], "absent")
        self.assertEqual(row["intolerance"]["label"], "Не обнаружен в составе")

        unconfirmed = self._intolerance_report("")
        row = unconfirmed.user_report()["personal_compatibility"][0]
        self.assertEqual(row["intolerance"]["state"], "unknown")
        self.assertEqual(row["intolerance"]["label"], "Не удалось определить")
