# vision_service.py
# Распознавание состава косметического продукта по фотографиям с помощью
# DeepSeek Vision (мультимодальный deepseek-flash), а также поиск продукта
# по распознанному INCI в существующей Product DB и регистрация ингредиентов
# в Ingredient DB.
#
# Это НЕ отдельная параллельная система: использует существующие абстракции
# (services.DEEPSEEK_*, ingredient_normalizer, database, ingredient_repository).

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import httpx

from .ingredient_normalizer import canonicalize_ingredient_name
from .ingredient_repository import IngredientRepository
from .database import get_connection, PRODUCTS_DB, AIDERMY_DB
from .services import DEEPSEEK_API_KEY, DEEPSEEK_API_URL, extract_json_from_response

# Модель с поддержкой изображений. deepseek-flash принимает картинки в формате,
# совместимом с OpenAI Chat Completions (image_url / base64 data URL).
DEEPSEEK_VISION_MODEL = os.getenv("DEEPSEEK_VISION_MODEL", "deepseek-flash")

# Порог, при котором матч по составу считается «уверенным предположением».
MATCH_CONFIDENT_THRESHOLD = 0.70


VISION_SYSTEM_PROMPT = (
    "Ты — система точного распознавания INCI-состава косметики по фотографиям этикеток. "
    "Ты читаешь текст с фотографий и возвращаешь ТОЛЬКО корректный JSON без пояснений и "
    "без markdown-разметки. Никогда не придумывай ингредиенты, которых нет на снимках."
)


def _vision_user_prompt(image_count: int) -> str:
    return f"""Тебе передано {image_count} фотографий, сделанных пользователем с одного косметического продукта.

ВАЖНО про серию фотографий:
- ВСЕ изображения относятся к ОДНОМУ и тому же продукту.
- Фотографии могут показывать РАЗНЫЕ участки одной этикетки (например, цилиндрический флакон, где состав не помещается в один кадр).
- Фотографии могут ЧАСТИЧНО ПЕРЕКРЫВАТЬСЯ между собой.
- Нужно собрать ПОЛНЫЙ состав из ВСЕХ изображений как единое целое.
- НЕЛЬЗЯ считать каждую фотографию отдельным составом.

Твои задачи:
1. Прочитай весь текст на всех фотографиях.
2. Определи, какой фрагмент текста является списком ингредиентов INCI (обычно начинается со слова "Ingredients", "Состав", "INCI", "Aqua/Water" или сразу с ингредиентов).
3. Объедини фрагменты INCI со всех фотографий в ОДИН список.
4. Определи правильную последовательность ингредиентов (по убыванию концентрации, как в INCI).
5. Устрани дублирующиеся фрагменты между фотографиями (если один и тот же участок попал на два кадра — оставь его один раз).
6. Исправь очевидные ошибки распознавания (например, перепутанные похожие символы в названиях ингредиентов).
7. Нормализуй названия ингредиентов в стандартный INCI-вид (например, "Aqua", "Glycerin", "Tocopherol").
8. Определи границы списка ингредиентов (не включай маркетинговые надписи, описание, состав упаковки).
9. НЕ придумывай ингредиенты, которых нет на фотографиях. Если часть состава невозможно прочитать, отметь её как сомнительную, а не выдумывай.

Верни СТРОГО один JSON-объект в следующем виде:

{{
  "is_inci": true,
  "raw_text": "полный собранный INCI одной строкой через запятую",
  "ingredients": [
    {{"raw": "как на фото", "normalized": "Aqua", "confidence": 0.99}},
    {{"raw": "как на фото", "normalized": "Glycerin", "confidence": 0.98}}
  ],
  "uncertain_items": [
    {{"text": "плохо читаемый фрагмент", "reason": "размыто / обрезано / закрыто"}}
  ],
  "overall_confidence": 0.0
}}

Правила для полей:
- "is_inci" — true, если на фото удалось найти состав/список ингредиентов, иначе false.
- "ingredients" — упорядоченный список распознанных ингредиентов. Каждый элемент: "raw" (текст как на фото), "normalized" (нормализованное INCI-название), "confidence" (0.0–1.0).
- "uncertain_items" — сомнительные или плохо читаемые участки состава, которые не удалось уверенно распознать (список, может быть пустым).
- "overall_confidence" — общая уверенность в распознанном составе (0.0–1.0).
- Не добавляй никаких других полей и никакого текста вне JSON.
"""


