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
        return item.get("id")
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
                ids.append(str(sid).strip().lower())

    for item in _as_list(profile.get("therapy")):
        sid = _canonical_matrix_id(_element_id(item))
        if sid:
            sid = str(sid).strip().lower()
            ids.append(sid)
            temporal[sid] = item if isinstance(item, dict) else {"active": True}

    for item in _as_list(profile.get("procedures")):
        sid = _canonical_matrix_id(_element_id(item))
        if sid:
            sid = str(sid).strip().lower()
            ids.append(sid)
            temporal[sid] = item if isinstance(item, dict) else {}

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
    warnings: List[str] = []
    context: List[str] = []
    active_therapy: List[str] = []
    active_procedures: List[str] = []

    for sid in selected_set:
        if sid in shadowed:
            continue
        node = matrix[sid]
        factor = 1.0
        if node.get("temporal"):
            t = temporal.get(sid, {})
            if node.get("category") == "therapy":
                factor = _therapy_factor(t)
                if factor > 0:
                    active_therapy.append(sid)
            elif node.get("category") == "procedure":
                factor = _procedure_factor(t)
                if factor > 0:
                    active_procedures.append(sid)
        if factor <= 0:
            continue
        for axis, w in node["axes"].items():
            raw[axis] += min(float(w), float(node.get("max_contribution", 1.0))) * factor
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
        "warnings": _dedupe(warnings),
        "restrictions": _as_list(profile.get("restrictions")),
        "intolerances": _as_list(profile.get("intolerances")),
        "allergies": _as_list(profile.get("allergies")),
        "age": profile.get("age"),
        "context": _dedupe(context),
        "active_therapy": _dedupe(active_therapy),
        "active_procedures": _dedupe(active_procedures),
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
    raw_st = str(profile.get("skin_type") or "").strip().lower()
    skin_type = ""
    for key, canon in LEGACY_SKIN_TYPE_MAP.items():
        if key in raw_st:
            skin_type = canon
            break

    concerns: List[str] = []
    for raw in _as_list(profile.get("concerns")):
        c = str(raw).strip().lower()
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
    return value if isinstance(value, list) else [value]


def normalize_scoring_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Merge legacy and structured constraints into the Score Engine input."""
    result = dict(profile or {})
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
