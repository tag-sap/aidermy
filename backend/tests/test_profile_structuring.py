import unittest

from app.profile_structuring import structure_profile


class ProfileStructuringTests(unittest.TestCase):
    def test_returns_all_structured_keys(self):
        s = structure_profile({"skin_type": "Сухая", "concerns": ["Обезвоженность"], "allergies": [], "custom_text": ""})
        for key in ("skin_type", "sensitivity", "skin_goals", "personal_weights",
                    "restrictions", "intolerances", "allergies", "preferences"):
            self.assertIn(key, s)

    def test_frontend_allergies_become_restrictions(self):
        s = structure_profile({"skin_type": "Сухая", "concerns": [], "allergies": ["Отдушки", "Спирт"], "custom_text": ""})
        self.assertEqual(set(s["restrictions"]), {"Отдушки", "Спирт"})
        self.assertEqual(s["allergies"], [])

    def test_custom_text_allergy_is_not_upgraded_to_restriction(self):
        # Заявленная аллергия из свободного текста -> поле allergies, не restrictions.
        s = structure_profile({"skin_type": "Сухая", "concerns": [], "allergies": [], "custom_text": "У меня аллергия на ланолин"})
        self.assertEqual(s["allergies"], ["ланолин"])
        self.assertEqual(s["restrictions"], [])

    def test_custom_text_intolerance(self):
        s = structure_profile({"skin_type": "Сухая", "concerns": [], "allergies": [], "custom_text": "Непереносимость спирта"})
        self.assertIn("спирта", s["intolerances"])

    def test_custom_text_restriction(self):
        s = structure_profile({"skin_type": "Сухая", "concerns": [], "allergies": [], "custom_text": "Исключить ретинол полностью"})
        self.assertTrue(any("ретинол" in r for r in s["restrictions"]))

    def test_sensitive_skin_inferred(self):
        s = structure_profile({"skin_type": "Чувствительная", "concerns": [], "allergies": [], "custom_text": ""})
        self.assertEqual(s["sensitivity"], "high")

    def test_skin_goals_from_concerns(self):
        s = structure_profile({"skin_type": "Сухая", "concerns": ["Акне"], "allergies": [], "custom_text": ""})
        self.assertIn("acne_control", s["skin_goals"])

    def test_deterministic_source(self):
        s = structure_profile({"skin_type": "Сухая", "concerns": [], "allergies": [], "custom_text": ""})
        self.assertEqual(s["source"], "deterministic")


if __name__ == "__main__":
    unittest.main()
