import unittest

from app.scoring_engine import score_product_against_profile


class ScoringEngineTests(unittest.TestCase):
    def setUp(self):
        self.user_profile = {
            'skin_type': 'dry',
            'concerns': ['dryness', 'sensitivity'],
            'allergies': [],
            'custom_text': '',
        }
        self.priority_weights = {
            'hydration': 0.35,
            'barrier_support': 0.25,
            'sensitivity': 0.2,
            'acne_control': 0.1,
            'brightening': 0.1,
        }

    def test_known_formula_scoring(self):
        ingredients = ['Water', 'Niacinamide', 'Glycerin', 'Fragrance']
        knowledge = {
            'water': {'hydration': {'direction': 'positive', 'strength': 0.7, 'confidence': 0.9}},
            'niacinamide': {
                'hydration': {'direction': 'positive', 'strength': 0.7, 'confidence': 0.9},
                'barrier_support': {'direction': 'positive', 'strength': 0.8, 'confidence': 0.85},
                'brightening': {'direction': 'positive', 'strength': 0.6, 'confidence': 0.8},
            },
            'glycerin': {'hydration': {'direction': 'positive', 'strength': 0.9, 'confidence': 0.95}},
            'fragrance': {'sensitivity': {'direction': 'negative', 'strength': 0.9, 'confidence': 0.9}},
        }

        result = score_product_against_profile(
            ingredients=ingredients,
            knowledge=knowledge,
            user_profile=self.user_profile,
            priority_weights=self.priority_weights,
        )

        self.assertGreater(result['score'], 45)
        self.assertLess(result['score'], 90)  # скор не должен насыщаться до 100%
        self.assertIn('hydration', result['dimensions'])
        self.assertIn('positive_factors', result)
        self.assertIn('negative_factors', result)

    def test_unknown_ingredients_are_neutral(self):
        ingredients = ['MysteryBlendX', 'BambooExtract']
        knowledge = {}

        result = score_product_against_profile(
            ingredients=ingredients,
            knowledge=knowledge,
            user_profile=self.user_profile,
            priority_weights=self.priority_weights,
        )

        self.assertEqual(result['unknown_factors'][0]['ingredient'], 'MysteryBlendX')
        self.assertGreaterEqual(result['score'], 40)

    def test_hard_flag_for_allergy(self):
        ingredients = ['Lactic Acid', 'Glycerin']
        knowledge = {
            'lactic acid': {'hydration': {'direction': 'positive', 'strength': 0.8, 'confidence': 0.9}},
            'glycerin': {'hydration': {'direction': 'positive', 'strength': 0.9, 'confidence': 0.95}},
        }

        user = {**self.user_profile, 'allergies': ['lactic acid']}
        result = score_product_against_profile(
            ingredients=ingredients,
            knowledge=knowledge,
            user_profile=user,
            priority_weights=self.priority_weights,
        )

        self.assertTrue(any(flag['type'] == 'allergy' for flag in result['hard_flags']))

    def test_position_weighting(self):
        ingredients = ['Niacinamide', 'Glycerin', 'Fragrance', 'Water']
        knowledge = {
            'niacinamide': {'barrier_support': {'direction': 'positive', 'strength': 0.8, 'confidence': 0.9}},
            'glycerin': {'hydration': {'direction': 'positive', 'strength': 0.8, 'confidence': 0.9}},
            'fragrance': {'sensitivity': {'direction': 'negative', 'strength': 0.9, 'confidence': 0.9}},
            'water': {'hydration': {'direction': 'positive', 'strength': 0.5, 'confidence': 0.8}},
        }

        result = score_product_against_profile(
            ingredients=ingredients,
            knowledge=knowledge,
            user_profile=self.user_profile,
            priority_weights=self.priority_weights,
        )

        self.assertIn('position_weight', result['positive_factors'][0])
        self.assertGreater(result['score'], 40)

    def test_reproducibility(self):
        ingredients = ['Glycerin', 'Niacinamide']
        knowledge = {
            'glycerin': {'hydration': {'direction': 'positive', 'strength': 0.9, 'confidence': 0.9}},
            'niacinamide': {'barrier_support': {'direction': 'positive', 'strength': 0.8, 'confidence': 0.9}},
        }

        first = score_product_against_profile(ingredients, knowledge, self.user_profile, self.priority_weights)
        second = score_product_against_profile(ingredients, knowledge, self.user_profile, self.priority_weights)

        self.assertEqual(first['score'], second['score'])
        self.assertEqual(first['dimensions'], second['dimensions'])


if __name__ == '__main__':
    unittest.main()
