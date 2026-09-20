import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.decision_engine import (
    DecisionEngine,
    build_summary,
    build_verdict,
    priorities_for_profile,
)


class DecisionEngineTests(unittest.TestCase):
    def test_sensitive_profile_summary_references_sensitive_skin(self):
        analysis = {
            "score": 62,
            "confidence": 0.6,
            "positive_factors": [
                {"ingredient": "Glycerin", "property": "hydration", "direction": "positive", "strength": 0.8, "confidence": 0.9},
            ],
            "negative_factors": [
                {"ingredient": "Fragrance", "property": "sensitivity", "direction": "negative", "strength": 0.7, "confidence": 0.8},
            ],
            "hard_flags": [],
        }
        profile = {"skin_type": "Чувствительная", "concerns": ["Покраснения"], "allergies": []}
        summary = build_summary(analysis, profile, "Чувствительная", 62)
        self.assertIn("чувствительной кожи", summary)
        self.assertNotIn("нормальной кожи", summary)

    def test_normal_skin_wording_only_when_profile_is_normal(self):
        analysis = {
            "score": 80,
            "confidence": 0.5,
            "positive_factors": [
                {"ingredient": "Glycerin", "property": "hydration", "direction": "positive", "strength": 0.8, "confidence": 0.9},
            ],
            "negative_factors": [],
            "hard_flags": [],
        }
        sensitive = build_summary(analysis, {"skin_type": "Чувствительная"}, "Чувствительная", 80)
        self.assertNotIn("нормальной кожи", sensitive)

        normal = build_summary(analysis, {"skin_type": "Нормальная"}, "Нормальная", 80)
        self.assertIn("нормальной кожи", normal)

    def test_summary_matches_score(self):
        analysis = {
            "confidence": 0.5,
            "positive_factors": [],
            "negative_factors": [
                {"ingredient": "Fragrance", "property": "sensitivity", "direction": "negative", "strength": 0.7, "confidence": 0.8},
            ],
            "hard_flags": [],
        }
        profile = {"skin_type": "Чувствительная"}
        low = build_summary(analysis, profile, "Чувствительная", 25)
        self.assertIn("не подходит", low)

        high = build_summary(analysis, profile, "Чувствительная", 85)
        self.assertIn("соответствует", high)

    def test_verdict_thresholds(self):
        self.assertEqual(build_verdict(80), "Подходит")
        self.assertEqual(build_verdict(55), "Требует внимания")
        self.assertEqual(build_verdict(20), "Не рекомендуется")

    def test_priorities_boost_sensitivity_for_sensitive_profile(self):
        weights = priorities_for_profile({"skin_type": "Чувствительная", "concerns": []}, "Чувствительная")
        self.assertGreater(weights["sensitivity"], weights["brightening"])

    def test_engine_allergy_hard_flag_lowers_score(self):
        engine = DecisionEngine()
        profile = {"skin_type": "Сухая", "concerns": [], "allergies": ["glycerin"]}
        result = engine.analyze("Крем", "Aqua, Glycerin", profile, "Сухая")
        self.assertTrue(any(f["type"] == "allergy" for f in result.get("hard_flags", [])))
        self.assertLessEqual(result["score"], 35)


if __name__ == "__main__":
    unittest.main()
