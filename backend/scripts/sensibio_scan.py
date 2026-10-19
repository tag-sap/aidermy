"""Скан продуктов Sensibio: найти score, близкий к указанному (диагностика)."""
from __future__ import annotations

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

# Кэш goal-evidence по составу (не влияет на score, только ускоряет скан).
_original_goal_map = IngredientRepository.get_goal_evidence_map
_goal_cache: dict = {}


def _cached_goal_map(self, ingredients=None):
    key = tuple(sorted(str(i) for i in (ingredients or [])))
    if key not in _goal_cache:
        _goal_cache[key] = _original_goal_map(self, ingredients)
    return _goal_cache[key]


IngredientRepository.get_goal_evidence_map = _cached_goal_map

TARGET = float(sys.argv[1]) if len(sys.argv) > 1 else 46.0
TOLERANCE = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0


def main() -> None:
    dsn = dotenv_values(".env")["SUPABASE_DATABASE_URL"]
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, ingredients FROM public.products "
                "WHERE name ILIKE %s AND ingredients IS NOT NULL ORDER BY id",
                ("%sensibio%",),
            )
            rows = cur.fetchall()
    engine = DecisionEngine()
    knowledge = IngredientRepository().get_canonical_knowledge_map()
    hits = 0
    for pid, name, ingredients in rows:
        clean_name = str(name).replace("\n", " ").strip()
        has_citric = "citric acid" in str(ingredients).lower()
        for profile in CALIBRATION_PROFILES:
            result = engine.analyze(
                clean_name, ingredients,
                {"structured": dict(profile["structured"])},
                knowledge=knowledge,
            )
            score = result.get("score")
            if score is not None and abs(score - TARGET) <= TOLERANCE:
                hits += 1
                print(f"id={pid} profile={profile['id']} score={score} citric={has_citric} "
                      f"status={result.get('phase1_status')} | {clean_name}")
    print(f"scanned products={len(rows)} hits={hits}")


if __name__ == "__main__":
    main()
