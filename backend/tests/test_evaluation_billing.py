"""Evaluation V2 charges one point only after a saved, final report."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.evaluation.api import _charge_evaluation


def report(*, final: bool = True):
    return SimpleNamespace(
        is_final=final,
        snapshot={
            "engine_version": "test-v1",
            "product": {"id": 42},
            "composition": {"hash": "a" * 64},
        },
    )


class EvaluationBillingTests(unittest.TestCase):
    def test_final_saved_report_charges_once(self):
        with patch("app.database.change_balance", return_value=19) as charge:
            _charge_evaluation(7, report(), {"skin_type": "dry"})
        charge.assert_called_once()
        args, kwargs = charge.call_args
        self.assertEqual(args[:2], (7, -1))
        self.assertIn("idempotency_key", kwargs)

    def test_incomplete_report_is_free(self):
        with patch("app.database.change_balance", return_value=19) as charge:
            _charge_evaluation(7, report(final=False), {"skin_type": "dry"})
        charge.assert_not_called()


if __name__ == "__main__":
    unittest.main()
