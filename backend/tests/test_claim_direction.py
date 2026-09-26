# tests/test_claim_direction.py
# Enrichment contract: direction = endpoint sign, НЕ «positive = good / negative = bad».

import unittest

from app.claim_direction import validate_claim


class DirectionContractTests(unittest.TestCase):
    def _v(self, axis, direction, evidence, confidence=0.8):
        return validate_claim(axis, direction, evidence, confidence)

    def test_anti_inflammatory_is_irritation_negative(self):
        verdict, corrected, _ = self._v("irritation", "positive", "anti-inflammatory activity")
        self.assertEqual((verdict, corrected), ("flip", "negative"))

    def test_soothing_is_irritation_negative(self):
        verdict, corrected, _ = self._v("irritation", "positive", "soothing and calming effect")
        self.assertEqual((verdict, corrected), ("flip", "negative"))

    def test_contact_dermatitis_is_sensitization_positive(self):
        verdict, corrected, _ = self._v("sensitization", "negative", "can cause contact dermatitis")
        self.assertEqual((verdict, corrected), ("flip", "positive"))

    def test_mattifying_is_sebum_negative(self):
        verdict, corrected, _ = self._v("sebum", "positive", "mattifying, absorbs oil")
        self.assertEqual((verdict, corrected), ("flip", "negative"))

    def test_sebum_absorbing_is_sebum_negative(self):
        verdict, corrected, _ = self._v("sebum", "positive", "absorbs excess sebum on skin surface")
        self.assertEqual((verdict, corrected), ("flip", "negative"))

    def test_inhibits_tyrosinase_is_pigmentation_negative(self):
        verdict, corrected, _ = self._v("pigmentation", "positive", "inhibits tyrosinase and melanogenesis")
        self.assertEqual((verdict, corrected), ("flip", "negative"))

    def test_hydration_benefit_is_positive(self):
        verdict, corrected, _ = self._v("hydration", "positive", "moisturizer, humectant")
        self.assertEqual((verdict, corrected), ("ok", None))

    def test_barrier_repair_is_positive(self):
        verdict, corrected, _ = self._v("barrier", "positive", "barrier repair, strengthens barrier function")
        self.assertEqual((verdict, corrected), ("ok", None))

    def test_no_clear_signal_does_not_flip(self):
        verdict, corrected, _ = self._v("irritation", "positive", "moderate")
        self.assertEqual((verdict, corrected), ("ok", None))

    def test_low_confidence_contradiction_is_rejected(self):
        verdict, corrected, _ = self._v("irritation", "positive", "anti-inflammatory", confidence=0.1)
        self.assertEqual((verdict, corrected), ("reject", None))

    def test_positive_is_not_good_for_harm_axis(self):
        # Контракт: positive != good. Для harm-оси «anti-inflammatory» = negative, а не positive.
        verdict, corrected, _ = self._v("irritation", "negative", "anti-inflammatory")
        self.assertEqual((verdict, corrected), ("ok", None))
        # а positive с «anti-inflammatory» — это ошибка, требующая flip
        verdict2, corrected2, _ = self._v("irritation", "positive", "anti-inflammatory")
        self.assertEqual((verdict2, corrected2), ("flip", "negative"))


if __name__ == "__main__":
    unittest.main()
