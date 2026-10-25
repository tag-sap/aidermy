"""Frontend payload contract for Evaluation V2.

The quiz in ``figma-make-preview`` must send every questionnaire section with
stable ids (labels are kept only for the legacy API). These tests read the real
``App.tsx``/``data.ts`` sources — no browser, no network.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from app.evaluation import resolve_parameters

FRONTEND = Path(__file__).resolve().parents[2] / "figma-make-preview" / "src"
APP_TSX = FRONTEND / "App.tsx"
DATA_TS = FRONTEND / "data.ts"
PANEL_TSX = FRONTEND / "evaluation-v2.tsx"
API_TS = FRONTEND / "api.ts"
MAPPING_TS = FRONTEND / "mapping.ts"


def _save_block(source: str) -> str:
    start = source.index("const structured = {")
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start: index + 1]
    raise AssertionError("structured block is not closed")


class FrontendPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not APP_TSX.exists():  # pragma: no cover - repository layout guard
            raise unittest.SkipTest(f"frontend source not found: {APP_TSX}")
        cls.source = APP_TSX.read_text(encoding="utf-8")
        cls.block = _save_block(cls.source)

    def test_structured_payload_has_all_sections_with_stable_ids(self):
        for key in (
            "skin_type",
            "age",
            "concerns",
            "therapy",
            "procedures",
            "intolerances",
            "goals",
        ):
            self.assertRegex(
                self.block,
                rf"(?m)^\s+{key}(,|:)",
                f"structured payload must contain {key!r} with stable ids",
            )

    def test_intolerances_and_goals_are_sent_as_ids_not_labels(self):
        # The raw id arrays are sent; labels stay only in the legacy fields.
        self.assertRegex(self.block, r"(?m)^\s+intolerances,$")
        self.assertRegex(self.block, r"(?m)^\s+goals,$")
        self.assertIn(
            "allergies: intolerances.map((i) => INTOLERANCE_OPTIONS.find((o) => o.id === i)?.label ?? i)",
            self.source,
        )

    def test_concerns_are_sent_as_ids_and_labels(self):
        self.assertRegex(self.block, r"(?m)^\s+concerns: cards,$")
        self.assertIn(
            "concerns: cards.map((c) => CONCERN_CARDS.find((b) => b.id === c)?.label ?? c)",
            self.source,
        )

    def test_therapy_and_procedures_use_stable_ids(self):
        self.assertRegex(self.block, r"(?m)^\s+therapy: structuredTherapy,$")
        self.assertRegex(
            self.block,
            r"procedures: Object\.entries\(procedures\)\.map\(\(\[id, period\]\) => \(\{ id, period \}\)\)",
        )

    def test_ids_declared_in_the_payload_exist_in_the_questionnaire(self):
        data = DATA_TS.read_text(encoding="utf-8")
        ids = set(re.findall(r'id: "([^"]+)"', data))
        for required in (
            "dry",
            "acne_general",
            "tretinoin",
            "recent_laser",
            "fragrance_intolerance",
            "hydration",
        ):
            self.assertIn(required, ids)

    def test_frontend_shaped_payload_resolves_to_expected_parameters(self):
        payload = {
            "skin_type": "dry",
            "age": "25_35",
            "concerns": ["Высыпания"],
            "allergies": ["Отдушки"],
            "structured": {
                "skin_type": "dry",
                "age": "25_35",
                "concerns": ["acne_general"],
                "therapy": [{"id": "tretinoin", "active": True}],
                "procedures": [{"id": "recent_laser", "period": "<7"}],
                "intolerances": ["fragrance_intolerance"],
                "goals": ["hydration"],
            },
        }
        resolved = resolve_parameters(payload)
        self.assertEqual(
            tuple(item.id for item in resolved.parameters),
            (
                "goal:hydration",
                "intolerance:fragrance_intolerance",
                "problem:acne_general",
                "procedure:recent_laser@<7",
                "skin_type:dry",
                "therapy:tretinoin",
            ),
        )
        self.assertEqual(resolved.unresolved, ())

    def test_age_stays_context_and_never_becomes_a_parameter(self):
        resolved = resolve_parameters(
            {"age": "45_plus", "structured": {"age": "45_plus"}}
        )
        self.assertEqual(resolved.parameters, ())


class EvaluationV2UiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not APP_TSX.exists() or not PANEL_TSX.exists():  # pragma: no cover
            raise unittest.SkipTest("frontend sources not found")
        cls.app = APP_TSX.read_text(encoding="utf-8")
        cls.panel = PANEL_TSX.read_text(encoding="utf-8")
        cls.api = API_TS.read_text(encoding="utf-8")
        cls.mapping = MAPPING_TS.read_text(encoding="utf-8")

    def test_product_drawer_has_no_legacy_current_report(self):
        drawer = self.app[self.app.index("function ProductDrawer") :]
        for legacy in ("Скрыть отчёт", "drawer__report-wrap", "Проверить совместимость"):
            self.assertNotIn(legacy, drawer, f"legacy drawer UI must not contain {legacy!r}")
        self.assertIn("EvaluationV2Panel", drawer)
        self.assertIn("<EvaluationV2Panel", drawer)

    def test_v2_panel_has_one_check_product_action(self):
        self.assertIn("Проверить", self.panel)
        self.assertNotIn("Проверить для меня", self.panel)
        self.assertNotIn("Проверить продукт", self.panel)
        self.assertNotIn("Оценить продукт", self.panel)
        self.assertNotIn("Проверить состав", self.panel)
        self.assertIn("compatApi.startIndividual", self.panel)
        self.assertIn("compatApi.task", self.panel)
        self.assertIn("Проверка запущена", self.panel)
        self.assertNotIn("evaluationProductEvaluate", self.panel)
        self.assertNotIn("evaluationProductAnalyze", self.panel)
        self.assertIn("v2Started", self.app)

    def test_v2_report_is_a_compact_numbered_verdict_list(self):
        self.assertIn("Базовая функция", self.panel)
        self.assertIn("evalv2__verdicts", self.panel)
        self.assertIn("evalv2__primary-factors", self.panel)
        self.assertIn("number={1}", self.panel)
        self.assertIn("number={2}", self.panel)
        self.assertIn("evalv2__info", self.panel)
        self.assertIn("aria-expanded", self.panel)
        self.assertIn("Источники", self.panel)
        self.assertIn("Не удалось проверить", self.panel)
        self.assertIn("display_text", self.panel)
        self.assertIn("LoadingState", self.panel)
        self.assertIn("Проверяем продукт", self.panel)
        self.assertNotIn("Персональная совместимость", self.panel)
        self.assertNotIn("Почему такой вывод", self.panel)
        self.assertNotIn("overall-counts", self.panel)
        self.assertNotIn("Проверено:", self.panel)
        self.assertNotIn("AI", self.panel)
        self.assertNotIn("◈", self.panel)
        for technical in (
            "Среднее по",
            "Оценено:",
            "Незавершённая оценка",
            "Что осталось непроверенным",
            "Вердикт отключён",
            "Проверить снова",
            "snapshot?.total",
            "analysis.gaps",
        ):
            self.assertNotIn(technical, self.panel, technical)
        self.assertNotIn("total", self.panel)

    def test_async_profile_update_reaches_mounted_report(self):
        self.assertIn("aidermy-profile-updated", self.mapping)
        self.assertIn("aidermy-profile-updated", self.app)

    def test_saved_report_loading_error_is_visible_and_not_missing(self):
        self.assertIn("setRestoreError", self.panel)
        self.assertIn("Не удалось загрузить сохранённый отчёт", self.panel)
        self.assertIn("restoreError", self.panel)

    def test_v2_panel_shows_human_function_and_comedo_states(self):
        self.assertIn("Хорошо выполняет свою задачу", self.panel)
        self.assertIn("Частично выполняет свою задачу", self.panel)
        self.assertIn("Соответствие не подтверждено", self.panel)
        self.assertIn("Что означают тюбики?", self.panel)
        self.assertIn("isRowToggleTarget", self.panel)
        self.assertIn("isRowToggleTarget(event.target)", self.panel)
        self.assertIn("duplicateFunctionNote", self.panel)
        self.assertIn("comedoIcon", self.panel)
        self.assertIn("<VerdictIcon icon={verdict.icon} />", self.panel)
        self.assertIn("<VerdictIcon icon={comedoIcon(item)} />", self.panel)
        self.assertIn("score_note", self.panel)
        self.assertIn("Роль продукта", self.panel)
        self.assertIn('"Недостаточно данных": "Комедогенные факторы не выявлены"', self.panel)
        self.assertIn('coverage_sufficient === true ? "happy" : "neutral"', self.panel)
        self.assertIn("COMEDO_HIDDEN_BASIS", self.panel)
        self.assertIn("stripComedoDataNotes", self.panel)
        comedo_source = self.panel[
            self.panel.index("function comedoRiskLabel"):self.panel.index("function VerdictRow")
        ]
        self.assertNotIn('"Недостаточно данных"', comedo_source)
        self.assertIn("Комедогенные факторы не выявлены", comedo_source)
        self.assertIn("Низкий потенциальный риск", comedo_source)
        self.assertIn("Есть основания для осторожности", comedo_source)
        self.assertIn("Повышенное внимание к комедогенности", comedo_source)
        self.assertIn("Выраженный потенциальный фактор риска", comedo_source)

    def test_api_exposes_composition_check(self):
        self.assertIn("evaluationCompositionCheck", self.api)
        self.assertIn("/composition/check", self.api)
        self.assertIn("EvaluationCompositionState", self.api)

    def test_personal_check_status_is_user_scoped_and_exposed(self):
        self.assertIn("evaluationProductStatuses", self.api)
        self.assertIn("/products/statuses", self.api)
        self.assertIn("applyCheckStatuses", self.mapping)
        self.assertIn("match: undefined", self.mapping)
        self.assertIn("authEpochRef", self.app)
        self.assertIn("clearPersonalState", self.app)
        self.assertIn("resetUserProfile", self.app)
        self.assertIn("resetUserProfile", self.mapping)
        self.assertIn("export const compatApi", self.api)
        self.assertIn("startCompatibility", self.api)
        self.assertIn("startIndividual", self.api)
        self.assertIn("async notifications", self.api)
        self.assertIn("check: undefined", self.app)
        self.assertIn("Проверено", self.app)
        self.assertIn("Данные устарели", self.app)
        self.assertIn("Проверить", self.app)
        # The global composition marker must not be rendered as a personal check.
        self.assertNotIn("pcard__verified", self.app)
        self.assertNotIn("Проверенный продукт", self.app)

    def test_shelf_compatibility_selection_and_async_task_contract(self):
        self.assertIn("compatApi.startCompatibility", self.app)
        self.assertIn("onTaskStarted", self.app)
        self.assertIn("shelf-tab", self.app)
        self.assertIn("shelf-search", self.app)
        self.assertIn("shelf-list__collect", self.app)
        self.assertIn("shelf-list__state", self.app)
        self.assertIn("updateShelfState", self.api)
        self.assertIn("＋ В набор", self.app)
        self.assertIn("✓ В наборе", self.app)
        self.assertIn("compat-cart", self.app)
        self.assertIn("CompatibilityReportView", self.app)
        self.assertIn("COMPAT_STATUS_LABEL", self.app)
        self.assertIn("/icons/to_my_shelf.svg", self.app)
        self.assertIn("compatApi.startIndividual", self.panel)
        # The check action starts a durable server task, not a long HTTP check.
        self.assertNotIn("handleBatchRefresh", self.app)
        self.assertNotIn("Не закрывайте раздел до завершения", self.app)
        # Remove controls are centered SVG icons, not a baseline-shifted glyph.
        self.assertIn('className="shelf-list__remove"', self.app)
        self.assertIn('<Icon name="close" size={15} />', self.app)

    def test_shelf_is_a_compact_list_with_real_capacity_copy(self):
        self.assertIn("shelf-info", self.app)
        self.assertIn("shelf-info__capacity", self.app)
        self.assertIn("Добавлено {totalShelved} из {limit} продуктов", self.app)
        self.assertIn("Осталось ${remaining}", self.app)
        self.assertIn("Лимит полки достигнут", self.app)
        self.assertIn("shelf-list__thumb", self.app)
        self.assertIn("shelf-list__check", self.app)
        self.assertIn("shelf-empty", self.app)
        self.assertNotIn("shelf-summary", self.app)
        self.assertNotIn("средняя совместимость", self.app)
        self.assertNotIn("как сочетаются средства", self.app)
        self.assertNotIn("shelf-rack-wrap", self.app)


if __name__ == "__main__":
    unittest.main()
