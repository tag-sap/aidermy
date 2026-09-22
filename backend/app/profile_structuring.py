# profile_structuring.py
# AI #1 — Profile Structuring.
#
# Преобразует «сырую» анкету пользователя (skin_type, concerns, allergies,
# custom_text, quiz_answers) в Structured User Profile, который дальше использует
# детерминированный scoring engine.
#
# Критично: AI НЕ превращает субъективное предпочтение в медицинский диагноз.
# Поля restrictions / intolerances / allergies формируются ТОЛЬКО из явных данных
# пользователя (детерминированно). AI может лишь уточнять skin_goals,
# personal_weights и preferences — без права менять медицинскую классификацию.

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Измерения scoring engine (совпадают с decision_engine.DIMENSIONS).
DIMENSIONS: Tuple[str, ...] = (
    "hydration",
    "barrier_support",
    "sensitivity",
    "acne_control",
    "brightening",
)

# Человекочитаемые concern'ы -> измерения (цели ухода).
_CONCERN_TO_GOALS: Dict[str, List[str]] = {
    "акне": ["acne_control"],
    "пигментаци": ["brightening"],
    "морщин": ["barrier_support", "brightening"],
    "покраснен": ["sensitivity", "barrier_support"],
    "пор": ["acne_control"],
    "тускл": ["brightening"],
    "обезвожен": ["hydration"],
    "купероз": ["sensitivity", "barrier_support"],
    "чувствительн": ["sensitivity", "barrier_support"],
    "сух": ["hydration", "barrier_support"],
    "жирн": ["acne_control", "sensitivity"],
}

# Ключевые слова для классификации custom_text. Порядок важен: сначала
# «жёсткие» сигналы (аллергия/непереносимость/исключение), затем предпочтения.
_RESTRICTION_HINTS = ("исключит", "нельзя", "противопоказан", "не использ", "запрещ")
_INTOLERANCE_HINTS = ("неперенос", "не переношу", "раздража", "не подходит мне", "плохо реагиру")
_ALLERGY_HINTS = ("аллерг", "allerg")
_PREFERENCE_HINTS = ("предпочита", "нравится", "люблю", "хочу", "текстур", "гель", "без", "не содержит")


def _normalize_list(value: Any) -> List[str]:
    """Приводит список/строку к списку чистых непустых строк (без дублей)."""
    if value is None:
        return []
    if isinstance(value, list):
        items = [str(x).strip() for x in value]
    elif isinstance(value, str):
        items = [x.strip() for x in re.split(r"[,;\n]+", value)]
    else:
        items = [str(value).strip()]
    result: List[str] = []
    seen = set()
    for item in items:
        if not item or item.lower() in seen:
            continue
        seen.add(item.lower())
        result.append(item)
    return result


def _skin_type_from_profile(profile: Dict[str, Any]) -> str:
    return str(
        (profile or {}).get("skin_type")
        or (profile or {}).get("skin_type_determined")
        or ""
    ).strip()


def _infer_sensitivity(profile: Dict[str, Any]) -> str:
    """low | medium | high — детерминированная оценка чувствительности."""
    text = " ".join(
        [
            _skin_type_from_profile(profile),
            " ".join(_normalize_list((profile or {}).get("concerns"))),
        ]
    ).lower()
    if "чувствительн" in text or "купероз" in text or "покраснен" in text:
        return "high"
    if "жирн" in text or "комбинирован" in text:
        return "medium"
    return "low"


def _skin_goals_from_concerns(profile: Dict[str, Any]) -> List[str]:
    """Цели ухода (измерения) из concern'ов и типа кожи."""
    goals: List[str] = []
    text = " ".join(
        [
            _skin_type_from_profile(profile),
            " ".join(_normalize_list((profile or {}).get("concerns"))),
        ]
    ).lower()
    for key, dims in _CONCERN_TO_GOALS.items():
        if key in text:
            for d in dims:
                if d not in goals:
                    goals.append(d)
    if not goals:
        goals = ["hydration", "barrier_support"]
    return goals


def _classify_restrictions(profile: Dict[str, Any]) -> Dict[str, List[str]]:
    """Разделяет явные ограничения пользователя на три непересекающихся класса.

    Возвращает:
      restrictions  — жёсткие исключения (hard exclusions);
      intolerances  — непереносимости (мягкий негативный вклад);
      allergies     — заявленные аллергии (hard flag/exclusion);
      preferences   — обычные предпочтения (не влияют на скор).

    Фронтенд отправляет поле `allergies` (набор категорий «Отдушки», «Спирт» и
    т.п.) — это явные запреты пользователя, поэтому трактуем их как restrictions.
    custom_text парсится по ключевым словам и НЕ «апгрейдится» до диагноза.
    """
    restrictions = _normalize_list((profile or {}).get("allergies"))
    intolerances: List[str] = []
    allergies: List[str] = []
    preferences: List[str] = []

    custom = str((profile or {}).get("custom_text") or "")
    if custom:
        phrases = [p.strip() for p in re.split(r"[.;\n!?]+", custom) if p.strip()]
        for phrase in phrases:
            lower = phrase.lower()
            if any(h in lower for h in _ALLERGY_HINTS):
                obj = re.sub(r".*?(аллерг[а-я]*|allerg[a-z]*)\s*(на|к)?\s*", "", phrase, flags=re.I).strip(" :,-")
                if obj:
                    allergies.append(obj)
            elif any(h in lower for h in _RESTRICTION_HINTS):
                obj = re.sub(r".*?(исключит|нельзя|противопоказан|не использ|запрещ)[а-я]*\s*", "", phrase, flags=re.I).strip(" :,-")
                if obj and obj not in restrictions:
                    restrictions.append(obj)
            elif any(h in lower for h in _INTOLERANCE_HINTS):
                obj = re.sub(r".*?(неперенос|не переношу|раздража|плохо реагиру)[а-я]*\s*", "", phrase, flags=re.I).strip(" :,-")
                if obj:
                    intolerances.append(obj)
            elif any(h in lower for h in _PREFERENCE_HINTS):
                preferences.append(phrase)

    return {
        "restrictions": restrictions,
        "intolerances": _normalize_list(intolerances),
        "allergies": _normalize_list(allergies),
        "preferences": _normalize_list(preferences),
    }


