"""Regression: AI Calibration Center — профили, cases, score run, audit, drift, compare, lifecycle."""
import asyncio
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.calibration_profiles import CALIBRATION_PROFILES, CALIBRATION_PROFILES_VERSION, profile_by_id
from app.calibration_service import (
    CALIBRATION_PROMPT_VERSION,
    DEFAULT_MODEL,
    STALE_SECONDS,
    audit,
    build_calibration_summary,
    build_cases,
    compare,
    create_run,
    find_drift,
    generate_ai_reference_batched,
    get_case_detail,
    get_run,
    is_stale,
    latest_active_run,
    persist_calibration_cases,
    reference_cache_key,
    run_score_engine,
    update_run,
    _case_metrics,
    _drift_group_label,
    _drift_verdict,
    _extract_json_array,
    _overall_status,
    _product_version,
)
from app.database import AIDERMY_DB, get_connection


def _now():
    return datetime.now(timezone.utc).isoformat()


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

    def test_extract_json_array_variants(self):
        plain = '[{"product_id": 1, "profile_id": "P03", "estimate": 50}]'
        self.assertEqual(_extract_json_array(plain)[0]["profile_id"], "P03")
        fenced = '```json\n[{"product_id": 2, "profile_id": "P05", "estimate": 60}]\n```'
        self.assertEqual(_extract_json_array(fenced)[0]["product_id"], 2)
        wrapped = '{"results": [{"product_id": 3, "profile_id": "P07", "estimate": 70}]}'
        self.assertEqual(_extract_json_array(wrapped)[0]["product_id"], 3)
        nested = '[{"product_id": 4, "profile_id": "P09", "positive_drivers": ["a", "b"], "negative_drivers": []}]'
        self.assertEqual(_extract_json_array(nested)[0]["positive_drivers"], ["a", "b"])
        self.assertIsNone(_extract_json_array("no json here"))
        self.assertIsNone(_extract_json_array('{"just": "an object"}'))


