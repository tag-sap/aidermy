"""Deterministic, concern-specific evidence derived from ingredient claims."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from .profile_matrix import PROFILE_MATRIX


# These are direct ingredient-effect mappings, not Score Engine axis weights.
# A property is usable only where its recorded meaning is relevant to the
# selected concern. Unsupported concerns intentionally have no mapping.
_CONCERN_PROPERTIES: Dict[str, Dict[str, str]] = {
    "acne_general": {
        "acne_control": "supports",
        "anti_acne": "supports",
    },
    "open_comedones": {
        "comedogenicity": "may_hinder",
        "pore_clogging": "may_hinder",
        "breakout_potential": "may_hinder",
        "acneogenicity": "may_hinder",
    },
    "closed_comedones": {
        "comedogenicity": "may_hinder",
        "pore_clogging": "may_hinder",
        "breakout_potential": "may_hinder",
        "acneogenicity": "may_hinder",
    },
    "blackheads": {
        "comedogenicity": "may_hinder",
        "pore_clogging": "may_hinder",
        "breakout_potential": "may_hinder",
        "acneogenicity": "may_hinder",
    },
    "clogged_pores": {
        "comedogenicity": "may_hinder",
        "pore_clogging": "may_hinder",
        "breakout_potential": "may_hinder",
        "acneogenicity": "may_hinder",
    },
    "excess_sebum": {
        "oil_control": "supports",
        "sebum_control": "supports",
        "sebum_regulating": "supports",
        "mattifying": "supports",
        "sebum": "may_hinder",
        "sebum_production": "may_hinder",
    },
    "oily_t_zone": {
        "oil_control": "supports",
        "sebum_control": "supports",
        "sebum_regulating": "supports",
        "mattifying": "supports",
        "sebum": "may_hinder",
        "sebum_production": "may_hinder",
    },
    "enlarged_pores": {
        "pore_refining": "supports",
        "pore_clogging": "may_hinder",
    },
    "visible_pores": {
        "pore_refining": "supports",
        "pore_clogging": "may_hinder",
    },
    "sebum_plugs": {
        "pore_clogging": "may_hinder",
        "comedogenicity": "may_hinder",
    },
    "dehydrated_skin": {
        "hydration": "supports",
        "moisturizing": "supports",
        "humectant": "supports",
    },
    "skin_tightness": {
        "hydration": "supports",
        "moisturizing": "supports",
        "humectant": "supports",
    },
    "impaired_barrier": {
        "barrier_support": "supports",
        "barrier_strengthening": "supports",
        "barrier": "supports",
    },
    "weak_barrier": {
        "barrier_support": "supports",
        "barrier_strengthening": "supports",
        "barrier": "supports",
    },
    "irritation_prone": {
        "soothing": "supports",
        "calming": "supports",
        "anti_irritation": "supports",
        "anti_inflammatory": "supports",
        "sensitivity": "supports",
        "irritation": "may_hinder",
        "irritation_risk": "may_hinder",
        "sensitization": "may_hinder",
        "allergen": "may_hinder",
    },
    "reactive_skin": {
        "soothing": "supports",
        "calming": "supports",
        "anti_irritation": "supports",
        "anti_inflammatory": "supports",
        "sensitivity": "supports",
        "irritation": "may_hinder",
        "irritation_risk": "may_hinder",
        "sensitization": "may_hinder",
        "allergen": "may_hinder",
    },
    "post_acne_pigmentation": {
        "brightening": "supports",
        "lightening": "supports",
        "whitening": "supports",
        "pigmentation": "may_hinder",
        "hyperpigmentation": "may_hinder",
    },
    "pigmentation": {
        "brightening": "supports",
        "lightening": "supports",
        "whitening": "supports",
        "pigmentation": "may_hinder",
        "hyperpigmentation": "may_hinder",
    },
    "dark_spots": {
        "brightening": "supports",
        "lightening": "supports",
        "whitening": "supports",
        "pigmentation": "may_hinder",
        "hyperpigmentation": "may_hinder",
    },
    "uneven_tone": {
        "brightening": "supports",
        "lightening": "supports",
        "whitening": "supports",
        "pigmentation": "may_hinder",
        "hyperpigmentation": "may_hinder",
    },
    "sun_pigmentation": {
        "brightening": "supports",
        "lightening": "supports",
        "whitening": "supports",
        "pigmentation": "may_hinder",
        "hyperpigmentation": "may_hinder",
    },
}


def scoped_concern_property(concern_id: str, property_name: str) -> str:
    return f"goal:{concern_id}:{property_name}"


def _property_for_concern(property_name: str, concern_id: str) -> str | None:
    prefix = f"goal:{concern_id}:"
    if property_name.startswith("goal:"):
        return property_name[len(prefix):] if property_name.startswith(prefix) else None
    return property_name


def selected_concern_ids(profile: Mapping[str, Any] | None) -> List[str]:
    if not isinstance(profile, Mapping):
        return []
    return _profile_concern_ids(profile)


def _profile_concern_ids(profile: Mapping[str, Any]) -> List[str]:
    structured = profile.get("structured")
    source = structured if isinstance(structured, dict) else profile
    values: List[Any] = []
    for key in ("concerns", "imperfections", "states", "selected"):
        value = source.get(key)
        if isinstance(value, list):
            values.extend(value)
        elif isinstance(value, str) and value.strip():
            values.append(value)

    if not isinstance(structured, dict):
        from .profile_resolver import legacy_profile_to_structured

        legacy = legacy_profile_to_structured(dict(profile))
        values.extend(legacy.get("concerns") or [])

    result: List[str] = []
    seen = set()
    for value in values:
        concern_id = value.get("id") if isinstance(value, dict) else value
        if not isinstance(concern_id, str):
            continue
        concern_id = concern_id.strip().lower()
        node = PROFILE_MATRIX.get(concern_id)
        if (
            not concern_id
            or concern_id in seen
            or not node
            or node.get("category") in {"skin_type", "therapy", "procedure"}
        ):
            continue
        seen.add(concern_id)
        result.append(concern_id)
    return result


def find_missing_concern_pairs(
    profile: Mapping[str, Any] | None,
    ingredients: Iterable[str],
    claims: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> List[Dict[str, Any]]:
    """Return only current-product ingredient/concern pairs without a direct claim."""
    if not isinstance(profile, Mapping):
        return []

    pairs: List[Dict[str, Any]] = []
    seen_pairs = set()
    for concern_id in _profile_concern_ids(profile):
        properties = _CONCERN_PROPERTIES.get(concern_id, {})
        if not properties:
            continue
        for raw_ingredient in ingredients:
            ingredient = str(raw_ingredient).strip().lower()
            pair_key = (ingredient, concern_id)
            if not ingredient or pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            ingredient_claims = claims.get(ingredient) or {}
            if any(
                property_name in ingredient_claims
                or scoped_concern_property(concern_id, property_name) in ingredient_claims
                for property_name in properties
            ):
                continue
            pairs.append({
                "ingredient": ingredient,
                "concern_id": concern_id,
                "properties": list(properties),
                "positive_direction": properties,
            })
    return pairs


def _valid_number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number < 0.0:
        return 0.0
    if number > 1.0:
        return 1.0
    return number


def _diminishing_total(values: Iterable[float]) -> float:
    return sum(value / rank for rank, value in enumerate(sorted(values, reverse=True), 1))


def evaluate_goal_evidence(
    profile: Mapping[str, Any] | None,
    ingredients: Iterable[str],
    claims: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> List[Dict[str, Any]]:
    """Aggregate explicit ingredient claims for the concerns selected by a user."""
    if not isinstance(profile, Mapping):
        return []

    ingredient_names = list(dict.fromkeys(
        str(name).strip().lower() for name in ingredients if str(name).strip()
    ))
    results: List[Dict[str, Any]] = []
    for concern_id in _profile_concern_ids(profile):
        node = PROFILE_MATRIX[concern_id]
        property_rules = _CONCERN_PROPERTIES.get(concern_id, {})
        evidence: List[Dict[str, Any]] = []
        support_weights: List[float] = []
        hinder_weights: List[float] = []
        neutral_weights: List[float] = []

        for ingredient in ingredient_names:
            for stored_property, claim in (claims.get(ingredient) or {}).items():
                property_name = _property_for_concern(
                    str(stored_property).strip().lower(),
                    concern_id,
                )
                expected = property_rules.get(property_name or "")
                if not expected or not isinstance(claim, Mapping):
                    continue

                direction = str(claim.get("direction") or "").strip().lower()
                if direction not in {"positive", "negative", "neutral"}:
                    continue
                strength = _valid_number(claim.get("strength"))
                confidence = _valid_number(claim.get("confidence"))
                if strength <= 0.0 or confidence <= 0.0:
                    continue

                verdict = expected
                if direction == "neutral":
                    verdict = "neutral"
                elif direction == "negative":
                    verdict = "may_hinder" if expected == "supports" else "supports"

                weight = strength * confidence
                if verdict == "supports":
                    support_weights.append(weight)
                elif verdict == "may_hinder":
                    hinder_weights.append(weight)
                else:
                    neutral_weights.append(weight)

                evidence.append({
                    "ingredient": ingredient,
                    "property": property_name,
                    "direction": direction,
                    "verdict": verdict,
                    "strength": strength,
                    "confidence": confidence,
                    "evidence_level": claim.get("evidence_level"),
                    "source_url": claim.get("source_url"),
                    "source_title": claim.get("source_title"),
                })

        support = _diminishing_total(support_weights)
        hinder = _diminishing_total(hinder_weights)
        if not evidence:
            verdict = "insufficient_data"
        elif support > hinder:
            verdict = "supports"
        elif hinder > support:
            verdict = "may_hinder"
        else:
            verdict = "neutral"

        results.append({
            "concern_id": concern_id,
            "label": node.get("label") or concern_id,
            "verdict": verdict,
            "evidence": evidence,
        })

    return results
