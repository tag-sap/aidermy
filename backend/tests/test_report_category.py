"""Тесты category-aware «Как применять» и включения полного 4-layer Match."""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import _category_application_hint, generate_ai_report_sections
from app.scoring_config import INTERACTION_SCORING_ENABLED_DEFAULT


class CategoryApplicationHintTests(unittest.TestCase):
    def test_patch_not_spread_evenly(self):
        hint = _category_application_hint("Патчи")
        self.assertTrue(hint)
        text = (hint["how_to_use"]["application"] + " " + hint["how_to_use"]["time"]).lower()
        self.assertIn("наклейте", text)
        self.assertNotIn("ровным слоем", text)

    def test_toner_after_cleansing(self):
        hint = _category_application_hint("Тонизирование")
        self.assertIn("очищени", hint["how_to_use"]["application"].lower())

    def test_serum(self):
        hint = _category_application_hint("Сыворотки")
        self.assertIn("сыворотк", hint["how_to_use"]["application"].lower())

    def test_cream(self):
        hint = _category_application_hint("Кремы")
        self.assertIn("крем", hint["how_to_use"]["application"].lower())

    def test_mask_type_aware(self):
        hint = _category_application_hint("Маски")
        self.assertIn("типу", hint["how_to_use"]["application"].lower())

    def test_cleanser_rinse(self):
        hint = _category_application_hint("Очищение и демакияж")
        app = hint["how_to_use"]["application"].lower()
        self.assertIn("смойте", app)
        self.assertIn("влажную кожу лица", app)

    def test_lips_not_face(self):
        hint = _category_application_hint("Уход для губ")
        self.assertIn("губы", hint["how_to_use"]["application"].lower())

    def test_hair_shampoo_not_face(self):
        hint = _category_application_hint("Шампуни")
        self.assertIn("волосы", hint["how_to_use"]["application"].lower())


class ReportSectionsCategoryAwareTests(unittest.TestCase):
    def test_sections_fallback_patch_when_no_factors(self):
        # Без факторов → детерминированный category-aware how_to_use (не универсальный крем-шаблон).
        result = asyncio.run(generate_ai_report_sections(
            "Patch",
            {"positive_factors": [], "negative_factors": []},
            {},
            "Патчи",
        ))
        self.assertTrue(result["how_to_use"])
        self.assertIn("наклейте", result["how_to_use"]["application"].lower())

    def test_interaction_scoring_enabled_in_production(self):
        self.assertTrue(INTERACTION_SCORING_ENABLED_DEFAULT)


if __name__ == "__main__":
    unittest.main()
