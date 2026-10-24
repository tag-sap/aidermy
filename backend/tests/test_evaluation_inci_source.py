"""Deterministic INCI answers from the stored composition."""
from __future__ import annotations

import unittest

from app.evaluation.analysis import AnalysisReport
from app.evaluation.gaps import AnalysisState, scan_parameters
from app.evaluation.inci import NOT_LISTED, PRESENT, check_intolerance
from app.evaluation.parameters import resolve_parameters


ART_FACT_INCI = (
    "Aqua/Water, Disodium Laureth Sulfosuccinate, Coco-Glucoside, Glycerin, "
    "Sodium PEG-7 Olive Oil Carboxylate, Cocamidopropyl Betaine, Dehydroacetic Acid, "
    "Benzyl Alcohol, Citric Acid, Chamomilla Recutita Flower Extract, Panax Ginseng Root Extract, "
    "Melissa Officinalis Leaf Extract, Cymbopogon Schoenanthus Extract, Salvia Officinalis Leaf Extract, "
    "Hydrolyzed Milk Protein, Aloe Barbadensis Leaf Extract, Sodium Lactate, Sodium Glycolate, "
    "Sodium Citrate, Sodium Malate, Disodium Tartrate, Lactic Acid, Glycolic Acid, Malic Acid, "
    "Tartaric Acid, Urea, Potassium Azeloyl Diglycinate, Sodium PCA, Glycine, Salicylic Acid, "
    "Arginine, Aspartic Acid, Pca, Alanine, Serine, Valine, Proline, Threonine, Isoleucine, "
    "Histidine, Phenylalanine, Cucumis Sativus (Cucumber) Extract, Panthenol"
)
PROFILE = {
    "structured": {
        "skin_type": "combination",
        "concerns": ["acne_general"],
        "intolerances": ["niacinamide_intolerance"],
    }
}
INCI_ONLY_PROFILE = {
    "structured": {
        "intolerances": ["niacinamide_intolerance"],
    }
}


def composition(inci: str = ART_FACT_INCI) -> dict:
    return {
        "composition_hash": "a" * 64,
        "status": "active",
        "inci_raw": inci,
        "source": "https://incidecoder.com/products/art-fact-aha-complex-bha-acid-face-foam",
    }


class InciSourceTests(unittest.TestCase):
    def test_art_fact_niacinamide_absent_from_saved_inci_is_positive(self):
        parameter = next(
            item for item in resolve_parameters(PROFILE).parameters
            if item.id == "intolerance:niacinamide_intolerance"
        )
        checked = check_intolerance(parameter, composition())
        self.assertEqual(checked.status, NOT_LISTED)
        self.assertTrue(checked.verified)

    def test_art_fact_niacinamide_present_in_saved_inci_is_positive(self):
        parameter = next(
            item for item in resolve_parameters(PROFILE).parameters
            if item.id == "intolerance:niacinamide_intolerance"
        )
        checked = check_intolerance(
            parameter,
            composition("Aqua, Glycerin, Niacinamide"),
        )
        self.assertEqual(checked.status, PRESENT)
        self.assertTrue(checked.verified)

    def test_deterministic_inci_closes_the_gap_without_research(self):
        scan = scan_parameters(
            evaluations=(),
            profile=INCI_ONLY_PROFILE,
            composition_hash="a" * 64,
            method_version="test",
            composition=composition(),
        )
        self.assertEqual(scan.needed, ())
        self.assertEqual(scan.gaps, ())

    def test_empty_inci_remains_unknown(self):
        scan = scan_parameters(
            evaluations=(),
            profile=INCI_ONLY_PROFILE,
            composition_hash="a" * 64,
            method_version="test",
            composition=composition(""),
        )
        self.assertIn("intolerance:niacinamide_intolerance", scan.needed)

    def test_user_report_adds_inci_row_even_when_snapshot_has_no_evaluation(self):
        report = AnalysisReport(
            product={"id": 1250, "name": "ART&FACT. AHA Complex + BHA Acid Face Foam"},
            composition=composition(),
            snapshot={"parameters": [], "analysis": {"status": "incomplete"}},
            analysis=AnalysisState(status="complete", is_final=True),
            primary_function={
                "label": "Очищение",
                "purpose": "",
                "score": None,
                "reason": "",
                "basis": [],
            },
            profile_input=PROFILE,
        )
        item = report.user_report()["personal_compatibility"][0]
        self.assertEqual(item["parameter_id"], "intolerance:niacinamide_intolerance")
        self.assertEqual(item["verdict"], "positive")
        self.assertEqual(item["display_text"], "Ниацинамид не обнаружен в составе.")
        self.assertEqual(item["derived"], True)


if __name__ == "__main__":
    unittest.main()
