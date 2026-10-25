"""Deterministic priority rules for the user-facing overall verdict."""
from __future__ import annotations

import unittest

from app.evaluation.analysis import _overall_verdict

POSITIVE = {
    "parameter_id": "skin_type:normal",
    "verdict": "positive",
    "label": "Нормальная кожа",
    "verdict_label": "Соответствует типу кожи",
}
CAUTION = {
    "parameter_id": "therapy:benzoyl_peroxide",
    "verdict": "caution",
    "label": "Бензоилпероксид",
    "verdict_label": "Возможна осторожность",
}
NEGATIVE = {
    "parameter_id": "goal:acne",
    "verdict": "negative",
    "label": "Акне",
    "verdict_label": "Не подходит",
}
CRITICAL = {
    "parameter_id": "therapy:adapalene",
    "verdict": "negative",
    "label": "Адапален",
    "verdict_label": "Конфликт с лечением",
}
UNKNOWN = {
    "parameter_id": "problem:dryness",
    "verdict": "unknown",
    "label": "Сухость",
    "verdict_label": "Не удалось определить",
}


class OverallPriorityTests(unittest.TestCase):
    def test_excellent_score_is_capped_by_confirmed_caution(self):
        result = _overall_verdict([POSITIVE, CAUTION], score=95)
        self.assertEqual(result["verdict"], "Подходит частично")
        self.assertEqual(result["tone"], "neutral")
        self.assertIn("требует осторожности", result["summary"])

    def test_noncritical_negative_caps_at_weak_not_excellent(self):
        result = _overall_verdict([POSITIVE, NEGATIVE], score=95)
        self.assertEqual(result["verdict"], "Слабо подходит")
        self.assertEqual(result["tone"], "warn")
        self.assertIn("подтверждённый конфликт", result["summary"])

    def test_critical_conflict_still_wins_over_everything(self):
        result = _overall_verdict([POSITIVE, CRITICAL], score=95)
        self.assertEqual(result["verdict"], "Не подходит")
        self.assertEqual(result["tone"], "bad")

    def test_unconfirmed_primary_function_caps_at_partial(self):
        result = _overall_verdict(
            [POSITIVE],
            score=95,
            primary_function={"status": "insufficient_evidence", "score": None},
        )
        self.assertEqual(result["verdict"], "Подходит частично")
        self.assertIn("Базовая функция не подтверждена", result["summary"])

    def test_minimal_primary_support_caps_at_good(self):
        result = _overall_verdict(
            [POSITIVE],
            score=95,
            primary_function={"status": "assessed", "score": 50},
        )
        self.assertEqual(result["verdict"], "Хорошо подходит")
        self.assertIn("минимально поддерживает", result["summary"])

    def test_strong_primary_support_does_not_cap(self):
        result = _overall_verdict(
            [POSITIVE],
            score=95,
            primary_function={"status": "assessed", "score": 65},
        )
        self.assertEqual(result["verdict"], "Отлично подходит")

    def test_high_comedo_status_caps_at_partial(self):
        result = _overall_verdict(
            [POSITIVE],
            score=95,
            comedogenicity={"status": "assessed", "applicable": True, "level": "high"},
        )
        self.assertEqual(result["verdict"], "Подходит частично")
        self.assertIn("фактор риска", result["summary"])

    def test_elevated_or_medium_comedo_caps_at_good(self):
        for level in ("elevated", "medium"):
            with self.subTest(level=level):
                result = _overall_verdict(
                    [POSITIVE],
                    score=95,
                    comedogenicity={"status": "assessed", "applicable": True, "level": level},
                )
                self.assertEqual(result["verdict"], "Хорошо подходит")
                self.assertIn("требующие внимания", result["summary"])

    def test_low_or_absent_comedo_factors_do_not_cap(self):
        for level in ("none", "low"):
            with self.subTest(level=level):
                result = _overall_verdict(
                    [POSITIVE],
                    score=95,
                    comedogenicity={"status": "assessed", "applicable": True, "level": level},
                )
                self.assertEqual(result["verdict"], "Отлично подходит")

    def test_insufficient_comedo_data_is_not_a_negative_or_a_safety_claim(self):
        result = _overall_verdict(
            [POSITIVE],
            score=95,
            comedogenicity={"status": "insufficient_evidence", "applicable": True, "level": "unknown"},
        )
        self.assertEqual(result["verdict"], "Отлично подходит")
        self.assertEqual(result["tone"], "good")

    def test_unknown_item_prevents_top_verdict_but_is_not_negative(self):
        result = _overall_verdict([POSITIVE, UNKNOWN], score=95)
        self.assertEqual(result["verdict"], "Хорошо подходит")
        self.assertIn("Часть пунктов не проверена", result["summary"])

    def test_same_inputs_and_rules_are_deterministic(self):
        kwargs = {
            "score": 95,
            "primary_function": {"status": "assessed", "score": 50},
            "comedogenicity": {"status": "assessed", "applicable": True, "level": "medium"},
        }
        first = _overall_verdict([POSITIVE, CAUTION], **kwargs)
        second = _overall_verdict([POSITIVE, CAUTION], **kwargs)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
