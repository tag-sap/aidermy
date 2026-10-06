# profile_resolver.py
# PROFILE RESOLVER: structured profile IDs -> 6 canonical axes (weights) +
# warnings/restrictions/context.
#
# Порядок:
#   UI profile -> structured IDs -> hierarchy/dedup -> modifiers (temporal decay)
#   -> caps -> normalization -> 6 canonical weights -> scoring engine.
#
# НЕ меняет формулу ingredient scoring. Только источник profile weights.
# Аллергии/непереносимости НЕ становятся axis weights — они идут в restrictions.

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .profile_matrix import (
    AXES,
    INTOLERANCE_CONFIG,
    INTOLERANCE_INGREDIENT_SYNONYMS,
    LEGACY_ALLERGY_MAP,
    LEGACY_CONCERN_MAP,
    LEGACY_SKIN_TYPE_MAP,
    PROCEDURE_TEMPORAL_DECAY,
    PROFILE_MATRIX,
    SKIN_TYPE_MATRIX,
    THERAPY_TEMPORAL_FACTOR,
)


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    return [value]


def _element_id(item: Any) -> Optional[str]:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("id") or item.get("value") or item.get("key")
    return None


def _depth(matrix: Dict[str, Any], sid: str) -> int:
    d = 0
    node = matrix.get(sid)
    while node and node.get("parent"):
        d += 1
        node = matrix.get(node["parent"])
    return d


def _total_weight(matrix: Dict[str, Any], sid: str) -> float:
    return sum(float(v) for v in matrix.get(sid, {}).get("axes", {}).values())


def _days_since(iso: Any) -> Optional[int]:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


# Алиасы: фронтенд-IDs анкеты (data.ts) -> канонические matrix-IDs (profile_matrix).
# Фронтенд использует собственные ID, которые не всегда совпадают с matrix-IDs.
_MATRIX_ID_ALIASES: Dict[str, str] = {
    # therapy
    "antibiotic": "topical_antibiotic",
    # procedures
    "recent_peeling": "professional_peel",
}

# Алиасы периодов процедур (фронтенд -> канонические ключи PROCEDURE_TEMPORAL_DECAY).
_PROCEDURE_PERIOD_ALIASES: Dict[str, str] = {
    "<7": "<7 days",
    "7-14": "7-14 days",
    "14-30": "14-30 days",
    "1-3m": "1-3 months",
    ">3m": ">3 months",
}


def _canonical_matrix_id(sid: str) -> Optional[str]:
    """Канонический matrix-ID из фронтенд-ID (алиасы)."""
    if sid is None:
        return None
    sid = str(sid).strip().lower()
    return _MATRIX_ID_ALIASES.get(sid, sid)


def _canonical_skin_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    canonical = _canonical_matrix_id(raw)
    if canonical in SKIN_TYPE_MATRIX:
        return canonical
    for alias, skin_type in LEGACY_SKIN_TYPE_MAP.items():
        if alias in raw:
            return skin_type
    return ""


def _therapy_factor(item: Dict[str, Any]) -> float:
    cfg = THERAPY_TEMPORAL_FACTOR
    if item.get("active"):
        return float(cfg["active"])
    days = _days_since(item.get("last_used_at") or item.get("started_at"))
    if days is None:
        return float(cfg["recent_factor"])
    if days < int(cfg["recent_days"]):
        return float(cfg["recent_factor"])
    if days < int(cfg["old_days"]):
        return float(cfg["old_factor"])
    return float(cfg["expired_factor"])


def _procedure_factor(item: Dict[str, Any]) -> float:
    period = str(item.get("period") or "").strip()
    period = _PROCEDURE_PERIOD_ALIASES.get(period, period)
    return float(PROCEDURE_TEMPORAL_DECAY.get(period, 0.0))


def _severity_factor(item: Dict[str, Any]) -> float:
    severity = item.get("severity")
    if isinstance(severity, (int, float)) and not isinstance(severity, bool):
        if severity <= 2:
            return 0.75
        if severity >= 4:
            return 1.25
        return 1.0
    value = str(severity or "").strip().lower()
    if value in {"low", "mild", "легкая", "лёгкая", "низкая"}:
        return 0.75
    if value in {"high", "severe", "тяжелая", "тяжёлая", "высокая"}:
        return 1.25
    return 1.0


