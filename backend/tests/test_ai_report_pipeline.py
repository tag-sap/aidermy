# test_ai_report_pipeline.py
# Проверка новой архитектуры AI Report: отчёт — вторичное текстовое представление
# User Analysis, а НЕ второй независимый анализ состава.

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import (
    build_active_ingredient,
    build_report_sections_prompt,
    generate_ai_report,
    generate_ai_report_sections,
    sanitize_report_sections,
)


class SanitizeReportSectionsTests(unittest.TestCase):
    """score 14% + negative factor → AI не может написать «подходит»."""

    def test_negative_verdict_rejects_positive_compatibility_claim(self):
        sections = {
            "how_to_use": {
                "application": "Тонкий слой",
                "time": "Вечером",
                "note": "Мягкая ПАВ-система подходит для чувствительной кожи с акне",
            },
        }
        cleaned = sanitize_report_sections("Не рекомендуется", sections)
        self.assertIsNone(cleaned["how_to_use"]["note"])

    def test_negative_verdict_keeps_caution_text(self):
        sections = {"expectations": {"danger": "fragrance может раздражать чувствительную кожу"}}
        cleaned = sanitize_report_sections("Не рекомендуется", sections)
        self.assertEqual(cleaned["expectations"]["danger"], "fragrance может раздражать чувствительную кожу")

    def test_positive_verdict_untouched(self):
        sections = {"how_to_use": {"note": "Подходит для ежедневного ухода"}}
        cleaned = sanitize_report_sections("Рекомендуется", sections)
        self.assertEqual(cleaned["how_to_use"]["note"], "Подходит для ежедневного ухода")


class BuildReportPromptTests(unittest.TestCase):
    def test_prompt_receives_structured_analysis_and_constraints(self):
        analysis = {
            "score": 14,
            "verdict": "Не рекомендуется",
            "summary": "формула не подходит",
            "positive_factors": [],
            "negative_factors": [{"ingredient": "fragrance", "property": "sensitivity"}],
            "safe_ingredients": [],
            "caution_ingredients": ["fragrance"],
        }
        prompt = build_report_sections_prompt("Мусс", analysis, {"skin_type": "Чувствительная"})
        self.assertIn("14%", prompt)
        self.assertIn("Не рекомендуется", prompt)
        self.assertIn("fragrance", prompt)
        self.assertIn("не пересчитывай процент", prompt)
        self.assertIn("не меняй вердикт", prompt)

    def test_positive_factor_does_not_become_verdict(self):
        analysis = {
            "score": 14,
            "verdict": "Не рекомендуется",
            "summary": "x",
            "positive_factors": [{"ingredient": "glycerin", "property": "hydration"}],
            "negative_factors": [{"ingredient": "fragrance", "property": "sensitivity"}],
        }
        prompt = build_report_sections_prompt("Мусс", analysis, {})
        self.assertIn("Не рекомендуется", prompt)
        self.assertNotIn("Рекомендуется", prompt)


class ActiveIngredientTests(unittest.TestCase):
    def test_active_ingredient_is_deterministic_first_ingredient(self):
        ai = build_active_ingredient({"normalized_ingredients": ["aqua", "glycerin", "fragrance"]})
        self.assertEqual(ai["name"], "aqua")
        self.assertEqual(ai["position"], 1)
        self.assertNotIn("effectiveness", ai)  # нет скрытого scoring factor

    def test_active_ingredient_none_without_composition(self):
        self.assertIsNone(build_active_ingredient({"normalized_ingredients": []}))


def _fake_ai_client(fake_json):
    """Патчит httpx.AsyncClient, возвращая статус 200 с поддельным ответом AI."""
    def decorator(fn):
        def wrapper(self):
            with patch("app.services.extract_json_from_response", return_value=fake_json):
                with patch("app.services.httpx.AsyncClient") as client_cls:
                    mock_client = AsyncMock()
                    client_cls.return_value.__aenter__.return_value = mock_client
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {"choices": [{"message": {"content": "{}"}}]}
                    mock_client.post.return_value = mock_response
                    return fn(self)
        return wrapper
    return decorator


