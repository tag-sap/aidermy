"""Диагностика позиционного веса на конкретном продукте (не калибровка).

Показывает: INCI с позициями, вклады Citric Acid до/после, топ-вклады и итог
для baseline (production) и кандидата.
"""
from __future__ import annotations

import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.chdir(BASE)

from dotenv import load_dotenv, dotenv_values  # noqa: E402

load_dotenv(".env")

import psycopg  # noqa: E402

from app.calibration_profiles import CALIBRATION_PROFILES  # noqa: E402
from app.decision_engine import DecisionEngine  # noqa: E402
from app.ingredient_repository import IngredientRepository  # noqa: E402
from app.ingredient_normalizer import canonicalize_ingredient_name  # noqa: E402

CANDIDATE = {"mode": "power", "exponent": 1.0, "min_weight": 0.30, "apply_to": "both"}


def load_product(product_id: int):
    dsn = dotenv_values(".env")["SUPABASE_DATABASE_URL"]
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, ingredients, catalog_category FROM public.products WHERE id=%s",
                (product_id,),
            )
            return cur.fetchone()


def positions(ingredients: str):
    parts = [p.strip() for p in str(ingredients or "").split(",") if p.strip()]
    return [(index, part) for index, part in enumerate(parts, start=1)]


def factor_view(factors, ingredient_key):
    out = []
    for factor in factors:
        if ingredient_key in str(factor.get("ingredient") or "").lower():
            out.append({
                "property": factor.get("property"),
                "direction": factor.get("direction"),
                "strength": factor.get("strength"),
                "confidence": factor.get("confidence"),
                "position_weight": factor.get("position_weight"),
                "weighted_value": factor.get("weighted_value"),
            })
    return out


def main() -> None:
    product_ids = [int(value) for value in sys.argv[1:]] or [4398]
    engine = DecisionEngine()
    knowledge = IngredientRepository().get_canonical_knowledge_map()
    profiles = {p["id"]: p for p in CALIBRATION_PROFILES}
    for product_id in product_ids:
        row = load_product(product_id)
        if not row:
            print(f"product {product_id}: NOT FOUND")
            continue
        _pid, raw_name, ingredients, category = row
        name = str(raw_name).replace("\n", " ").strip()
        ingredients = ingredients or ""
        print("=" * 80)
        print(f"product {product_id}: {name} | {category}")
        for position, part in positions(ingredients):
            print(f"  {position:2d}. {part}")
        for profile_id in ("P01", "P06", "P15", "P24"):
            profile = profiles[profile_id]
            base = engine.analyze(name, ingredients, {"structured": dict(profile["structured"])},
                                  knowledge=knowledge)
            cand = engine.analyze(name, ingredients, {"structured": dict(profile["structured"])},
                                  knowledge=knowledge, position_config=CANDIDATE)
            print(f"\n  profile {profile_id} ({profile['label']}): "
                  f"baseline={base.get('score')} candidate={cand.get('score')}")
            for label, result in (("baseline", base), ("candidate", cand)):
                citric = factor_view(result.get("negative_factors") or [], "citric acid")
                print(f"    {label}: citric_acid={json.dumps(citric, ensure_ascii=False)}")
                top_pos = sorted(
                    result.get("positive_factors") or [],
                    key=lambda f: -abs(float(f.get("weighted_value") or 0)),
                )[:3]
                top_neg = sorted(
                    result.get("negative_factors") or [],
                    key=lambda f: -abs(float(f.get("weighted_value") or 0)),
                )[:3]
                print("      top+:", [(f["ingredient"], f["property"], round(float(f.get("weighted_value") or 0), 3)) for f in top_pos])
                print("      top-:", [(f["ingredient"], f["property"], round(float(f.get("weighted_value") or 0), 3)) for f in top_neg])
                if label == "baseline":
                    print("      dimensions:", result.get("dimensions"))
            print("      position_model:", base.get("position_model"), "->", cand.get("position_model"))


if __name__ == "__main__":
    main()
