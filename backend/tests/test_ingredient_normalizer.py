import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ingredient_normalizer import normalize_ingredient_name, canonicalize_ingredient_name, parse_inci_list


class IngredientNormalizerTests(unittest.TestCase):
    def test_water_variants_canonicalize_to_water(self):
        for v in ["Purified Water", "Deionized Water", "Distilled Water", "Aqua Water", "Water Aqua Eau"]:
            self.assertEqual(canonicalize_ingredient_name(v), "water", v)

    def test_nano_filters_canonicalize_to_base(self):
        self.assertEqual(canonicalize_ingredient_name("Titanium Dioxide Nano"), "titanium dioxide")
        self.assertEqual(canonicalize_ingredient_name("Zinc Oxide Nano"), "zinc oxide")

    def test_salix_alba_maps_to_bark_extract(self):
        self.assertEqual(canonicalize_ingredient_name("Salix Alba"), "salix alba bark extract")

    def test_fragrance_parfum_aliases(self):
        self.assertEqual(canonicalize_ingredient_name("Parfum"), "fragrance")
        self.assertEqual(canonicalize_ingredient_name("Parfum/Fragrance"), "fragrance")

    def test_unknown_stays_unknown(self):
        self.assertEqual(canonicalize_ingredient_name("Mystery Compound Xyz"), "mystery compound xyz")

    def test_parse_inci_drops_water(self):
        self.assertEqual(parse_inci_list("Aqua, Glycerin"), ["glycerin"])


if __name__ == "__main__":
    unittest.main()
