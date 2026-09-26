# tests/test_ingredient_claim_correction.py
# Regression-тесты для исправления direction ingredient_claims (data correction).
# Проверяют НАПРАВЛЕНИЕ/поведение данных, а НЕ фиксируют конкретный score Birch Juice.

import os
import sqlite3
import tempfile
import unittest

from app.axes import canonicalize_knowledge_map, canonicalize_weights
from app.correct_ingredient_claims import (
    _apply_flip_corrections,
    _apply_vitc_corrections,
    VITC_SENSITIVITY_STRENGTH,
)
from app.ingredient_repository import IngredientRepository
from app.scoring_engine import score_product_against_profile_canonical


class IngredientClaimCorrectionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test.db")
        self.repo = IngredientRepository(self.db_path)
        self.repo.ensure_ingredient_tables()

    def tearDown(self):
        self._tmp.cleanup()

    def _conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _claim(self, name, prop):
        conn = self._conn()
        row = conn.execute(
            "SELECT direction, strength FROM ingredient_claims c "
            "JOIN ingredients_catalog i ON i.id = c.ingredient_id "
            "WHERE i.normalized_name = ? AND c.property_name = ?",
            (name, prop),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def test_curcuma_longa_irritation_direction(self):
        self.repo.save_enriched_ingredient({
            "inci_name": "Curcuma Longa", "normalized_name": "curcuma longa",
            "claims": [{"property_name": "irritation", "direction": "positive",
                        "strength": 0.6, "confidence": 0.6}],
        })
        conn = self._conn()
        _apply_flip_corrections(conn)
        conn.commit()
        conn.close()
        self.assertEqual(self._claim("curcuma longa", "irritation")["direction"], "negative")

    def test_curcuma_longa_sensitization_direction(self):
        self.repo.save_enriched_ingredient({
            "inci_name": "Curcuma Longa", "normalized_name": "curcuma longa",
            "claims": [{"property_name": "sensitization", "direction": "negative",
                        "strength": 0.3, "confidence": 0.3}],
        })
        conn = self._conn()
        _apply_flip_corrections(conn)
        conn.commit()
        conn.close()
        self.assertEqual(self._claim("curcuma longa", "sensitization")["direction"], "positive")

    def test_ocimum_sanctum_irritation_direction(self):
        self.repo.save_enriched_ingredient({
            "inci_name": "Ocimum Sanctum Leaf Extract",
            "normalized_name": "ocimum sanctum leaf extract",
            "claims": [{"property_name": "irritation", "direction": "positive",
                        "strength": 0.6, "confidence": 0.5}],
        })
        conn = self._conn()
        _apply_flip_corrections(conn)
        conn.commit()
        conn.close()
        self.assertEqual(self._claim("ocimum sanctum leaf extract", "irritation")["direction"], "negative")

    def test_ocimum_sanctum_sensitization_direction(self):
        self.repo.save_enriched_ingredient({
            "inci_name": "Ocimum Sanctum Leaf Extract",
            "normalized_name": "ocimum sanctum leaf extract",
            "claims": [{"property_name": "sensitization", "direction": "negative",
                        "strength": 0.3, "confidence": 0.3}],
        })
        conn = self._conn()
        _apply_flip_corrections(conn)
        conn.commit()
        conn.close()
        self.assertEqual(self._claim("ocimum sanctum leaf extract", "sensitization")["direction"], "positive")

    def test_ascorbic_acid_sensitivity_is_mild(self):
        self.repo.save_enriched_ingredient({
            "inci_name": "Ascorbic Acid", "normalized_name": "ascorbic acid",
            "claims": [{"property_name": "sensitivity", "direction": "negative",
                        "strength": 0.7, "confidence": 0.85}],
        })
        conn = self._conn()
        _apply_vitc_corrections(conn)
        conn.commit()
        conn.close()
        claim = self._claim("ascorbic acid", "sensitivity")
        self.assertIsNotNone(claim)
        self.assertAlmostEqual(claim["strength"], VITC_SENSITIVITY_STRENGTH)

    def test_ascorbic_acid_no_negative_hydration(self):
        self.repo.save_enriched_ingredient({
            "inci_name": "Ascorbic Acid", "normalized_name": "ascorbic acid",
            "claims": [{"property_name": "hydration", "direction": "negative",
                        "strength": 0.35, "confidence": 0.7}],
        })
        conn = self._conn()
        _apply_vitc_corrections(conn)
        conn.commit()
        conn.close()
        self.assertIsNone(self._claim("ascorbic acid", "hydration"))

    def test_curcuma_soothing_gives_positive_irritation_contribution(self):
        # После коррекции «curcuma = soothing» → irritation должен быть ПОЛОЖИТЕЛЬНЫМ (польза).
        self.repo.save_enriched_ingredient({
            "inci_name": "Curcuma Longa", "normalized_name": "curcuma longa",
            "claims": [{"property_name": "irritation", "direction": "positive",
                        "strength": 0.6, "confidence": 0.6}],
        })
        conn = self._conn()
        _apply_flip_corrections(conn)
        conn.commit()
        conn.close()

        knowledge = canonicalize_knowledge_map(self.repo.get_knowledge_map())
        profile = {"skin_type": "Сухая", "concerns": [], "allergies": [],
                   "intolerances": [], "restrictions": []}
        weights = canonicalize_weights({"hydration": 0.35, "barrier_support": 0.25,
                                        "sensitivity": 0.2, "acne_control": 0.1, "brightening": 0.1})
        result = score_product_against_profile_canonical(
            ["curcuma longa"], knowledge, profile, weights
        )
        self.assertGreater(result["dimensions"]["irritation"], 0)

    def test_birch_juice_oily_regression_not_hardcoded(self):
        # Birch Juice: проверяем, что после коррекции ботаника не помечается раздражителем.
        # (НЕ фиксируем конкретный score.)
        for name in ["curcuma longa", "ocimum sanctum leaf extract"]:
            self.repo.save_enriched_ingredient({
                "inci_name": name.title(), "normalized_name": name,
                "claims": [{"property_name": "irritation", "direction": "positive",
                            "strength": 0.6, "confidence": 0.6}],
            })
        conn = self._conn()
        _apply_flip_corrections(conn)
        conn.commit()
        conn.close()
        self.assertEqual(self._claim("curcuma longa", "irritation")["direction"], "negative")
        self.assertEqual(self._claim("ocimum sanctum leaf extract", "irritation")["direction"], "negative")


if __name__ == "__main__":
    unittest.main()