class CalibrationLifecycleTests(unittest.TestCase):
    def setUp(self):
        self._keys = []

    def tearDown(self):
        conn = get_connection(AIDERMY_DB)
        for k in self._keys:
            conn.execute("DELETE FROM calibration_runs WHERE run_key=?", (k,))
            conn.execute("DELETE FROM calibration_cases WHERE run_key=?", (k,))
        conn.commit()
        conn.close()

    def _mk(self, params=None):
        key = create_run(params or {"product_limit": 5, "use_cache": True})
        self._keys.append(key)
        return key

    def test_lifecycle_queued_running_completed(self):
        key = self._mk({"product_limit": 10})
        run = get_run(key)
        self.assertEqual(run["status"], "queued")
        self.assertIsNotNone(run["params"])

        update_run(key, status="running", started_at=_now())
        self.assertEqual(get_run(key)["status"], "running")

        update_run(key, status="completed", completed_at=_now(), processed_cases=10, total_cases=10)
        self.assertEqual(get_run(key)["status"], "completed")

    def test_lifecycle_failed(self):
        key = self._mk()
        update_run(key, status="running", started_at=_now())
        update_run(key, status="failed", error="boom", completed_at=_now())
        run = get_run(key)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error"], "boom")

    def test_is_stale_detects_dead_worker(self):
        key = self._mk()
        update_run(key, status="running", started_at=_now(),
                   updated_at=(datetime.now(timezone.utc) - timedelta(seconds=STALE_SECONDS + 60)).isoformat())
        self.assertTrue(is_stale(get_run(key)))

        update_run(key, updated_at=datetime.now(timezone.utc).isoformat())
        self.assertFalse(is_stale(get_run(key)))

        update_run(key, status="completed", completed_at=_now())
        self.assertFalse(is_stale(get_run(key)))

    def test_double_click_returns_active_run(self):
        key = self._mk()
        active = latest_active_run()
        self.assertEqual(active["run_key"], key)
        self.assertIn(active["status"], ("queued", "running"))

    def test_cached_references_not_regenerated(self):
        product = {"id": 987654321, "name": "Cache Test", "ingredients": "aqua, glycerin",
                   "category": "Увлажнение и питание"}
        profile = profile_by_id("P03")
        pv = _product_version(product)
        ck = reference_cache_key(product["id"], pv, profile["id"], CALIBRATION_PROMPT_VERSION, DEFAULT_MODEL)
        ref = {"product_id": product["id"], "profile_id": profile["id"], "range_min": 40, "range_max": 60,
               "estimate": 50, "confidence": 0.8, "positive_drivers": [], "negative_drivers": [], "reason": "test"}
        conn = get_connection(AIDERMY_DB)
        conn.execute(
            "INSERT OR REPLACE INTO calibration_references (cache_key, product_id, profile_id, reference, model, prompt_version, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ck, product["id"], profile["id"], json.dumps(ref, ensure_ascii=False), DEFAULT_MODEL,
             CALIBRATION_PROMPT_VERSION, _now()),
        )
        conn.commit()
        conn.close()
        try:
            refs, stats = asyncio.run(generate_ai_reference_batched([product], [profile], use_cache=True))
            self.assertIn(f'{product["id"]}:{profile["id"]}', refs)
            self.assertEqual(stats["ai_requests"], 0)
            self.assertGreaterEqual(stats["cache_hits"], 1)
        finally:
            conn = get_connection(AIDERMY_DB)
            conn.execute("DELETE FROM calibration_references WHERE cache_key=?", (ck,))
            conn.commit()
            conn.close()

    def test_summary_helpers(self):
        self.assertEqual(_drift_group_label("concern:reactive_skin"), "реактивная кожа")
        self.assertEqual(_drift_group_label("sensitive"), "Чувствительная")
        self.assertEqual(_drift_group_label("cat:Сыворотки"), "Сыворотки")
        self.assertEqual(_drift_verdict(10), "Завышает")
        self.assertEqual(_drift_verdict(-10), "Занижает")
        self.assertEqual(_drift_verdict(2), "OK")
        self.assertEqual(_overall_status({"mean_signed_error": 3}, []), "ХОРОШАЯ КАЛИБРОВКА")
        self.assertEqual(_overall_status({"mean_signed_error": 8}, []), "ЕСТЬ СИСТЕМНЫЙ ДРЕЙФ")
        self.assertEqual(_overall_status({"mean_signed_error": 3}, [{"average_drift": 30}]), "СИЛЬНЫЙ ДРЕЙФ")
        self.assertEqual(_overall_status({"mean_signed_error": 16}, []), "СИЛЬНЫЙ ДРЕЙФ")

    def test_build_calibration_summary(self):
        key = create_run({"product_limit": 3})
        self._keys.append(key)
        audit_m = {"case_count": 4, "mae": 15.0, "median_abs_error": 10, "mean_signed_error": 12.0,
                   "range_coverage": 0.5, "overestimation_rate": 0.4, "underestimation_rate": 0.1}
        drift = [
            {"group": "concern:reactive_skin", "cases": 30, "average_drift": 25.1, "outside_range": 29,
             "confidence": 0.6, "potential_cause": "X"},
            {"group": "sensitive", "cases": 90, "average_drift": -10.0, "outside_range": 50,
             "confidence": 0.6, "potential_cause": "Y"},
        ]
        update_run(key, status="completed", metrics=json.dumps({"audit": audit_m, "drift": drift}))

        products = [{"id": 100001, "name": "Product A", "ingredients": "water"},
                    {"id": 100002, "name": "Product B", "ingredients": "water"}]
        profiles = [profile_by_id("P03"), profile_by_id("P06")]
        results = []
        refs = {}
        for p in products:
            for pr in profiles:
                est = 50 if p["id"] == 100001 else 60
                ref = {"product_id": p["id"], "profile_id": pr["id"], "range_min": est - 10,
                       "range_max": est + 10, "estimate": est, "confidence": 0.7}
                refs[f'{p["id"]}:{pr["id"]}'] = ref
                results.append({"product": p, "profile": pr, "score": est + 30, "verdict": "ok", "trace": {}})
        self.assertEqual(persist_calibration_cases(key, results, refs), 4)

        s = build_calibration_summary(key)
        self.assertEqual(s["overall_status"], "СИЛЬНЫЙ ДРЕЙФ")
        self.assertEqual(s["verdict"]["cases"], 4)
        self.assertEqual(s["verdict"]["coverage_pct"], 50.0)
        self.assertEqual(len(s["drift_groups"]), 2)
        self.assertEqual(s["drift_groups"][0]["group"], "реактивная кожа")
        self.assertEqual(s["drift_groups"][0]["verdict"], "Завышает")
        self.assertEqual(s["drift_groups"][1]["verdict"], "Занижает")
        self.assertEqual(len(s["top_cases"]), 4)
        self.assertEqual(s["top_cases"][0]["difference"], 30)

    def test_case_detail_trace(self):
        key = self._mk()
        update_run(key, status="completed", metrics=json.dumps({"audit": {}, "drift": []}))
        product = {"id": 100010, "name": "Trace Product", "ingredients": "aqua, glycerin"}
        profile = profile_by_id("P03")
        ref = {"product_id": 100010, "profile_id": "P03", "range_min": 40, "range_max": 60,
               "estimate": 50, "confidence": 0.7}
        refs = {f'{product["id"]}:{profile["id"]}': ref}
        results = [{"product": product, "profile": profile, "score": 71, "verdict": "Подходит", "trace": {}}]
        self.assertEqual(persist_calibration_cases(key, results, refs), 1)

        d = get_case_detail(key, 100010, "P03")
        self.assertIsNotNone(d)
        self.assertIn("100010", d["product"])
        self.assertEqual(d["profile"], profile["label"])
        self.assertEqual(d["score"], 71)
        self.assertEqual(d["drift"], 21)
        self.assertEqual(len(d["axis_breakdown"]), 6)
        self.assertIn("hydration", [a["axis"] for a in d["axis_breakdown"]])
        self.assertEqual(d["final_aggregation"]["final_score"], 71)


if __name__ == "__main__":
    unittest.main()
