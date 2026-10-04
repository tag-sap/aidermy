# tests/test_report_grounding.py
# Фаза 18 — Report grounding: actual INCI is the only source of truth for ingredients.
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import _ground_report_text, _ground_report_sections, _report_allowed_ingredients

# The Ordinary AHA 30% + BHA 2% Peeling Solution — actual normalized INCI (short version).
THE_ORDINARY_NORMALIZED = [
    "aqua", "sodium hydroxide", "daucus carota sativa extract", "propanediol",
    "cocamidopropyl dimethylamine", "salicylic acid", "lactic acid",
    "tartaric acid", "citric acid", "panthenol",
    "sodium hyaluronate crosspolymer", "tasmannia lanceolata fruit",
    "glycerin", "pentylene glycol", "xanthan gum", "polysorbate 20",
    "trisodium ethylenediamine disuccinate", "potassium sorbate",
    "sodium benzoate", "ethylhexylglycerin", "1,2-hexanediol", "caprylyl glycol",
]


class ReportGroundingTests(unittest.TestCase):
    def _allowed(self):
        return _report_allowed_ingredients({"normalized_ingredients": THE_ORDINARY_NORMALIZED})

    def test_invented_key_ingredient_rejected(self):
        # Niacinamide отсутствует в actual INCI -> reject.
        self.assertIsNone(_ground_report_text("Ключевой компонент — ниацинамид", self._allowed(), True))

    def test_invented_report_ingredient_rejected(self):
        # Aloe Barbadensis Leaf Water отсутствует -> reject.
        self.assertIsNone(_ground_report_text("В составе есть алоэ вера", self._allowed(), True))

    def test_synonym_without_mapping_rejected(self):
        # Sodium Hyaluronate Crosspolymer есть, но «гиалуроновая кислота» без mapping -> reject.
        self.assertIsNone(_ground_report_text("Содержит гиалуроновую кислоту", self._allowed(), True))

    def test_contradiction_rejected(self):
        # Есть negative factors (кислоты), а LLM пишет «агрессивных активов нет» -> reject.
        self.assertIsNone(_ground_report_text("Агрессивных активов нет", self._allowed(), True))
        # Без negative factors такая фраза не блокируется.
        self.assertIsNotNone(_ground_report_text("Агрессивных активов нет", self._allowed(), False))

    def test_valid_ingredient_accepted(self):
        # Panthenol реально есть -> accept.
        self.assertIsNotNone(_ground_report_text("Пантенол успокаивает", self._allowed(), True))

    def test_score_and_verdict_invariant_are_not_touched_by_grounding(self):
        # Grounding не пересчитывает score/verdict — только проверяет текст.
        text = "Совместимость 14%, вердикт не меняется"
        grounded = _ground_report_text(text, self._allowed(), True)
        self.assertEqual(grounded, text)


# ARAVIA Laboratories Aloe Vera Aqua Gel — actual normalized INCI (production bug repro).
ALOE_NORMALIZED = [
    "aqua", "chamomilla recutita flower extract", "aloe barbadensis",
    "glycerin", "triethanolamine", "acrylates",
    "peg-40 hydrogenated castor oil", "disodium edta", "fragrance",
    "dmdm hydantoin", "iodopropynyl butylcarbamate", "propylene glycol",
]

ALOE_DETERMINISTIC = {
    "normalized_ingredients": ALOE_NORMALIZED,
    "negative_factors": [{"ingredient": "fragrance", "property": "irritation", "direction": "negative"}],
    "positive_factors": [{"ingredient": "aloe barbadensis", "property": "hydration", "direction": "positive"}],
}


class AloeVeraGroundingTests(unittest.TestCase):
    def _allowed(self):
        return _report_allowed_ingredients(ALOE_DETERMINISTIC)

    def test_invented_hyaluronic_rejected(self):
        self.assertIsNone(_ground_report_text("Содержит гиалуроновую кислоту", self._allowed(), True, ALOE_DETERMINISTIC))

    def test_invented_niacinamide_rejected(self):
        self.assertIsNone(_ground_report_text("Ниацинамид выравнивает тон", self._allowed(), True, ALOE_DETERMINISTIC))

    def test_invented_panthenol_rejected(self):
        self.assertIsNone(_ground_report_text("Пантенол успокаивает", self._allowed(), True, ALOE_DETERMINISTIC))

    def test_retinoid_mention_rejected_without_evidence(self):
        self.assertIsNone(_ground_report_text("Возможна реакция при сочетании с ретиноидом", self._allowed(), True, ALOE_DETERMINISTIC))

    def test_real_ingredient_accepted(self):
        self.assertIsNotNone(_ground_report_text("Глицерин увлажняет", self._allowed(), True, ALOE_DETERMINISTIC))

    def test_sections_grounded(self):
        sections = {
            "how_to_use": {"application": "Нанесите", "time": "Вечером", "note": "С ретиноидом не сочетать"},
            "expectations": {"when": "Сразу", "normal": "Ниацинамид улучшает тон", "danger": "Пантенол может щипать"},
        }
        grounded = _ground_report_sections(sections, self._allowed(), True, ALOE_DETERMINISTIC)

        # invented ingredients dropped from individual fields, safe fields kept
        self.assertIsNotNone(grounded.get("expectations"))
        self.assertIsNone(grounded["expectations"].get("normal"))
        self.assertIsNone(grounded["expectations"].get("danger"))
        self.assertEqual(grounded["expectations"].get("when"), "Сразу")

        self.assertIsNotNone(grounded.get("how_to_use"))
        self.assertIsNone(grounded["how_to_use"].get("note"))
        self.assertEqual(grounded["how_to_use"].get("application"), "Нанесите")
        self.assertEqual(grounded["how_to_use"].get("time"), "Вечером")


if __name__ == "__main__":
    unittest.main()