def _collect_score_ids(profile: Dict[str, Any]) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    ids: List[str] = []
    temporal: Dict[str, Dict[str, Any]] = {}

    st = profile.get("skin_type")
    if st:
        ids.append(str(st).strip().lower())

    for key in ("concerns", "imperfections", "states", "selected"):
        for item in _as_list(profile.get(key)):
            sid = _element_id(item)
            if sid:
                sid = _canonical_matrix_id(str(sid).strip().lower())
                ids.append(sid)
                if isinstance(item, dict):
                    temporal.setdefault(sid, dict(item))

    for item in _as_list(profile.get("therapy")):
        sid = _canonical_matrix_id(_element_id(item))
        if sid:
            sid = str(sid).strip().lower()
            ids.append(sid)
            temporal[sid] = {
                **(item if isinstance(item, dict) else {"active": True}),
                "_profile_source": "therapy",
            }

    for item in _as_list(profile.get("procedures")):
        sid = _canonical_matrix_id(_element_id(item))
        if sid:
            sid = str(sid).strip().lower()
            ids.append(sid)
            temporal[sid] = {
                **(item if isinstance(item, dict) else {}),
                "_profile_source": "procedure",
            }

    return ids, temporal


def resolve_personal_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Возвращает {weights, warnings, restrictions, context, active_therapy,
    active_procedures, intolerances, allergies}."""
    profile = profile or {}
    matrix = PROFILE_MATRIX

    ids, temporal = _collect_score_ids(profile)
    score_ids = [s for s in ids if s in matrix and matrix[s].get("mode") == "score"]
    selected_set = set(score_ids)

    # 1) hierarchy dedup: ancestor затеняется более специфичным потомком.
    shadowed: set = set()
    for sid in selected_set:
        parent = matrix[sid].get("parent")
        while parent:
            if parent in selected_set:
                shadowed.add(parent)
            parent = matrix.get(parent, {}).get("parent")

    # 2) mutually_exclusive_group: в группе остаётся самый специфичный.
    groups: Dict[str, List[str]] = {}
    for sid in selected_set - shadowed:
        g = matrix[sid].get("mutually_exclusive_group")
        if g:
            groups.setdefault(g, []).append(sid)
    for members in groups.values():
        if len(members) > 1:
            ordered = sorted(members, key=lambda s: (_depth(matrix, s), _total_weight(matrix, s)), reverse=True)
            for m in ordered[1:]:
                shadowed.add(m)

    # 3) аккумулируем axes (с temporal factor).
    raw = {axis: 0.0 for axis in AXES}
    severity_totals = {axis: 0.0 for axis in AXES}
    severity_weights = {axis: 0.0 for axis in AXES}
    warnings: List[str] = []
    context: List[str] = []
    active_therapy: List[str] = []
    active_procedures: List[str] = []

    for sid in selected_set:
        if sid in shadowed:
            continue
        node = matrix[sid]
        factor = 1.0
        t = temporal.get(sid, {})
        if node.get("temporal"):
            source = t.get("_profile_source")
            if source == "procedure" or node.get("category") == "procedure":
                factor = _procedure_factor(t)
                if factor > 0:
                    active_procedures.append(sid)
            elif source == "therapy" or node.get("category") == "therapy":
                factor = _therapy_factor(t)
                if factor > 0:
                    active_therapy.append(sid)
        if factor <= 0:
            continue
        severity_factor = _severity_factor(t)
        temporal_modifier = t.get("_profile_source") in {"therapy", "procedure"} \
            or node.get("category") in {"therapy", "procedure"}
        for axis, w in node["axes"].items():
            contribution = min(float(w), float(node.get("max_contribution", 1.0))) * factor
            raw[axis] += contribution
            if not temporal_modifier:
                severity_totals[axis] += contribution * severity_factor
                severity_weights[axis] += contribution
        if node.get("warning"):
            warnings.append(node["warning"])

    # warning-элементы (mode=warning) и context-элементы.
    for sid in ids:
        if sid not in matrix:
            continue
        node = matrix[sid]
        if node.get("mode") == "warning" and node.get("warning"):
            warnings.append(node["warning"])
        elif node.get("mode") == "context":
            context.append(sid)

    # 4) normalization.
    total = sum(raw.values())
    if total > 0:
        weights = {axis: round(raw[axis] / total, 6) for axis in AXES}
    else:
        weights = _default_weights()

    return {
        "weights": weights,
        "axis_multipliers": {
            axis: round(severity_totals[axis] / severity_weights[axis], 6)
            if severity_weights[axis] > 0 else 1.0
            for axis in AXES
        },
        "warnings": _dedupe(warnings),
        "restrictions": _as_list(profile.get("restrictions")),
        "intolerances": _as_list(profile.get("intolerances")),
        "allergies": _as_list(profile.get("allergies")),
        "age": profile.get("age"),
        "context": _dedupe(context),
        "active_therapy": _dedupe(active_therapy),
        "active_procedures": _dedupe(active_procedures),
        "selected_ids": _dedupe(list(selected_set)),
        "concern_severity": {
            sid: temporal[sid].get("severity")
            for sid in selected_set
            if temporal.get(sid, {}).get("severity") is not None
        },
    }


def _dedupe(items: List[str]) -> List[str]:
    out: List[str] = []
    for it in items:
        if it not in out:
            out.append(it)
    return out


def _default_weights() -> Dict[str, float]:
    return {axis: round(1.0 / len(AXES), 6) for axis in AXES}


def profile_weights(profile: Dict[str, Any], skin_type: str = "") -> Dict[str, float]:
    return resolve_personal_profile(profile)["weights"]


def legacy_profile_to_structured(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Старые RU-поля (skinType/concerns/allergies) -> новый structured профиль."""
    profile = profile or {}
    raw_st = str(
        profile.get("skin_type") or profile.get("skin_type_determined") or ""
    ).strip().lower()
    skin_type = ""
    for key, canon in LEGACY_SKIN_TYPE_MAP.items():
        if key in raw_st:
            skin_type = canon
            break

    concerns: List[str] = []
    for raw in _as_list(profile.get("concerns")):
        c = str(_element_id(raw) or raw).strip().lower()
        if c in PROFILE_MATRIX and PROFILE_MATRIX[c].get("mode") == "score":
            if c not in concerns:
                concerns.append(c)
            continue
        for key, canon in LEGACY_CONCERN_MAP.items():
            if key in c:
                if canon not in concerns:
                    concerns.append(canon)
                break

    intolerances: List[str] = []
    for raw in _as_list(profile.get("allergies")):
        a = str(raw).strip().lower()
        if a in ("нет", "нету", "none", ""):
            continue
        for key, canon in LEGACY_ALLERGY_MAP.items():
            if key in a:
                if canon not in intolerances:
                    intolerances.append(canon)
                break

    return {
        "skin_type": skin_type,
        "concerns": concerns,
        "imperfections": [],
        "states": [],
        "therapy": [],
        "procedures": [],
        "goals": [],
        "intolerances": intolerances,
        "allergies": [],
    }


