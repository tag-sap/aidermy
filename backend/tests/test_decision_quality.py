import unittest

from app.decision_engine import DecisionEngine
from app.profile_resolver import normalize_scoring_profile


class DataQualityCaveatTests(unittest.TestCase):
    def test_low_coverage_summary_is_explicitly_caveated(self):
        profile = normalize_scoring_profile({"skin_type": "Нормальная", "age": "25-34"})
        knowledge = {"glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.9}}}
        result = DecisionEngine().analyze(
            "Test", "Glycerin, Mystery A, Mystery B, Mystery C", profile, "Нормальная", knowledge=knowledge
        )
        self.assertLess(result["data_quality"]["coverage"], 0.5)
        self.assertIn("ориентировочная", result["summary"])
