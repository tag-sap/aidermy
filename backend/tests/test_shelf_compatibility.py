import unittest

from app.shelf_compatibility import compute_shelf_compatibility


class ShelfCompatibilityTests(unittest.TestCase):
    def test_empty_returns_none(self):
        self.assertIsNone(compute_shelf_compatibility([])["score"])

    def test_single_product_equals_base(self):
        r = compute_shelf_compatibility([{"name": "A", "category": "Крем", "ingredients": "Aqua, Glycerin", "score": 87}])
        self.assertEqual(r["score"], 87)

    def test_no_conflicts_equals_average(self):
        products = [
            {"name": "A", "category": "Очищение", "ingredients": "Aqua, Glycerin", "score": 90},
            {"name": "B", "category": "Увлажнение", "ingredients": "Aqua, Panthenol", "score": 80},
        ]
        r = compute_shelf_compatibility(products)
        # base 85 + coverage bonus 2 = 87, без конфликтов
        self.assertEqual(r["score"], 87)

    def test_conflicting_actives_lower_score(self):
        # Ретинол + салициловая кислота — конфликт (снижает совместимость).
        products = [
            {"name": "Serum with Retinol", "category": "Сыворотки", "ingredients": "Aqua, Retinol", "score": 90},
            {"name": "BHA Toner", "category": "Тонизация", "ingredients": "Aqua, Salicylic Acid", "score": 90},
        ]
        r = compute_shelf_compatibility(products)
        self.assertGreater(len(r["conflicts"]), 0)
        self.assertLess(r["score"], 90)

    def test_duplicate_actives_soft_penalty(self):
        products = [
            {"name": "A", "category": "Сыворотки", "ingredients": "Aqua, Niacinamide", "score": 90},
            {"name": "B", "category": "Крем", "ingredients": "Aqua, Niacinamide", "score": 90},
        ]
        r = compute_shelf_compatibility(products)
        self.assertGreater(len(r["duplicate_actives"]), 0)
        self.assertLess(r["score"], 90)

    def test_not_just_average(self):
        # Разные формулы дают разные результаты при одинаковом среднем.
        clean = [
            {"name": "A", "category": "Очищение", "ingredients": "Aqua, Glycerin", "score": 80},
            {"name": "B", "category": "Крем", "ingredients": "Aqua, Panthenol", "score": 80},
        ]
        conflict = [
            {"name": "A", "category": "Сыворотки", "ingredients": "Aqua, Retinol", "score": 80},
            {"name": "B", "category": "Тонизация", "ingredients": "Aqua, Salicylic Acid", "score": 80},
        ]
        self.assertNotEqual(compute_shelf_compatibility(clean)["score"], compute_shelf_compatibility(conflict)["score"])


if __name__ == "__main__":
    unittest.main()
