# correct_ingredient_claims.py
# Исправление direction ingredient_claims + полный аудит direction по всей БД.
#
# СЕМАНТИКА DIRECTION (зафиксирована из кода, НЕ меняется):
#   canonical axes = подписанные биологические endpoint'ы.
#   benefit-оси (hydration, barrier):
#       positive = усиливает свойство  -> benefit (+вклад)
#       negative = ослабляет свойство  -> harm    (-вклад)
#   harm-оси (irritation, sensitization, sebum, pigmentation):
#       positive = усиливает вред      -> harm    (-вклад)
#       negative = ослабляет вред/soothing -> benefit (+вклад)
#
#   Примеры:
#       irritation positive = увеличивает раздражение  (вред)
#       irritation negative = снижает раздражение/soothing (польза)
#       sensitization positive = сенсибилизирует       (вред)
#       sebum negative = снижает себум/oil-control     (польза)
#       pigmentation negative = осветляет               (польза)
#
# Legacy aliases (с flip, см. scoring_config.AXIS_ALIASES):
#       soothing positive  -> irritation negative
#       sensitivity positive -> irritation negative
#       oil_control positive -> sebum negative
#       brightening positive -> pigmentation negative
#       barrier_support positive -> barrier positive
#
# Это DATA CORRECTION, а НЕ новая версия scoring config. Weights/formula/floor не меняются.

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .database import AIDERMY_DB, PRODUCTS_DB, get_connection

# ---------------------------------------------------------------------------
# HIGH-CONFIDENCE исправления (подтверждены внешними источниками).
# (normalized_name, property_name, old_direction, new_direction, new_strength, reason)
# new_strength=None -> не менять strength. new_direction=None -> не менять direction.
# ---------------------------------------------------------------------------
FLIP_CORRECTIONS: List[Tuple[str, str, str, str, Optional[float], str]] = [
    ("curcuma longa", "irritation", "positive", "negative", None,
     "внешне: turmeric anti-inflammatory/soothing (INCIDecoder), регулирует sebum"),
    ("curcuma longa", "sensitization", "negative", "positive", None,
     "внешне: «can cause contact dermatitis» — сенсибилизирующий, не снижающий"),
    ("curcuma longa", "pigmentation", "positive", "negative", None,
     "evidence «inhibits tyrosinase/melanogenesis» = снижает пигментацию"),
    ("ocimum sanctum leaf extract", "irritation", "positive", "negative", None,
     "внешне: holy basil anti-inflammatory (INCIDecoder skin conditioning)"),
    ("ocimum sanctum leaf extract", "sensitization", "negative", "positive", None,
     "evidence «eugenol may cause sensitization» — сенсибилизирующий"),
    ("ocimum basilicum", "irritation", "positive", "negative", None,
     "внешне: basil anti-inflammatory"),
    ("ocimum basilicum", "sensitization", "negative", "positive", None,
     "evidence «eugenol/linalool, potential sensitizers»"),
]

# ascorbic acid / l-ascorbic acid: снизить sensitivity до mild, удалить hydration negative.
VITC_INGREDIENTS = ["ascorbic acid", "l-ascorbic acid"]
VITC_SENSITIVITY_STRENGTH = 0.15


# ---------------------------------------------------------------------------
# Аудит direction: эвристики «evidence-текст противоречит direction».
# ---------------------------------------------------------------------------
# benefit-индикаторы (для harm-осей означают «ослабляет вред» -> direction должен быть negative).
_BENEFIT_HINTS = (
    "anti-inflammatory", "anti inflammatory", "sooth", "calm", "anti-irritat",
    "reduce irritation", "reduce erythema", "reduce redness", "reduce inflammation",
    "anti-inflammat", "skin conditioning",
)
# harm-индикаторы (для harm-осей означают «усиливает вред» -> direction positive).
_HARM_HINTS = (
    "contact dermatitis", "sensitiz", "allerg", "may cause irritation", "irritat",
    "sting", "potential sensitizer", "eugenol", "linalool", "can cause", "risk of",
)
# осветление (для pigmentation: «снижает пигментацию» -> negative; для brightening -> positive).
_LIGHTEN_HINTS = ("tyrosinase", "melanogenesis", "brighten", "whiten", "lighten",
                  "reduce hyperpigmentation", "reduce pigmentation", "anti-pigment")
