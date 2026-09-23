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
                        "evidence_level": claim.get("evidence_level") or record.get("evidence_level") or "moderate",
                    })
                record["claims"] = claims

                if repo.save_enriched_ingredient(record):
                    saved += 1
            return saved
        except Exception:
            continue

    return 0

