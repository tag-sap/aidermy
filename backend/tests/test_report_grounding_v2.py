"""Regression: report grounding v2 — категория + эффекты не должны галлюцинировать.

Фаза 7: essence больше не попадает в «Тонизирование»; отчёт не вправе описывать
свойства вне осей Score Engine (коллаген/регенерация и т.п.) или оси без factors.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import _ground_report_text, _report_allowed_ingredients, _allowed_axes, _has_forbidden_effect, _mentioned_axes
from app.catalog_taxonomy import classify_product


DET = {
    "normalized_ingredients": ["snail secretion filtrate", "betaine", "glycerin"],
    "positive_factors": [
        {"ingredient": "snail secretion filtrate", "property": "hydration", "direction": "positive"},
        {"ingredient": "snail secretion filtrate", "property": "barrier", "direction": "positive"},
    ],
    "negative_factors": [],
}


class ForbiddenEffectTests(unittest.TestCase):
    def test_collagen_rejected(self):
        self.assertTrue(_has_forbidden_effect("Муцин стимулирует выработку коллагена"))

    def test_regeneration_rejected(self):
        self.assertTrue(_has_forbidden_effect("ускоряет регенерацию кожи"))

    def test_hydration_allowed(self):
        self.assertFalse(_has_forbidden_effect("хорошо увлажняет кожу"))


class AxisGroundingTests(unittest.TestCase):
    def setUp(self):
        self.allowed = _report_allowed_ingredients(DET)

    def test_allowed_axis_kept(self):
        out = _ground_report_text("Муцин увлажняет кожу.", self.allowed, False, DET)
        self.assertIsNotNone(out)

    def test_axis_without_factor_rejected(self):
        # sebum имеет вес/упоминание, но факторов по sebum нет → отбросить.
        out = _ground_report_text("Средство матирует жирную кожу.", self.allowed, False, DET)
        self.assertIsNone(out)

    def test_forbidden_effect_rejected(self):
        out = _ground_report_text("Муцин стимулирует коллаген.", self.allowed, False, DET)
        self.assertIsNone(out)


class EssenceCategoryTests(unittest.TestCase):
    def test_essence_maps_to_serums(self):
        p = {"name": "COSRX Advanced Snail 96 Mucin Power Essence", "category": "Тонер", "subcategory": "Тонизирование", "description": ""}
        self.assertEqual(classify_product(p).get("canonical_category"), "Сыворотки")

    def test_toner_stays_toner(self):
        p = {"name": "Biotanys Toner A La Niacinamide", "category": "Тонер", "subcategory": "Тонизирование", "description": ""}
        self.assertEqual(classify_product(p).get("canonical_category"), "Тонизирование")

    def test_serum_stays_serum(self):
        p = {"name": "Avene Ultra Serum Feuchtigkeit", "category": "Сыворотка", "subcategory": "Сыворотки", "description": ""}
        self.assertEqual(classify_product(p).get("canonical_category"), "Сыворотки")


if __name__ == "__main__":
    unittest.main()
