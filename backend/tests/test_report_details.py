import unittest

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
