"""Structured, source-labelled explanation of an already calculated Match.

This module does not score anything. It turns the persisted deterministic trace
into the detailed part of the report, using ingredient knowledge from the
existing Ingredient DB and the same factor list that produced the score.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from .database import AIDERMY_DB, get_connection
from .ingredient_normalizer import normalize_ingredient_name
from .category_knowledge import get_category_knowledge

REPORT_DETAILS_VERSION = "1.0.1"

_FUNCTION_LABELS = {
    "humectant": "увлажнитель",
    "soothing": "успокаивающее действие",
    "skin conditioning": "уход за кожей",
    "skin_conditioning": "уход за кожей",
    "barrier repair": "восстановление барьера",
    "barrier_repair": "восстановление барьера",
    "preservative": "консервант",
    "antimicrobial": "антимикробное действие",
    "solvent": "растворитель",
    "uv filter": "UV-фильтр",
    "colorant": "краситель",
    "opacifying agent": "создание непрозрачности",
    "antioxidant": "антиоксидант",
    "emollient": "эмолент",
    "surfactant": "поверхностно-активное вещество",
    "fragrance": "ароматизатор",
    "anti-aging": "антивозрастное действие",
    "collagen stimulator": "стимулятор коллагена",
    "prebiotic": "пребиотик",
    "hydration": "увлажнение",
}

_AXIS_LABELS = {
    "hydration": "увлажнение",
    "barrier": "поддержка барьера",
    "irritation": "раздражение",
    "sensitization": "риск нежелательной реакции",
    "sebum": "жирность/себум",
    "pigmentation": "пигментация",
}


def _as_text(value: Any) -> str:
    """Render catalogue JSON values as a compact human-readable string.

    Ingredient knowledge is stored both as plain text and as JSON arrays
    (for example ``'["humectant", "soothing"]'``).  Passing such a value
    through ``str()`` made the report show raw JSON, and an empty list showed
    ``[]``.  Parse JSON-shaped values, join arrays, and keep unknown values
    untouched instead of inventing a description.
    """
    if isinstance(value, str):
        text = value.strip()
        if not text or text in {"[]", "{}", "null", "None"}:
            return ""
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            return _FUNCTION_LABELS.get(text.lower(), text)
        return _as_text(parsed)
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return "; ".join(part for part in (_as_text(item) for item in value) if part)
    if isinstance(value, dict):
        title = value.get("title") or value.get("name") or value.get("label")
        url = value.get("url") or value.get("link")
        if title:
            title_text = str(title).strip()
            url_text = str(url).strip() if url else ""
            return f"{title_text} ({url_text})" if url_text and url_text not in title_text else title_text
        return "; ".join(part for part in (_as_text(item) for item in value.values()) if part)
    text = str(value).strip()
    return _FUNCTION_LABELS.get(text.lower(), text) if text else ""


def _ingredient_meta(names: List[str]) -> Dict[str, Dict[str, Any]]:
    keys = [normalize_ingredient_name(name) for name in names if normalize_ingredient_name(name)]
    if not keys:
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    try:
        conn = get_connection(AIDERMY_DB)
        cur = conn.cursor()
        placeholders = ",".join("?" for _ in keys)
        rows = cur.execute(
            f"SELECT normalized_name, inci_name, functions, skin_effects, evidence_level, sources "
            f"FROM ingredients_catalog WHERE normalized_name IN ({placeholders})",
            keys,
        ).fetchall()
        for row in rows:
            item = dict(row)
            result[item.get("normalized_name") or ""] = item
        conn.close()
    except Exception:
        pass
    return result


def _quality(analysis: Dict[str, Any], total: int, unknown: int) -> Dict[str, Any]:
    confidence = float(analysis.get("confidence") or 0.0)
    coverage = max(0.0, 1.0 - (unknown / total)) if total else 0.0
    if coverage >= 0.8 and confidence >= 0.7:
        label = "высокая"
    elif coverage >= 0.5 and confidence >= 0.45:
        label = "средняя"
    else:
        label = "ограниченная"
    return {
        "known_ingredients": max(0, total - unknown),
        "unknown_ingredients": unknown,
        "total_ingredients": total,
        "coverage": round(coverage, 3),
        "confidence": round(confidence, 3),
        "label": label,
    }


def _top_factors(analysis: Dict[str, Any], limit: int = 6) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for direction in ("positive", "negative"):
        for factor in analysis.get(f"{direction}_factors") or []:
            if not isinstance(factor, dict):
                continue
            name = str(factor.get("ingredient") or "").strip()
            if not name:
                continue
            rows.append({
                "ingredient": name,
                "axis": factor.get("property") or "",
                "direction": direction,
                "strength": factor.get("strength"),
                "confidence": factor.get("confidence"),
                "position_weight": factor.get("position_weight"),
                "interaction_id": factor.get("interaction_id"),
            })
    rows.sort(key=lambda item: abs(float(item.get("strength") or 0)), reverse=True)
    return rows[:limit]


def _interaction_rows(analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for item in analysis.get("interaction_breakdown") or []:
        if not isinstance(item, dict):
            continue
        rows.append({
            "ingredient_a": item.get("ingredient_a"),
            "ingredient_b": item.get("ingredient_b"),
            "axis": item.get("axis"),
            "direction": item.get("direction"),
            "weighted_contribution": item.get("weighted_contribution"),
            "confidence": item.get("confidence"),
            "source_type": item.get("source_type"),
            "evidence": item.get("evidence"),
        })
    return rows


def _profile_rows(profile: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    structured = profile.get("structured") if isinstance(profile.get("structured"), dict) else {}
    effects = analysis.get("profile_effects") or {}
    return {
        "skin_type": structured.get("skin_type") or profile.get("skin_type") or "",
        "concerns": structured.get("concerns") or profile.get("concerns") or [],
        "sensitivity": structured.get("sensitivity") or effects.get("sensitivity") or "",
        "therapy": structured.get("therapy") or effects.get("active_therapy") or [],
        "procedures": structured.get("procedures") or effects.get("active_procedures") or [],
        "age": profile.get("age") or "",
    }


def build_report_details(
    product_name: str,
    product_type: str,
    analysis: Dict[str, Any],
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a detailed report from the saved deterministic trace.

    The result deliberately labels facts, general ingredient knowledge, algorithm
    conclusions and limitations separately. It never introduces an ingredient
    that is absent from the normalized INCI.
    """
    analysis = analysis or {}
    profile = profile or {}
    inci = [str(i) for i in (analysis.get("normalized_ingredients") or []) if str(i).strip()]
    unknown_rows = analysis.get("unknown_factors") or []
    unknown_names = {
        normalize_ingredient_name(str(row.get("ingredient") or ""))
        for row in unknown_rows if isinstance(row, dict)
    }
    unknown_count = len([x for x in inci if normalize_ingredient_name(x) in unknown_names])
    quality = _quality(analysis, len(inci), unknown_count)
    meta = _ingredient_meta(inci)
    factors = _top_factors(analysis)
    key_names: List[str] = []
    for factor in factors:
        name = factor["ingredient"]
        if name not in key_names:
            key_names.append(name)
    key_names = key_names[:5]

    def ingredient_item(name: str, is_key: bool = False) -> Dict[str, Any]:
        key = normalize_ingredient_name(name)
        info = meta.get(key, {})
        related = [f for f in factors if normalize_ingredient_name(f["ingredient"]) == key]
        direction = "negative" if any(f["direction"] == "negative" for f in related) else ("positive" if related else "neutral")
        function = _as_text(info.get("functions"))
        effects = _as_text(info.get("skin_effects"))
        if not function and not effects:
            function = "Функция в базе знаний не описана."
        role = "Входит в нормализованный INCI продукта."
        if related:
            axes = ", ".join(sorted({_AXIS_LABELS.get(f["axis"], f["axis"]) for f in related if f.get("axis")}))
            role = (
                "В алгоритмической оценке отмечен как фактор "
                + ("в пользу" if direction == "positive" else "требующий внимания")
                + (f" по оси: {axes}." if axes else ".")
            )
        return {
            "name": name,
            "inci_name": info.get("inci_name") or name,
            "function": function,
            "skin_effects": effects,
            "role": role,
            "evidence_level": info.get("evidence_level") or ("algorithm_only" if related else "unknown"),
            "sources": _as_text(info.get("sources")),
            "direction": direction,
            "unknown": not bool(info),
            "is_key": is_key,
        }

    key_items = [ingredient_item(name, True) for name in key_names]
    other_items = [ingredient_item(name) for name in inci if name not in key_names]
    factors_for_axes = factors
    positive_axes = sorted({
        _AXIS_LABELS.get(str(f.get("axis") or ""), str(f.get("axis") or ""))
        for f in factors_for_axes if f.get("direction") == "positive" and f.get("axis")
    })
    negative_axes = sorted({
        _AXIS_LABELS.get(str(f.get("axis") or ""), str(f.get("axis") or ""))
        for f in factors_for_axes if f.get("direction") == "negative" and f.get("axis")
    })
    interactions = _interaction_rows(analysis)
    phase1 = analysis.get("phase1") or {}
    hard_flags = analysis.get("hard_flags") or []
    profile_info = _profile_rows(profile, analysis)
    category_knowledge = get_category_knowledge(product_type)
    category_purpose = str(category_knowledge.get("intended_purpose") or "").strip()
    category_functions = [str(item) for item in (category_knowledge.get("typical_functions") or []) if str(item).strip()]
    category_limitations = [str(item) for item in (category_knowledge.get("limitations") or []) if str(item).strip()]


    limitations: List[str] = []
    if quality["unknown_ingredients"]:
        unknown_labels = ", ".join(
            str(row.get("ingredient") or "") for row in unknown_rows if isinstance(row, dict) and row.get("ingredient")
        )
        limitations.append(
            f"Нет подтверждённых данных для: {unknown_labels or 'части состава'}. "
            f"Они не считались известными; покрытие базы знаний — {round(quality['coverage'] * 100)}%."
        )
    if quality["label"] == "ограниченная":
        limitations.append("Состав или база знаний покрывают продукт неполно, поэтому оценка менее уверенная.")
    if category_limitations:
        limitations.append("Для этой категории нельзя автоматически заключать: " + "; ".join(category_limitations) + ".")
    if phase1.get("status") == "insufficient_data":
        limitations.append("Недостаточно данных для обычной оценки совместимости.")
    if hard_flags:
        flagged = ", ".join(
            str(item.get("ingredient") or "") for item in hard_flags if isinstance(item, dict) and item.get("ingredient")
        )
        if flagged:
            limitations.append(f"Алгоритм отметил жёсткое ограничение по ингредиентам: {flagged}.")
    if not interactions:
        limitations.append("Подтверждённых взаимодействий ингредиентов для этого состава в базе знаний нет; это не доказывает их отсутствие.")
    if not limitations:
        limitations.append("Оценка основана на доступном INCI и профиле; она не предсказывает индивидуальную реакцию кожи.")

    sections = [
        {
            "id": "product",
            "title": "Что это за продукт",
            "basis": "факт из карточки/категории",
            "paragraphs": [
                f"Тип продукта: {product_type or 'не определён'}.",
                f"Назначение по категории: {category_purpose or 'не установлено по доверенным данным'}.",
                (
                    "Типичные функции категории: " + "; ".join(category_functions) + "."
                    if category_functions else "Типичные функции категории не установлены."
                ),
                f"В составе {quality['total_ingredients']} ингредиентов; подтверждённые данные есть для {quality['known_ingredients']}.",
                "Назначение ниже описывается по категории и составу, а не по рекламным обещаниям.",
            ],
        },
        {
            "id": "why",
            "title": "Почему получен именно такой результат",
            "basis": "алгоритм Score Engine",
            "paragraphs": [
                f"Итоговая оценка: {analysis.get('score') if analysis.get('score') is not None else 'не рассчитана'}.",
                ("Факторы в пользу: " + ", ".join(positive_axes) + ".") if positive_axes else "Подтверждённых факторов в пользу в алгоритме нет.",
                ("Факторы, требующие внимания: " + ", ".join(negative_axes) + ".") if negative_axes else "Подтверждённых отрицательных факторов в алгоритме нет.",
            ],
        },
        {
            "id": "profile",
            "title": "Как продукт соотносится с профилем",
            "basis": "профиль + алгоритм",
            "paragraphs": [
                f"Тип кожи: {profile_info.get('skin_type') or 'не указан'}.",
                f"Учтённые особенности: {', '.join(profile_info.get('concerns') or []) or 'не указаны'}.",
                f"Активная терапия/процедуры: {len(profile_info.get('therapy') or []) + len(profile_info.get('procedures') or [])}.",
                "Это алгоритмическая персонализация, а не медицинская рекомендация.",
            ],
        },
        {
            "id": "limitations",
            "title": "Ограничения и предостережения",
            "basis": "факт + ограничения данных",
            "paragraphs": limitations,
        },
        {
            "id": "interpretation",
            "title": "Как понимать результат",
            "basis": "методика оценки",
            "paragraphs": [
                "Процент — это мера соответствия состава вашему профилю по правилам Score Engine, а не вероятность клинического эффекта.",
                f"Качество данных: {quality['label']} (покрытие {round(quality['coverage'] * 100)}%, уверенность {round(quality['confidence'] * 100)}%).",
                "Если состав неполный, оценка остаётся ориентиром и требует проверки INCI.",
            ],
        },
    ]

    if interactions:
        sections.append({
            "id": "interactions",
            "title": "Подтверждённые взаимодействия",
            "basis": "правила взаимодействий",
            "paragraphs": [
                f"{row.get('ingredient_a')} + {row.get('ingredient_b')}: {_AXIS_LABELS.get(str(row.get('axis') or ''), row.get('axis'))}."
                for row in interactions[:8]
            ],
        })

    return {
        "version": REPORT_DETAILS_VERSION,
        "data_quality": quality,
        "sections": sections,
        "key_ingredients": key_items,
        "other_ingredients": other_items,
        "interactions": interactions,
        "hard_flags": hard_flags,
    }
