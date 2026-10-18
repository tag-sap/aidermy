import os, sys, unittest, importlib.util
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_spec = importlib.util.spec_from_file_location(
    "enrich_active_ingredients",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "enrich_active_ingredients.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
ENRICH = _mod.ENRICH

CANONICAL_AXES = {"hydration", "barrier", "irritation", "sensitization", "sebum", "pigmentation"}


class EnrichActiveIngredientsTests(unittest.TestCase):
    def test_nonempty_and_has_claims(self):
        self.assertGreaterEqual(len(ENRICH), 20)
        for key, inci, claims in ENRICH:
            self.assertTrue(key and key == key.strip().lower(), key)
            self.assertTrue(claims, f"{key} has no claims")

    def test_axes_and_directions_valid(self):
        for key, inci, claims in ENRICH:
            for prop, direction, strength, confidence in claims:
                self.assertIn(prop, CANONICAL_AXES, f"{key}: bad axis {prop}")
                self.assertIn(direction, ("positive", "negative"), f"{key}: bad dir")
                self.assertTrue(0.0 <= strength <= 1.0, f"{key}: strength {strength}")
                self.assertTrue(0.0 <= confidence <= 1.0, f"{key}: confidence {confidence}")

    def test_semantic_directions(self):
        # benefit-ось (hydration/barrier): positive = польза.
        # harm-ось: negative = польза (irritation negative = soothing,
        # pigmentation negative = brightening); positive = вред.
        for key, inci, claims in ENRICH:
            for prop, direction, strength, confidence in claims:
                if prop in ("hydration", "barrier"):
                    self.assertEqual(direction, "positive", f"{key}: {prop} must be positive benefit")
                else:
                    # Оба направления допустимы на harm-осях.
                    pass

    def test_curated_source_has_no_fake_url(self):
        # Происхождение должно быть помечено curated_science без выдуманного URL.
        self.assertEqual(_mod.SOURCE_TYPE, "curated_science")
        self.assertIn("curated", _mod.RESEARCH_VERSION)

    def test_normalizer_matches_keys(self):
        from app.ingredient_normalizer import canonicalize_ingredient_name
        for key, inci, claims in ENRICH:
            self.assertEqual(canonicalize_ingredient_name(inci), key, f"{inci} -> {key}")


class EnrichKnowledgeMapTests(unittest.TestCase):
    def test_enriched_ingredients_in_knowledge_map(self):
        # Integration check: requires SUPABASE_DATABASE_URL already present in
        # the environment (e.g. production/deploy). Do NOT call load_dotenv here:
        # it mutates os.environ globally and breaks subsequent SQLite tests.
        if not os.environ.get("SUPABASE_DATABASE_URL"):
            self.skipTest("no SUPABASE_DATABASE_URL in environment")
        from app.ingredient_repository import IngredientRepository
        km = IngredientRepository().get_canonical_knowledge_map()
        missing = [k for k, _, _ in ENRICH if k not in km]
        self.assertEqual(missing, [], f"missing from knowledge map: {missing}")


if __name__ == "__main__":
    unittest.main()
