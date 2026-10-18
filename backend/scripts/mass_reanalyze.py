#!/usr/bin/env python3
"""Mass ingredient reanalysis via DeepSeek (checkpointed, resumable, idempotent).

Iterates ALL unique ingredients in Postgres, sends batches to DeepSeek with
existing context, strictly validates the response, compares against current
claims and applies only defensible corrections (source_type=deepseek_reanalysis,
history preserved).
Usage:
  python scripts/mass_reanalyze.py --limit N   (smoke test on N ingredients)
  python scripts/mass_reanalyze.py             (full run, resumable)
  python scripts/mass_reanalyze.py --status    (show checkpoint)
"""
import hashlib
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import psycopg
from dotenv import load_dotenv

from app.axes import canonicalize_effect

CANONICAL_AXES = ["hydration", "barrier", "irritation", "sensitization", "sebum", "pigmentation"]
BATCH_SIZE = 8
MAX_RETRIES = 4
TIMEOUT_SEC = 60
MODEL = "deepseek-chat"
PROMPT_VERSION = "reanalysis-1.0"
SOURCE_TYPE = "deepseek_reanalysis"
DATA_DIR = BACKEND / "data"
STATE_FILE = DATA_DIR / "reanalysis_state.json"
AUDIT_FILE = DATA_DIR / "reanalysis_audit.jsonl"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hash(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


def connect():
    load_dotenv(BACKEND / ".env")
    return psycopg.connect(os.environ["SUPABASE_DATABASE_URL"])


def load_ingredients(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, canonical_name, normalized_name, synonyms FROM ingredients_catalog ORDER BY id")
    rows = cur.fetchall()
    cur.execute(
        "SELECT c.ingredient_id, c.property_name, c.direction, c.strength, c.confidence, "
        "c.source_type, c.source_title FROM ingredient_claims c")
    claims = {}
    for iid, prop, direction, strength, confidence, st, stitle in cur.fetchall():
        claims.setdefault(iid, []).append({
            "property": prop, "direction": direction, "strength": strength,
            "confidence": confidence, "source_type": st or "", "source_title": (stitle or "")[:120],
        })
    out = []
    for iid, name, norm, syns in rows:
        out.append({
            "id": iid, "name": name or norm or "", "normalized": norm or "",
            "synonyms": syns or "", "claims": claims.get(iid, []),
        })
    return out


def build_prompt(batch):
    lines = []
    lines.append("Ты — косметический химик, перепроверяющий базу знаний ингредиентов.")
    lines.append("Канонические оси: hydration, barrier, irritation, sensitization, sebum, pigmentation.")
    lines.append("harm-оси (irritation/sensitization/sebum/pigmentation): direction positive = усиление вреда.")
    lines.append("benefit-оси (hydration/barrier): direction positive = польза.")
    lines.append("Для каждого ингредиента укажи только ПОДТВЕРЖДЁННЫЕ свойства по осям.")
    lines.append("Не выдумывай концентрации, исследования, ссылки, pH. Если данных недостаточно — не указывай свойство.")
    lines.append("")
    for ing in batch:
        lines.append("---")
        lines.append("INGREDIENT: " + ing["name"])
        if ing["synonyms"]:
            lines.append("SYNONYMS: " + str(ing["synonyms"])[:200])
        if ing["claims"]:
            lines.append("CURRENT CLAIMS:")
            for cl in ing["claims"][:12]:
                lines.append("  - %s %s strength=%s confidence=%s src=%s %s" % (
                    cl["property"], cl["direction"], cl["strength"], cl["confidence"],
                    cl["source_type"], cl["source_title"]))
        else:
            lines.append("CURRENT CLAIMS: (none)")
    lines.append("")
    lines.append("Верни ТОЛЬКО JSON-массив объектов (без markdown):")
    lines.append(
        '[{"name": "...", "claims": [{"axis": "hydration|barrier|irritation|sensitization|sebum|pigmentation", '
        '"direction": "positive|negative", "strength": 0..1, "confidence": 0..1, '
        '"evidence_type": "confirmed|likely|insufficient|contradicted|context_dependent", "rationale": "..."}], '
        '"conflicts": ["..."], "uncertainties": ["..."], "recommendation": "keep|add|correct|needs_review"}]')
    return "\n".join(lines)


def parse_response(content):
    s = (content or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", s)
    if fence:
        s = fence.group(1).strip()
    start = s.find("[")
    if start == -1:
        return None
    end = s.rfind("]")
    if end <= start:
        return None
    try:
        obj = json.loads(s[start:end + 1])
        return obj if isinstance(obj, list) else None
    except Exception:
        return None


def validate_record(rec):
    if not isinstance(rec, dict):
        return None
    name = str(rec.get("name") or "").strip()
    if not name:
        return None
    claims = rec.get("claims") or []
    valid = []
    for cl in claims:
        if not isinstance(cl, dict):
            continue
        axis = str(cl.get("axis") or "").strip().lower()
        direction = str(cl.get("direction") or "").strip().lower()
        if axis not in CANONICAL_AXES or direction not in ("positive", "negative"):
            continue
        try:
            strength = float(cl.get("strength"))
            confidence = float(cl.get("confidence"))
        except (TypeError, ValueError):
            continue
        if not 0.0 <= strength <= 1.0 or not 0.0 <= confidence <= 1.0:
            continue
        valid.append({
            "axis": axis, "direction": direction, "strength": round(strength, 3),
            "confidence": round(confidence, 3),
            "evidence_type": str(cl.get("evidence_type") or "likely").strip().lower(),
            "rationale": str(cl.get("rationale") or "")[:300],
        })
    return {
        "name": name, "claims": valid,
        "conflicts": [str(x)[:200] for x in (rec.get("conflicts") or [])],
        "uncertainties": [str(x)[:200] for x in (rec.get("uncertainties") or [])],
        "recommendation": str(rec.get("recommendation") or "keep").strip().lower(),
    }


def call_deepseek(prompt):
    load_dotenv(BACKEND / ".env")
    import httpx
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    api_url = os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
    if not api_key:
        return None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = httpx.post(
                api_url,
                headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                json={"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.1, "max_tokens": 4000},
                timeout=TIMEOUT_SEC,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage") or {}
                return {"content": content, "usage": usage}
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(min(2 ** attempt, 30) + random.random())
                continue
            return None
        except Exception:
            time.sleep(min(2 ** attempt, 30) + random.random())
    return None


def existing_canonical(ing):
    ex = {}
    for cl in ing["claims"]:
        axis, direction = canonicalize_effect(cl["property"], cl["direction"])
        if axis is None:
            continue
        ex.setdefault(axis, []).append({
            "direction": direction, "strength": cl["strength"], "confidence": cl["confidence"],
            "source_type": cl["source_type"], "source_title": cl["source_title"],
        })
    return ex


def decide_actions(ing, rec):
    ex = existing_canonical(ing)
    actions = []
    for cl in rec["claims"]:
        axis = cl["axis"]
        direction = cl["direction"]
        existing = ex.get(axis, [])
        same_dir = [e for e in existing if e["direction"] == direction]
        opp_dir = [e for e in existing if e["direction"] != direction]
        if cl["evidence_type"] == "insufficient" or cl["confidence"] < 0.5:
            action, detail = "skip", "insufficient/low-confidence"
        elif opp_dir and cl["evidence_type"] == "confirmed" and cl["confidence"] >= 0.7:
            action, detail = "correct", "contradicts %d opposite-direction claims" % len(opp_dir)
        elif opp_dir:
            action, detail = "needs_review", "conflicts with existing direction"
        elif not same_dir:
            action, detail = "add", "new axis"
        else:
            top = max(same_dir, key=lambda e: e["confidence"])
            if abs(top["strength"] - cl["strength"]) > 0.3 or abs(top["confidence"] - cl["confidence"]) > 0.3:
                action, detail = "correct", "strength/confidence differs"
            else:
                action, detail = "skip", "agrees with existing"
        actions.append({"axis": axis, "direction": direction, "action": action,
                        "detail": detail, "claim": cl})
    return actions


def apply_actions(conn, ing, actions):
    cur = conn.cursor()
    applied = 0
    for a in actions:
        if a["action"] not in ("add", "correct"):
            continue
        cl = a["claim"]
        h = _hash(ing["id"], cl["axis"], cl["direction"], PROMPT_VERSION)
        cur.execute("SELECT id FROM ingredient_claims WHERE source_hash=%s", (h,))
        if cur.fetchone():
            continue
        cur.execute(
            "INSERT INTO ingredient_claims (ingredient_id, property_name, direction, strength, confidence, "
            "evidence_level, source_type, source_title, researched_at, research_version, source_hash) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (ing["id"], cl["axis"], cl["direction"], cl["strength"], cl["confidence"],
             "moderate" if cl["evidence_type"] == "confirmed" else "low",
             SOURCE_TYPE, cl["rationale"][:300], _now(), PROMPT_VERSION, h),
        )
        applied += 1
    conn.commit()
    return applied


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"processed": [], "failed": {},
            "stats": {"batches": 0, "applied": 0, "needs_review": 0, "requests": 0, "tokens": 0}}


def save_state(state):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    args = sys.argv[1:]
    if "--status" in args:
        st = load_state()
        print(json.dumps({"processed": len(st["processed"]), "stats": st["stats"]}, ensure_ascii=False))
        return 0
    limit = None
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    all_ing = load_ingredients(conn)
    state = load_state()
    processed_ids = set(state["processed"])
    todo = [ing for ing in all_ing if ing["id"] not in processed_ids]
    if limit:
        todo = todo[:limit]
    print("total=%d todo=%d processed=%d" % (len(all_ing), len(todo), len(processed_ids)), flush=True)
    for i in range(0, len(todo), BATCH_SIZE):
        batch = todo[i:i + BATCH_SIZE]
        prompt = build_prompt(batch)
        result = call_deepseek(prompt)
        state["stats"]["requests"] += 1
        if result is None:
            for ing in batch:
                state["failed"][str(ing["id"])] = "api error"
            save_state(state)
            print("batch %d FAILED" % (i // BATCH_SIZE), flush=True)
            continue
        state["stats"]["tokens"] += (result["usage"].get("total_tokens") or 0)
        records = parse_response(result["content"])
        if records is None:
            for ing in batch:
                state["failed"][str(ing["id"])] = "unparseable"
            save_state(state)
            print("batch %d UNPARSEABLE" % (i // BATCH_SIZE), flush=True)
            continue
        by_name = {}
        for rec in records:
            v = validate_record(rec)
            if v:
                by_name[v["name"].lower()] = v
        for ing in batch:
            rec = by_name.get(ing["name"].lower()) or by_name.get(ing["normalized"].lower())
            if rec is None:
                state["failed"][str(ing["id"])] = "missing in response"
                continue
            actions = decide_actions(ing, rec)
            n_applied = apply_actions(conn, ing, actions)
            state["stats"]["applied"] += n_applied
            state["stats"]["needs_review"] += sum(1 for a in actions if a["action"] == "needs_review")
            state["processed"].append(ing["id"])
            with open(AUDIT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ingredient_id": ing["id"], "name": ing["name"],
                    "actions": [{k: a[k] for k in ("axis", "direction", "action", "detail")} for a in actions],
                    "applied": n_applied, "recommendation": rec["recommendation"],
                    "conflicts": rec["conflicts"], "uncertainties": rec["uncertainties"],
                    "model": MODEL, "prompt_version": PROMPT_VERSION, "ts": _now(),
                }, ensure_ascii=False) + "\n")
        state["stats"]["batches"] += 1
        save_state(state)
        print("batch %d done (applied=%d, needs_review=%d)" % (
            i // BATCH_SIZE, state["stats"]["applied"], state["stats"]["needs_review"]), flush=True)
        time.sleep(1.0)
    print("COMPLETE stats=%s" % json.dumps(state["stats"]), flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())




