import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.category_knowledge import (
    CATEGORY_KNOWLEDGE_VERSION,
    FALLBACK_CATEGORY_KNOWLEDGE,
    get_category_knowledge,
    render_category_knowledge,
)


class CategoryKnowledgeLookupTests(unittest.TestCase):
    def test_cleansing_for_makeup_remover(self):
        k = get_category_knowledge("Очищение и демакияж")
        self.assertEqual(k["category_key"], "face:cleansing")
        self.assertIn("демакияж", k["display_name"].lower())

    def test_scrubs_differ_from_cleansing(self):
        cleansing = get_category_knowledge("Очищение и демакияж")
        scrubs = get_category_knowledge("Скрабы и пилинги")
        self.assertNotEqual(cleansing["category_key"], scrubs["category_key"])
        self.assertIn("отшелушивание", " ".join(scrubs["typical_functions"]).lower())

    def test_cream_not_cleansing(self):
        cream = get_category_knowledge("Кремы")
        self.assertEqual(cream["category_key"], "face:creams")
        self.assertNotEqual(cream["category_key"], "face:cleansing")

    def test_unknown_category_fallback(self):
        k = get_category_knowledge("НеизвестнаяКатегория")
        self.assertEqual(k["category_key"], "unknown")
        self.assertEqual(k["display_name"], "Неопределённая категория")

    def test_empty_category_fallback(self):
        self.assertEqual(get_category_knowledge("")["category_key"], "unknown")

    def test_makeup_eyes_disambiguated_from_face_eyes(self):
        face_eyes = get_category_knowledge("Для кожи вокруг глаз")
        makeup_eyes = get_category_knowledge("Для глаз")
        self.assertEqual(face_eyes["category_key"], "face:eyes")
        self.assertEqual(makeup_eyes["category_key"], "makeup:eyes")
        self.assertNotEqual(face_eyes["category_key"], makeup_eyes["category_key"])


class CategoryKnowledgeAntiTemplateTests(unittest.TestCase):
    def test_cleansing_does_not_claim_nourish_hydrate_barrier(self):
        """Отчёт о средстве для демакияжа не должен утверждать питание/увлажнение/барьер."""
        k = get_category_knowledge("Очищение и демакияж")
        limitations = " ".join(k["limitations"]).lower()
        self.assertIn("не питает", limitations)
        self.assertIn("не даёт интенсивного увлажнения", limitations)
        self.assertIn("не восстанавливает барьер", limitations)

    def test_cream_does_not_claim_barrier_restoration_automatically(self):
        k = get_category_knowledge("Кремы")
        limitations = " ".join(k["limitations"]).lower()
        self.assertIn("название «крем» не доказывает", limitations)

    def test_scrubs_do_not_claim_concentration(self):
        k = get_category_knowledge("Скрабы и пилинги")
        limitations = " ".join(k["limitations"]).lower()
        self.assertIn("концентрац", limitations)


class CategoryKnowledgeRenderTests(unittest.TestCase):
    def test_render_includes_definition_and_limitations(self):
        text = render_category_knowledge("Очищение и демакияж")
        self.assertIn("Категория:", text)
        self.assertIn("Что это:", text)
        self.assertIn("Нельзя автоматически заключать:", text)

    def test_version_present(self):
        k = get_category_knowledge("Сыворотки")
        self.assertEqual(k["version"], CATEGORY_KNOWLEDGE_VERSION)

    def test_knowledge_independent_of_score_engine(self):
        # База знаний не должна импортировать Score Engine.
        import app.category_knowledge as ck
        src = open(ck.__file__).read()
        self.assertNotIn("scoring_engine", src)
        self.assertNotIn("scoring_config", src)


class BuildReportContextTests(unittest.TestCase):
    def test_context_includes_category_knowledge(self):
        from app.report_prompt import build_report_context
        analysis = {
            "score": 72,
            "verdict": "Подходит",
            "dimensions": {"hydration": 1.0, "barrier": 0.5, "irritation": -0.2},
            "priorities": {"hydration": 0.4, "barrier": 0.3, "irritation": 0.3},
            "positive_factors": [],
            "negative_factors": [],
            "normalized_ingredients": ["glycerin"],
            "goal_evidence": [],
        }
        ctx = build_report_context("Test", analysis, {}, "Очищение и демакияж")
        self.assertIn("category_knowledge", ctx)
        self.assertIn("демакияж", ctx["category_knowledge"].lower())
        self.assertIn("product_type", ctx)
        self.assertEqual(ctx["product_type"], "Очищение и демакияж")

    def test_context_unknown_category_uses_fallback(self):
        from app.report_prompt import build_report_context
        analysis = {
            "score": 50, "verdict": "Нейтральный результат",
            "dimensions": {}, "priorities": {},
            "positive_factors": [], "negative_factors": [],
            "normalized_ingredients": ["glycerin"], "goal_evidence": [],
        }
        ctx = build_report_context("Test", analysis, {}, "Нечто неопределённое")
        self.assertIn("Неопределённая категория", ctx["category_knowledge"])


if __name__ == "__main__":
    unittest.main()
