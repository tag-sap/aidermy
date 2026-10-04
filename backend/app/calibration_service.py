# calibration_service.py
# AI Calibration / Calibration Auditor — внутренний QA-слой поверх deterministic Score Engine.
# НЕ является production scoring engine и НЕ меняет production score.
from __future__ import annotations

import asyncio
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .calibration_profiles import CALIBRATION_PROFILES, CALIBRATION_PROFILES_VERSION, profile_by_id
from .database import AIDERMY_DB, get_connection, get_product_by_id
from .scoring_config import SCORING_CONFIG_VERSION

CALIBRATION_PROMPT_VERSION = "1.0"
DEFAULT_MODEL = "deepseek-chat"


def _db():
    return get_connection(AIDERMY_DB)


def ensure_tables() -> None:
    conn = _db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS calibration_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_key TEXT UNIQUE,
            created_at TEXT,
            product_count INTEGER,
            profile_count INTEGER,
            case_count INTEGER,
            ai_request_count INTEGER,
            cache_hits INTEGER,
            cache_misses INTEGER,
            model TEXT,
            scoring_config_version TEXT,
            calibration_profiles_version TEXT,
            prompt_version TEXT,
            candidate_config TEXT,
            metrics TEXT,
            status TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS calibration_references (
            cache_key TEXT PRIMARY KEY,
            product_id INTEGER,
            profile_id TEXT,
            reference TEXT,
            model TEXT,
            prompt_version TEXT,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS calibration_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_key TEXT,
            product_id INTEGER,
            profile_id TEXT,
            reference TEXT,
            score INTEGER,
            verdict TEXT,
            trace TEXT,
            drift INTEGER,
            inside_range INTEGER,
            UNIQUE(run_key, product_id, profile_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS calibration_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            config TEXT,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS golden_calibration_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT,
            product_id INTEGER,
            profile_id TEXT,
            min_score INTEGER,
            max_score INTEGER,
            UNIQUE(product_id, profile_id)
        )
    """)
    conn.commit()
    conn.close()


def reference_cache_key(product_id: int, product_version: str, profile_id: str,
                        prompt_version: str, model: str) -> str:
    raw = f"{product_id}|{product_version}|{profile_id}|{prompt_version}|{model}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _product_version(product: Dict[str, Any]) -> str:
    ing = (product.get("ingredients") or "").strip()
    return hashlib.sha256(ing.encode("utf-8")).hexdigest()[:12]


def build_cases(products: List[Dict[str, Any]], profiles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{"product": p, "profile": pr} for p in products for pr in profiles]


def load_products(limit: int = 500, categories: Optional[List[str]] = None,
                  random_seed: Optional[int] = None) -> List[Dict[str, Any]]:
    """Загружает canonical products (is_canonical=1, с INCI) из products.db."""
    from .database import PRODUCTS_DB
    conn = get_connection(PRODUCTS_DB)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(products)").fetchall()]
    sql = "SELECT * FROM products WHERE is_canonical = 1 AND ingredients IS NOT NULL AND ingredients != ''"
    params: List[Any] = []
    if categories:
        sql += " AND subcategory IN (" + ",".join("?" * len(categories)) + ")"
        params = list(categories)
    sql += " ORDER BY id LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    products = []
    for row in rows:
        d = dict(zip(cols, row))
        cat = d.get("subcategory") or d.get("taxonomy_category") or d.get("category") or ""
        products.append({
            "id": d.get("id"),
            "name": (d.get("name") or "").replace("\n", " ").strip(),
            "brand": d.get("brand") or "",
            "category": cat,
            "ingredients": d.get("ingredients") or "",
        })
    if random_seed is not None:
        import random as _r
        _r.seed(random_seed)
        _r.shuffle(products)
    return products
def _estimate_batch_size(products: List[Dict[str, Any]], target_chars: int = 14000) -> int:
    sizes = [len(p.get("ingredients") or "") for p in products]
    if not sizes:
        return 1
    avg = sum(sizes) / len(sizes)
    per_case = avg + 120
    return max(1, min(int(target_chars / per_case), len(products)))


def _build_reference_prompt(products: List[Dict[str, Any]], profiles: List[Dict[str, Any]]) -> str:
    prof_lines = []
    for pr in profiles:
        st = pr["structured"]
        prof_lines.append(
            f'{pr["id"]}: тип={st["skin_type"]}, concerns={",".join(st.get("concerns") or []) or "-"}, '
            f'therapy={[t["id"] for t in st.get("therapy") or []] or "-"}, '
            f'procedures={[p["id"] for p in st.get("procedures") or []] or "-"}'
        )
    prod_lines = []
    for p in products:
        prod_lines.append(
            f'P{p["id"]}: {p["name"]} | brand={p.get("brand") or "-"} | category={p.get("category") or "-"}\n'
            f'  INCI: {(p.get("ingredients") or "")[:600]}'
        )
    return (
        "Ты — независимый эксперт по совместимости косметики. Оцени ОЖИДАЕМУЮ совместимость "
        "каждого продукта с каждым профилем (0-100), исходя ТОЛЬКО из состава (INCI), категории и профиля. "
        "Это независимая референс-оценка, НЕ часть production-алгоритма.\n\n"
        "ПРОФИЛИ:\n" + "\n".join(prof_lines) + "\n\n"
        "ПРОДУКТЫ:\n" + "\n\n".join(prod_lines) + "\n\n"
        "Правила: оценивай совместимость именно С ЭТИМ профилем; не выдумывай ингредиенты; "
        "не давай медицинских диагнозов; используй только переданные INCI/категорию/профиль. "
        "Верни ТОЛЬКО JSON-массив (без markdown):\n"
        '[{"product_id": <число>, "profile_id": "PXX", "range_min": <0-100>, "range_max": <0-100>, '
        '"estimate": <0-100>, "confidence": <0..1>, "positive_drivers": [..], "negative_drivers": [..], '
        '"reason": "..."}, ...]\n'
        "Для КАЖДОЙ пары product×profile верни ОДИН элемент массива."
    )

async def _ai_call(prompt: str, model: str) -> Optional[Any]:
    import httpx
    from .services import DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_MODEL_FALLBACKS, extract_json_from_response
    if not DEEPSEEK_API_KEY:
        return None
    models = [model] + [m for m in DEEPSEEK_MODEL_FALLBACKS if m != model]
    for m in models:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    DEEPSEEK_API_URL,
                    headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                    json={"model": m, "messages": [{"role": "user", "content": prompt}],
                          "temperature": 0.2, "max_tokens": 4000},
                    timeout=120,
                )
            if resp.status_code != 200:
                continue
            data = resp.json()
            content = (data["choices"][0]["message"]["content"] or "").strip()
            return extract_json_from_response(content)
        except Exception:
            continue
    return None


def _norm_ref(r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        est = int(r.get("estimate", 50))
        return {
            "product_id": int(r.get("product_id")),
            "profile_id": str(r.get("profile_id")),
            "range_min": max(0, min(100, int(r.get("range_min", est)))),
            "range_max": max(0, min(100, int(r.get("range_max", est)))),
            "estimate": max(0, min(100, est)),
            "confidence": max(0.0, min(1.0, float(r.get("confidence", 0.5)))),
            "positive_drivers": list(r.get("positive_drivers") or []),
            "negative_drivers": list(r.get("negative_drivers") or []),
            "reason": str(r.get("reason") or ""),
        }
    except Exception:
        return None


def _deepseek_available() -> bool:
    try:
        from .services import DEEPSEEK_API_KEY
        return bool(DEEPSEEK_API_KEY)
    except Exception:
        return False


async def generate_ai_reference_batched(
    products: List[Dict[str, Any]],
    profiles: List[Dict[str, Any]],
    model: str = DEFAULT_MODEL,
    use_cache: bool = True,
    force_refresh: bool = False,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """Генерирует AI reference для всех product×profile cases (batch + cache).

    Возвращает (references_by_key, stats)."""
    ensure_tables()
    conn = _db()
    batch_size = _estimate_batch_size(products)
    stats = {"batch_count": 0, "ai_requests": 0, "cache_hits": 0, "cache_misses": 0, "errors": 0}
    refs: Dict[str, Dict[str, Any]] = {}

    cached: Dict[str, Dict[str, Any]] = {}
    if use_cache:
        for ck, ref in conn.execute("SELECT cache_key, reference FROM calibration_references").fetchall():
            try:
                cached[ck] = json.loads(ref)
            except Exception:
                pass

    for p in products:
        pv = _product_version(p)
        for pr in profiles:
            ck = reference_cache_key(p["id"], pv, pr["id"], CALIBRATION_PROMPT_VERSION, model)
            key = f'{p["id"]}:{pr["id"]}'
            if not force_refresh and ck in cached:
                refs[key] = cached[ck]
                stats["cache_hits"] += 1
            else:
                stats["cache_misses"] += 1

    if stats["cache_misses"] > 0 and _deepseek_available():
        batches = [products[i:i + batch_size] for i in range(0, len(products), batch_size)]
        stats["batch_count"] = len(batches)
        for batch in batches:
            prompt = _build_reference_prompt(batch, profiles)
            result = await _ai_call(prompt, model)
            stats["ai_requests"] += 1
            if not isinstance(result, list):
                stats["errors"] += 1
                continue
            by_pair: Dict[str, Dict[str, Any]] = {}
            for raw in result:
                nr = _norm_ref(raw)
                if nr is not None:
                    by_pair[f'{nr["product_id"]}:{nr["profile_id"]}'] = nr
            for p in batch:
                pv = _product_version(p)
                for pr in profiles:
                    key = f'{p["id"]}:{pr["id"]}'
                    ck = reference_cache_key(p["id"], pv, pr["id"], CALIBRATION_PROMPT_VERSION, model)
                    if key in refs:
                        continue
                    nr = by_pair.get(key)
                    if nr is None:
                        stats["errors"] += 1
                        continue
                    refs[key] = nr
                    conn.execute(
                        "INSERT OR REPLACE INTO calibration_references "
                        "(cache_key, product_id, profile_id, reference, model, prompt_version, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (ck, p["id"], pr["id"], json.dumps(nr, ensure_ascii=False), model,
                         CALIBRATION_PROMPT_VERSION, datetime.now(timezone.utc).isoformat()),
                    )
            conn.commit()
    conn.close()
    return refs, stats

def run_score_engine(cases: List[Dict[str, Any]], config_override: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Прогоняет ВСЕ cases через реальный production Score Engine (DecisionEngine)."""
    from .decision_engine import DecisionEngine
    from .scoring_config import SATURATION_SCALE

    override = config_override or {}
    saturation = float(override.get("saturation_scale", SATURATION_SCALE))
    engine = DecisionEngine()
    results: List[Dict[str, Any]] = []
    for case in cases:
        p = case["product"]
        pr = case["profile"]
        structured = dict(pr["structured"])
        try:
            res = engine.analyze(
                p["name"], p.get("ingredients") or "", {"structured": structured},
                skin_type=structured.get("skin_type") or "Нормальная",
                saturation_scale=saturation,
            )
        except TypeError:
            res = engine.analyze(
                p["name"], p.get("ingredients") or "", {"structured": structured},
                skin_type=structured.get("skin_type") or "Нормальная",
            )
        results.append({
            "product": p,
            "profile": pr,
            "score": int(res.get("score") or 0),
            "verdict": res.get("verdict") or "",
            "trace": {
                "dimensions": res.get("dimensions") or {},
                "priorities": res.get("priorities") or {},
                "positive_factors": (res.get("positive_factors") or [])[:12],
                "negative_factors": (res.get("negative_factors") or [])[:12],
                "hard_flags": res.get("hard_flags") or [],
            },
        })
    return results


def _case_metrics(reference: Dict[str, Any], score: int) -> Dict[str, Any]:
    rmin = reference.get("range_min", 50)
    rmax = reference.get("range_max", 50)
    est = reference.get("estimate", 50)
    inside = rmin <= score <= rmax
    if inside:
        distance = 0
    else:
        distance = score - rmax if score > rmax else rmin - score
    return {
        "delta_from_estimate": score - est,
        "distance_to_range": distance,
        "inside_range": inside,
        "direction": "within" if inside else ("over" if score > rmax else "under"),
    }


def audit(results: List[Dict[str, Any]], references: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Считает метрики calibration run (reference vs deterministic score)."""
    abs_deltas: List[float] = []
    signed: List[float] = []
    inside = 0
    over = 0
    under = 0
    confs: List[float] = []
    conf_weighted: List[float] = []
    n = 0
    for r in results:
        key = f'{r["product"]["id"]}:{r["profile"]["id"]}'
        ref = references.get(key)
        if ref is None:
            continue
        n += 1
        m = _case_metrics(ref, r["score"])
        abs_deltas.append(abs(m["delta_from_estimate"]))
        signed.append(m["delta_from_estimate"])
        conf = ref.get("confidence", 0.5)
        confs.append(conf)
        conf_weighted.append(abs(m["delta_from_estimate"]) * conf)
        if m["inside_range"]:
            inside += 1
        elif m["direction"] == "over":
            over += 1
        else:
            under += 1
    if n == 0:
        return {"case_count": 0}
    return {
        "case_count": n,
        "mae": round(sum(abs_deltas) / n, 2),
        "median_abs_error": round(sorted(abs_deltas)[n // 2], 2),
        "mean_signed_error": round(sum(signed) / n, 2),
        "range_coverage": round(inside / n, 4),
        "outside_range": round((over + under) / n, 4),
        "overestimation_rate": round(over / n, 4),
        "underestimation_rate": round(under / n, 4),
        "average_confidence": round(sum(confs) / n, 4),
        "confidence_weighted_error": round(sum(conf_weighted) / n, 2),
    }

def find_drift(results: List[Dict[str, Any]], references: Dict[str, Dict[str, Any]],
               min_cases: int = 10) -> List[Dict[str, Any]]:
    """Группирует cases по skin_type/concern/category и ищет систематический drift."""
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in results:
        key = f'{r["product"]["id"]}:{r["profile"]["id"]}'
        ref = references.get(key)
        if ref is None:
            continue
        m = _case_metrics(ref, r["score"])
        r["_m"] = m
        r["_ref"] = ref
        groups[r["profile"]["structured"].get("skin_type", "?")].append(r)
        for c in r["profile"]["structured"].get("concerns") or []:
            groups[f"concern:{c}"].append(r)
        groups[f"cat:{r['product'].get('category') or '?'}"].append(r)
    out: List[Dict[str, Any]] = []
    for gname, recs in groups.items():
        if len(recs) < min_cases:
            continue
        drift = sum(r["_m"]["delta_from_estimate"] for r in recs) / len(recs)
        conf = sum((r["_ref"].get("confidence") or 0.5) for r in recs) / len(recs)
        outside = sum(1 for r in recs if not r["_m"]["inside_range"])
        if abs(drift) >= 8 and outside >= max(1, int(len(recs) * 0.3)):
            out.append({
                "group": gname,
                "cases": len(recs),
                "average_drift": round(drift, 2),
                "outside_range": outside,
                "confidence": round(conf, 3),
                "potential_cause": _suggest_cause(gname, drift),
            })
    out.sort(key=lambda x: -abs(x["average_drift"]))
    return out[:30]


def _suggest_cause(group: str, drift: float) -> str:
    g = group.lower()
    if g.startswith("concern:") and drift > 0:
        return "PROFILE_INTERACTION_UNDERWEIGHTED"
    if g.startswith("concern:") and drift < 0:
        return "PROFILE_INTERACTION_OVERWEIGHTED"
    if "sebum" in g or "oily" in g:
        return "SEBUM_AXIS_UNDERWEIGHTED" if drift > 0 else "SEBUM_AXIS_OVERWEIGHTED"
    if "sensitive" in g or "reactive" in g or "irritation" in g:
        return "PROFILE_INTERACTION_UNDERWEIGHTED" if drift > 0 else "PROFILE_INTERACTION_OVERWEIGHTED"
    if "cat:" in g:
        return "CATEGORY_ERROR"
    return "NO_SYSTEMATIC_PROBLEM"


def compare(prod_results: List[Dict[str, Any]], cand_results: List[Dict[str, Any]],
            references: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Сравнивает production vs candidate по AI reference."""
    prod_metrics = audit(prod_results, references)
    cand_metrics = audit(cand_results, references)
    prod_by_key = {f'{r["product"]["id"]}:{r["profile"]["id"]}': r for r in prod_results}
    improved = 0
    worsened = 0
    cohorts: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"prod": [], "cand": []})
    for r in cand_results:
        key = f'{r["product"]["id"]}:{r["profile"]["id"]}'
        ref = references.get(key)
        if ref is None or key not in prod_by_key:
            continue
        p = prod_by_key[key]
        pm = _case_metrics(ref, p["score"])
        cm = _case_metrics(ref, r["score"])
        if cm["inside_range"] and not pm["inside_range"]:
            improved += 1
        elif not cm["inside_range"] and pm["inside_range"]:
            worsened += 1
        st = r["profile"]["structured"].get("skin_type", "?")
        cohorts[st]["prod"].append(abs(pm["delta_from_estimate"]))
        cohorts[st]["cand"].append(abs(cm["delta_from_estimate"]))
    cohort_view = {}
    for st, v in cohorts.items():
        cohort_view[st] = {
            "prod_mae": round(sum(v["prod"]) / len(v["prod"]), 2) if v["prod"] else None,
            "cand_mae": round(sum(v["cand"]) / len(v["cand"]), 2) if v["cand"] else None,
        }
    return {
        "production": prod_metrics,
        "candidate": cand_metrics,
        "improved_cases": improved,
        "worsened_cases": worsened,
        "cohorts": cohort_view,
    }


GOLDEN_SET: List[Dict[str, Any]] = [
    {"label": "sensitive + acid peel (should be low)", "product_hint": "aha 30", "profile_id": "P24", "min_score": 0, "max_score": 45},
    {"label": "gentle cleanser + sensitive (should be ok)", "product_hint": "sensibio h2o", "profile_id": "P06", "min_score": 45, "max_score": 100},
    {"label": "moisturizer + dry barrier (should be good)", "product_hint": "ceramide", "profile_id": "P15", "min_score": 50, "max_score": 100},
]

