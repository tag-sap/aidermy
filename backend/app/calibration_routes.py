# calibration_routes.py
# Админ-панель AI Calibration Center (HTTP Basic auth, как admin_routes).
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse

from .admin_routes import verify_admin
from .calibration_profiles import CALIBRATION_PROFILES, CALIBRATION_PROFILES_VERSION
from .calibration_service import (
    CALIBRATION_PROMPT_VERSION,
    DEFAULT_MODEL,
    audit,
    build_cases,
    compare,
    ensure_tables,
    find_drift,
    generate_ai_reference_batched,
    load_products,
    run_score_engine,
)
from .scoring_config import SCORING_CONFIG_VERSION


def _run_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def _save_run(products_n: int, profiles_n: int, case_n: int, stats: Dict[str, Any],
              metrics: Dict[str, Any], candidate: Optional[Dict[str, Any]] = None) -> str:
    from .calibration_service import _db
    conn = _db()
    key = _run_key()
    conn.execute(
        "INSERT INTO calibration_runs (run_key, created_at, product_count, profile_count, case_count, "
        "ai_request_count, cache_hits, cache_misses, model, scoring_config_version, "
        "calibration_profiles_version, prompt_version, candidate_config, metrics, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (key, datetime.now(timezone.utc).isoformat(), products_n, profiles_n, case_n,
         stats.get("ai_requests", 0), stats.get("cache_hits", 0), stats.get("cache_misses", 0),
         DEFAULT_MODEL, SCORING_CONFIG_VERSION, CALIBRATION_PROFILES_VERSION, CALIBRATION_PROMPT_VERSION,
         json.dumps(candidate, ensure_ascii=False) if candidate else None,
         json.dumps(metrics, ensure_ascii=False), "completed"),
    )
    conn.commit()
    conn.close()
    return key
