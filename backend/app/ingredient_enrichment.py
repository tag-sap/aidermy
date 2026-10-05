# ingredient_enrichment.py
# AI #2 — Ingredient Enrichment.
#
# Обогащает только отсутствующие знания по ингредиентам из текущего анализа:
# неизвестные ингредиенты и missing ingredient/concern evidence pairs.
# Результат сохраняется в существующие Ingredient DB / ingredient_claims.
#
# Цель: до scoring engine все ингредиенты товара должны быть известны системе.

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Set

from .goal_evidence import (
    find_missing_concern_pairs,
    scoped_concern_property,
    selected_concern_ids,
)
from .ingredient_normalizer import normalize_ingredient_name
from .ingredient_repository import IngredientRepository


def find_missing_concern_evidence(
    profile: Mapping[str, Any],
    ingredients: List[str],
    repository: Optional[IngredientRepository] = None,
) -> List[Dict[str, Any]]:
    if not selected_concern_ids(profile):
        return []
    repo = repository or IngredientRepository()
    repo.ensure_ingredient_tables()
    return find_missing_concern_pairs(
        profile,
        ingredients,
        repo.get_goal_evidence_map(ingredients),
    )


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
    from .claim_direction import prompt_instruction

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
        '"claims": [{"property": "hydration|barrier|irritation|sensitization|sebum|pigmentation", '
        '"direction": "positive|negative", "strength": 0..1, "confidence": 0..1, '
        '"evidence": "..."}], '
        '"allergen": {"is_allergen": true|false, "is_sensitizer": true|false, '
        '"allergen_level": "none|low|moderate|high|known", "sensitization_potential": 0..1}}]\n\n'
        "claims используй ТОЛЬКО канонические оси (см. выше).\n"
        + prompt_instruction() + "\n"
        "claims используй только для известных свойств; неизвестные свойства не выдумывай "
        "(confidence низкий). Если ингредиент не является аллергеном/сенсибилизатором, "
        'allergen = {"is_allergen": false, "is_sensitizer": false}. Верни ТОЛЬКО JSON.'
    )


# Для enrichment используем только deepseek-chat: фолбэки deepseek-v4-flash /
# deepseek-flash — это reasoning-модели, возвращающие пустой `content`
# (ответ кладут в `reasoning_content`), поэтому для JSON-задачи они бесполезны.
_ENRICH_MODEL_FALLBACKS = ["deepseek-chat"]
_ENRICH_MAX_TOKENS = 8000


def _parse_enrichment_response(content: str) -> List[dict]:
    """Парсит ответ AI для enrichment.

    AI может вернуть JSON-массив `[{...}, {...}]` (как просит промпт) или
    объект `{"ingredients": [...]}`. Промпт просит именно массив, поэтому
    `extract_json_from_response` (он возвращает только dict) здесь не подходит —
    он ломался на массиве regex'ом на фигурных скобках и кидал «Невалидный JSON».
    """
    import json as _json
    import re as _re

    if not content or not isinstance(content, str):
        raise ValueError("Пустой ответ AI")

    s = content.strip()

    # Снимаем markdown-ограждение, если модель обернула JSON в ```json ... ```.
    fence = _re.search(r"```(?:json)?\s*([\s\S]*?)```", s, _re.DOTALL)
    if fence:
        s = fence.group(1).strip()

    obj = None
    try:
        obj = _json.loads(s)
    except Exception:
        obj = None

    # Массив может быть обёрнут пояснительным текстом — берём первый `[ ... ]`.
    if obj is None:
        start, end = s.find("["), s.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                obj = _json.loads(s[start:end + 1])
            except Exception:
                obj = None

    # Или `{"ingredients": [...]}`.
    if obj is None:
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                obj = _json.loads(s[start:end + 1])
            except Exception:
                obj = None

    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        return obj.get("ingredients") or obj.get("data") or []
    raise ValueError("Невалидный JSON")


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
        )
    except Exception:
        return 0

    if not DEEPSEEK_API_KEY:
        return 0

    import httpx

    prompt = _prompt(unknown)

    for model_name in _ENRICH_MODEL_FALLBACKS:
        try:
            from .instrumentation import METRICS
            METRICS.increment("ai_call_count")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    DEEPSEEK_API_URL,
                    headers={
                        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                        "max_tokens": _ENRICH_MAX_TOKENS,
                    },
                    timeout=60,
                )
            if response.status_code != 200:
                continue
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            records = _parse_enrichment_response(content)
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
                        "evidence_level": (claim.get("evidence")
                                          or claim.get("evidence_level")
                                          or record.get("evidence_level")
                                          or "moderate"),
                    })
                record["claims"] = claims

                if repo.save_enriched_ingredient(record):
                    saved += 1
            return saved
        except Exception:
            continue

    return 0


def persist_concern_evidence_claims(
    records: List[Dict[str, Any]],
    missing_pairs: List[Dict[str, Any]],
    repository: Optional[IngredientRepository] = None,
) -> int:
    """Validate and append returned concern claims to the existing claim store."""
    if not records or not missing_pairs:
        return 0

    repo = repository or IngredientRepository()
    repo.ensure_ingredient_tables()
    requested = {
        (
            normalize_ingredient_name(pair.get("ingredient", "")),
            str(pair.get("concern_id") or "").strip().lower(),
        ): {str(prop).strip().lower() for prop in pair.get("properties") or []}
        for pair in missing_pairs
    }
    saved = 0

    for record in records:
        if not isinstance(record, Mapping):
            continue
        ingredient_name = str(record.get("ingredient") or record.get("inci_name") or "").strip()
        ingredient = normalize_ingredient_name(ingredient_name)
        concern_id = str(record.get("concern_id") or record.get("concern") or "").strip().lower()
        allowed_properties = requested.get((ingredient, concern_id))
        if not allowed_properties:
            continue

        ingredient_id = repo.upsert_ingredient(ingredient_name, ingredient_name, ingredient)
        if not ingredient_id:
            continue
        for claim in record.get("claims") or []:
            if not isinstance(claim, Mapping):
                continue
            property_name = str(claim.get("property_name") or claim.get("property") or "").strip().lower()
            direction = str(claim.get("direction") or "").strip().lower()
            if property_name not in allowed_properties or direction not in {"positive", "negative", "neutral"}:
                continue
            evidence = str(claim.get("evidence") or "").strip()
            if not evidence:
                continue
            try:
                strength = float(claim.get("strength"))
                confidence = float(claim.get("confidence"))
            except (TypeError, ValueError):
                continue
            if not 0.0 <= strength <= 1.0 or not 0.0 < confidence <= 1.0:
                continue

            evidence_level = str(claim.get("evidence_level") or "low").strip().lower()
            if evidence_level not in {"low", "moderate", "high"}:
                evidence_level = "low"
            source_url = str(claim.get("source_url") or "").strip()
            if not source_url.startswith(("https://", "http://")):
                source_url = ""
            source_title = str(claim.get("source_title") or evidence).strip()[:500]
            if repo.add_claim_if_missing(
                ingredient_id,
                scoped_concern_property(concern_id, property_name),
                direction,
                strength,
                confidence,
                evidence_level=evidence_level,
                source_url=source_url,
                source_title=source_title,
                source_type="ai_concern_enrichment",
            ):
                saved += 1

    return saved
