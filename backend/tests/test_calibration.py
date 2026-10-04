"""Regression: AI Calibration Center — профили, cases, score run, audit, drift, compare."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.calibration_profiles import CALIBRATION_PROFILES, CALIBRATION_PROFILES_VERSION, profile_by_id
from app.calibration_service import (
    build_cases,
    reference_cache_key,
    _case_metrics,
    audit,
    find_drift,
    compare,
    run_score_engine,
)


class CalibrationProfilesTests(unittest.TestCase):
    def test_30_profiles_versioned(self):
        self.assertEqual(len(CALIBRATION_PROFILES), 30)
        self.assertEqual(CALIBRATION_PROFILES_VERSION, "1.0")
        for p in CALIBRATION_PROFILES:
            self.assertIn("structured", p)
            self.assertIn("skin_type", p["structured"])
        # stress profile P30 содержит therapy + procedures
        p30 = profile_by_id("P30")
        self.assertTrue(p30["structured"]["therapy"])
        self.assertTrue(p30["structured"]["procedures"])


class CalibrationServiceTests(unittest.TestCase):
    def test_cache_key_deterministic(self):
        a = reference_cache_key(1, "v1", "P01", "prompt1", "deepseek-chat")
        b = reference_cache_key(1, "v1", "P01", "prompt1", "deepseek-chat")
        c = reference_cache_key(1, "v2", "P01", "prompt1", "deepseek-chat")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_build_cases(self):
        products = [{"id": 1, "name": "A", "ingredients": "water"}, {"id": 2, "name": "B", "ingredients": "water"}]
        cases = build_cases(products, CALIBRATION_PROFILES[:3])
        self.assertEqual(len(cases), 2 * 3)

    def test_case_metrics(self):
        ref = {"range_min": 10, "range_max": 20, "estimate": 15, "confidence": 0.8}
        inside = _case_metrics(ref, 15)
        self.assertTrue(inside["inside_range"])
        over = _case_metrics(ref, 44)
        self.assertFalse(over["inside_range"])
        self.assertEqual(over["direction"], "over")
        self.assertEqual(over["delta_from_estimate"], 29)

    def test_audit_metrics(self):
        results = [{"product": {"id": i}, "profile": {"id": f"P{i}"}, "score": s}
                   for i, s in enumerate([50, 50, 50])]
        refs = {f'{i}:P{i}': {"estimate": 50, "range_min": 45, "range_max": 55, "confidence": 0.8}
                for i in range(3)}
        m = audit(results, refs)
        self.assertEqual(m["case_count"], 3)
        self.assertEqual(m["mae"], 0.0)
        self.assertEqual(m["range_coverage"], 1.0)

    def test_run_score_engine_and_candidate(self):
        products = [{"id": 1, "name": "Test", "ingredients": "aqua, glycerin", "category": "Увлажнение и питание"}]
        cases = build_cases(products, [profile_by_id("P03")])
        prod = run_score_engine(cases)
        cand = run_score_engine(cases, {"saturation_scale": 3.0})
        self.assertIsInstance(prod[0]["score"], int)
        self.assertIsInstance(cand[0]["score"], int)
        # trace содержит оси/веса
        self.assertIn("dimensions", prod[0]["trace"])
        self.assertIn("priorities", prod[0]["trace"])

    def test_find_drift_detects_systematic(self):
        # Имитируем системный перекос: engine на 30 выше reference.
        results = [{"product": {"id": i, "category": "Сыворотки"}, "profile": {"structured": {"skin_type": "oily", "concerns": []}}, "score": 70}
                   for i in range(20)]
        refs = {f'{i}:P{i}': {"estimate": 40, "range_min": 35, "range_max": 45, "confidence": 0.8}
                for i in range(20)}
        # profile keys должны совпадать с find_drift (использует profile["structured"])
        results = [{"product": {"id": i, "category": "Сыворотки"}, "profile": {"id": f"P{i}", "structured": {"skin_type": "oily", "concerns": []}}, "score": 70}
                   for i in range(20)]
        refs = {f'{i}:P{i}': {"estimate": 40, "range_min": 35, "range_max": 45, "confidence": 0.8}
                for i in range(20)}
        drift = find_drift(results, refs, min_cases=10)
        self.assertTrue(any(d["group"] == "oily" and d["average_drift"] > 0 for d in drift))


if __name__ == "__main__":
    unittest.main()
