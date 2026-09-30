"""Regression-тесты: JS-взаимодействие scraper (раскрытие Ingredients)."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scraper.service import _expand_ingredients, _INGREDIENTS_ACCORDION_LABELS


class ExpandIngredientsTests(unittest.TestCase):
    def test_labels_cover_variants(self):
        for label in ("Ingredients", "Full Ingredients", "Ingredient List", "Состав", "Ингредиенты"):
            self.assertIn(label, _INGREDIENTS_ACCORDION_LABELS)

    def test_clicks_ingredients_element(self):
        clicks = []

        class Loc:
            def count(self):
                return 1

            @property
            def first(self):
                return self

            def click(self, force=False, timeout=None):
                clicks.append("click")

        class Page:
            def get_by_role(self, role, name=None):
                return Loc()

            def locator(self, sel):
                return Loc()

            def wait_for_timeout(self, ms):
                pass

        _expand_ingredients(Page())
        self.assertTrue(clicks)

    def test_no_ingredients_no_click_and_no_crash(self):
        class NoLoc:
            def count(self):
                return 0

        class Page:
            def get_by_role(self, role, name=None):
                return NoLoc()

            def locator(self, sel):
                return NoLoc()

            def wait_for_timeout(self, ms):
                pass

        # Не должен падать и не должен кликать.
        _expand_ingredients(Page())


if __name__ == "__main__":
    unittest.main()