def intolerance_to_ingredients(profile: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """intolerance IDs -> (soft_intolerances, hard_restrictions) — списки ингредиентов.

    category-intolerance -> категория (обрабатывается существующими синонимами);
    ingredient-intolerance -> конкретный ингредиент (напр. niacinamide).
    """
    soft: List[str] = []
    hard: List[str] = []
    for item in _as_list(profile.get("intolerances")):
        if isinstance(item, dict):
            tid = item.get("type")
            if tid == "specific_ingredient" or item.get("ingredient_id"):
                ing = item.get("ingredient_id") or item.get("ingredient")
                if ing:
                    hard.append(str(ing))
            elif isinstance(tid, str):
                soft.append(tid)
        elif isinstance(item, str):
            cfg = INTOLERANCE_CONFIG.get(item)
            if cfg:
                if cfg.get("type") == "ingredient":
                    hard.append(cfg.get("ingredient", item))
                else:
                    soft.append(item)
    return _dedupe(soft), _dedupe(hard)


def intolerance_ingredient_aliases(item: Any) -> List[str]:
    """Return ingredient tokens for a category intolerance ID or legacy label."""
    if isinstance(item, dict):
        item = item.get("type") or item.get("ingredient_id") or item.get("ingredient")
    if not isinstance(item, str):
        return []
    key = item.strip().lower()
    if key in INTOLERANCE_INGREDIENT_SYNONYMS:
        return list(INTOLERANCE_INGREDIENT_SYNONYMS[key])
    for intolerance_id, config in INTOLERANCE_CONFIG.items():
        if str(config.get("label") or "").strip().lower() == key:
            return list(INTOLERANCE_INGREDIENT_SYNONYMS.get(intolerance_id, []))
    for legacy, intolerance_id in LEGACY_ALLERGY_MAP.items():
        if legacy in key:
            return list(INTOLERANCE_INGREDIENT_SYNONYMS.get(intolerance_id, []))
    return []


def _as_profile_values(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str) and "," in value:
        return [item.strip() for item in value.split(",") if item.strip()]
    return [value]


def _merge_profile_items(*groups: List[Any]) -> List[Any]:
    merged: List[Any] = []
    positions: Dict[str, int] = {}
    for group in groups:
        for item in group:
            item_id = _element_id(item)
            key = str(item_id if item_id is not None else item).strip().lower()
            if not key:
                continue
            position = positions.get(key)
            if position is None:
                positions[key] = len(merged)
                merged.append(item)
            elif isinstance(item, dict) and not isinstance(merged[position], dict):
                merged[position] = item
    return merged


def merge_profile_layers(profile: Dict[str, Any], skin_type: str = "") -> Dict[str, Any]:
    """Merge legacy API fields with the canonical structured profile."""
    result = dict(profile or {})
    structured = result.get("structured")
    structured = dict(structured) if isinstance(structured, dict) else {}

    legacy_source = dict(result)
    if not legacy_source.get("skin_type"):
        legacy_source["skin_type"] = (
            legacy_source.get("skin_type_determined") or skin_type
        )
    legacy = legacy_profile_to_structured(legacy_source)

    concern_items = []
    for item in _as_profile_values(result.get("concerns")):
        item_id = _element_id(item) or item
        if str(item_id).strip().lower() in PROFILE_MATRIX:
            concern_items.append(item)

    keys = (
        "concerns", "imperfections", "states", "selected", "therapy", "procedures",
        "goals", "skin_goals", "intolerances", "allergies", "restrictions",
    )
    for key in keys:
        additions = _as_profile_values(result.get(key))
        if key == "concerns":
            additions = concern_items + legacy.get("concerns", [])
        structured[key] = _merge_profile_items(
            _as_profile_values(structured.get(key)), additions
        )

    raw_skin_type = (
        result.get("skin_type") or result.get("skin_type_determined") or skin_type
    )
    canonical_skin_type = _canonical_skin_type(raw_skin_type) or legacy.get("skin_type") or ""
    structured["skin_type"] = (
        _canonical_skin_type(structured.get("skin_type")) or canonical_skin_type
    )
    structured["sensitivity"] = (
        structured.get("sensitivity") or result.get("sensitivity") or ""
    )
    structured["age"] = structured.get("age") or result.get("age")
    result["structured"] = structured
    return result


def normalize_scoring_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Merge legacy and structured constraints into the Score Engine input."""
    result = merge_profile_layers(profile)
    structured = result.get("structured")
    structured = structured if isinstance(structured, dict) else {}

    allergies: List[Any] = []
    allergy_items = (
        _as_profile_values(result.get("allergies"))
        + _as_profile_values(structured.get("allergies"))
    )
    for item in allergy_items:
        aliases = intolerance_ingredient_aliases(item)
        allergies.extend(aliases or [item])

    restrictions = (
        _as_profile_values(result.get("restrictions"))
        + _as_profile_values(structured.get("restrictions"))
    )
    soft_intolerances, hard_intolerances = intolerance_to_ingredients(structured)
    restrictions.extend(hard_intolerances)
    intolerances = _as_profile_values(result.get("intolerances")) + soft_intolerances

    result["allergies"] = _dedupe([str(x).strip() for x in allergies if str(x).strip()])
    result["restrictions"] = _dedupe([str(x).strip() for x in restrictions if str(x).strip()])
    result["intolerances"] = _dedupe(intolerances)
    return result
