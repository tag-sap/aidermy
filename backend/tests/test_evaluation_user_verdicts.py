"""User-facing verdict projection: no 0–100 scales in the report."""
from __future__ import annotations

import unittest

from app.evaluation.analysis import AnalysisReport
from app.evaluation.gaps import AnalysisState, ParameterGap


def make_report(rows, *, inci="Aqua, Glycerin, Niacinamide", gaps=(), evidence=None):
    evidence = evidence if evidence is not None else {
        "skin_type:normal": [
            {
                "id": 1,
                "verification": "confirmed",
                "quote": "not shown",
                "source": {"url": "https://example.com/source"},
            }
        ]
    }
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
        evidence=evidence,
        primary_function={
            "label": "Очищение",
            "purpose": "Очистить кожу.",
            "score": None,
            "reason": "Функция определена по категории.",
            "basis": [],
        },
    )


def row(parameter_id: str, value, *, label: str = "", included: bool = True, summary: str | None = None):
    return {
        "parameter_id": parameter_id,
        "label": label or parameter_id,
        "value": value,
        "included": included,
        "summary": summary if summary is not None else f"Объяснение для {parameter_id}",
    }


class OverallVerdictTests(unittest.TestCase):
    def test_all_positive_is_suitable(self):
        public = make_report([row("skin_type:normal", 100)]).user_report()
        self.assertEqual(public["overall"]["verdict"], "Отлично подходит")
        self.assertEqual(public["overall"]["positive"], 1)
        self.assertEqual(public["personal_compatibility"][0]["verdict_icon"], "happy")

    def test_relevant_benefit_without_harm_is_positive(self):
        # A cleanser need not treat dryness to be compatible with it. A mixed
        # benefit score without confirmed harm is compatibility, not a warning.
        public = make_report([row("problem:dryness", 50)]).user_report()
        self.assertEqual(public["overall"]["verdict"], "Отлично подходит")
        self.assertEqual(public["personal_compatibility"][0]["verdict"], "positive")
        self.assertEqual(public["personal_compatibility"][0]["verdict_icon"], "happy")

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

    def test_moderate_confirmed_risk_evidence_becomes_caution(self):
        public = make_report(
            [row("therapy:benzoyl_peroxide", 50, label="Совместимость с лечением: «Бензоилпероксид»")],
            evidence={
                "therapy:benzoyl_peroxide": [
                    {
                        "verification": "confirmed",
                        "direction": "contradicts",
                        "strength": "moderate",
                        "confidence": 0.8,
                        "claim": "Кислоты увеличивают раздражающую нагрузку.",
                    },
                    {
                        "verification": "confirmed",
                        "direction": "supports",
                        "strength": "moderate",
                        "confidence": 0.7,
                        "claim": "Есть успокаивающие компоненты.",
                    },
                ]
            },
        ).user_report()
        item = public["personal_compatibility"][0]
        self.assertEqual(item["verdict"], "caution")
        self.assertEqual(item["risk_kind"], "probable")
        self.assertEqual(
            item["display_text"],
            "С лечением «Бензоилпероксид» возможна осторожность.",
        )
        self.assertEqual(item["status_label"], "С осторожностью")
        self.assertTrue(item["risk"])
        self.assertTrue(item["recommendation"])
        self.assertEqual(public["overall"]["verdict"], "Подходит частично")

    def test_sorting_is_positive_caution_unknown(self):
        public = make_report(
            [
                row("problem:dryness", 50, label="Проблема: «Сухость»"),
                row("skin_type:normal", 100, label="Тип кожи: «Нормальная»"),
                row("goal:acne", 0, label="Цель: «Убрать акне»"),
            ],
            gaps=(ParameterGap("goal:hydration", "missing", "оценки нет"),),
        ).user_report()
        self.assertEqual(
            [item["verdict"] for item in public["personal_compatibility"]],
            ["positive", "positive", "neutral", "unknown"],
        )

    def test_long_explanation_is_trimmed_at_sentence_boundary(self):
        public = make_report(
            [
                row(
                    "skin_type:normal",
                    75,
                    label="Тип кожи: «Нормальная»",
                    summary=(
                        "Состав соответствует нормальной коже. "
                        "Он не содержит подтверждённых раздражителей. "
                        "Оценка 75/100. За требование: длинная цитата."
                    ),
                )
            ]
        ).user_report()
        explanation = public["personal_compatibility"][0]["explanation"]
        self.assertEqual(
            explanation,
            "Состав соответствует нормальной коже. Он не содержит подтверждённых раздражителей.",
        )
        self.assertNotIn("Оценка", explanation)

    def test_low_goal_without_confirmed_harm_is_not_a_warning(self):
        public = make_report(
            [
                row("skin_type:normal", 100),
                row("goal:acne", 0, label="Цель: «Убрать акне»"),
            ]
        ).user_report()
        self.assertEqual(public["overall"]["verdict"], "Хорошо подходит")
        self.assertEqual(public["overall"]["negative"], 0)
        self.assertEqual(public["overall"]["caution"], 0)
        self.assertEqual(
            public["personal_compatibility"][1]["verdict"],
            "neutral",
        )
        self.assertEqual(
            public["personal_compatibility"][1]["verdict_label"],
            "Цель не подтверждена",
        )

    def test_cleanser_brightening_goal_is_not_a_caution_or_false_efficacy(self):
        report = make_report(
            [
                row("skin_type:oily", 75, label="Тип кожи: «Жирная»"),
                row("goal:brightening", 100, label="Цель: «Выровнять тон»"),
            ],
        )
        report.product.update({
            "category": "Очищение",
            "subcategory": "Очищение и демакияж",
            "name": "ROUND LAB 1025 Dokdo Cleanser",
        })
        public = report.user_report()
        ids = {item["parameter_id"] for item in public["personal_compatibility"]}
        self.assertNotIn("goal:brightening", ids)
        self.assertEqual(public["overall"]["caution"], 0)
        self.assertEqual(public["overall"]["negative"], 0)

    def test_confirmed_risk_still_wins_over_goal_relevance(self):
        report = make_report(
            [row("goal:brightening", 50, label="Цель: «Выровнять тон»")],
            evidence={
                "goal:brightening": [{
                    "verification": "confirmed",
                    "direction": "contradicts",
                    "strength": "moderate",
                    "confidence": 0.8,
                    "claim": "Подтверждённый раздражающий риск.",
                }]
            },
        )
        report.product.update({
            "category": "Очищение",
            "subcategory": "Очищение и демакияж",
        })
        public = report.user_report()
        goal = public["personal_compatibility"][0]
        self.assertEqual(goal["verdict"], "caution")
        self.assertTrue(goal["risk"])
        self.assertEqual(public["overall"]["caution"], 1)

    def test_not_applicable_parameter_is_omitted_and_not_aggregated(self):
        public = make_report(
            [row("problem:acne_general", None, included=False)],
        ).user_report()
        self.assertEqual(public["personal_compatibility"], [])
        self.assertEqual(public["overall"]["assessed"], 0)
        self.assertEqual(public["overall"]["verdict"], "Недостаточно данных")

    def test_unknown_only_is_insufficient_and_never_a_check(self):
        public = make_report(
            [],
            gaps=(ParameterGap("problem:dryness", "missing", "оценки нет"),),
        ).user_report()
        self.assertEqual(public["overall"]["verdict"], "Недостаточно данных")
        self.assertEqual(public["overall"]["unknown"], 1)
        self.assertEqual(public["personal_compatibility"][0]["verdict"], "unknown")
        self.assertEqual(public["personal_compatibility"][0]["verdict_icon"], "neutral")

    def test_unknown_next_to_positive_adds_a_caveat_not_a_check(self):
        public = make_report(
            [row("skin_type:normal", 100)],
            gaps=(ParameterGap("problem:dryness", "missing", "оценки нет"),),
        ).user_report()
        self.assertEqual(public["overall"]["verdict"], "Подходит частично")
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

    def test_display_sentences_are_concrete_and_short(self):
        public = make_report(
            [
                row("therapy:adapalene", 0, label="Совместимость с лечением: «Адапален»"),
                row(
                    "procedure:recent_biorevitalization@<7",
                    100,
                    label="Уход после процедуры: «Биоревитализация», Последние 7 дней",
                ),
                row("problem:acne_general", 50, label="Проблема: «Высыпания»"),
            ]
        ).user_report()
        items = {item["parameter_id"]: item for item in public["personal_compatibility"]}
        self.assertEqual(
            items["therapy:adapalene"]["display_text"],
            "Не рекомендуется использовать с лечением «Адапален».",
        )
        self.assertEqual(
            items["procedure:recent_biorevitalization@<7"]["display_text"],
            "Можно использовать после процедуры «Биоревитализация» (первые 7 дней).",
        )
        self.assertEqual(
            items["problem:acne_general"]["display_text"],
            "Соответствует задаче «Высыпания».",
        )

    def test_unknown_display_text_is_not_positive(self):
        public = make_report(
            [],
            gaps=(ParameterGap("problem:dryness", "missing", "оценки нет"),),
        ).user_report()
        item = public["personal_compatibility"][0]
        self.assertEqual(item["verdict"], "unknown")
        self.assertTrue(item["display_text"].startswith("Не удалось определить"))


