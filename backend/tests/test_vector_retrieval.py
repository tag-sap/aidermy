# tests/test_vector_retrieval.py
# Тесты для PPM + единого Product Vector index + retrieval (Clamped Dot).
import os
import sys
import tempfile
import unittest
from unittest import mock
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ingredient_repository import IngredientRepository
from app.ppm import build_ppm
from app.ppm_service import _prepare, build_or_refresh_ppm, refresh_ppms_for_ingredients
from app.product_model import composition_hash
from app.product_vector import build_product_vector, clamped_dot
from app.profile_resolver import resolve_personal_profile
from app.scoring_config import AXES


def _seed_repo(db_path: str) -> IngredientRepository:
    repo = IngredientRepository(db_path)
    repo.ensure_ingredient_tables()
    gid = repo.upsert_ingredient("Glycerin", "Glycerin", "glycerin")
    repo.add_claim(gid, "hydration", "positive", 0.8, 0.9)
    nid = repo.upsert_ingredient("Niacinamide", "Niacinamide", "niacinamide")
    repo.add_claim(nid, "irritation", "negative", 0.7, 0.8)
    return repo


class PpmTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _seed_repo(os.path.join(self._tmp.name, "test.db"))
        self.knowledge = self.repo.get_canonical_knowledge_map()

    def tearDown(self):
        self._tmp.cleanup()

    def _unknown(self, raw):
        from app.ingredient_enrichment import find_unknown_ingredients
        norm = _prepare(raw)
        return norm, find_unknown_ingredients(norm, self.repo)

    # 1. PPM строится из состава.
    def test_build_ppm_from_composition(self):
        norm, unknown = self._unknown("Glycerin, Niacinamide, ExoticPeptide")
        ppm = build_ppm({"id": 1, "ingredients": "Glycerin, Niacinamide, ExoticPeptide"},
                        norm, unknown, self.knowledge)
        self.assertEqual(ppm["product_id"], 1)
        self.assertEqual(ppm["known_count"], 2)
        self.assertEqual(ppm["unknown_count"], 1)
        self.assertIn("exoticpeptide", ppm["unknown_ingredients"])
        self.assertAlmostEqual(ppm["coverage"], 2 / 3, places=3)

    # 2. Unknown ingredient не получает отрицательный contribution.
    def test_unknown_ingredient_zero_contribution(self):
        vector = build_product_vector(["exoticpeptide"], self.knowledge)
        self.assertEqual(vector, {axis: 0.0 for axis in AXES})

    # 3. Coverage корректно считается.
    def test_coverage(self):
        norm, unknown = self._unknown("Glycerin, ExoticPeptide")
        ppm = build_ppm({"id": 1, "ingredients": "Glycerin, ExoticPeptide"},
                        norm, unknown, self.knowledge)
        self.assertEqual(ppm["known_count"], 1)
        self.assertEqual(ppm["unknown_count"], 1)
        self.assertAlmostEqual(ppm["coverage"], 0.5)

    # 6. Clamped Dot корректно считает retrieval.
    def test_clamped_dot(self):
        vector = {"hydration": 2.0, "barrier": -0.5, "irritation": 0.5,
                  "sensitization": 0.0, "sebum": 0.0, "pigmentation": 0.0}
        weights = {"hydration": 0.5, "barrier": 0.5, "irritation": 0.0,
                   "sensitization": 0.0, "sebum": 0.0, "pigmentation": 0.0}
        self.assertAlmostEqual(clamped_dot(vector, weights), 1.0 * 0.5)

    # 7. Profile Vector берётся из resolve_personal_profile.
    def test_profile_vector_from_resolver(self):
        w = resolve_personal_profile({"skin_type": "dry"})["weights"]
        self.assertEqual(set(w.keys()), set(AXES))
        self.assertAlmostEqual(sum(w.values()), 1.0, places=3)

    # 12. Interactions не участвуют в vector (vector = individual effects).
    def test_interactions_do_not_affect_vector(self):
        norm, _ = self._unknown("Glycerin, Niacinamide")
        v1 = build_product_vector(norm, self.knowledge)
        self.repo.seed_interactions()
        v2 = build_product_vector(norm, self.repo.get_canonical_knowledge_map())
        self.assertEqual(v1, v2)

    # 4+5. PM заменяет PPM; один product_id — одна vector-запись (не PM+PPM сразу).
    def test_pm_replaces_ppm_in_vector(self):
        p = {"id": 42, "ingredients": "Glycerin, Niacinamide"}
        r = build_or_refresh_ppm(p, repo=self.repo, canonical_knowledge=self.knowledge)
        self.assertEqual(r["representation_type"], "PPM")
        self.assertEqual(self.repo.get_product_vector(42)["representation_type"], "PPM")
        self.assertIsNotNone(self.repo.get_ppm(42))

        h = composition_hash(p["ingredients"])
        self.repo.save_product_model(42, {
            "product_id": 42, "composition_hash": h,
            "taxonomy_version": "v1", "knowledge_version": "v1",
            "interaction_version": "seed-v1", "model_version": "v1",
            "classes": [], "individual_effects": {}, "internal_interaction_ids": [],
            "ingredient_names": ["glycerin", "niacinamide"],
        })
        r2 = build_or_refresh_ppm(p, repo=self.repo, canonical_knowledge=self.knowledge)
        self.assertEqual(r2["representation_type"], "PM")
        rows = self.repo.get_all_product_vectors()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["representation_type"], "PM")

    # 9+10. Enrichment одного ingredient инвалидирует только связанные PPM и обновляет vector.
    def test_enrichment_invalidates_only_related_ppms(self):
        p1 = {"id": 1, "ingredients": "Glycerin, ExoticA"}
        p2 = {"id": 2, "ingredients": "Glycerin, ExoticB"}
        build_or_refresh_ppm(p1, repo=self.repo, canonical_knowledge=self.knowledge)
        build_or_refresh_ppm(p2, repo=self.repo, canonical_knowledge=self.knowledge)

        self.repo.upsert_ingredient("ExoticA", "ExoticA", "exotica")
        refreshed = refresh_ppms_for_ingredients(["exotica"], repo=self.repo)
        self.assertEqual(refreshed, 1)

        ppm1 = self.repo.get_ppm(1)
        self.assertNotIn("exotica", ppm1["unknown_ingredients"])
        ppm2 = self.repo.get_ppm(2)
        self.assertIn("exoticb", ppm2["unknown_ingredients"])

    # 14. Recommendation results не содержат внутренних PPM/vector полей.
    def test_retrieve_candidates_no_internal_fields(self):
        from app import vector_retrieval

        products = [{"id": 1, "name": "A", "slug": "a", "category": "Очищение",
                     "brand": "", "ingredients": "Glycerin", "image_url": "",
                     "taxonomy_category": ""}]
        fake_index = mock.Mock()
        fake_index.is_loaded.return_value = True
        fake_index.search.return_value = [(1, 0.5)]

        with patch("app.vector_retrieval.VECTOR_INDEX", fake_index), \
             patch("app.database.get_all_canonical_products", return_value=products), \
             patch("app.shelf_service.is_product_compatible", return_value=(True, "")), \
             patch("app.shelf_service._hard_filter_exclusion", return_value=False), \
             patch("app.profile_resolver.resolve_personal_profile",
                   return_value={"weights": {k: 1 / 6 for k in AXES}}):
            recs = vector_retrieval.retrieve_candidates(
                {"skin_type": "dry"}, "face", "Очищение", set())

        self.assertEqual(len(recs), 1)
        for r in recs:
            for bad in ("_retrieval_score", "vector", "coverage",
                        "unknown_count", "representation_type", "unknown_ingredients"):
                self.assertNotIn(bad, r)


if __name__ == "__main__":
    unittest.main()