class GenerateReportSectionsTests(unittest.TestCase):
    def test_no_structured_evidence_returns_none(self):
        result = asyncio.run(
            generate_ai_report_sections(
                "Мусс", {"score": 14, "positive_factors": [], "negative_factors": []}, {}
            )
        )
        self.assertIsNone(result["how_to_use"])
        self.assertIsNone(result["expectations"])

    @_fake_ai_client({
        "how_to_use": {"application": "Тонкий слой", "time": "Вечером"},
        "expectations": {"when": "1-2 недели", "normal": "увлажнение", "danger": "fragrance"},
    })
    def test_ai_sections_do_not_change_score(self):
        analysis = {
            "score": 14,
            "verdict": "Не рекомендуется",
            "positive_factors": [{"ingredient": "glycerin", "property": "hydration"}],
            "negative_factors": [{"ingredient": "fragrance", "property": "sensitivity"}],
        }
        result = asyncio.run(generate_ai_report_sections("Мусс", analysis, {}))
        self.assertNotIn("score", result)
        self.assertNotIn("verdict", result)
        self.assertEqual(result["how_to_use"]["application"], "Тонкий слой")

    @_fake_ai_client({
        "how_to_use": {"application": "Тонкий слой", "time": "Вечером", "note": "подходит чувствительной коже"},
        "expectations": {"when": "1-2 недели", "normal": "увлажнение", "danger": "fragrance"},
    })
    def test_contradicting_ai_output_is_sanitized(self):
        analysis = {
            "score": 14,
            "verdict": "Не рекомендуется",
            "positive_factors": [{"ingredient": "glycerin", "property": "hydration"}],
            "negative_factors": [{"ingredient": "fragrance", "property": "sensitivity"}],
        }
        result = asyncio.run(generate_ai_report_sections("Мусс", analysis, {}))
        self.assertIsNone(result["how_to_use"]["note"])


class ReportCachingTests(unittest.TestCase):
    """Отчёт привязан к конкретному актуальному User Analysis."""

    def test_same_analysis_returns_cached_report(self):
        # Повторное открытие того же актуального анализа — готовый отчёт (без нового AI).
        from app.shelf_service import _find_history_score
        product = {"name": "Мусс", "slug": "mousse"}
        history = [{
            "id": 1, "product_name": "Мусс", "slug": "mousse", "skin_type": "чувствительная",
            "score": 14, "verdict": "Не рекомендуется", "summary": "x", "ai_report": "готовый отчёт",
        }]
        score, analysis = _find_history_score(
            {"id": 1}, product, history=history, current_skin="чувствительная"
        )
        self.assertEqual(score, 14)
        self.assertEqual(analysis["report"], "готовый отчёт")

    def test_stale_analysis_skipped_when_skin_changed(self):
        # User Analysis стал неактуальным после смены профиля — старый отчёт не используется.
        from app.shelf_service import _find_history_score
        product = {"name": "Мусс", "slug": "mousse"}
        history = [{
            "id": 1, "product_name": "Мусс", "slug": "mousse", "skin_type": "нормальная",
            "score": 80, "verdict": "Рекомендуется", "summary": "x", "ai_report": "старый отчёт",
        }]
        score, analysis = _find_history_score(
            {"id": 1}, product, history=history, current_skin="чувствительная"
        )
        self.assertIsNone(score)
        self.assertIsNone(analysis)


class NeutralReasonTests(unittest.TestCase):
    """Превью карточки/подбора не выводит technical факторы как причины."""

    def test_reason_from_analysis_is_neutral(self):
        from app.shelf_service import _reason_from_analysis
        analysis = {
            "verdict": "Не рекомендуется",
            "positive_factors": [{"ingredient": "Glycerin", "property": "hydration"}],
            "negative_factors": [{"ingredient": "Fragrance", "property": "sensitivity"}],
        }
        reason = _reason_from_analysis(analysis)
        self.assertEqual(reason, "Не рекомендуется")
        self.assertNotIn("Glycerin", reason)
        self.assertNotIn("Fragrance", reason)
        self.assertNotIn("Подходит", reason)
        self.assertNotIn("Требует внимания", reason)

    def test_reason_falls_back_to_score(self):
        from app.shelf_service import _reason_from_analysis
        self.assertEqual(_reason_from_analysis({"score": 14}), "Совместимость 14%")


class GenerateReportFactorsTests(unittest.TestCase):
    def test_generate_ai_report_passes_structured_factors(self):
        # AI получает исходные structured factors (property/direction), а не ingredient-only.
        analysis = {
            "score": 14,
            "positive_factors": [{"ingredient": "glycerin", "property": "hydration", "direction": "positive"}],
            "negative_factors": [{"ingredient": "fragrance", "property": "sensitivity", "direction": "negative"}],
            "summary": "x",
        }
        with patch("app.ai_summary.summarize_with_ai", return_value="рецензия") as mock:
            report = asyncio.run(generate_ai_report("Мусс", analysis, {}))
        self.assertEqual(report, "рецензия")
        passed_analysis = mock.call_args[0][2]
        self.assertEqual(passed_analysis["positive_factors"][0]["property"], "hydration")
        self.assertEqual(passed_analysis["negative_factors"][0]["direction"], "negative")


class AIPromptHumanTermsTests(unittest.TestCase):
    def test_prompt_receives_factor_and_instructs_human_terms(self):
        from app.ai_summary import _prompt
        prompt = _prompt(
            "Мусс",
            14,
            [],
            [{"ingredient": "fragrance", "property": "sensitivity", "direction": "negative"}],
            "Чувствительная",
            [],
        )
        # Фактор передаётся AI как данные (не как готовый UI-текст).
        self.assertIn("fragrance", prompt)
        # AI инструктирован объяснять человеческим языком, не выводя технические INCI-имена.
        self.assertIn("человеческим языком", prompt)
        self.assertIn("парфюмерная композиция", prompt)
