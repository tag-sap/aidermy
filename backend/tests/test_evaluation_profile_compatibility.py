"""Fingerprint compatibility for reopening saved reports."""
from __future__ import annotations

import unittest

from app.evaluation.snapshot import profile_compatible


CURRENT = {
    "skin_type": "combination",
    "age": "25_35",
    "problems": ["acne_general"],
    "therapy": ["adapalene", "antibiotic", "benzoyl_peroxide"],
    "procedures": ["recent_biorevitalization@<7"],
    "goals": ["acne"],
    "intolerance_count": 1,
    "unresolved_count": 0,
}


class ProfileCompatibilityTests(unittest.TestCase):
    def test_legacy_optional_fields_and_age_separator_are_compatible(self):
        stored = {
            "skin_type": "combination",
            "age": "25–35",
            "problems": ["acne_general"],
            "therapy": ["antibiotic", "adapalene", "benzoyl_peroxide"],
            "procedures": ["recent_biorevitalization@<7"],
        }
        self.assertTrue(profile_compatible(stored, CURRENT))

    def test_changed_skin_type_is_not_compatible(self):
        stored = dict(CURRENT, skin_type="oily")
        self.assertFalse(profile_compatible(stored, CURRENT))

    def test_changed_core_answer_is_not_compatible(self):
        stored = dict(CURRENT, problems=["dryness"])
        self.assertFalse(profile_compatible(stored, CURRENT))

    def test_changed_optional_goal_is_not_compatible_when_both_present(self):
        stored = dict(CURRENT, goals=["hydration"])
        self.assertFalse(profile_compatible(stored, CURRENT))

    def test_changed_optional_count_is_not_compatible_when_both_present(self):
        stored = dict(CURRENT, intolerance_count=2)
        self.assertFalse(profile_compatible(stored, CURRENT))


if __name__ == "__main__":
    unittest.main()
