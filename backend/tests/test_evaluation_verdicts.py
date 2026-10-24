"""User-facing five-band verdicts and the four sprite icons."""
from __future__ import annotations

import unittest
from pathlib import Path

from app.evaluation.analysis import _overall_verdict
from app.evaluation.verdicts import icon_for_status, verdict_band, verdict_text

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "figma-make-preview" / "src" / "evaluation-v2.tsx"
APP = ROOT / "figma-make-preview" / "src" / "App.tsx"
MAPPING = ROOT / "figma-make-preview" / "src" / "mapping.ts"
SPRITE = ROOT / "figma-make-preview" / "public" / "icons" / "verdict_icons.svg"


class VerdictBandsTests(unittest.TestCase):
    def test_all_five_bands_and_boundaries(self):
        cases = (
            (0, "Не подходит", "dead"),
            (19, "Не подходит", "dead"),
            (19.99, "Не подходит", "dead"),
            (20, "Слабо подходит", "alert"),
            (39, "Слабо подходит", "alert"),
            (39.99, "Слабо подходит", "alert"),
            (40, "Подходит частично", "neutral"),
            (59, "Подходит частично", "neutral"),
            (59.99, "Подходит частично", "neutral"),
            (60, "Хорошо подходит", "happy"),
            (79, "Хорошо подходит", "happy"),
            (79.99, "Хорошо подходит", "happy"),
            (80, "Отлично подходит", "happy"),
            (100, "Отлично подходит", "happy"),
        )
        for score, label, icon in cases:
            with self.subTest(score=score):
                band = verdict_band(score)
                self.assertIsNotNone(band)
                self.assertEqual(band["label"], label)
                self.assertEqual(band["icon"], icon)

    def test_missing_score_does_not_invent_a_band(self):
        self.assertIsNone(verdict_band(None))
        self.assertEqual(verdict_text(None), "Недостаточно данных")

    def test_overall_uses_score_without_reweighting(self):
        items = [{
            "parameter_id": "skin_type:normal",
            "verdict": "positive",
            "label": "Нормальная",
            "verdict_label": "Соответствует типу кожи",
        }]
        self.assertEqual(_overall_verdict(items, score=19)["verdict"], "Не подходит")
        self.assertEqual(_overall_verdict(items, score=20)["verdict"], "Слабо подходит")
        self.assertEqual(_overall_verdict(items, score=40)["verdict"], "Подходит частично")
        self.assertEqual(_overall_verdict(items, score=60)["verdict"], "Хорошо подходит")
        self.assertEqual(_overall_verdict(items, score=80)["verdict"], "Отлично подходит")

    def test_critical_conflict_cannot_be_hidden_by_a_high_score(self):
        items = [{
            "parameter_id": "therapy:retinoid",
            "verdict": "negative",
            "label": "Ретиноид",
            "verdict_label": "Конфликт с лечением",
        }]
        self.assertEqual(_overall_verdict(items, score=95)["verdict"], "Не подходит")

    def test_semantic_fallback_uses_the_same_five_labels(self):
        positive = {
            "parameter_id": "skin_type:normal", "verdict": "positive",
            "label": "Нормальная", "verdict_label": "Соответствует",
        }
        neutral = {
            "parameter_id": "goal:acne", "verdict": "neutral",
            "label": "Акне", "verdict_label": "Цель не подтверждена",
        }
        caution = {
            "parameter_id": "therapy:adapalene", "verdict": "caution",
            "label": "Адапален", "verdict_label": "Требует осторожности",
        }
        self.assertEqual(_overall_verdict([positive])["verdict"], "Отлично подходит")
        self.assertEqual(_overall_verdict([positive, neutral])["verdict"], "Хорошо подходит")
        self.assertEqual(_overall_verdict([neutral])["verdict"], "Подходит частично")
        self.assertEqual(_overall_verdict([caution])["verdict"], "Подходит частично")


