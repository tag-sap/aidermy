"""Regression: production config store — validate, apply, rollback, audit log."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import AIDERMY_DB, get_connection
from app.scoring_config_store import (
    apply_production_config,
    get_audit_log,
    get_production_config,
    get_production_saturation_scale,
    rollback_production_config,
    validate_production_config,
)

TEST_AUTHOR = "test_runner"


class ScoringConfigStoreTests(unittest.TestCase):
    def tearDown(self):
        conn = get_connection(AIDERMY_DB)
        conn.execute("DELETE FROM scoring_config_versions WHERE applied_by=?", (TEST_AUTHOR,))
        conn.execute("DELETE FROM scoring_audit_log WHERE author=?", (TEST_AUTHOR,))
        conn.commit()
        conn.close()

    def test_validate_rejects_unknown_and_bad_params(self):
        self.assertIsNone(validate_production_config({"saturation_scale": 2.0}))
        self.assertIsNotNone(validate_production_config({"saturation_scale": "abc"}))
        self.assertIsNotNone(validate_production_config({"saturation_scale": 0.01}))
        self.assertIsNotNone(validate_production_config({"saturation_scale": 99}))
        self.assertIsNotNone(validate_production_config({"axis_weights": {"hydration": 1.0}}))
        self.assertIsNotNone(validate_production_config("not_a_dict"))

    def test_apply_bumps_version_and_rollback_restores(self):
        before = get_production_config()
        applied = apply_production_config({"saturation_scale": 2.5}, "test apply", TEST_AUTHOR)
        self.assertNotEqual(applied["version"], before["version"])
        self.assertEqual(applied["saturation_scale"], 2.5)
        self.assertEqual(get_production_saturation_scale(), 2.5)

        rolled = rollback_production_config("test rollback", TEST_AUTHOR)
        self.assertEqual(rolled["saturation_scale"], before["saturation_scale"])
        self.assertEqual(get_production_saturation_scale(), before["saturation_scale"])

        log = get_audit_log(50)
        events = [e["event"] for e in log if e["author"] == TEST_AUTHOR]
        self.assertIn("apply_config", events)
        self.assertIn("rollback_config", events)


if __name__ == "__main__":
    unittest.main()
