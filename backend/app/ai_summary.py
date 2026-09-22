# ai_summary.py
# AI #3 — Summary.
#
# Вызывается ТОЛЬКО ПОСЛЕ того, как scoring engine рассчитал итоговый процент.
# AI получает готовый результат (score, positive/negative factors, relevant
# ingredients) и пишет понятное объяснение. AI НЕ имеет права менять score.

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .decision_engine import DIMENSION_LABELS


def _effect_label(property_name: str) -> str:
    return DIMENSION_LABELS.get(str(property_name or ""), str(property_name or ""))


def _factor_text(factor: Dict[str, Any]) -> str:
    ing = str(factor.get("ingredient") or "").strip()
    prop = _effect_label(factor.get("property"))
    return f"{ing} ({prop})" if ing else prop


def _prompt(
    product_name: str,
    score: int,
    positive: List[Dict[str, Any]],
    negative: List[Dict[str, Any]],
    skin_type: str,
    concerns: List[str],
) -> str:
    pos = "; ".join(_factor_text(f) for f in positive[:6]) or "—"
    neg = "; ".join(_factor_text(f) for f in negative[:6]) or "—"
    return (
        "Ты — косметолог. Дай КРАТКОЕ объяснение результата подбора косметики.\n\n"
        f"Продукт: {product_name}\n"
        f"Тип кожи: {skin_type or 'не указан'}\n"
        f"Итоговая совместимость (рассчитана алгоритмом, не меняй её): {score}%\n"
        f"Положительные факторы: {pos}\n"
        f"Отрицательные факторы: {neg}\n\n"
        "Напиши максимум 2-3 коротких предложения (до 280 символов). Только ключевые "
        "причины результата: что дало основной положительный вклад и на что обратить "
        "внимание. Без списков, без пересказа INCI, без маркдауна.\n"
        f"ВАЖНО: процент не пересчитывай, он зафиксирован и равен {score}%. Верни только текст."
    )


async def summarize_with_ai(
    product_name: str,
    score: int,
    analysis: Dict[str, Any],
    profile: Dict[str, Any],
) -> Optional[str]:
    """AI #3 — пишет человекочитаемое резюме. Возвращает None при недоступности AI."""
    try:
        from .services import (
            DEEPSEEK_API_KEY,
            DEEPSEEK_API_URL,
            DEEPSEEK_MODEL_FALLBACKS,
        )
    except Exception:
        return None

    if not DEEPSEEK_API_KEY:
        return None

    import httpx

    positive = analysis.get("positive_factors") or []
    negative = analysis.get("negative_factors") or []
    skin_type = str((profile or {}).get("skin_type") or (profile or {}).get("skin_type_determined") or "")
    concerns = (profile or {}).get("concerns") or []

    prompt = _prompt(product_name, score, positive, negative, skin_type, concerns)

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
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.4,
                        "max_tokens": 260,
                    },
                    timeout=30,
                )
            if response.status_code != 200:
                continue
            data = response.json()
            content = (data["choices"][0]["message"]["content"] or "").strip()
            if content:
                return content
        except Exception as exc:
            print(f"[SUMMARY] AI {model_name} failed: {exc}")
            continue

    return None
