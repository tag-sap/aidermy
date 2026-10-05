# calibration_service.py
# AI Calibration / Calibration Auditor — внутренний QA-слой поверх deterministic Score Engine.
# НЕ является production scoring engine и НЕ меняет production score.
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
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
            updated_at TEXT,
            started_at TEXT,
            completed_at TEXT,
            error TEXT,
            params TEXT,
            product_count INTEGER,
            profile_count INTEGER,
            case_count INTEGER,
            total_cases INTEGER,
            processed_cases INTEGER,
            current_batch INTEGER,
            total_batches INTEGER,
            ai_request_count INTEGER,
            cache_hits INTEGER,
            cache_misses INTEGER,
            ai_references_generated INTEGER,
            errors INTEGER,
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
            created_at TEXT,
            status TEXT,
            base_version TEXT,
            metrics TEXT,
            calibration_run TEXT,
            changed_params TEXT
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
    _ensure_columns(conn, "calibration_runs", _RUN_EXTRA_COLUMNS)
    _ensure_columns(conn, "calibration_candidates", _CANDIDATE_EXTRA_COLUMNS)
    conn.commit()
    conn.close()


_RUN_EXTRA_COLUMNS = [
    ("updated_at", "TEXT"),
    ("started_at", "TEXT"),
    ("completed_at", "TEXT"),
    ("error", "TEXT"),
    ("params", "TEXT"),
    ("total_cases", "INTEGER"),
    ("processed_cases", "INTEGER"),
    ("current_batch", "INTEGER"),
    ("total_batches", "INTEGER"),
    ("ai_references_generated", "INTEGER"),
    ("errors", "INTEGER"),
]

_CANDIDATE_EXTRA_COLUMNS = [
    ("status", "TEXT"),
    ("base_version", "TEXT"),
    ("metrics", "TEXT"),
    ("calibration_run", "TEXT"),
    ("changed_params", "TEXT"),
]


def _ensure_columns(conn, table: str, columns: List[tuple]) -> None:
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, typ in columns:
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")


def _run_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_conn():
    conn = _db()
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def create_run(params: Dict[str, Any]) -> str:
    """Создаёт calibration_run со статусом queued и возвращает run_key."""
    ensure_tables()
    conn = _run_conn()
    key = _run_key()
    conn.execute(
        "INSERT INTO calibration_runs (run_key, created_at, updated_at, status, params, model, "
        "scoring_config_version, calibration_profiles_version, prompt_version) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (key, _now(), _now(), "queued", json.dumps(params, ensure_ascii=False), DEFAULT_MODEL,
         SCORING_CONFIG_VERSION, CALIBRATION_PROFILES_VERSION, CALIBRATION_PROMPT_VERSION),
    )
    conn.commit()
    conn.close()
    return key


def get_run(run_key: str) -> Optional[Dict[str, Any]]:
    ensure_tables()
    conn = _run_conn()
    row = conn.execute("SELECT * FROM calibration_runs WHERE run_key=?", (run_key,)).fetchone()
    conn.close()
    return {k: row[k] for k in row.keys()} if row is not None else None


def update_run(run_key: str, **fields) -> None:
    if not fields:
        return
    conn = _run_conn()
    cols = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE calibration_runs SET {cols} WHERE run_key=?", (*fields.values(), run_key))
    conn.commit()
    conn.close()


