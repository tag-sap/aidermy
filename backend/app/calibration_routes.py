# calibration_routes.py
# Админ-панель AI Calibration Center (HTTP Basic auth, как admin_routes).
# Run создаётся быстро (queued) и выполняется в отдельном процессе calibration_worker.
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse

from .admin_routes import verify_admin
from .calibration_profiles import CALIBRATION_PROFILES, CALIBRATION_PROFILES_VERSION
from .calibration_service import (
    CALIBRATION_PROMPT_VERSION,
    create_run,
    ensure_tables,
    get_run,
    is_stale,
    latest_active_run,
    update_run,
)
from .scoring_config import SCORING_CONFIG_VERSION

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _spawn_worker(run_key: str) -> None:
    """Запускает calibration_worker в отдельном detached процессе."""
    env = os.environ.copy()
    pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _BASE_DIR + (os.pathsep + pp if pp else "")
    log_path = os.path.join(_BASE_DIR, "calibration_worker.log")
    logf = open(log_path, "a", encoding="utf-8")
    logf.write(f"[{_now()}] spawn worker for {run_key}\n")
    logf.flush()
    kwargs: Dict[str, Any] = dict(cwd=_BASE_DIR, env=env, stdout=logf, stderr=subprocess.STDOUT, close_fds=True)
    if os.name == "posix":
        kwargs["start_new_session"] = True
    subprocess.Popen([sys.executable, "-m", "app.calibration_worker", "--run-key", run_key], **kwargs)
    logf.close()


