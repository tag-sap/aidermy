import asyncio
import unittest

from app.scoring_scope import resolve_scoring_scope
from app.services import check_product_with_ingredients


class ScoringScopeTests(unittest.TestCase):
    def test_fragrance_is_not_skin_scored(self):
        scope = resolve_scoring_scope(product_name="Eau de Parfum Rose", category="Парфюмерия")
        self.assertFalse(scope["applies"])
        self.assertEqual(scope["body_area"], "fragrance")
        self.assertTrue(scope["reason"])

    def test_makeup_is_not_skin_scored(self):
        scope = resolve_scoring_scope(product_name="Matte Powder", category="Пудры")
        self.assertFalse(scope["applies"])
        self.assertEqual(scope["body_area"], "makeup")

    def test_face_cream_is_scored(self):
        scope = resolve_scoring_scope(product_name="Barrier Cream", category="Кремы")
        self.assertTrue(scope["applies"])

    def test_eye_category_limits_axes(self):
        scope = resolve_scoring_scope(product_name="Eye Cream", category="Для кожи вокруг глаз")
        self.assertTrue(scope["applies"])
        self.assertEqual(
            set(scope["relevant_axes"]),
            {"hydration", "barrier", "irritation", "sensitization"},
        )

    def test_fragrance_check_returns_no_fake_percentage(self):
        result = asyncio.run(check_product_with_ingredients(
            "Eau de Parfum Rose",
            "Нормальная",
            {"skin_type": "Нормальная", "age": "25-34"},
            "Aqua, Parfum",
            product_category="Парфюмерия",
        ))
        self.assertIsNone(result["score"])
        self.assertEqual(result["phase1_status"], "not_applicable")
        self.assertEqual(result["recommendation_status"], "Не оценивается")
        self.assertFalse(result["score_scope"]["applies"])
