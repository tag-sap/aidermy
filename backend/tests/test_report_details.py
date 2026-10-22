import unittest
from unittest.mock import patch

from app.report_details import build_report_details


def _analysis():
    return {
        "score": 64,
        "confidence": 0.55,
        "normalized_ingredients": ["Water", "Niacinamide", "Fragrance", "Mystery X"],
        "unknown_factors": [{"ingredient": "Mystery X", "reason": "unknown_ingredient"}],
        "positive_factors": [{
            "ingredient": "Niacinamide", "property": "barrier", "direction": "positive",
            "strength": 0.8, "confidence": 0.9, "position_weight": 0.8,
        }],
        "negative_factors": [{
            "ingredient": "Fragrance", "property": "irritation", "direction": "negative",
            "strength": 0.7, "confidence": 0.8, "position_weight": 0.7,
        }],
        "interaction_breakdown": [{
            "interaction_id": 1, "ingredient_a": "niacinamide", "ingredient_b": "fragrance",
            "axis": "irritation", "direction": "positive", "weighted_contribution": -0.4,
            "confidence": 0.9, "source_type": "pubmed", "evidence": "trial",
        }],
        "phase1": {"status": "passed"},
        "hard_flags": [],
    }


class ReportDetailsTests(unittest.TestCase):
    def test_sections_are_source_labelled_and_do_not_invent_ingredients(self):
        details = build_report_details(
            "Test Product",
            "Крем",
            _analysis(),
            {"skin_type": "Чувствительная", "structured": {"skin_type": "sensitive", "concerns": ["redness"]}},
        )
        ids = [section["id"] for section in details["sections"]]
        self.assertIn("product", ids)
        self.assertIn("why", ids)
        self.assertIn("limitations", ids)
        self.assertIn("interactions", ids)
        names = {item["name"] for item in details["key_ingredients"] + details["other_ingredients"]}
        self.assertEqual(names, {"Water", "Niacinamide", "Fragrance", "Mystery X"})
        self.assertTrue(any(item["unknown"] for item in details["other_ingredients"]))
        self.assertIn("Mystery X", " ".join(details["sections"][3]["paragraphs"]))

    def test_data_quality_is_explicit(self):
        details = build_report_details("Test", "Крем", _analysis(), {})
        quality = details["data_quality"]
        self.assertEqual(quality["total_ingredients"], 4)
        self.assertEqual(quality["unknown_ingredients"], 1)
        self.assertEqual(quality["label"], "средняя")

    @patch("app.report_details._ingredient_meta")
    def test_catalogue_json_lists_are_rendered_as_human_readable_text(self, meta):
        meta.return_value = {
            "niacinamide": {
                "inci_name": "Niacinamide",
                "functions": '["humectant", "soothing"]',
                "skin_effects": '["hydration"]',
                "sources": '[{"title": "Pubmed", "url": "https://example.org/study"}]',
                "evidence_level": "high",
            }
        }
        details = build_report_details("Test", "Крем", _analysis(), {})
        item = next(x for x in details["key_ingredients"] if x["name"] == "Niacinamide")
        self.assertEqual(item["function"], "увлажнитель; успокаивающее действие")
        self.assertEqual(item["skin_effects"], "увлажнение")
        self.assertEqual(item["sources"], "Pubmed (https://example.org/study)")
        self.assertNotIn("[", item["function"])

    @patch("app.report_details._ingredient_meta")
    def test_empty_catalogue_arrays_use_explicit_fallback(self, meta):
        meta.return_value = {
            "glycerin": {
                "inci_name": "Glycerin",
                "functions": "[]",
                "skin_effects": "[]",
                "sources": "[]",
                "evidence_level": "moderate",
            }
        }
        analysis = {
            "score": 50,
            "confidence": 0.5,
            "normalized_ingredients": ["Glycerin"],
            "positive_factors": [],
            "negative_factors": [],
            "unknown_factors": [],
        }
        details = build_report_details("Test", "Крем", analysis, {})
        item = details["other_ingredients"][0]
        self.assertEqual(item["function"], "Функция в базе знаний не описана.")
        self.assertEqual(item["skin_effects"], "")
        self.assertEqual(item["sources"], "")
