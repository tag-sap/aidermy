# ai_summary.py
# AI #3 — Summary.
#
# Вызывается ТОЛЬКО ПОСЛЕ того, как scoring engine рассчитал итоговый процент.
# AI получает готовый результат (score, positive/negative factors, relevant
# ingredients) и пишет понятное объяснение. AI НЕ имеет права менять score.

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .decision_engine import DIMENSION_LABELS

# Нейтральные human-метки осей (без позитивной/негативной окраски), чтобы AI
# корректно объяснял negative-факторы (например, «раздражение», а не «снижение раздражения»).
_AXIS_NEUTRAL_LABELS: Dict[str, str] = {
    "hydration": "увлажнение",
    "barrier": "барьер кожи",
    "irritation": "раздражение",
    "sensitization": "сенсибилизация",
    "sebum": "себум/жирность",
    "pigmentation": "пигментация",
}


def _effect_label(property_name: str) -> str:
    return _AXIS_NEUTRAL_LABELS.get(str(property_name or ""), DIMENSION_LABELS.get(str(property_name or ""), str(property_name or "")))


def _factor_text(factor: Dict[str, Any]) -> str:
    ing = str(factor.get("ingredient") or "").strip()
    prop = _effect_label(factor.get("property"))
    direction = str(factor.get("direction") or "").lower()
    if ing and prop:
        return f"{ing} (эффект «{prop}», {'негативный' if direction == 'negative' else 'позитивный'})"
    if ing:
        return ing
    return prop


def breakdown_text(analysis: Dict[str, Any]) -> str:
    """Текстовое deterministic-разложение score по осям для AI-контекста."""
    dims = analysis.get("dimensions") or {}
    prio = analysis.get("priorities") or {}
    lines: List[str] = []
    for axis in ("hydration", "barrier", "irritation", "sensitization", "sebum", "pigmentation"):
        val = dims.get(axis)
        if val is None:
            continue
        w = prio.get(axis)
        lines.append(f"  - {axis}: value={round(float(val), 3)}, weight={round(float(w or 0), 4)}")
    return "\n".join(lines) if lines else "  (нет данных по осям)"


def _prompt(
    product_name: str,
    score: int,
    positive: List[Dict[str, Any]],
    negative: List[Dict[str, Any]],
    skin_type: str,
    concerns: List[str],
    product_type: str = "",
    breakdown: str = "",
    balance: str = "",
    inci: str = "",
) -> str:
    pos = "; ".join(_factor_text(f) for f in positive[:8]) or "—"
    neg = "; ".join(_factor_text(f) for f in negative[:8]) or "—"
    return (
        "Ты — косметолог. Объясни пользователю УЖЕ ГОТОВЫЙ результат подбора косметики "
        "обычным человеческим языком.\n\n"
        f"Продукт: {product_name}\n"
        f"Тип продукта (категория): {product_type or 'не указан'}\n"
        f"Тип кожи: {skin_type or 'не указан'}\n"
        f"Итоговая совместимость (рассчитана алгоритмом, НЕ меняй её): {score}%\n"
        f"Баланс вкладов (что дало плюс, что дало минус, и почему итог такой):\n{balance or '  (нет данных)'}\n"
        f"Разложение score по осям (значение и вес оси для профиля):\n{breakdown or '  (нет данных)'}\n"
        f"Положительные факторы (ингредиент → эффект): {pos}\n"
        f"Отрицательные факторы (ингредиент → эффект): {neg}\n"
        f"Полный состав (нормализованный INCI — единственный источник ингредиентов): {inci or '—'}\n\n"
        "Правила (строго):\n"
        "- Объясни БАЛАНС, а не просто перечисли хорошее и плохое отдельно: какие факторы дали "
        "положительный вклад, какие — отрицательный, и почему в итоге score оказался именно таким.\n"
        "- Сила объяснения должна соответствовать величине вклада: [значимо] — главная причина, [умеренно] — можно упомянуть, [слабо] — НЕ делай причиной результата.\n"
        "- Если отрицательный вклад очень мал (например −0.5 п.п.), не пиши «тянет итог вниз» — скажи, что существенных отрицательных факторов нет.\n"
        "- Соотнеси итог с нейтральной зоной ~50%: немного выше (например 56%) — положительный профиль без выраженной специфики под профиль; заметно ниже — отрицательные факторы существенны.\n"
        "- Итог — это БАЛАНС положительных и отрицательных вкладов. Ниже нейтральной зоны — значит положительный вклад умеренный и/или есть отрицательные факторы. Не пиши «процент хороших ингредиентов». "
        "\n"
        "- Упоминай ТОЛЬКО ингредиенты из состава и ТОЛЬКО эффекты из факторов выше.\n"
        "- НЕ приписывай ингредиентам свойства, которых нет в факторах (например, «стимулирует коллаген», "
        "«омолаживает», «отшелушивает» — если этого нет в факторах).\n"
        "- НЕ пиши категоричные медицинские утверждения («вызовет раздражение») — формулируй как "
        "«могут повышать вероятность раздражения/чувствительности».\n"
        "- НЕ пересчитывай процент и НЕ определяй вердикт сам.\n"
        "- НЕ выводи технические INCI-названия; перефразируй человеческим языком, опираясь на факторы.\n\n"
        "Напиши максимум 2-3 коротких предложения, которые объясняют ПРИЧИНУ результата через баланс.\n\n"
        f"ВАЖНО: процент зафиксирован и равен {score}%. Никогда не пиши другой процент.\n\n"
        "Верни ТОЛЬКО JSON. fragments — список предложений. Каждое предложение — ОТДЕЛЬНЫЙ fragment, "
        "с одним sentiment (positive ИЛИ negative). НЕ объединяй позитив и негатив в одном fragment: "
        "если в одном предложении есть и плюс, и минус — разбей его на два предложения.\n"
        '{\n'
        '  \"fragments\": [\n'
        '    {\"text\": \"...\", \"sentiment\": \"positive|negative\"},\n'
        '    {\"text\": \"...\", \"sentiment\": \"positive|negative\"}\n'
        '  ]\n'
        '}\n'
    )