def _coerce_recognition(raw: Any) -> Dict[str, Any]:
    """Приводит ответ модели к стабильной структуре для дальнейшей обработки."""
    if not isinstance(raw, dict):
        raw = {}

    ingredients: List[Dict[str, Any]] = []
    for item in raw.get("ingredients") or []:
        if isinstance(item, str):
            item = {"raw": item, "normalized": item, "confidence": None}
        if not isinstance(item, dict):
            continue
        raw_name = str(item.get("raw") or item.get("normalized") or "").strip()
        normalized = str(item.get("normalized") or raw_name).strip()
        if not normalized and not raw_name:
            continue
        try:
            confidence = float(item.get("confidence"))
        except (TypeError, ValueError):
            confidence = None
        ingredients.append({
            "raw": raw_name or normalized,
            "normalized": normalized or raw_name,
            "confidence": confidence,
        })

    uncertain: List[Dict[str, Any]] = []
    for item in raw.get("uncertain_items") or []:
        if isinstance(item, str):
            uncertain.append({"text": item, "reason": ""})
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("raw") or "").strip()
            if text:
                uncertain.append({"text": text, "reason": str(item.get("reason") or "")})

    try:
        overall = float(raw.get("overall_confidence"))
    except (TypeError, ValueError):
        overall = None
    if overall is None and ingredients:
        known = [i["confidence"] for i in ingredients if i["confidence"] is not None]
        overall = (sum(known) / len(known)) if known else 0.0

    return {
        "is_inci": bool(raw.get("is_inci", True)),
        "raw_text": str(raw.get("raw_text") or "").strip(),
        "ingredients": ingredients,
        "uncertain_items": uncertain,
        "overall_confidence": overall,
    }


async def recognize_composition(images: List[str]) -> Dict[str, Any]:
    """Отправляет все фото одной серии в DeepSeek Vision одним запросом.

    images — список base64 data URL (data:image/...;base64,...).
    """
    if not images:
        raise ValueError("Не передано ни одной фотографии")

    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY не настроен на сервере")

    # Все фото передаём как единый контекст в одном user-сообщении.
    content_blocks: List[Dict[str, Any]] = [
        {"type": "text", "text": _vision_user_prompt(len(images))}
    ]
    for img in images:
        content_blocks.append({
            "type": "image_url",
            "image_url": {"url": img},
        })

    models: List[str] = []
    for m in [DEEPSEEK_VISION_MODEL, "deepseek-flash"]:
        if m and m not in models:
            models.append(m)

    last_error: Optional[str] = None
    for model_name in models:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=20.0)) as client:
                response = await client.post(
                    DEEPSEEK_API_URL,
                    headers={
                        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": VISION_SYSTEM_PROMPT},
                            {"role": "user", "content": content_blocks},
                        ],
                        "stream": False,
                    },
                )
            if response.status_code != 200:
                last_error = f"DeepSeek {model_name} status {response.status_code}: {response.text[:300]}"
                continue

            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                last_error = "DeepSeek вернул пустой choices"
                continue
            content = (choices[0].get("message") or {}).get("content") or ""
            if not content:
                last_error = "DeepSeek вернул пустой content"
                continue

            parsed = extract_json_from_response(content)
            return _coerce_recognition(parsed)
        except Exception as exc:  # noqa: BLE001
            last_error = f"DeepSeek {model_name} failed: {exc}"
            continue

    raise RuntimeError(last_error or "Не удалось распознать состав")


