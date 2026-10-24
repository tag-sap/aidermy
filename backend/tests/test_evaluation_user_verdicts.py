"""User-facing verdict projection: no 0–100 scales in the report."""
from __future__ import annotations

import unittest

from app.evaluation.analysis import AnalysisReport
from app.evaluation.gaps import AnalysisState, ParameterGap


def make_report(rows, *, inci="Aqua, Glycerin, Niacinamide", gaps=()):
    return AnalysisReport(
        product={"id": 1, "name": "Test product"},
        composition={
            "composition_hash": "a" * 64,
            "status": "active",
            "inci_raw": inci,
            "source": "https://example.com/product",
        },
        snapshot={"parameters": rows, "analysis": {"status": "complete"}},
        analysis=AnalysisState(
            status="incomplete" if gaps else "complete",
            is_final=not gaps,
            gaps=tuple(gaps),
        ),
        evidence={
            "skin_type:normal": [
                {
                    "id": 1,
                    "verification": "confirmed",
                    "quote": "not shown",
                    "source": {"url": "https://example.com/source"},
                }
            ]
        },
        primary_function={
            "label": "Очищение",
            "purpose": "Очистить кожу.",
            "score": None,
            "reason": "Функция определена по категории.",
            "basis": [],
        },
    )


def row(parameter_id: str, value, *, label: str = "", included: bool = True):
    return {
        "parameter_id": parameter_id,
        "label": label or parameter_id,
        "value": value,
        "included": included,
        "summary": f"Объяснение для {parameter_id}",
    }


class OverallVerdictTests(unittest.TestCase):
    def test_all_positive_is_suitable(self):
        public = make_report([row("skin_type:normal", 100)]).user_report()
        self.assertEqual(public["overall"]["verdict"], "Подходит")
        self.assertEqual(public["overall"]["positive"], 1)
        self.assertEqual(public["personal_compatibility"][0]["verdict_icon"], "check")

    def test_neutral_is_with_caveats(self):
        public = make_report([row("problem:dryness", 50)]).user_report()
        self.assertEqual(public["overall"]["verdict"], "Подходит с оговорками")
        self.assertEqual(public["personal_compatibility"][0]["verdict"], "neutral")
        self.assertEqual(public["personal_compatibility"][0]["verdict_icon"], "dash")

    def test_critical_therapy_conflict_is_not_suitable(self):
        public = make_report(
            [
                row("skin_type:normal", 100),
                row("therapy:adapalene", 0, label="Совместимость с лечением: «Адапален»"),
            ]
        ).user_report()
        self.assertEqual(public["overall"]["verdict"], "Не подходит")
        item = public["personal_compatibility"][1]
        self.assertEqual(item["verdict"], "negative")
        self.assertEqual(item["verdict_label"], "Конфликт с лечением")

    def test_noncritical_goal_conflict_is_with_caveats(self):
        public = make_report(
            [
                row("skin_type:normal", 100),
                row("goal:acne", 0, label="Цель: «Убрать акне»"),
            ]
        ).user_report()
        self.assertEqual(public["overall"]["verdict"], "Подходит с оговорками")
        self.assertEqual(public["overall"]["negative"], 1)

    def test_unknown_only_is_insufficient_and_never_a_check(self):
        public = make_report(
            [],
            gaps=(ParameterGap("problem:dryness", "missing", "оценки нет"),),
        ).user_report()
        self.assertEqual(public["overall"]["verdict"], "Недостаточно данных")
        self.assertEqual(public["overall"]["unknown"], 1)
        self.assertEqual(public["personal_compatibility"][0]["verdict"], "unknown")
        self.assertEqual(public["personal_compatibility"][0]["verdict_icon"], "dash")

    def test_unknown_next_to_positive_adds_a_caveat_not_a_check(self):
        public = make_report(
            [row("skin_type:normal", 100)],
            gaps=(ParameterGap("problem:dryness", "missing", "оценки нет"),),
        ).user_report()
        self.assertEqual(public["overall"]["verdict"], "Подходит с оговорками")
        self.assertEqual(public["overall"]["positive"], 1)
        self.assertEqual(public["overall"]["unknown"], 1)

    def test_procedure_has_period_specific_verdict(self):
        public = make_report(
            [row("procedure:recent_laser@<7", 0, label="Уход после процедуры: «Лазер», Последние 7 дней")]
        ).user_report()
        item = public["personal_compatibility"][0]
        self.assertEqual(item["verdict_label"], "Не рекомендуется в этот период")
        self.assertEqual(public["overall"]["verdict"], "Не подходит")

    def test_sources_are_only_urls(self):
        public = make_report([row("skin_type:normal", 100)]).user_report()
        self.assertEqual(public["sources"], ["https://example.com/source"])


class IntoleranceVerdictTests(unittest.TestCase):
    def _item(self, inci: str):
        public = make_report(
            [row("intolerance:niacinamide_intolerance", 100, label="Наличие в составе: «Ниацинамид»")],
            inci=inci,
        ).user_report()
        return public["personal_compatibility"][0]

    def test_present_is_red_cross(self):
        item = self._item("Aqua, Glycerin, Niacinamide")
        self.assertEqual(item["verdict"], "negative")
        self.assertEqual(item["verdict_icon"], "cross")
        self.assertEqual(item["verdict_label"], "Обнаружен в составе")

    def test_present_intolerance_makes_overall_unsuitable(self):
        public = make_report(
            [row("intolerance:niacinamide_intolerance", 0)],
            inci="Aqua, Glycerin, Niacinamide",
        ).user_report()
        self.assertEqual(public["overall"]["verdict"], "Не подходит")

    def test_absent_is_green_check(self):
        item = self._item("Aqua, Glycerin")
        self.assertEqual(item["verdict"], "positive")
        self.assertEqual(item["verdict_icon"], "check")
        self.assertEqual(item["verdict_label"], "Не обнаружен в составе")

    def test_unconfirmed_is_neutral_unknown(self):
        item = self._item("")
        self.assertEqual(item["verdict"], "unknown")
        self.assertEqual(item["verdict_icon"], "dash")
        self.assertEqual(item["verdict_label"], "Не удалось определить")


if __name__ == "__main__":
    unittest.main()