# sebum control (для sebum -> negative; для oil_control -> positive).
_SEBUM_CONTROL_HINTS = ("sebum", "oil control", "oil-control", "mattif", "anti-acne", "regulate sebum")
# дегидратация (для hydration -> negative = вред).
_DEHYDRATE_HINTS = ("dehydrat", "drying", "reduces hydration", "transepidermal water loss")


def _affected_products() -> Dict[str, int]:
    """normalized_name -> количество продуктов, содержащих этот ингредиент (в INCI)."""
    from .ingredient_normalizer import normalize_ingredient_name

    counts: Counter = Counter()
    conn = get_connection(PRODUCTS_DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT ingredients FROM products WHERE is_canonical = 1").fetchall()
        for r in rows:
            seen = set()
            for part in re.split(r"(?<!\d),(?!\d)|[;\n]+", r["ingredients"] or ""):
                key = normalize_ingredient_name(part)
                if key and key not in seen:
                    seen.add(key)
                    counts[key] += 1
    finally:
        conn.close()
    return dict(counts)


def _suspicion(name: str, prop: str, direction: str, evidence: str, affected: int) -> Tuple[str, Optional[str]]:
    """(level, reason) — есть ли противоречие direction vs evidence."""
    ev = (evidence or "").lower()
    d = (direction or "").strip().lower()
    prop_key = prop.lower().replace(" ", "_")

    # --- irritation (и aliases soothing/sensitivity) ---
    if prop_key in ("irritation", "soothing", "sensitivity", "irritation_risk"):
        if any(h in ev for h in _BENEFIT_HINTS) and d == "positive":
            return ("HIGH", f"evidence='{evidence}' (benefit) но direction=positive")
        if any(h in ev for h in _HARM_HINTS) and d == "negative":
            return ("HIGH", f"evidence='{evidence}' (harm) но direction=negative")

    # --- sensitization ---
    if prop_key in ("sensitization", "sensitizer", "allergen"):
        if any(h in ev for h in _HARM_HINTS) and d == "negative":
            return ("HIGH", f"evidence='{evidence}' (сенсибилизирующий) но direction=negative")
        if "hypoallergenic" in ev and d == "positive":
            return ("HIGH", f"evidence='{evidence}' (гипоаллергенный) но direction=positive")

    # --- pigmentation / brightening ---
    if prop_key in ("pigmentation", "hyperpigmentation"):
        if any(h in ev for h in _LIGHTEN_HINTS) and d == "positive":
            return ("HIGH", f"evidence='{evidence}' (осветляет) но direction=positive")
    if prop_key in ("brightening", "whitening", "lightening"):
        if any(h in ev for h in _LIGHTEN_HINTS) and d == "negative":
            return ("HIGH", f"evidence='{evidence}' (осветляет) но direction=negative")

    # --- sebum / oil_control ---
    if prop_key in ("sebum", "sebum_production"):
        if any(h in ev for h in _SEBUM_CONTROL_HINTS) and d == "positive":
            return ("HIGH", f"evidence='{evidence}' (контроль себума) но direction=positive")
    if prop_key in ("oil_control", "sebum_control", "sebum_regulating", "mattifying"):
        if any(h in ev for h in _SEBUM_CONTROL_HINTS) and d == "negative":
            return ("HIGH", f"evidence='{evidence}' (контроль себума) но direction=negative")

    # --- hydration ---
    if prop_key == "hydration":
        if any(h in ev for h in _DEHYDRATE_HINTS) and d == "positive":
            return ("MEDIUM", f"evidence='{evidence}' (дегидратация) но direction=positive")

    # --- barrier ---
    if prop_key in ("barrier", "barrier_support"):
        if ("barrier" in ev and ("repair" in ev or "strengthen" in ev or "restore" in ev or "improve" in ev)) and d == "negative":
            return ("HIGH", f"evidence='{evidence}' (укрепляет барьер) но direction=negative")

    return ("CLEAN", None)


def _load_claims(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT c.id, c.ingredient_id, i.normalized_name, c.property_name, c.direction,
               c.strength, c.confidence, c.evidence_level, c.source_type, c.source_url
        FROM ingredient_claims c
        JOIN ingredients_catalog i ON i.id = c.ingredient_id
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _apply_flip_corrections(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Применяет подтверждённые flip-исправления direction. Возвращает список изменений."""
    changes: List[Dict[str, Any]] = []
    claims = _load_claims(conn)
    by_key = defaultdict(list)
    for c in claims:
        by_key[(c["normalized_name"], c["property_name"], c["direction"])].append(c)

    for name, prop, old_dir, new_dir, new_strength, reason in FLIP_CORRECTIONS:
        for c in by_key.get((name, prop, old_dir), []):
            conn.execute(
                "UPDATE ingredient_claims SET direction = ? WHERE id = ?",
                (new_dir, c["id"]),
            )
            if new_strength is not None:
                conn.execute(
                    "UPDATE ingredient_claims SET strength = ? WHERE id = ?",
                    (new_strength, c["id"]),
                )
            changes.append({
                "id": c["id"], "ingredient": name, "property": prop,
                "before_direction": old_dir, "after_direction": new_dir,
                "before_strength": c["strength"],
                "after_strength": new_strength if new_strength is not None else c["strength"],
                "evidence": c["evidence_level"], "reason": reason, "confidence": "HIGH",
            })
    return changes


def _apply_vitc_corrections(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """ascorbic acid: sensitivity -> mild (0.15); удалить hydration negative."""
    changes: List[Dict[str, Any]] = []
    claims = _load_claims(conn)
    for c in claims:
        if c["normalized_name"] not in VITC_INGREDIENTS:
            continue
        if (c["property_name"] == "sensitivity" and c["direction"] == "negative"
                and (c["strength"] or 0) > VITC_SENSITIVITY_STRENGTH):
            conn.execute("UPDATE ingredient_claims SET strength = ? WHERE id = ?",
                         (VITC_SENSITIVITY_STRENGTH, c["id"]))
            changes.append({
                "id": c["id"], "ingredient": c["normalized_name"], "property": "sensitivity",
                "before_direction": "negative", "after_direction": "negative",
                "before_strength": c["strength"], "after_strength": VITC_SENSITIVITY_STRENGTH,
                "evidence": c["evidence_level"],
                "reason": "витамин C = slight tingling (не сильный ирритант)", "confidence": "HIGH",
            })
        if c["property_name"] == "hydration" and c["direction"] == "negative":
            conn.execute("DELETE FROM ingredient_claims WHERE id = ?", (c["id"],))
            changes.append({
                "id": c["id"], "ingredient": c["normalized_name"], "property": "hydration",
                "before_direction": "negative", "after_direction": "DELETED",
                "before_strength": c["strength"], "after_strength": None,
                "evidence": c["evidence_level"],
                "reason": "витамин C не дегидратирует", "confidence": "HIGH",
            })
    return changes


def _coverage(claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    from .scoring_config import AXES, AXIS_ALIASES
    prop_to_axis = {p: a for p, (a, _f) in AXIS_ALIASES.items()}
    axis_ing = defaultdict(set)
    for c in claims:
        axis = prop_to_axis.get(c["property_name"].lower().replace(" ", "_"))
        if axis and axis in AXES:
            axis_ing[axis].add(c["ingredient_id"])
    return {axis: len(ings) for axis, ings in axis_ing.items()}


def _audit_all(conn: sqlite3.Connection) -> Dict[str, Any]:
    claims = _load_claims(conn)
    affected = _affected_products()
    suspicious: List[Dict[str, Any]] = []
    for c in claims:
        lvl, reason = _suspicion(
            c["normalized_name"], c["property_name"], c["direction"],
            c["evidence_level"], affected.get(c["normalized_name"], 0),
        )
        if lvl in ("HIGH", "MEDIUM"):
            suspicious.append({
                "ingredient": c["normalized_name"], "property": c["property_name"],
                "direction": c["direction"], "strength": c["strength"],
                "confidence": c["confidence"], "evidence": c["evidence_level"],
                "affected_products": affected.get(c["normalized_name"], 0),
                "level": lvl, "reason": reason,
            })
    suspicious.sort(key=lambda s: (-s["affected_products"], -(s["confidence"] or 0), -(s["strength"] or 0)))
    return {
        "total_claims": len(claims),
        "high_suspicion": [s for s in suspicious if s["level"] == "HIGH"],
        "medium_suspicion": [s for s in suspicious if s["level"] == "MEDIUM"],
        "coverage": _coverage(claims),
    }


def run(apply: bool) -> int:
    conn = get_connection(AIDERMY_DB)
    audit_before = _audit_all(conn)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(f"/root/aidermy_backups/{ts}_claims")
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(AIDERMY_DB, backup_dir / "aidermy.db.before.db")

    if apply:
        try:
            conn.execute("BEGIN")
            flip_changes = _apply_flip_corrections(conn)
            vitc_changes = _apply_vitc_corrections(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    else:
        try:
            conn.execute("BEGIN")
            flip_changes = _apply_flip_corrections(conn)
            vitc_changes = _apply_vitc_corrections(conn)
        finally:
            conn.rollback()

    audit_after = _audit_all(conn) if apply else None
    changes = flip_changes + vitc_changes

    report = {
        "mode": "APPLY" if apply else "DRY-RUN",
        "timestamp": ts,
        "backup_dir": str(backup_dir),
        "semantics": {
            "benefit_axes": ["hydration", "barrier"],
            "harm_axes": ["irritation", "sensitization", "sebum", "pigmentation"],
            "note": "positive = усиливает (benefit для benefit-осей, harm для harm-осей); "
                    "negative = ослабляет (harm для benefit-осей, benefit/soothing для harm-осей)",
        },
        "total_claims": audit_before["total_claims"],
        "corrected_count": len(changes),
        "corrected_high_confidence": changes,
        "audit_before": {
            "high_suspicion": audit_before["high_suspicion"],
            "medium_suspicion": audit_before["medium_suspicion"],
            "coverage": audit_before["coverage"],
        },
        "audit_after": {
            "high_suspicion": audit_after["high_suspicion"] if audit_after else None,
            "medium_suspicion": audit_after["medium_suspicion"] if audit_after else None,
            "coverage": audit_after["coverage"] if audit_after else None,
        },
    }
    conn.close()

    Path("/var/www/aidermy/calibration/ingredient_claim_correction_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"mode: {report['mode']}")
    print(f"total claims: {audit_before['total_claims']}")
    print(f"corrected HIGH-confidence: {len(changes)}")
    for c in changes:
        print(f"  [{c['ingredient'][:32]}] {c['property']}: {c['before_direction']}->{c['after_direction']} "
              f"(strength {c['before_strength']}->{c['after_strength']})")
    print(f"audit HIGH suspicion (before): {len(audit_before['high_suspicion'])}")
    print(f"audit MEDIUM suspicion (before): {len(audit_before['medium_suspicion'])}")
    print(f"backup: {backup_dir}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Correct ingredient claim directions + full direction audit")
    p.add_argument("--apply", action="store_true", help="Apply corrections (default dry-run)")
    return run(apply=p.parse_args().apply)


if __name__ == "__main__":
    raise SystemExit(main())

