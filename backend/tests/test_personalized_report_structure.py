import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import services


def _profile_case(label, concern_id, property_name, ingredient, verdict):
    evidence = []
    if concern_id:
        evidence = [{
            "concern_id": concern_id,
            "label": label,
            "verdict": verdict,
            "evidence": [{
                "ingredient": ingredient,
                "property": property_name,
                "verdict": verdict,
                "strength": 0.8,
                "confidence": 0.9,
                "evidence_level": "ingredient_claim",
            }],
        }]
    return {
        "profile": {"skin_type": label, "concerns": [label] if concern_id else []},
        "analysis": {
            "score": 62,
            "verdict": "Требует внимания",
            "dimensions": {"hydration": 1.5},
            "priorities": {"hydration": 0.5},
            "positive_factors": [{"ingredient": "glycerin", "property": "hydration"}],
            "negative_factors": [],
            "normalized_ingredients": ["aqua", "glycerin", "niacinamide", "salicylic acid"],
            "goal_evidence": evidence,
        },
    }


class PersonalizedReportStructureTests(unittest.TestCase):
    def test_prompt_uses_only_saved_goal_evidence_for_personalization(self):
        cases = [
            _profile_case(
                "Чувствительная кожа",
                "irritation_prone",
                "soothing",
                "niacinamide",
                "supports",
            ),
            _profile_case(
                "Акне",
                "acne_general",
                "anti_acne",
                "salicylic acid",
                "supports",
            ),
            _profile_case(
                "Постакне и пигментация",
                "post_acne_pigmentation",
                "brightening",
                "niacinamide",
                "supports",
            ),
            _profile_case("Жирная кожа", None, "", "", ""),
        ]
        prompts = []
        output = {
            "explanation": "Формулировка основана на предоставленных данных состава и профиля.",
            "how_to_use": None,
            "expectations": None,
        }

        for case in cases:
            with self.subTest(profile=case["profile"]):
                with patch.object(services, "DEEPSEEK_API_KEY", "test-key"), \
                     patch("app.services.httpx.AsyncClient") as client_cls, \
                     patch.object(services, "extract_json_from_response", return_value=output):
                    async_client = AsyncMock()
                    client_cls.return_value.__aenter__.return_value = async_client
                    response = Mock()
                    response.status_code = 200
                    response.json.return_value = {
                        "choices": [{"message": {"content": "{}"}}],
                    }
                    async_client.post.return_value = response
                    parts = asyncio.run(
                        services.generate_report_once(
                            "Тестовый продукт",
                            case["analysis"],
                            case["profile"],
                            "Кремы",
                        )
                    )
                    prompts.append(
                        async_client.post.call_args.kwargs["json"]["messages"][0]["content"]
                    )
                self.assertIsNotNone(parts)

        sensitive_prompt, acne_prompt, pigmentation_prompt, neutral_prompt = prompts
        self.assertIn("irritation_prone", sensitive_prompt)
        self.assertIn("acne_general", acne_prompt)
        self.assertIn("post_acne_pigmentation", pigmentation_prompt)
        self.assertIn(":\n[]", neutral_prompt)
        self.assertNotIn("acne_general", neutral_prompt)
        for prompt in prompts:
            self.assertIn('"explanation"', prompt)
            self.assertIn('"how_to_use"', prompt)
            self.assertIn('"expectations"', prompt)
            self.assertNotIn('"positive":', prompt)
            self.assertNotIn('"negative":', prompt)

    def test_full_report_returns_only_user_facing_blocks_and_preserves_match(self):
        saved = {
            "score": 0,
            "verdict": "Не рекомендуется",
            "deterministic": {
                "score": 41,
                "verdict": "Другое значение",
                "summary": "Сохранённое deterministic объяснение.",
                "normalized_ingredients": ["aqua", "glycerin"],
                "positive_factors": [],
                "negative_factors": [],
            },
        }
        generated = {
            "explanation": "Состав требует осторожности с учётом сохранённых факторов.",
            "how_to_use": {"application": "Нанести после очищения.", "time": "Вечером.", "note": ""},
            "expectations": "Ориентируйтесь на переносимость состава.",
        }
        with patch.object(services, "DEEPSEEK_API_KEY", "test-key"), \
             patch.object(services, "generate_report_once", new_callable=AsyncMock, return_value=generated):
            report = asyncio.run(
                services.generate_full_report(
                    "Тестовый продукт",
                    "Aqua, Glycerin",
                    {"skin_type": "Чувствительная"},
                    "Чувствительная",
                    "Кремы",
                    saved_analysis=saved,
                )
            )

        self.assertEqual(report["score"], 0)
        self.assertEqual(report["verdict"], "Не рекомендуется")
        self.assertEqual(report["explanation"], generated["explanation"])
        self.assertEqual(report["review"][0]["text"], generated["explanation"])
        self.assertEqual(
            set(report),
            {"score", "verdict", "explanation", "review", "how_to_use", "expectations"},
        )


if __name__ == "__main__":
    unittest.main()
