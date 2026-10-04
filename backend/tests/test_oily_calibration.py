"""Regression: жирная кожа — калибровка весов осей (sebum не должен доминировать).

Фаза calibration: у «жирной» кожи ось sebum имела вес 0.45 (34.6% после
нормализации), хотя oil_control-claims заполнены лишь ~16% составов. Это
систематически занижало score для средств без oil_control (мягкие cleanser'ы,
ниацинамид). Вес sebum снижен до 0.20, а освободившийся вес перераспределён
на irritation/hydration/barrier (заполнены ~95-98%).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.decision_engine import DecisionEngine, profile_weights

OILY_PROFILE = {"skin_type": "Жирная", "concerns": [], "allergies": [], "custom_text": ""}

# (slug, label, min, max)
CASES = [
    ("round-lab-soybean-panthenol-cleanser", "gentle cleanser", 61, 71),
    ("celimax-baking-soda-deep-foam-pore-cleansing", "exfoliating cleanser", 9, 19),
    ("natura-siberica-bereza-siberica-polar-white-birch-pore-refining-face-cleanser", "birch cleanser", 62, 72),
    ("uspokaivayushchiy-i-ukreplyayushchiy-krem-dlya-litsa-neulii-092-phyto-vive-barrier-complex", "moisturizing cream", 77, 87),
    ("aravia-laboratories-hyaluronic-active-serum", "hyaluronic serum", 61, 71),
    ("spf-50-pa-round-lab-birch-juice-moisturizing-sunscreen", "SPF birch juice", 68, 78),
    ("aravia-laboratories-anti-acne-peeling", "acid peel", 22, 32),
    ("anua-niacinamide-30", "niacinamide serum", 72, 82),
    ("the-ordinary-100-organic-cold-pressed-rose-hip-seed-oil", "heavy oil", 22, 32),
    ("zephyr-beauty-skin-lavender-cleanser", "fragrance cleanser", 16, 26),
]


class OilySkinCalibrationTests(unittest.TestCase):
    def _score(self, slug):
        from app.database import get_connection, PRODUCTS_DB
        conn = get_connection(PRODUCTS_DB)
        conn.row_factory = None
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
