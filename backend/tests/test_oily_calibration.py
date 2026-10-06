"""Regression: жирная кожа — калибровка весов осей (sebum не должен доминировать).

Проверяет:
1) веса осей жирной кожи (sebum не доминирует, irritation/hydration — топ);
2) score-диапазоны реальных продуктов (sanity-диапазоны вокруг фактических значений
   после signed-нормализации score = clamp(50 + 50*weighted_avg(tanh(raw/S)), 0, 100)
   и diminishing-returns по однотипным claims: hydration/barrier — сильнейший claim,
   остальные оси — 1/rank).

Диапазоны отражают СЕМАНТИКУ (мягкие очищающие > агрессивных), а не точные значения.

Калибровка обновлена под diminishing-returns формулу (см. ef784d0): раньше диапазоны
задавались под линейную сумму всех claims по оси, из-за чего после введения
diminishing-returns все score сместились вниз на ~10–15 пунктов и тест завышал ожидания.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.decision_engine import DecisionEngine, profile_weights

OILY_PROFILE = {"skin_type": "Жирная", "concerns": [], "allergies": [], "custom_text": ""}

# (slug, label, min, max)
CASES = [
    ("round-lab-soybean-panthenol-cleanser", "gentle cleanser", 62, 72),
    ("celimax-baking-soda-deep-foam-pore-cleansing", "exfoliating cleanser", 49, 59),
    ("natura-siberica-bereza-siberica-polar-white-birch-pore-refining-face-cleanser", "birch cleanser", 62, 72),
    ("aravia-laboratories-hyaluronic-active-serum", "hyaluronic serum", 65, 75),
    ("round-lab-birch-juice-moisturizing-sunscreen-spf-50-pa", "SPF birch juice", 67, 77),
    ("aravia-laboratories-anti-acne-peeling", "acid peel", 53, 63),
    ("the-ordinary-100-organic-cold-pressed-rose-hip-seed-oil", "heavy oil", 58, 68),
    ("zephyr-beauty-skin-lavender-cleanser", "fragrance cleanser", 46, 56),
]


class OilySkinCalibrationTests(unittest.TestCase):
    def _score(self, slug):
        from app.database import get_connection, PRODUCTS_DB
        conn = get_connection(PRODUCTS_DB)
        row = conn.execute("SELECT name, ingredients FROM products WHERE slug = ?", (slug,)).fetchone()
        conn.close()
        if not row:
            self.skipTest(f"product {slug} not in catalog")
        return DecisionEngine().analyze(
            row[0], row[1] or "", OILY_PROFILE, skin_type="Жирная",
        )

    def test_oily_skin_axis_weights(self):
        w = profile_weights(OILY_PROFILE, "Жирная")
        self.assertLess(w.get("sebum", 1.0), 0.25, f"sebum weight too high: {w}")
        self.assertGreater(w.get("irritation", 0.0), 0.25, f"irritation should be a top axis: {w}")
        self.assertGreater(w.get("hydration", 0.0), 0.25, f"hydration should be well-weighted: {w}")

    def test_product_score_ranges(self):
        for slug, label, lo, hi in CASES:
            res = self._score(slug)
            sc = int(res.get("score") or 0)
            self.assertGreaterEqual(sc, lo, f"{label} ({slug}) score={sc} < {lo}")
            self.assertLessEqual(sc, hi, f"{label} ({slug}) score={sc} > {hi}")


if __name__ == "__main__":
    unittest.main()
