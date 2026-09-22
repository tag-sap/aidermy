# ingredient_enrichment.py
# AI #2 — Ingredient Enrichment.
#
# Запускается ТОЛЬКО когда в Ingredient DB не найден ингредиент из INCI.
# AI определяет: что это, aliases, функции, свойства, влияние на кожу,
# irritation/sensitization и (при необходимости) аллергенный статус.
# Результат сохраняется в Ingredient DB и Allergen/Sensitizer DB.
#
# Цель: до scoring engine все ингредиенты товара должны быть известны системе.

from __future__ import annotations

from typing import List, Optional, Set

from .ingredient_normalizer import normalize_ingredient_name
from .ingredient_repository import IngredientRepository


def find_unknown_ingredients(
    ingredients: List[str],
    repository: Optional[IngredientRepository] = None,
) -> List[str]:
    """Возвращает список ингредиентов, которых нет в Ingredient DB.

    Проверка дешёвая: по normalized_name и синонимам (get_known_names).
    """
    repo = repository or IngredientRepository()
    repo.ensure_ingredient_tables()
    known = repo.get_known_names()

    unknown: List[str] = []
    seen: Set[str] = set()
    for raw in ingredients:
        key = normalize_ingredient_name(raw)
        if not key or key in seen or key in {"water", "aqua"}:
            continue
        seen.add(key)
        if key not in known:
            unknown.append(raw)
    return unknown


def _prompt(unknown: List[str]) -> str:
    return (
        "Ты — косметический химик. Для каждого из перечисленных INCI-ингредиентов "
        "составь структурированную запись для базы знаний.\n\n"
        "Ингредиенты:\n" + "\n".join(f"- {name}" for name in unknown) + "\n\n"
        "Верни ТОЛЬКО JSON-массив объектов:\n"
        '[{"inci_name": "...", "canonical_name": "...", "aliases": ["..."], '
        '"functions": ["..."], "skin_effects": ["..."], '
        '"hydration": 0..1, "barrier_support": 0..1, "soothing": 0..1, '
        '"oil_control": 0..1, "brightening": 0..1, '
        '"irritation_risk": 0..1, "comedogenicity": 0..5, "sensitization": 0..1, '
        '"evidence_level": "low|moderate|high", "confidence": 0..1, '
        '"claims": [{"property": "hydration|barrier_support|sensitivity|acne_control|brightening", '
        '"direction": "positive|negative", "strength": 0..1, "confidence": 0..1}], '
        '"allergen": {"is_allergen": true|false, "is_sensitizer": true|false, '
        '"allergen_level": "none|low|moderate|high|known", "sensitization_potential": 0..1}}]\n\n'
        "claims используй только для известных свойств; неизвестные свойства не выдумывай "
        "(confidence низкий). Если ингредиент не является аллергеном/сенсибилизатором, "
        'allergen = {"is_allergen": false, "is_sensitizer": false}. Верни ТОЛЬКО JSON.'
    )


async def enrich_unknown_ingredients(
    unknown: List[str],
    repository: Optional[IngredientRepository] = None,
) -> int:
    """AI #2 — обогащает неизвестные ингредиенты и сохраняет в БД.

    Возвращает количество успешно сохранённых ингредиентов.
    """
    if not unknown:
        return 0

    repo = repository or IngredientRepository()
    repo.ensure_ingredient_tables()

    try:
        from .services import (
            DEEPSEEK_API_KEY,
            DEEPSEEK_API_URL,
            DEEPSEEK_MODEL_FALLBACKS,
            extract_json_from_response,
        )
    except Exception:
        return 0

    if not DEEPSEEK_API_KEY:
        return 0

    import httpx

    for model_name in DEEPSEEK_MODEL_FALLBACKS:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    DEEPSEEK_API_URL,
                    headers={
                        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model_name,
                        "messages": [{"role": "user", "content": _prompt(unknown)}],
                        "temperature": 0.2,
                        "max_tokens": 3000,
                    },
                    timeout=60,
                )
            if response.status_code != 200:
                continue
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            result = extract_json_from_response(content)
            records = result if isinstance(result, list) else (result.get("ingredients") if isinstance(result, dict) else None)
            if not isinstance(records, list):
                continue

            saved = 0
            for record in records:
                if not isinstance(record, dict):
                    continue
                record.setdefault("inci_name", record.get("canonical_name") or record.get("name") or "")
                record.setdefault("normalized_name", normalize_ingredient_name(record.get("inci_name") or ""))
                record.setdefault("synonyms", record.get("aliases") or [])

                claims = []
                for claim in record.get("claims") or []:
                    claims.append({
                        "property_name": claim.get("property_name") or claim.get("property") or "",
                        "direction": claim.get("direction") or "neutral",
                        "strength": claim.get("strength") or 0.0,
                        "confidence": claim.get("confidence") or 0.0,
                        "evidence_level": claim.get("evidence_level") or record.get("evidence_level") or "moderate",
                    })
                record["claims"] = claims

                if repo.save_enriched_ingredient(record):
                    saved += 1
            return saved
        except Exception as exc:
            print(f"[ENRICH] AI enrichment {model_name} failed: {exc}")
            continue

    return 0