def setup_calibration_routes(app):
    ensure_tables()

    @app.get("/admin/calibration", response_class=HTMLResponse)
    async def calibration_panel(_: bool = Depends(verify_admin)):
        return HTMLResponse(CALIBRATION_HTML)

    @app.get("/admin/calibration/api/overview")
    async def calibration_overview(_: bool = Depends(verify_admin)):
        from .calibration_service import _db
        conn = _db()
        runs = conn.execute(
            "SELECT run_key, created_at, product_count, profile_count, case_count, ai_request_count, "
            "cache_hits, cache_misses, scoring_config_version, metrics, status "
            "FROM calibration_runs ORDER BY id DESC LIMIT 10"
        ).fetchall()
        refs_total = conn.execute("SELECT COUNT(*) FROM calibration_references").fetchone()[0]
        candidates = conn.execute("SELECT id, name, config, created_at FROM calibration_candidates ORDER BY id DESC").fetchall()
        golden = conn.execute("SELECT id, label, product_id, profile_id, min_score, max_score FROM golden_calibration_cases").fetchall()
        conn.close()
        return {
            "scoring_config_version": SCORING_CONFIG_VERSION,
            "profiles_version": CALIBRATION_PROFILES_VERSION,
            "prompt_version": CALIBRATION_PROMPT_VERSION,
            "profiles_count": len(CALIBRATION_PROFILES),
            "reference_cache_count": refs_total,
            "runs": [dict(zip(["run_key", "created_at", "product_count", "profile_count", "case_count",
                               "ai_request_count", "cache_hits", "cache_misses", "scoring_config_version",
                               "metrics", "status"], r)) for r in runs],
            "candidates": [{"id": r[0], "name": r[1], "config": r[2], "created_at": r[3]} for r in candidates],
            "golden_set": [dict(zip(["id", "label", "product_id", "profile_id", "min_score", "max_score"], r)) for r in golden],
        }

    @app.get("/admin/calibration/api/profiles")
    async def calibration_profiles(_: bool = Depends(verify_admin)):
        return {"version": CALIBRATION_PROFILES_VERSION, "profiles": CALIBRATION_PROFILES}

    @app.post("/admin/calibration/api/run")
    async def calibration_run(req: Request, _: bool = Depends(verify_admin)):
        body = await req.json()
        product_limit = int(body.get("product_limit", 500))
        use_cache = bool(body.get("use_cache", True))
        force_refresh = bool(body.get("force_refresh", False))
        candidate = body.get("candidate")
        profile_ids = body.get("profile_ids") or []

        profiles = [p for p in CALIBRATION_PROFILES if not profile_ids or p["id"] in profile_ids]
        products = load_products(limit=product_limit)
        cases = build_cases(products, profiles)

        references, stats = await generate_ai_reference_batched(
            products, profiles, model=DEFAULT_MODEL, use_cache=use_cache, force_refresh=force_refresh
        )
        prod_results = run_score_engine(cases)
        metrics = audit(prod_results, references)
        drift = find_drift(prod_results, references)

        comparison = None
        if candidate:
            cand_results = run_score_engine(cases, candidate)
            comparison = compare(prod_results, cand_results, references)

        run_key = _save_run(len(products), len(profiles), len(cases), stats, metrics, candidate)
        return {
            "run_key": run_key,
            "products": len(products),
            "profiles": len(profiles),
            "cases": len(cases),
            "ai_stats": stats,
            "metrics": metrics,
            "drift": drift,
            "comparison": comparison,
        }

    @app.post("/admin/calibration/api/candidates")
    async def create_candidate(req: Request, _: bool = Depends(verify_admin)):
        from .calibration_service import _db
        body = await req.json()
        name = str(body.get("name") or "candidate")
        config = body.get("config") or {}
        conn = _db()
        cur = conn.execute(
            "INSERT INTO calibration_candidates (name, config, created_at) VALUES (?, ?, ?)",
            (name, json.dumps(config, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
        return {"id": cur.lastrowid, "name": name}

CALIBRATION_HTML = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>AI Calibration</title>
<style>
body{font-family:system-ui,sans-serif;margin:24px;color:#1a1a1a;background:#fafafa}
h1{font-size:22px}h2{font-size:17px;margin-top:20px}
.badge{display:inline-block;padding:2px 8px;border-radius:99px;font-size:12px;font-weight:700}
.ok{background:#d9f7be;color:#237804}.warn{background:#fff1b8;color:#ad6800}.bad{background:#ffccc7;color:#cf1322}
.mono{font-family:ui-monospace,monospace;font-size:12px}
button{padding:7px 14px;border:1px solid #bbb;border-radius:6px;background:#fff;cursor:pointer;font-size:13px}
section{background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:16px;margin-top:14px}
input[type=number]{width:80px}
</style></head><body>
<h1>AI Calibration Center</h1>
<p class="mono">Score Engine <b id="se"></b> · Profiles <b id="pv"></b> · References cached <b id="rc"></b></p>
<section><h2>Run Calibration</h2>
<label>Products <input id="pl" type="number" value="500" min="1"></label>
<label><input id="uc" type="checkbox" checked> Use cache</label>
<label><input id="fr" type="checkbox"> Force refresh</label><br><br>
<label>Candidate config (JSON):<br><textarea id="cand" rows="2" style="width:100%;font-family:monospace" placeholder='{"saturation_scale": 2.0}'></textarea></label><br>
<button onclick="run()">RUN CALIBRATION</button>
<pre id="out" class="mono" style="white-space:pre-wrap;min-height:80px"></pre>
</section>
<section><h2>History</h2><div id="runs"></div></section>
<script>
async function j(method,url,body){const o={method,headers:{'Content-Type':'application/json'}};if(body)o.body=JSON.stringify(body);const r=await fetch(url,o);return r.json();}
async function load(){const o=await j('GET','/admin/calibration/api/overview');document.getElementById('se').textContent=o.scoring_config_version;document.getElementById('pv').textContent=o.profiles_version;document.getElementById('rc').textContent=o.reference_cache_count;
document.getElementById('runs').innerHTML=(o.runs||[]).map(r=>`<div class="mono">${r.run_key} · products=${r.product_count} profiles=${r.profile_count} cases=${r.case_count} · ai_req=${r.ai_request_count} hit=${r.cache_hits} miss=${r.cache_misses}</div>`).join('');}
async function run(){const body={product_limit:+document.getElementById('pl').value,use_cache:document.getElementById('uc').checked,force_refresh:document.getElementById('fr').checked};const c=document.getElementById('cand').value.trim();if(c){try{body.candidate=JSON.parse(c)}catch(e){alert('bad JSON');return}}document.getElementById('out').textContent='running…';const r=await j('POST','/admin/calibration/api/run',body);document.getElementById('out').textContent=JSON.stringify(r,null,2);load();}
load();
</script></body></html>
"""