def latest_active_run() -> Optional[Dict[str, Any]]:
    """Последний run (для защиты от двойного нажатия / resume)."""
    conn = _run_conn()
    row = conn.execute("SELECT run_key, status, updated_at FROM calibration_runs ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return {k: row[k] for k in row.keys()} if row is not None else None


STALE_SECONDS = 120


def is_stale(run: Dict[str, Any], stale_seconds: int = STALE_SECONDS) -> bool:
    """Run 'running/queued' без heartbeat дольше stale_seconds — мёртвый worker."""
    if run.get("status") not in ("queued", "running"):
        return False
    updated = run.get("updated_at")
    if not updated:
        return False
    try:
        dt = datetime.fromisoformat(updated)
        return (datetime.now(timezone.utc) - dt).total_seconds() > stale_seconds
    except Exception:
        return False


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

def _extract_json_array(content: str) -> Optional[List[Any]]:
    """Извлекает JSON-массив из ответа AI (markdown fences / wrapped object / nested lists)."""
    if not content or not isinstance(content, str):
        return None
    cleaned = content.strip()
    m = re.search(r'```(?:json)?\s*([\s\S]*?)```', cleaned, re.DOTALL)
    if m:
        cleaned = m.group(1).strip()
    start = cleaned.find('[')
    if start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(cleaned[start:i + 1])
                        if isinstance(parsed, list):
                            return parsed
                    except Exception:
                        pass
                    break
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            for v in obj.values():
                if isinstance(v, list):
                    return v
    except Exception:
        pass
    return None


async def _ai_call(prompt: str, model: str) -> Optional[Any]:
    import httpx
    from .services import DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_MODEL_FALLBACKS
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
                          "temperature": 0.2, "max_tokens": 8000},
                    timeout=120,
                )
            if resp.status_code != 200:
                continue
            data = resp.json()
            content = (data["choices"][0]["message"]["content"] or "").strip()
            return _extract_json_array(content)
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
    on_batch: Optional[Any] = None,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """Генерирует AI reference для всех product×profile cases (batch + cache).

    Обрабатывает продукты батчами; после каждого батча сохраняет references в БД
    и вызывает on_batch(stats) для персиста прогресса lifecycle run.
    Возвращает (references_by_key, stats)."""
    ensure_tables()
    conn = _db()
    conn.execute("PRAGMA busy_timeout = 30000")
    batch_size = _estimate_batch_size(products)
    # Выход ограничивает батч: ~150 токенов на reference, max_tokens=8000.
    batch_size = min(batch_size, max(1, 8000 // max(1, len(profiles) * 150)))
    batches = [products[i:i + batch_size] for i in range(0, len(products), batch_size)]
    total_cases = len(products) * len(profiles)
    stats: Dict[str, Any] = {
        "total_batches": len(batches),
        "current_batch": 0,
        "total_cases": total_cases,
        "processed_cases": 0,
        "ai_requests": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "references_generated": 0,
        "errors": 0,
    }
    refs: Dict[str, Dict[str, Any]] = {}

    cached: Dict[str, Dict[str, Any]] = {}
    if use_cache and not force_refresh:
        for ck, ref in conn.execute("SELECT cache_key, reference FROM calibration_references").fetchall():
            try:
                cached[ck] = json.loads(ref)
            except Exception:
                pass

    have_ai = _deepseek_available()
    processed_products = 0
    for bi, batch in enumerate(batches):
        stats["current_batch"] = bi + 1
        batch_refs: Dict[str, Dict[str, Any]] = {}
        batch_misses = 0
        for p in batch:
            pv = _product_version(p)
            for pr in profiles:
                ck = reference_cache_key(p["id"], pv, pr["id"], CALIBRATION_PROMPT_VERSION, model)
                key = f'{p["id"]}:{pr["id"]}'
                if ck in cached:
                    batch_refs[key] = cached[ck]
                    stats["cache_hits"] += 1
                else:
                    batch_misses += 1
                    stats["cache_misses"] += 1

        if batch_misses > 0 and have_ai:
            prompt = _build_reference_prompt(batch, profiles)
            result = await _ai_call(prompt, model)
            stats["ai_requests"] += 1
            if isinstance(result, list):
                by_pair: Dict[str, Dict[str, Any]] = {}
                for raw in result:
                    nr = _norm_ref(raw)
                    if nr is not None:
                        by_pair[f'{nr["product_id"]}:{nr["profile_id"]}'] = nr
                for p in batch:
                    pv = _product_version(p)
                    for pr in profiles:
                        key = f'{p["id"]}:{pr["id"]}'
                        if key in batch_refs:
                            continue
                        nr = by_pair.get(key)
                        if nr is None:
                            stats["errors"] += 1
                            continue
                        batch_refs[key] = nr
                        ck = reference_cache_key(p["id"], pv, pr["id"], CALIBRATION_PROMPT_VERSION, model)
                        conn.execute(
                            "INSERT OR REPLACE INTO calibration_references "
                            "(cache_key, product_id, profile_id, reference, model, prompt_version, created_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (ck, p["id"], pr["id"], json.dumps(nr, ensure_ascii=False), model,
                             CALIBRATION_PROMPT_VERSION, datetime.now(timezone.utc).isoformat()),
                        )
                        stats["references_generated"] += 1
                conn.commit()
            else:
                stats["errors"] += 1

        for key, nr in batch_refs.items():
            refs[key] = nr
        processed_products += len(batch)
        stats["processed_cases"] = processed_products * len(profiles)

        if on_batch is not None:
            snapshot = dict(stats)
            if asyncio.iscoroutinefunction(on_batch):
                await on_batch(snapshot)
            else:
                on_batch(snapshot)

    conn.close()
    return refs, stats

def run_score_engine(cases: List[Dict[str, Any]], config_override: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Прогоняет ВСЕ cases через реальный production Score Engine (DecisionEngine)."""
    from .decision_engine import DecisionEngine
    from .scoring_config import SATURATION_SCALE

    override = config_override or {}
    saturation = float(override.get("saturation_scale", SATURATION_SCALE))
    engine = DecisionEngine()
    try:
        from .ingredient_repository import IngredientRepository
        knowledge = IngredientRepository().get_canonical_knowledge_map()
    except Exception:
        knowledge = None
    results: List[Dict[str, Any]] = []
    for case in cases:
        p = case["product"]
        pr = case["profile"]
        structured = dict(pr["structured"])
        try:
            res = engine.analyze(
                p["name"], p.get("ingredients") or "", {"structured": structured},
                skin_type=structured.get("skin_type") or "Нормальная",
                knowledge=knowledge,
                saturation_scale=saturation,
            )
        except TypeError:
            res = engine.analyze(
                p["name"], p.get("ingredients") or "", {"structured": structured},
                skin_type=structured.get("skin_type") or "Нормальная",
                knowledge=knowledge,
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
                "interaction_breakdown": res.get("interaction_breakdown") or [],
                "interaction_scoring_version": res.get("interaction_scoring_version"),
                "saturation_scale": saturation,
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


# ---------------------------------------------------------------------------
# Компактная диагностическая сводка (summary) + per-case persistence.
# Не меняет Score Engine / audit / drift — только читает и форматирует.
# ---------------------------------------------------------------------------

_SKIN_TYPE_LABELS = {
    "normal": "Нормальная",
    "dry": "Сухая",
    "oily": "Жирная",
    "combination": "Комбинированная",
    "dehydrated": "Обезвоженная",
    "sensitive": "Чувствительная",
}

_CONCERN_LABELS = {
    "reactive_skin": "реактивная кожа",
    "irritation_prone": "склонность к раздражению",
    "redness": "покраснение",
    "rosacea": "розацеа",
    "acne_general": "акне",
    "enlarged_pores": "расширенные поры",
    "inflammatory_acne": "воспалительное акне",
    "impaired_barrier": "нарушенный барьер",
    "scaling": "шелушение",
    "dehydrated_skin": "обезвоженность",
    "pigmentation": "пигментация",
    "post_acne_pigmentation": "пигментация после акне",
    "dullness": "тусклость",
    "fine_lines": "морщины",
}


def _profile_label(profile_id: str) -> str:
    p = profile_by_id(profile_id)
    return p["label"] if p else profile_id


def _drift_group_label(group: str) -> str:
    if group.startswith("concern:"):
        cid = group[len("concern:"):]
        return _CONCERN_LABELS.get(cid, cid)
    if group.startswith("cat:"):
        return group[len("cat:"):]
    return _SKIN_TYPE_LABELS.get(group, group)


def _drift_verdict(signed_error: float) -> str:
    if signed_error >= 5:
        return "Завышает"
    if signed_error <= -5:
        return "Занижает"
    return "OK"


def _overall_status(audit_m: Dict[str, Any], drift: List[Dict[str, Any]]) -> str:
    mse = abs(audit_m.get("mean_signed_error") or 0)
    top_drift = max([abs(g.get("average_drift") or 0) for g in drift], default=0)
    if mse >= 15 or top_drift >= 25:
        return "СИЛЬНЫЙ ДРЕЙФ"
    if mse >= 5 or drift:
        return "ЕСТЬ СИСТЕМНЫЙ ДРЕЙФ"
    return "ХОРОШАЯ КАЛИБРОВКА"


def persist_calibration_cases(run_key: str, results: List[Dict[str, Any]],
                              references: Dict[str, Dict[str, Any]]) -> int:
    """Сохраняет per-case результаты в calibration_cases (для summary/аудита)."""
    ensure_tables()
    conn = _run_conn()
    n = 0
    for r in results:
        p = r["product"]
        pr = r["profile"]
        key = f'{p["id"]}:{pr["id"]}'
        ref = references.get(key)
        if ref is None:
            continue
        score = int(r.get("score") or 0)
        est = int(ref.get("estimate", 50))
        rmin = int(ref.get("range_min", 0))
        rmax = int(ref.get("range_max", 100))
        drift = score - est
        inside = 1 if rmin <= score <= rmax else 0
        conn.execute(
            "INSERT OR REPLACE INTO calibration_cases "
            "(run_key, product_id, profile_id, reference, score, verdict, trace, drift, inside_range) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_key, p["id"], pr["id"], json.dumps(ref, ensure_ascii=False),
             score, r.get("verdict") or "", json.dumps(r.get("trace") or {}, ensure_ascii=False),
             drift, inside),
        )
        n += 1
    conn.commit()
    conn.close()
    return n


def backfill_calibration_cases(run_key: str) -> int:
    """Заполняет calibration_cases для completed run по кэшированным references (БЕЗ AI)."""
    run = get_run(run_key)
    if run is None:
        return 0
    params = json.loads(run["params"]) if run.get("params") else {}
    product_limit = int(params.get("product_limit", 500))
    profile_ids = params.get("profile_ids") or []
    profiles = [p for p in CALIBRATION_PROFILES if not profile_ids or p["id"] in profile_ids]
    products = load_products(limit=product_limit)
    cases = build_cases(products, profiles)
    references, _stats = asyncio.run(generate_ai_reference_batched(
        products, profiles, model=DEFAULT_MODEL, use_cache=True, force_refresh=False,
    ))
    results = run_score_engine(cases)
    return persist_calibration_cases(run_key, results, references)


def _product_name(product_id: int) -> str:
    try:
        from .database import PRODUCTS_DB
        conn = get_connection(PRODUCTS_DB)
        row = conn.execute("SELECT name FROM products WHERE id=?", (product_id,)).fetchone()
        conn.close()
        name = (row["name"] or "").replace("\n", " ").strip() if row else ""
        return name or f"#{product_id}"
    except Exception:
        return f"#{product_id}"


def _top_problematic_cases(run_key: str, limit: int = 5) -> List[Dict[str, Any]]:
    """TOP-N кейсов с максимальным |drift| (только те, где есть reference)."""
    ensure_tables()
    conn = _run_conn()
    rows = conn.execute(
        "SELECT product_id, profile_id, reference, score, drift FROM calibration_cases "
        "WHERE run_key=? AND reference IS NOT NULL ORDER BY ABS(drift) DESC LIMIT ?",
        (run_key, limit),
    ).fetchall()
    conn.close()
    out = []
    for row in rows:
        try:
            ref = json.loads(row["reference"]) if row["reference"] else {}
        except Exception:
            ref = {}
        out.append({
            "product_id": row["product_id"],
            "profile_id": row["profile_id"],
            "product": _product_name(row["product_id"]),
            "profile": _profile_label(row["profile_id"]),
            "estimate": ref.get("estimate"),
            "range_min": ref.get("range_min"),
            "range_max": ref.get("range_max"),
            "score": row["score"],
            "difference": row["drift"],
        })
    return out


def build_calibration_summary(run_key: str) -> Optional[Dict[str, Any]]:
    """Компактная диагностическая сводка для completed run (читает metrics + cases)."""
    run = get_run(run_key)
    if run is None:
        return None
    metrics = json.loads(run["metrics"]) if run.get("metrics") else {}
    audit_m = metrics.get("audit") or {}
    drift = metrics.get("drift") or []

    verdict = {
        "cases": audit_m.get("case_count") or run.get("case_count") or 0,
        "mae": audit_m.get("mae"),
        "median_error": audit_m.get("median_abs_error"),
        "mean_signed_error": audit_m.get("mean_signed_error"),
        "coverage_pct": round((audit_m.get("range_coverage") or 0) * 100, 1),
        "overestimated_pct": round((audit_m.get("overestimation_rate") or 0) * 100, 1),
        "underestimated_pct": round((audit_m.get("underestimation_rate") or 0) * 100, 1),
    }

    drift_top = [
        {
            "group": _drift_group_label(g.get("group", "")),
            "cases": g.get("cases"),
            "signed_error": g.get("average_drift"),
            "verdict": _drift_verdict(g.get("average_drift") or 0),
        }
        for g in drift[:5]
    ]

    return {
        "run_key": run_key,
        "status": run.get("status"),
        "overall_status": _overall_status(audit_m, drift),
        "verdict": verdict,
        "drift_groups": drift_top,
        "top_cases": _top_problematic_cases(run_key, limit=5),
    }


# ---------------------------------------------------------------------------
# Case drill-down + Candidate (sandbox config) + production apply/rollback.
# ---------------------------------------------------------------------------

_AXIS_ORDER = ["hydration", "barrier", "irritation", "sensitization", "sebum", "pigmentation"]


def _axis_breakdown(trace: Dict[str, Any]) -> List[Dict[str, Any]]:
    dims = trace.get("dimensions") or {}
    weights = trace.get("priorities") or {}
    s = trace.get("saturation_scale")
    if s is None:
        try:
            from .scoring_config_store import get_production_saturation_scale
            s = get_production_saturation_scale()
        except Exception:
            s = 1.5
    try:
        s = float(s) or 1.5
    except Exception:
        s = 1.5
    out = []
    for axis in _AXIS_ORDER:
        raw = float(dims.get(axis, 0.0) or 0.0)
        weight = float(weights.get(axis, 0.0) or 0.0)
        saturation_factor = math.tanh(raw / s)
        out.append({
            "axis": axis,
            "raw": round(raw, 3),
            "weight": round(weight, 3),
            "weighted": round(raw * weight, 3),
            "saturation_factor": round(saturation_factor, 4),
            "contribution": round(saturation_factor * weight, 4),
        })
    return out


def _product_category(product_id: int) -> str:
    try:
        from .database import PRODUCTS_DB
        conn = get_connection(PRODUCTS_DB)
        row = conn.execute(
            "SELECT subcategory, taxonomy_category, category FROM products WHERE id=?", (product_id,)
        ).fetchone()
        conn.close()
        return (row["subcategory"] or row["taxonomy_category"] or row["category"] or "") if row else ""
    except Exception:
        return ""


def _profile_structured(profile_id: str) -> Dict[str, Any]:
    p = profile_by_id(profile_id)
    return (p.get("structured") or {}) if p else {}


def get_case_detail(run_key: str, product_id: int, profile_id: str) -> Optional[Dict[str, Any]]:
    ensure_tables()
    conn = _run_conn()
    row = conn.execute(
        "SELECT product_id, profile_id, reference, score, verdict, trace, drift, inside_range "
        "FROM calibration_cases WHERE run_key=? AND product_id=? AND profile_id=?",
        (run_key, product_id, profile_id),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    try:
        ref = json.loads(row["reference"]) if row["reference"] else {}
    except Exception:
        ref = {}
    try:
        trace = json.loads(row["trace"]) if row["trace"] else {}
    except Exception:
        trace = {}
    axis = _axis_breakdown(trace)
    total_weight = sum(a["weight"] for a in axis) or 1.0
    weighted_total = sum(a["contribution"] for a in axis)
    return {
        "run_key": run_key,
        "product_id": row["product_id"],
        "profile_id": row["profile_id"],
        "product": _product_name(row["product_id"]),
        "profile": _profile_label(row["profile_id"]),
        "category": _product_category(row["product_id"]),
        "reference": {
            "estimate": ref.get("estimate"),
            "range_min": ref.get("range_min"),
            "range_max": ref.get("range_max"),
            "confidence": ref.get("confidence"),
            "positive_drivers": ref.get("positive_drivers") or [],
            "negative_drivers": ref.get("negative_drivers") or [],
            "reason": ref.get("reason") or "",
        },
        "score": row["score"],
        "verdict": row["verdict"],
        "drift": row["drift"],
        "inside_range": row["inside_range"],
        "axis_breakdown": axis,
        "final_aggregation": {
            "saturation_scale": float(trace.get("saturation_scale") or 1.5),
            "weighted_total": round(weighted_total, 4),
            "sum_weights": round(total_weight, 3),
            "final_score": int(row["score"] or 0),
            "verdict": row["verdict"],
        },
        "profile_structured": _profile_structured(row["profile_id"]),
        "interaction_breakdown": trace.get("interaction_breakdown") or [],
        "positive_factors": trace.get("positive_factors") or [],
        "negative_factors": trace.get("negative_factors") or [],
        "hard_flags": trace.get("hard_flags") or [],
    }


def list_candidates() -> List[Dict[str, Any]]:
    ensure_tables()
    conn = _run_conn()
    rows = conn.execute("SELECT * FROM calibration_candidates ORDER BY id DESC").fetchall()
    conn.close()
    out = []
    for row in rows:
        d = {k: row[k] for k in row.keys()}
        for f in ("config", "metrics", "changed_params"):
            raw = d.get(f)
            if isinstance(raw, str) and raw:
                try:
                    d[f] = json.loads(raw)
                except Exception:
                    pass
            elif raw is None:
                d[f] = {} if f == "config" else ([] if f == "changed_params" else None)
        out.append(d)
    return out


def create_candidate(name: str, config: Dict[str, Any], calibration_run: Optional[str] = None,
                     base_version: Optional[str] = None,
                     changed_params: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    ensure_tables()
    conn = _run_conn()
    cur = conn.execute(
        "INSERT INTO calibration_candidates (name, config, created_at, status, base_version, calibration_run, changed_params) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, json.dumps(config, ensure_ascii=False), _now(), "Draft",
         base_version, calibration_run, json.dumps(changed_params or [], ensure_ascii=False)),
    )
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return get_candidate(cid)


def get_candidate(candidate_id: int) -> Optional[Dict[str, Any]]:
    ensure_tables()
    conn = _run_conn()
    row = conn.execute("SELECT * FROM calibration_candidates WHERE id=?", (candidate_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    d = {k: row[k] for k in row.keys()}
    for f in ("config", "metrics", "changed_params"):
        raw = d.get(f)
        if isinstance(raw, str) and raw:
            try:
                d[f] = json.loads(raw)
            except Exception:
                pass
        elif raw is None:
            d[f] = {} if f == "config" else ([] if f == "changed_params" else None)
    return d


def update_candidate_status(candidate_id: int, status: str,
                            metrics: Optional[Dict[str, Any]] = None) -> None:
    conn = _run_conn()
    if metrics is not None:
        conn.execute("UPDATE calibration_candidates SET status=?, metrics=? WHERE id=?",
                     (status, json.dumps(metrics, ensure_ascii=False), candidate_id))
    else:
        conn.execute("UPDATE calibration_candidates SET status=? WHERE id=?", (status, candidate_id))
    conn.commit()
    conn.close()


def compute_changed_params(production_config: Dict[str, Any],
                           candidate_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    changed = []
    for k in sorted(set(list(production_config.keys()) + list(candidate_config.keys()))):
        pv = production_config.get(k)
        cv = candidate_config.get(k)
        if pv != cv:
            changed.append({"param": k, "production": pv, "candidate": cv})
    return changed


def run_candidate_comparison(run_key: str, candidate_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Прогоняет candidate на том же наборе cases/references (БЕЗ AI) и сравнивает с production."""
    run = get_run(run_key)
    if run is None:
        return None
    params = json.loads(run["params"]) if run.get("params") else {}
    product_limit = int(params.get("product_limit", 500))
    profile_ids = params.get("profile_ids") or []
    profiles = [p for p in CALIBRATION_PROFILES if not profile_ids or p["id"] in profile_ids]
    products = load_products(limit=product_limit)
    cases = build_cases(products, profiles)
    references, _stats = asyncio.run(generate_ai_reference_batched(
        products, profiles, model=DEFAULT_MODEL, use_cache=True, force_refresh=False,
    ))
    prod = run_score_engine(cases)
    cand = run_score_engine(cases, candidate_config)
    cmp = compare(prod, cand, references)
    drift_prod = find_drift(prod, references)
    drift_cand = find_drift(cand, references)

    prod_by_key = {f'{r["product"]["id"]}:{r["profile"]["id"]}': r for r in prod}
    cand_by_key = {f'{r["product"]["id"]}:{r["profile"]["id"]}': r for r in cand}
    top = []
    for key, pr in prod_by_key.items():
        ref = references.get(key)
        if ref is None:
            continue
        pd = pr["score"] - int(ref.get("estimate", 50))
        cr = cand_by_key.get(key)
        top.append({
            "key": key,
            "product": (pr["product"].get("name") or "").replace("\n", " ").strip(),
            "profile": _profile_label(pr["profile"]["id"]),
            "estimate": ref.get("estimate"),
            "range_min": ref.get("range_min"),
            "range_max": ref.get("range_max"),
            "prod_score": pr["score"],
            "cand_score": cr["score"] if cr else None,
            "prod_drift": pd,
            "cand_drift": (cr["score"] - int(ref.get("estimate", 50))) if cr else None,
        })
    top.sort(key=lambda x: -abs(x["prod_drift"]))
    return {
        "production": cmp["production"],
        "candidate": cmp["candidate"],
        "improved_cases": cmp["improved_cases"],
        "worsened_cases": cmp["worsened_cases"],
        "cohorts": cmp["cohorts"],
        "drift_prod": drift_prod,
        "drift_cand": drift_cand,
        "top_cases": top[:5],
    }