def _decode_run(run: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(run)
    for field in ("params", "metrics", "candidate_config"):
        raw = out.get(field)
        if isinstance(raw, str) and raw:
            try:
                out[field] = json.loads(raw)
            except Exception:
                pass
    return out
def setup_calibration_routes(app):
    ensure_tables()

    @app.get("/admin/calibration", response_class=HTMLResponse)
    async def calibration_panel(_: bool = Depends(verify_admin)):
        return HTMLResponse(CALIBRATION_HTML)

    @app.get("/admin/calibration/api/overview")
    async def calibration_overview(_: bool = Depends(verify_admin)):
        from .calibration_service import _db
        conn = _db()
        rows = conn.execute("SELECT * FROM calibration_runs ORDER BY id DESC LIMIT 10").fetchall()
        refs_total = conn.execute("SELECT COUNT(*) FROM calibration_references").fetchone()[0]
        candidates = conn.execute("SELECT id, name, config, created_at FROM calibration_candidates ORDER BY id DESC").fetchall()
        golden = conn.execute("SELECT id, label, product_id, profile_id, min_score, max_score FROM golden_calibration_cases").fetchall()
        conn.close()
        runs = []
        for r in rows:
            d = _decode_run({k: r[k] for k in r.keys()})
            if d.get("status") in ("queued", "running") and is_stale(d):
                update_run(d["run_key"], status="failed", error="stale: worker killed/timed out",
                           completed_at=_now(), updated_at=_now())
                d["status"] = "failed"
            runs.append(d)
        return {
            "scoring_config_version": SCORING_CONFIG_VERSION,
            "profiles_version": CALIBRATION_PROFILES_VERSION,
            "prompt_version": CALIBRATION_PROMPT_VERSION,
            "profiles_count": len(CALIBRATION_PROFILES),
            "reference_cache_count": refs_total,
            "runs": runs,
            "candidates": [{"id": r[0], "name": r[1], "config": r[2], "created_at": r[3]} for r in candidates],
            "golden_set": [dict(zip(["id", "label", "product_id", "profile_id", "min_score", "max_score"], r)) for r in golden],
        }

    @app.get("/admin/calibration/api/profiles")
    async def calibration_profiles(_: bool = Depends(verify_admin)):
        return {"version": CALIBRATION_PROFILES_VERSION, "profiles": CALIBRATION_PROFILES}

    @app.get("/admin/calibration/api/run/{run_key}")
    async def calibration_run_status(run_key: str, _: bool = Depends(verify_admin)):
        run = get_run(run_key)
        if run is None:
            return {"error": "not_found"}
        if run.get("status") in ("queued", "running") and is_stale(run):
            update_run(run_key, status="failed", error="stale: worker killed/timed out",
                       completed_at=_now(), updated_at=_now())
            run = get_run(run_key)
        return _decode_run(run)

    @app.post("/admin/calibration/api/run")
    async def calibration_run(req: Request, _: bool = Depends(verify_admin)):
        body = await req.json()

        # Resume существующего run (idempotent): использует уже сохранённые references/cases.
        existing_key = body.get("run_key")
        if existing_key:
            run = get_run(existing_key)
            if run is None:
                return {"error": "not_found"}
            if run.get("status") == "completed":
                return {"run_key": existing_key, "status": "completed", "message": "already completed"}
            _spawn_worker(existing_key)
            return {"run_key": existing_key, "status": "queued", "message": "resumed"}

        # Защита от двойного нажатия RUN: активный (не stale) run уже есть.
        active = latest_active_run()
        if active and active.get("status") in ("queued", "running") and not is_stale(active):
            return {"run_key": active["run_key"], "status": active["status"], "message": "already running"}

        params = {
            "product_limit": int(body.get("product_limit", 500)),
            "profile_ids": body.get("profile_ids") or [],
            "use_cache": bool(body.get("use_cache", True)),
            "force_refresh": bool(body.get("force_refresh", False)),
            "candidate": body.get("candidate"),
        }
        run_key = create_run(params)
        _spawn_worker(run_key)
        return {"run_key": run_key, "status": "queued", "message": "started"}

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
.ok{background:#d9f7be;color:#237804}.warn{background:#fff1b8;color:#ad6800}.bad{background:#ffccc7;color:#cf1322}.run{background:#d6e4ff;color:#1d39c4}
.mono{font-family:ui-monospace,monospace;font-size:12px}
button{padding:7px 14px;border:1px solid #bbb;border-radius:6px;background:#fff;cursor:pointer;font-size:13px}
button:disabled{opacity:.5;cursor:not-allowed}
section{background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:16px;margin-top:14px}
input[type=number]{width:80px}
.bar{background:#eee;border-radius:99px;height:10px;overflow:hidden;margin:6px 0}
.bar>i{display:block;height:10px;background:#237804}
</style></head><body>
<h1>AI Calibration Center</h1>
<p class="mono">Score Engine <b id="se"></b> · Profiles <b id="pv"></b> · References cached <b id="rc"></b></p>
<section><h2>Run Calibration</h2>
<label>Products <input id="pl" type="number" value="500" min="1"></label>
<label><input id="uc" type="checkbox" checked> Use cache</label>
<label><input id="fr" type="checkbox"> Force refresh</label><br><br>
<label>Candidate config (JSON):<br><textarea id="cand" rows="2" style="width:100%;font-family:monospace" placeholder='{"saturation_scale": 2.0}'></textarea></label><br>
<button id="runbtn" onclick="run()">RUN CALIBRATION</button>
<pre id="out" class="mono" style="white-space:pre-wrap;min-height:40px"></pre>
</section>
<section><h2>History</h2><div id="runs"></div></section>
<script>
async function j(method,url,body){const o={method,headers:{'Content-Type':'application/json'}};if(body)o.body=JSON.stringify(body);const r=await fetch(url,o);return r.json();}
const BADGE={queued:'run',running:'run',completed:'ok',failed:'bad'};
function badge(s){return `<span class="badge ${BADGE[s]||'warn'}">${s}</span>`;}
function pct(p,t){if(!t)return '';const w=Math.min(100,Math.round(p/t*100));return `<div class="bar"><i style="width:${w}%"></i></div>`;}
async function load(){
  const o=await j('GET','/admin/calibration/api/overview');
  document.getElementById('se').textContent=o.scoring_config_version;
  document.getElementById('pv').textContent=o.profiles_version;
  document.getElementById('rc').textContent=o.reference_cache_count;
  const runs=o.runs||[];
  const active=runs.find(r=>r.status==='queued'||r.status==='running');
  document.getElementById('runbtn').disabled=!!active;
  document.getElementById('runs').innerHTML=runs.map(r=>{
    const prog=pct(r.processed_cases,r.case_count);
    const err=r.error?`<br>error: ${r.error}`:'';
    const resume=(r.status==='failed'||r.status==='queued')?` <button onclick="resume('${r.run_key}')">resume</button>`:'';
    return `<div class="mono" style="margin-bottom:10px">${r.run_key} ${badge(r.status||'queued')}${resume}<br>`+
      `products=${r.product_count} profiles=${r.profile_count} cases=${r.case_count} · `+
      `processed=${r.processed_cases||0}/${r.case_count||0} · batch=${r.current_batch||0}/${r.total_batches||0} · `+
      `ai_req=${r.ai_request_count||0} hit=${r.cache_hits||0} miss=${r.cache_misses||0} errors=${r.errors||0}`+
      `${prog}${err}</div>`;
  }).join('');
}
async function run(){
  const body={product_limit:+document.getElementById('pl').value,use_cache:document.getElementById('uc').checked,force_refresh:document.getElementById('fr').checked};
  const c=document.getElementById('cand').value.trim();
  if(c){try{body.candidate=JSON.parse(c)}catch(e){alert('bad JSON');return}}
  document.getElementById('out').textContent='starting…';
  const r=await j('POST','/admin/calibration/api/run',body);
  document.getElementById('out').textContent=JSON.stringify(r,null,2);
  load();
}
async function resume(key){
  const r=await j('POST','/admin/calibration/api/run',{run_key:key});
  document.getElementById('out').textContent=JSON.stringify(r,null,2);
  load();
}
load();
setInterval(load,2000);
</script></body></html>
"""