class IntoleranceVerdictTests(unittest.TestCase):
    def _item(self, inci: str):
        public = make_report(
            [row("intolerance:niacinamide_intolerance", 100, label="Наличие в составе: «Ниацинамид»")],
            inci=inci,
        ).user_report()
        return public["personal_compatibility"][0]

    def test_present_is_a_negative_restriction_answer(self):
        item = self._item("Aqua, Glycerin, Niacinamide")
        self.assertEqual(item["verdict"], "negative")
        self.assertEqual(item["verdict_icon"], "dead")
        self.assertEqual(item["verdict_label"], "Обнаружен в составе")

    def test_absent_is_a_positive_restriction_answer(self):
        item = self._item("Aqua, Glycerin")
        self.assertEqual(item["verdict"], "positive")
        self.assertEqual(item["verdict_icon"], "happy")
        self.assertEqual(item["verdict_label"], "Не обнаружен в составе")

    def test_absent_intolerance_satisfies_the_restriction(self):
        public = make_report(
            [row("intolerance:niacinamide_intolerance", 0)],
            inci="Aqua, Glycerin",
        ).user_report()
        self.assertEqual(public["overall"]["verdict"], "Отлично подходит")

    def test_unconfirmed_is_neutral_unknown(self):
        item = self._item("")
        self.assertEqual(item["verdict"], "unknown")
        self.assertEqual(item["verdict_icon"], "neutral")
        self.assertEqual(item["verdict_label"], "Не удалось определить")


if __name__ == "__main__":
    unittest.main()
