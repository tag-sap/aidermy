import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scoring_engine import score_product_against_profile_canonical
from app.profile_resolver import normalize_scoring_profile, resolve_personal_profile
from app.decision_engine import profile_weights

WEIGHTS = {"hydration": 0.30, "barrier": 0.15, "irritation": 0.30,
           "sensitization": 0.04, "sebum": 0.15, "pigmentation": 0.04}
KNOWLEDGE = {"glycerin": {"hydration": {"direction": "positive", "strength": 0.9, "confidence": 0.95}}}


def _sp():
    profile = {"skin_type": "Нормальная", "concerns": [], "allergies": [], "intolerances": []}
    sp = normalize_scoring_profile(profile)
    sp["structured"]["axis_multipliers"] = resolve_personal_profile(sp.get("structured") or {})["axis_multipliers"]
    return sp


class SaturationScaleTests(unittest.TestCase):
    """Меньшая saturation_scale -> выше итоговый балл (менее сжатая шкала tanh)."""

    def _score(self, sat):
        return score_product_against_profile_canonical(
            ingredients=["glycerin"],
            canonical_knowledge=KNOWLEDGE,
            user_profile=_sp(),
            canonical_weights=WEIGHTS,
            saturation_scale=sat,
        )["score"]

    def test_sharper_saturation_increases_positive_score(self):
        soft = self._score(1.5)
        sharp = self._score(1.2)
        self.assertGreaterEqual(sharp, soft)

    def test_saturation_monotonic(self):
        scores = [self._score(s) for s in (2.0, 1.5, 1.2, 1.0)]
        self.assertEqual(scores, sorted(scores))


if __name__ == "__main__":
    unittest.main()