async def summarize_with_ai(
    product_name: str,
    score: int,
    analysis: Dict[str, Any],
    profile: Dict[str, Any],
    product_type: str = "",
) -> Optional[List[Dict[str, str]]]:
    """AI #3 — пишет human-резюме в виде fragments [{text, sentiment}].

    Возвращает None при недоступности AI."""
    try:
        from .services import (
            DEEPSEEK_API_KEY,
            DEEPSEEK_API_URL,
            DEEPSEEK_MODEL_FALLBACKS,
            _score_balance_text,
            extract_json_from_response,
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
    breakdown = breakdown_text(analysis)
    balance = _score_balance_text(analysis)
    inci = ", ".join(str(i) for i in (analysis.get("normalized_ingredients") or []))

    prompt = _prompt(product_name, score, positive, negative, skin_type, concerns, product_type, breakdown, balance, inci)

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
                        "max_tokens": 400,
                    },
                    timeout=30,
                )
            if response.status_code != 200:
                continue
            data = response.json()
            content = (data["choices"][0]["message"]["content"] or "").strip()
            if not content:
                continue
            parsed = extract_json_from_response(content)
            fragments = _validated_fragments(parsed, score)
            if fragments:
                return fragments
            # фолбэк: если LLM вернул plain text — один fragment.
            if not isinstance(parsed, dict):
                sentiment = "negative" if int(score or 0) < 60 else "positive"
                return [{"text": content, "sentiment": sentiment}]
        except Exception as exc:
            print(f"[SUMMARY] AI {model_name} failed: {exc}")
            continue

    return None


def _validated_fragments(parsed, score) -> List[Dict[str, str]]:
    """Достаёт и валидирует fragments из ответа AI (только positive/negative)."""
    if not isinstance(parsed, dict):
        return []
    raw = parsed.get("fragments")
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, str]] = []
    for f in raw:
        if not isinstance(f, dict):
            continue
        text = str(f.get("text") or "").strip()
        sentiment = str(f.get("sentiment") or "").strip().lower()
        if not text:
            continue
        if sentiment not in {"positive", "negative"}:
            sentiment = "negative" if int(score or 0) < 60 else "positive"
        out.append({"text": text, "sentiment": sentiment})
    return out
