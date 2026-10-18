import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.scoring_engine as SE  # noqa: E402
from app.decision_engine import DecisionEngine  # noqa: E402

BLOCKED = {
    "status": "blocked",
    "branches": {},
    "violations": [],
    "hard_violations": [],
    "negative_dimensions": {"irritation": -1.2},
    "version": "test",
}
PASSED = {"status": "passed", "branches": {}, "violations": [], "hard_violations": [], "version": "test"}

PROFILE = {
    "structured": {
        "skin_type": "Нормальная",
        "sensitivity": "Средняя",
        "concerns": [],
        "allergies": [],
        "active_therapy": [],
        "active_procedures": [],
    }
}
NAME = "Phase1 Experiment Probe"
INCI = "Water, Glycerin, Niacinamide, Panthenol, Cetearyl Alcohol, Phenoxyethanol"


class Phase1ExperimentModeTests(unittest.TestCase):
    def setUp(self):
        self._saved_flag = SE.PHASE1_AFFECTS_SCORE

    def tearDown(self):
        SE.PHASE1_AFFECTS_SCORE = self._saved_flag

    def _analyze(self):
        return DecisionEngine().analyze(NAME, INCI, PROFILE, skin_type="Нормальная")

    def test_production_default_is_enabled(self):
        self.assertTrue(SE.PHASE1_AFFECTS_SCORE, "production по умолчанию: Phase 1 влияет на score")

    def test_blocked_phase1_changes_score_by_default(self):
        with patch("app.phase1.evaluate_phase1", return_value=dict(BLOCKED)):
            SE.PHASE1_AFFECTS_SCORE = True
            blocked = self._analyze()
            SE.PHASE1_AFFECTS_SCORE = False
            untouched = self._analyze()

        self.assertEqual(blocked.get("phase1_status"), "blocked")
        self.assertNotEqual(
            blocked.get("score"), untouched.get("score"),
            "в baseline заблокированный товар должен считаться иначе",
        )

    def test_experiment_mode_keeps_phase2_score_and_reports_status(self):
        with patch("app.phase1.evaluate_phase1", return_value=dict(BLOCKED)):
            SE.PHASE1_AFFECTS_SCORE = False
            result = self._analyze()
        # Phase 1 не влияет на score, но статус сохраняется для диагностики.
        self.assertEqual(result.get("phase1_status"), "blocked")
        self.assertTrue(result.get("phase1_diagnostics_only"))
        self.assertIsNotNone(result.get("score"))

    def test_passed_phase1_scores_identically_in_both_modes(self):
        with patch("app.phase1.evaluate_phase1", return_value=dict(PASSED)):
            SE.PHASE1_AFFECTS_SCORE = True
            baseline = self._analyze()
            SE.PHASE1_AFFECTS_SCORE = False
            experimental = self._analyze()
        self.assertEqual(baseline.get("score"), experimental.get("score"))


if __name__ == "__main__":
    unittest.main()
