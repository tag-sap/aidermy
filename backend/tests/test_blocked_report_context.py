import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.report_prompt import build_report_context


class BlockedReportContextTests(unittest.TestCase):
    def test_blocked_report_hides_goals_and_uses_only_negative_factors(self):
        analysis = {
            "score": 33,
            "verdict": "Не рекомендовано",
            "phase1_status": "blocked",
            "dimensions": {},
            "priorities": {},
            "negative_factors": [
                {"ingredient": "glycolic acid", "property": "irritation"},
            ],
            "positive_factors": [
                {"ingredient": "niacinamide", "property": "hydration"},
            ],
            "normalized_ingredients": ["aqua", "glycolic acid", "niacinamide"],
            "goal_evidence": [
                {
                    "concern_id": "pores",
                    "label": "Расширенные поры",
                    "verdict": "supports",
                    "evidence": [],
                }
            ],
        }
        profile = {
            "skin_type": "Жирная кожа с расширенными порами",
            "concerns": ["акне", "расширенные поры"],
            "custom_text": "профиль пользователя",
        }

        context = build_report_context(
            "ARAVIA Laboratories Anti-acne Peeling",
            analysis,
            profile,
            "scrubs",
        )

        self.assertEqual(context["goal_evidence"], "[]")
        self.assertEqual(context["skin_type"], "не передаётся при заблокированном результате")
        self.assertIn("glycolic acid → irritation", context["deterministic_input"])
        self.assertNotIn("Расширенные поры", context["deterministic_input"])
        self.assertNotIn("niacinamide", context["deterministic_input"])
        self.assertIn("не обсуждай цели пользователя", context["deterministic_input"].lower())


if __name__ == "__main__":
    unittest.main()
