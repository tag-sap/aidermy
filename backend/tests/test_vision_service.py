import os
import tempfile

from app.vision_service import (
    _coerce_recognition,
    recognized_normalized_list,
    _tokenize_inci,
    find_product_matches,
    register_ingredients,
)


def test_coerce_recognition_string_items_and_missing_fields():
    raw = {
        "is_inci": True,
        "ingredients": [
            {"raw": "Aqua", "normalized": "Aqua", "confidence": 0.99},
            "Glycerin",
            {"raw": "", "normalized": "", "confidence": 0.5},
        ],
        "uncertain_items": ["размыто", {"text": "обрез", "reason": "край"}],
        "overall_confidence": 0.9,
    }
    result = _coerce_recognition(raw)
    assert result["is_inci"] is True
    assert len(result["ingredients"]) == 2
    assert result["ingredients"][0]["normalized"] == "Aqua"
    assert result["ingredients"][1]["normalized"] == "Glycerin"
    assert len(result["uncertain_items"]) == 2
    assert result["uncertain_items"][1]["reason"] == "край"
    assert result["overall_confidence"] == 0.9


def test_coerce_recognition_falls_back_overall_confidence():
    raw = {
        "ingredients": [
            {"raw": "Aqua", "normalized": "Aqua", "confidence": 0.8},
            {"raw": "Glycerin", "normalized": "Glycerin", "confidence": 0.6},
        ],
    }
    result = _coerce_recognition(raw)
    assert result["overall_confidence"] == 0.7


def test_recognized_normalized_list_dedup_and_order():
    recognition = {
        "ingredients": [
            {"raw": "Aqua", "normalized": "Aqua"},
            {"raw": "Glycerine", "normalized": "Glycerin"},
            {"raw": "glycerin", "normalized": "glycerin"},
            {"raw": "Niacinamide", "normalized": "Niacinamide"},
        ]
    }
    result = recognized_normalized_list(recognition)
    # glycerine и glycerin канонизируются в один ингредиент, без дублей.
    assert result == ["aqua", "glycerin", "niacinamide"]


def test_tokenize_inci_splits_and_normalizes():
    tokens = _tokenize_inci("Aqua, Glycerin; Niacinamide\nTocopherol (Vit E)")
    assert tokens == {"aqua", "glycerin", "niacinamide", "tocopherol"}


def test_find_product_matches_returns_sorted_matches():
    matches = find_product_matches(["aqua", "glycerin", "niacinamide"], limit=3)
    assert isinstance(matches, list)
    assert len(matches) <= 3
    for m in matches:
        assert "slug" in m
        assert "match_percent" in m
        assert m["match_percent"] > 0
    # сортировка по убыванию совпадения
    percents = [m["match_percent"] for m in matches]
    assert percents == sorted(percents, reverse=True)


def test_find_product_matches_empty_for_unknown():
    matches = find_product_matches(["some_unknown_ingredient_xyz"], limit=3)
    assert matches == []


def test_register_ingredients_dedup_and_reuse():
    db_path = os.path.join(tempfile.mkdtemp(), "test.db")
    first = register_ingredients(
        [
            {"raw": "Glycerin", "normalized": "Glycerin"},
            {"raw": "glycerine", "normalized": "glycerine"},
            {"raw": "Aqua", "normalized": "Aqua"},
        ],
        db_path=db_path,
    )
    names = [r["normalized"] for r in first]
    assert names == ["glycerin", "aqua"]

    second = register_ingredients([{"raw": "Glycerin", "normalized": "Glycerin"}], db_path=db_path)
    assert second[0]["id"] == first[0]["id"]
