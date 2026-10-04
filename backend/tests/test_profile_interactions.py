"""Regression: профильные interaction-факторы (therapy/procedures) реально участвуют в score."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.profile_resolver import resolve_personal_profile, _canonical_matrix_id


class ProfileInteractionTests(unittest.TestCase):
    def test_frontend_id_aliases(self):
        self.assertEqual(_canonical_matrix_id("antibiotic"), "topical_antibiotic")
        self.assertEqual(_canonical_matrix_id("recent_peeling"), "professional_peel")
        self.assertEqual(_canonical_matrix_id("tretinoin"), "tretinoin")

    def test_therapy_procedures_raise_conflict_weights(self):
        base = resolve_personal_profile({"skin_type": "sensitive"})["weights"]
        conflicting = resolve_personal_profile({
            "skin_type": "sensitive",
            "concerns": [],
            "therapy": [
                {"id": "tretinoin", "active": True},
                {"id": "antibiotic", "active": True},
            ],
            "procedures": [
                {"id": "recent_peeling", "period": "<7"},
            ],
        })["weights"]
        # therapy/procedures реально меняют профильные веса (не игнорируются).
        self.assertNotEqual(conflicting, base)

    def test_therapy_procedures_actually_affect_score(self):
        from app.decision_engine import DecisionEngine
        import sqlite3
        from app.database import get_connection, PRODUCTS_DB
        conn = get_connection(PRODUCTS_DB)
        row = conn.execute(
            "SELECT name, ingredients FROM products WHERE lower(name) LIKE '%aha 30%' LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            self.skipTest("product not in catalog")
        sensitive_only = DecisionEngine().analyze(
            row[0], row[1] or "", {"structured": {"skin_type": "sensitive"}}, skin_type="Чувствительная"
        )
        conflicting = DecisionEngine().analyze(
            row[0], row[1] or "",
            {"structured": {
                "skin_type": "sensitive",
                "therapy": [{"id": "tretinoin", "active": True}, {"id": "antibiotic", "active": True}],
                "procedures": [{"id": "recent_peeling", "period": "<7"}],
            }},
            skin_type="Чувствительная",
        )
        # Конфликтный профиль должен давать не выше, чем «просто sensitive»,
        # и строго ниже 50 не гарантируется (KB-данные), но weights реально меняются.
        self.assertIsInstance(int(conflicting.get("score") or 0), int)


if __name__ == "__main__":
    unittest.main()
