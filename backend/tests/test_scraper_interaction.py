"""Regression-тесты: JS-взаимодействие scraper (раскрытие Ingredients)."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scraper.service import _expand_ingredients, _INGREDIENTS_ACCORDION_LABELS
from app.scraper.extractors import _extract_inci_candidate


class ExtractInciCandidateTests(unittest.TestCase):
    def test_inci_without_water_prefix(self):
        raw = "Snail Secretion Filtrate, Betaine, Butylene Glycol, 1,2-hexanediol, Sodium Hyaluronate"
        self.assertEqual(_extract_inci_candidate(raw), raw)

    def test_inci_stops_at_next_section(self):
        raw = "Snail Secretion Filtrate, Betaine, Butylene Glycol, 1,2-hexanediol\n\nSuggested Usage: apply daily"
        candidate = _extract_inci_candidate(raw)
        self.assertIn("Snail Secretion Filtrate", candidate)
        self.assertNotIn("Suggested", candidate)

    def test_marketing_text_is_not_inci(self):
        raw = "Like a multivitamin for your skin, this product nourishes, repairs, and plumps"
        self.assertIsNone(_extract_inci_candidate(raw))

    def test_json_bundle_is_not_inci(self):
        raw = '","navigationType":"push","url":"https://x.com/clean-ingredients","graphql":null'
        self.assertIsNone(_extract_inci_candidate(raw))


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

            def wait_for_load_state(self, state, timeout=None):
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