class VerdictIconTests(unittest.TestCase):
    def test_status_icons_are_the_four_existing_assets(self):
        self.assertEqual(icon_for_status("positive"), "happy")
        self.assertEqual(icon_for_status("negative"), "dead")
        self.assertEqual(icon_for_status("caution"), "alert")
        self.assertEqual(icon_for_status("neutral"), "neutral")
        self.assertEqual(icon_for_status("unknown"), "neutral")
        self.assertEqual(icon_for_status("check"), "happy")
        self.assertEqual(icon_for_status("cross"), "dead")
        self.assertEqual(icon_for_status("dash"), "neutral")

    def test_sprite_contains_four_symbols_with_original_gradients(self):
        source = SPRITE.read_text(encoding="utf-8")
        for name in ("dead", "happy", "neutral", "alert"):
            self.assertIn(f'<symbol id="verdict-{name}"', source)
        for gradient in ("deadGradient", "happyGradient", "neutralGradient", "alertGradient"):
            self.assertIn(f'id="{gradient}"', source)
        self.assertIn("feDropShadow", source)
        self.assertNotIn("<text", source)  # labels are accessible names, not tiny art

    def test_panel_uses_sprite_and_has_no_glyph_fallbacks(self):
        source = PANEL.read_text(encoding="utf-8")
        self.assertIn("/icons/verdict_icons.svg#verdict-", source)
        self.assertIn("VERDICT_ICON_BY_STATUS", source)
        for glyph in ("✓", "✕", "⚠", "—"):
            self.assertNotIn(glyph, source)

    def test_legacy_score_fallback_uses_same_labels(self):
        from app.services import _report_verdict_text

        cases = {
            0: "Не подходит",
            19: "Не подходит",
            20: "Слабо подходит",
            39: "Слабо подходит",
            40: "Подходит частично",
            59: "Подходит частично",
            60: "Хорошо подходит",
            79: "Хорошо подходит",
            80: "Отлично подходит",
            100: "Отлично подходит",
        }
        for score, label in cases.items():
            with self.subTest(score=score):
                self.assertEqual(_report_verdict_text(score), label)

    def test_frontend_score_mapping_uses_same_boundaries(self):
        source = MAPPING.read_text(encoding="utf-8")
        for fragment in (
            'if (score < 20) return "Не подходит"',
            'if (score < 40) return "Слабо подходит"',
            'if (score < 60) return "Подходит частично"',
            'if (score < 80) return "Хорошо подходит"',
            'return "Отлично подходит"',
        ):
            self.assertIn(fragment, source)

    def test_report_and_saved_payload_have_consistent_icon(self):
        from app.evaluation.gaps import AnalysisState
        from app.evaluation.analysis import AnalysisReport

        report = AnalysisReport(
            product={"id": 1, "name": "Test"},
            composition={"composition_hash": "a" * 64, "status": "active"},
            snapshot={
                "parameters": [{
                    "parameter_id": "skin_type:normal",
                    "label": "Тип кожи: «Нормальная»",
                    "value": 100,
                    "included": True,
                    "summary": "Соответствует.",
                }],
                "total": 100,
                "analysis": {"status": "complete"},
            },
            analysis=AnalysisState(status="complete", is_final=True),
        )
        public = report.user_report()
        saved = report.as_dict()["user_report"]
        self.assertEqual(public, saved)
        self.assertEqual(public["overall"]["verdict"], "Отлично подходит")
        self.assertEqual(public["overall"]["icon"], "happy")
        self.assertEqual(
            public["personal_compatibility"][0]["verdict_icon"],
            public["overall"]["icon"],
        )

    def test_old_general_verdict_words_are_absent_from_ui_sources(self):
        panel = PANEL.read_text(encoding="utf-8")
        app = APP.read_text(encoding="utf-8")
        for old in ("Скорее не подходит", "Есть нюансы", "Нейтрально", "Нейтральный результат"):
            self.assertNotIn(old, panel)
            self.assertNotIn(old, app)
        # Old labels survive only in the central historical-payload adapter.
        mapping = MAPPING.read_text(encoding="utf-8")
        self.assertIn("LEGACY_VERDICT_ALIASES", mapping)


if __name__ == "__main__":
    unittest.main()