def _personal_weights(profile: Dict[str, Any]) -> Dict[str, float]:
    """Веса измерений, согласованные с decision_engine.priorities_for_profile."""
    try:
        from .decision_engine import priorities_for_profile
    except Exception:
        return {
            "hydration": 0.35,
            "barrier_support": 0.25,
            "sensitivity": 0.2,
            "acne_control": 0.1,
            "brightening": 0.1,
        }
    return priorities_for_profile(
        {
            "skin_type": _skin_type_from_profile(profile),
            "concerns": _normalize_list((profile or {}).get("concerns")),
        },
        _skin_type_from_profile(profile),
    )


def structure_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Детерминированное структурирование анкеты в Structured User Profile.

    Не использует AI. Является надёжным фолбэком и «полом» для AI-структурирования.
    """
    profile = profile or {}
    classification = _classify_restrictions(profile)
    goals = _skin_goals_from_concerns(profile)

    structured: Dict[str, Any] = {
        "skin_type": _skin_type_from_profile(profile),
        "sensitivity": _infer_sensitivity(profile),
        "skin_goals": goals,
        "personal_weights": _personal_weights(profile),
        "restrictions": classification["restrictions"],
        "intolerances": classification["intolerances"],
        "allergies": classification["allergies"],
        "preferences": classification["preferences"],
        "structured_at": datetime.now(timezone.utc).isoformat(),
        "source": "deterministic",
    }
    return structured


def _ai_prompt(profile: Dict[str, Any]) -> str:
    return (
        "Ты — косметолог-технолог. Структурируй анкету пользователя для алгоритма подбора косметики.\n\n"
        f"Анкета:\n- Тип кожи: {_skin_type_from_profile(profile) or 'не указан'}\n"
        f"- Проблемы: {', '.join(_normalize_list(profile.get('concerns'))) or 'не указаны'}\n"
        f"- Отказ от категорий: {', '.join(_normalize_list(profile.get('allergies'))) or 'не указаны'}\n"
        f"- Комментарий: {profile.get('custom_text') or ''}\n\n"
        "Заполни ТОЛЬКО не-медицинские поля структурированного профиля:\n"
        '{"skin_goals": ["hydration", "barrier_support", ...], '
        '"preferences": ["текст предпочтения", ...], '
        '"sensitivity": "low" | "medium" | "high"}\n\n'
        "skin_goals — только из списка: hydration, barrier_support, sensitivity, acne_control, brightening.\n"
        "preferences — обычные пожелания (текстура, формат), НЕ диагнозы.\n\n"
        "ВАЖНО: не создавай поля allergies/restrictions/intolerances. Не превращай "
        "предпочтение в аллергию или непереносимость. Верни ТОЛЬКО JSON."
    )


async def structure_profile_with_ai(profile: Dict[str, Any]) -> Dict[str, Any]:
    """AI #1 — Profile Structuring. Возвращает структурированный профиль.

    Детерминированное ядро всегда является основой. AI уточняет только
    skin_goals / preferences / sensitivity. При отсутствии ключа или ошибке
    возвращается детерминированный результат.
    """
    base = structure_profile(profile)

    try:
        from .services import (
            DEEPSEEK_API_KEY,
            DEEPSEEK_API_URL,
            DEEPSEEK_MODEL_FALLBACKS,
            extract_json_from_response,
        )
    except Exception:
        return base

    if not DEEPSEEK_API_KEY:
        return base

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
                        "messages": [{"role": "user", "content": _ai_prompt(profile)}],
                        "temperature": 0.2,
                        "max_tokens": 900,
                    },
                    timeout=30,
                )
            if response.status_code != 200:
                continue
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            result = extract_json_from_response(content)
            if not isinstance(result, dict):
                continue
            for key in ("skin_goals", "preferences"):
                value = result.get(key)
                if isinstance(value, list):
                    base[key] = _normalize_list(value)
            sensitivity = str(result.get("sensitivity") or "").strip().lower()
            if sensitivity in {"low", "medium", "high"}:
                base["sensitivity"] = sensitivity
            base["source"] = "ai"
            return base
        except Exception as exc:
            print(f"[PROFILE] AI structuring {model_name} failed: {exc}")
            continue

    return base


def serialize_structured(structured: Dict[str, Any]) -> str:
    return json.dumps(structured, ensure_ascii=False)


def deserialize_structured(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except Exception:
        return None