def recognized_normalized_list(recognition: Dict[str, Any]) -> List[str]:
    """Извлекает нормализованный список INCI в правильном порядке без дублей."""
    result: List[str] = []
    seen: set = set()
    for item in recognition.get("ingredients") or []:
        name = str(item.get("normalized") or item.get("raw") or "").strip()
        canonical = canonicalize_ingredient_name(name)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        result.append(canonical)
    return result


def _tokenize_inci(raw: str) -> set:
    tokens: set = set()
    for part in re.split(r"[,;\n]+", raw or ""):
        normalized = canonicalize_ingredient_name(part)
        if normalized:
            tokens.add(normalized)
    return tokens


def _split_product_name(raw_name: str) -> tuple:
    parts = [x.strip() for x in (raw_name or "").split("\n") if x.strip()]
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    return "", (parts[0] if parts else (raw_name or "").strip())


def find_product_matches(ingredients: List[str], limit: int = 5) -> List[Dict[str, Any]]:
    """Ищет в Product DB продукты, чей состав совпадает с распознанным INCI."""
    recognized = {canonicalize_ingredient_name(i) for i in ingredients}
    recognized.discard("")
    if not recognized:
        return []

    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, slug, brand, image_url, category, ingredients FROM products "
        "WHERE is_canonical = 1 AND ingredients IS NOT NULL AND TRIM(ingredients) != ''"
    )
    rows = cursor.fetchall()
    conn.close()

    scored: List[Dict[str, Any]] = []
    for row in rows:
        product_tokens = _tokenize_inci(row["ingredients"])
        if not product_tokens:
            continue
        intersection = recognized & product_tokens
        matched_count = len(intersection)
        if matched_count == 0:
            continue
        # «Совпадение состава» = доля распознанного состава, покрытая продуктом.
        coverage = matched_count / len(recognized)
        # Джакард учитывает и лишние ингредиенты продукта, чтобы не завышать
        # совпадение для продуктов с очень длинным составом.
        union = recognized | product_tokens
        jaccard = matched_count / len(union) if union else 0.0
        match_percent = round(100 * ((2 * coverage * jaccard) / (coverage + jaccard)) if (coverage + jaccard) else 0.0, 1)

        brand, title = _split_product_name(row["name"])
        scored.append({
            "slug": row["slug"] or "",
            "name": title or (row["name"] or ""),
            "brand": (row["brand"] or brand).strip(),
            "image_url": row["image_url"] or "",
            "category": row["category"] or "",
            "match_percent": match_percent,
            "matched_count": matched_count,
            "total_recognized": len(recognized),
        })

    scored.sort(key=lambda r: (-r["match_percent"], -r["matched_count"], r["name"]))
    return scored[:limit]


def register_ingredients(ingredients: List[Dict[str, Any]], db_path: str = AIDERMY_DB) -> List[Dict[str, Any]]:
    """Регистрирует распознанные ингредиенты в Ingredient DB без дублей.

    Для каждого ингредиента: нормализует название, ищет существующий по
    normalized_name; если найден — использует его ID, иначе создаёт.
    """
    repository = IngredientRepository(db_path=db_path)
    repository.ensure_ingredient_tables()

    conn = get_connection(db_path)
    registered: List[Dict[str, Any]] = []
    seen: set = set()

    for item in ingredients:
        raw = str(item.get("raw") or item.get("normalized") or "").strip()
        if not raw:
            continue
        canonical = canonicalize_ingredient_name(item.get("normalized") or raw)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)

        row = conn.execute(
            "SELECT id FROM ingredients_catalog WHERE normalized_name = ? LIMIT 1",
            (canonical,),
        ).fetchone()
        if row:
            ingredient_id = int(row["id"])
        else:
            cur = conn.execute(
                "INSERT INTO ingredients_catalog (inci_name, canonical_name, normalized_name, synonyms) "
                "VALUES (?, ?, ?, '')",
                (raw, canonical, canonical),
            )
            ingredient_id = int(cur.lastrowid)

        registered.append({
            "raw": raw,
            "normalized": canonical,
            "id": ingredient_id,
            "confidence": item.get("confidence"),
        })

    conn.commit()
    conn.close()
    return registered


