from app.shelf_service import (
    infer_cabinet_category,
    is_product_compatible,
    _allergy_conflict,
)
from app.decision_engine import build_summary


def test_body_lotion_not_face_toner():
    cabinet, cat = infer_cabinet_category("Тонер", "Naturium Bio-Lipid Restoring Body Lotion")
    assert cabinet == "body"
    assert cat == "Кремы / лосьоны"


def test_hair_mask_not_face_mask():
    cabinet, cat = infer_cabinet_category("Маска", "Ecolatier Aloe Vera Hydrating & Fortifying Hair Mask")
    assert cabinet == "hair"


def test_toner_stays_face():
    cabinet, cat = infer_cabinet_category("Тонер", "Hydrating Facial Toner")
    assert cabinet == "face"
    assert cat == "Тонизация"


def test_body_lotion_rejected_for_face_toner():
    ok, reason = is_product_compatible(
        {"name": "Naturium Bio-Lipid Restoring Body Lotion", "category": "Тонер"},
        "face",
        "Тонизация",
    )
    assert ok is False


def test_allergy_conflict_niacinamide():
    assert _allergy_conflict("Aqua, Niacinamide, Glycerin", ["Niacinamide"]) is True


def test_allergy_conflict_clean():
    assert _allergy_conflict("Aqua, Glycerin", ["Niacinamide"]) is False


def test_allergy_conflict_fragrance_synonym():
    assert _allergy_conflict("Aqua, Parfum, Glycerin", ["Отдушки"]) is True


def test_allergy_conflict_acid_synonym_does_not_match_hyaluronic():
    # «acid» не должен ловить «hyaluronic acid» — иначе исключается почти всё.
    assert _allergy_conflict("Aqua, Hyaluronic Acid, Glycerin", ["Кислоты"]) is False


def test_allergy_conflict_acid_synonym_matches_salicylic():
    assert _allergy_conflict("Aqua, Salicylic Acid, Glycerin", ["Кислоты"]) is True


def test_summary_has_no_internal_factor_names():
    summary = build_summary(
        {
            "hard_flags": [],
            "positive_factors": [
                {"ingredient": "Glycerin", "property": "hydration", "direction": "positive", "strength": 0.8, "confidence": 0.9}
            ],
            "negative_factors": [
                {"ingredient": "Alcohol", "property": "sensitivity", "direction": "negative", "strength": 0.7, "confidence": 0.8}
            ],
            "confidence": 0.9,
        },
        {"skin_type": "Сухая"},
        "Сухая",
        75,
    )
    assert "фактор" not in summary
    # hardcoded-объяснения причин убраны: summary не содержит ингредиентов и эффектов.
    assert "Glycerin" not in summary
    assert "увлажнение" not in summary
    assert "Alcohol" not in summary
