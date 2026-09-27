# tests/test_questionnaire_integration.py
# Интеграция PROFILE MATRIX questionnaire:
#   анкета (canonical IDs) -> save/load structured_profile -> resolver -> weights.
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.database as database
from app.profile_resolver import resolve_personal_profile
from app.decision_engine import profile_weights
from app.models import Profile, CheckRequest

AXES = {"hydration", "barrier", "irritation", "sensitization", "sebum", "pigmentation"}

# Типичный structured profile, который производит анкета (canonical IDs).
QUESTIONNAIRE_PROFILE = {
    "skin_type": "oily",
    "concerns": ["acne_general", "enlarged_pores"],
    "imperfections": [],
    "states": [],
    "therapy": [],
    "procedures": [],
    "goals": [],
    "intolerances": ["fragrance_intolerance"],
    "allergies": [],
}


class QuestionnaireResolverTests(unittest.TestCase):
    def test_questionnaire_structured_resolves_weights(self):
        r = resolve_personal_profile(QUESTIONNAIRE_PROFILE)
        self.assertEqual(set(r["weights"].keys()), AXES)
        self.assertAlmostEqual(sum(r["weights"].values()), 1.0, places=5)
        # oily + acne + pores -> sebum доминирует над hydration.
        self.assertGreater(r["weights"]["sebum"], r["weights"]["hydration"])

    def test_profile_weights_uses_structured_dict(self):
        # decision_engine.profile_weights: явный structured-профиль идёт напрямую в resolver.
        w = profile_weights({"structured": QUESTIONNAIRE_PROFILE}, "Нормальная")
        self.assertEqual(set(w.keys()), AXES)
        self.assertGreater(w["sebum"], 0.2)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=5)

    def test_legacy_profile_still_analyzes(self):
        # Старый RU-профиль -> legacy mapper -> resolver (backward compat).
        w = profile_weights({"skin_type": "Жирная", "concerns": ["Акне"]}, "Жирная")
        self.assertGreater(w["sebum"], 0.0)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=5)

    def test_hierarchy_prevents_double_counting(self):
        # acne_general затеняется потомком pustules.
        both = resolve_personal_profile(
            {"skin_type": "oily", "concerns": ["acne_general"], "imperfections": ["pustules"]}
        )
        specific = resolve_personal_profile({"skin_type": "oily", "imperfections": ["pustules"]})
        self.assertEqual(both["weights"], specific["weights"])

    def test_unknown_branch_ids_ignored(self):
        # Анкета может добавить category-names (sebum_pores, dryness) — resolver их игнорирует.
        with_branch = resolve_personal_profile(
            {"skin_type": "oily", "concerns": ["sebum_pores", "enlarged_pores"]}
        )
        without_branch = resolve_personal_profile({"skin_type": "oily", "concerns": ["enlarged_pores"]})
        self.assertEqual(with_branch["weights"], without_branch["weights"])

    def test_therapy_and_intolerance_flow(self):
        r = resolve_personal_profile({
            "skin_type": "dry",
            "therapy": [{"id": "tretinoin", "active": True}],
            "intolerances": ["niacinamide_intolerance"],
        })
        # активная терапия попадает в active_therapy; intolerance не меняет weights, но сохраняется.
        self.assertEqual(r["active_therapy"], ["tretinoin"])
        self.assertIn("niacinamide_intolerance", r["intolerances"])


class QuestionnaireModelTests(unittest.TestCase):
    def test_profile_model_accepts_structured(self):
        p = Profile(age="25_35", concerns=[], allergies=[], structured=QUESTIONNAIRE_PROFILE)
        self.assertEqual(p.structured["skin_type"], "oily")

    def test_check_request_serializes_structured(self):
        cr = CheckRequest(
            product_name="X",
            skin_type="Жирная",
            profile=Profile(age="25_35", concerns=[], allergies=[], structured=QUESTIONNAIRE_PROFILE),
        )
        d = cr.profile.dict()
        self.assertEqual(d["structured"]["skin_type"], "oily")
        self.assertEqual(d["structured"]["concerns"], ["acne_general", "enlarged_pores"])


class QuestionnaireDbRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self._old = database.AIDERMY_DB
        database.AIDERMY_DB = self.tmp
        conn = database.get_connection(database.AIDERMY_DB)
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE user_profiles (id INTEGER PRIMARY KEY, user_id INTEGER UNIQUE, name TEXT, "
            "skin_type TEXT, age TEXT, concerns TEXT, allergies TEXT, custom_text TEXT, "
            "quiz_answers TEXT, skin_type_determined TEXT, structured_profile TEXT, updated_at TEXT)"
        )
        cur.execute("INSERT INTO user_profiles (user_id, name, skin_type) VALUES (1, 'U', 'Жирная')")
        conn.commit()
        conn.close()

    def tearDown(self):
        database.AIDERMY_DB = self._old
        try:
            if os.path.exists(self.tmp):
                os.remove(self.tmp)
        except PermissionError:
            pass

    def test_save_load_roundtrip(self):
        from app.database import save_structured_profile, get_structured_profile
        self.assertTrue(save_structured_profile(1, QUESTIONNAIRE_PROFILE))
        loaded = get_structured_profile(1)
        self.assertEqual(loaded["skin_type"], "oily")
        self.assertEqual(loaded["concerns"], ["acne_general", "enlarged_pores"])
        self.assertEqual(loaded["intolerances"], ["fragrance_intolerance"])

    def test_roundtrip_then_resolve(self):
        from app.database import save_structured_profile, get_structured_profile
        save_structured_profile(1, QUESTIONNAIRE_PROFILE)
        loaded = get_structured_profile(1)
        w = resolve_personal_profile(loaded)["weights"]
        self.assertGreater(w["sebum"], w["hydration"])
        self.assertAlmostEqual(sum(w.values()), 1.0, places=5)


if __name__ == "__main__":
    unittest.main()
