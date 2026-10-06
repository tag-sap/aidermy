# report_prompt_routes.py
# Admin AI/Report tab: управление Report prompt (версии, production, rollback) +
# Playground для тестирования prompt на реальном профиле + продукте.
#
# HTTP Basic auth (как admin_routes / calibration_routes). Все endpoints только для Admin.
# Score/verdict НЕ редактируются: это отдельная система от Score Engine.

from __future__ import annotations

from typing import Any, Dict

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from .admin_routes import verify_admin
from . import report_prompt as rp


def _compute_deterministic(user_id, slug, product_id):
    """Считает deterministic result по реальному профилю + продукту (без LLM)."""
    from .database import get_product_by_slug, get_product_by_id
    from .shelf_service import _build_user_profile
    from .decision_engine import DecisionEngine
    from .catalog_taxonomy import classify_product

    product = None
    if product_id:
        try:
            product = get_product_by_id(int(product_id))
        except (TypeError, ValueError):
            product = None
    if not product and slug:
        product = get_product_by_slug(slug)
    if not product:
        raise HTTPException(status_code=404, detail="Продукт не найден")

    user = {"id": int(user_id)} if user_id else {}
    profile = _build_user_profile(user) if user_id else {"skin_type": ""}

    name = (product.get("name") or "").replace("\n", " ").strip()
    ingredients = product.get("ingredients") or ""
    engine = DecisionEngine()
    deterministic = engine.analyze(name, ingredients, profile, profile.get("skin_type") or "")

    product_type = ""
    try:
        product_type = classify_product(product).get("canonical_category") or ""
    except Exception:
        pass

    return deterministic, profile, product, name, product_type


def _sanitize_profile_for_display(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Убирает служебные/чувствительные поля для отображения в Admin."""
    out = dict(profile or {})
    out.pop("custom_text", None)
    return out


def setup_report_prompt_routes(app):
    rp.ensure_report_prompt_tables()
    rp.seed_report_prompt()

    @app.get("/admin/report", response_class=HTMLResponse)
    async def report_prompt_panel(_: bool = Depends(verify_admin)):
        return HTMLResponse(REPORT_PROMPT_HTML)

    @app.get("/admin/report/api/prompts")
    async def list_prompts(_: bool = Depends(verify_admin)):
        prompts = rp.list_report_prompts()
        production = rp.get_production_report_prompt()
        return {
            "prompts": prompts,
            "production": production,
            "placeholders": rp.REPORT_PROMPT_PLACEHOLDERS,
        }

    @app.get("/admin/report/api/prompts/{prompt_id}")
    async def get_prompt(prompt_id: int, _: bool = Depends(verify_admin)):
        p = rp.get_report_prompt_by_id(prompt_id)
        if not p:
            raise HTTPException(status_code=404, detail="Prompt не найден")
        return p

    @app.post("/admin/report/api/prompts")
    async def create_prompt(req: Request, _: bool = Depends(verify_admin)):
        body = await req.json()
        name = str(body.get("name") or "")
        system_prompt = str(body.get("system_prompt") or "")
        user_prompt_template = str(body.get("user_prompt_template") or "")
        if not user_prompt_template.strip():
            raise HTTPException(status_code=400, detail="user_prompt_template не может быть пустым")
        description = str(body.get("description") or "")
        created_by = str(body.get("created_by") or "admin")
        return rp.create_report_prompt(name, system_prompt, user_prompt_template, description, created_by)

    @app.post("/admin/report/api/prompts/{prompt_id}/publish")
    async def publish_prompt(prompt_id: int, _: bool = Depends(verify_admin)):
        p = rp.publish_report_prompt(prompt_id)
        if not p:
            raise HTTPException(status_code=404, detail="Prompt не найден")
        return {"production": p}

    @app.get("/admin/report/api/products")
    async def list_products(q: str = "", _: bool = Depends(verify_admin)):
        from .database import get_all_canonical_products
        products = get_all_canonical_products()
        ql = (q or "").strip().lower()
        items = []
        for p in products:
            name = (p.get("name") or "").replace("\n", " ").strip()
            if ql and ql not in name.lower() and ql not in (p.get("slug") or "").lower():
                continue
            items.append({"id": p.get("id"), "slug": p.get("slug") or "", "name": name})
            if len(items) >= 300:
                break
        return {"products": items}

    @app.get("/admin/report/api/profiles")
    async def list_profiles(_: bool = Depends(verify_admin)):
        from .database import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                """
                SELECT u.id, u.email, p.skin_type, p.age, p.concerns
                FROM users u
                LEFT JOIN user_profiles p ON p.user_id = u.id
                WHERE u.email IS NOT NULL AND u.email != ''
                ORDER BY u.id DESC
                LIMIT 300
                """
            ).fetchall()
            items = []
            for r in rows:
                items.append({
                    "id": r["id"],
                    "email": r["email"] or "",
                    "skin_type": r["skin_type"] or "",
                    "age": r["age"] or "",
                    "concerns": r["concerns"] or "",
                })
            return {"profiles": items}
        finally:
            conn.close()

    @app.post("/admin/report/api/deterministic")
    async def deterministic(req: Request, _: bool = Depends(verify_admin)):
        """Показывает deterministic result + raw LLM input (без вызова LLM)."""
        body = await req.json()
        user_id = body.get("user_id")
        slug = body.get("slug")
        product_id = body.get("product_id")
        prompt_id = body.get("prompt_id")

        deterministic, profile, product, name, product_type = _compute_deterministic(user_id, slug, product_id)
        prompt = rp.get_report_prompt_by_id(int(prompt_id)) if prompt_id else rp.get_production_report_prompt()
        context = rp.build_report_context(name, deterministic, profile, product_type)
        rendered = rp.render_report_prompt(prompt, context) if prompt else {"system": "", "user": ""}

        return {
            "deterministic": deterministic,
            "profile": _sanitize_profile_for_display(profile),
            "product": {"id": product.get("id"), "slug": product.get("slug"), "name": name},
            "product_type": product_type,
            "prompt": prompt,
            "input": rendered,
            "score_engine_version": deterministic.get("score_engine_version"),
        }

    @app.post("/admin/report/api/test")
    async def test_generate(req: Request, _: bool = Depends(verify_admin)):
        """Playground: генерирует тестовый отчёт (НЕ сохраняет production Report)."""
        from .services import generate_report_once

        body = await req.json()
        user_id = body.get("user_id")
        slug = body.get("slug")
        product_id = body.get("product_id")
        prompt_id = body.get("prompt_id")

        deterministic, profile, product, name, product_type = _compute_deterministic(user_id, slug, product_id)
        prompt = rp.get_report_prompt_by_id(int(prompt_id)) if prompt_id else rp.get_production_report_prompt()
        if not prompt:
            raise HTTPException(status_code=404, detail="Prompt не найден")

        context = rp.build_report_context(name, deterministic, profile, product_type)
        rendered = rp.render_report_prompt(prompt, context)

        report = await generate_report_once(name, deterministic, profile, product_type, prompt=prompt, debug=True)

        raw_input = (report or {}).get("_raw_input", rendered)
        raw_output = (report or {}).get("_raw_output", "")
        if report:
            report.pop("_raw_input", None)
            report.pop("_raw_output", None)

        return {
            "deterministic": deterministic,
            "profile": _sanitize_profile_for_display(profile),
            "product": {"id": product.get("id"), "slug": product.get("slug"), "name": name},
            "product_type": product_type,
            "prompt": prompt,
            "input": raw_input,
            "ai_output": raw_output,
            "report": report,
        }


REPORT_PROMPT_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aidermy Admin — AI / Report</title>
<style>
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f5f5;margin:0;padding:20px;color:#1a1a1a}
.container{max-width:1400px;margin:0 auto}
h1{font-size:24px;margin:0 0 4px}
h2{font-size:18px;margin:24px 0 10px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;white-space:pre-wrap;word-break:break-word}
.card{background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.08);padding:16px;margin-bottom:16px}
.kv{display:grid;grid-template-columns:180px 1fr;gap:2px 10px;font-size:13px}
.kv b{color:#FF4F00}
.btn{background:#FF4F00;color:#fff;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;margin-right:8px}
.btn.secondary{background:#666}.btn.green{background:#4CAF50}.btn.danger{background:#f44336}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn:hover{opacity:.85}
textarea{width:100%;font-family:ui-monospace,Menlo,monospace;font-size:12px;border:1px solid #ddd;border-radius:6px;padding:8px;min-height:120px}
input,select{padding:8px;border:1px solid #ddd;border-radius:6px;font-size:13px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
.badge{background:#FF4F00;color:#fff;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600;display:inline-block}
.badge.prod{background:#4CAF50}
.hist-row{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 10px;border-bottom:1px solid #eee;font-size:13px;flex-wrap:wrap}
.hist-row:hover{background:#fafafa}
details{border:1px solid #eee;border-radius:8px;padding:8px;margin-top:8px}
summary{cursor:pointer;font-weight:600;font-size:13px;color:#FF4F00}
.verdict-good{color:#4CAF50;font-weight:700}.verdict-caution{color:#ff9800;font-weight:700}.verdict-bad{color:#f44336;font-weight:700}
</style>
</head>
<body>
<div class="container">
<h1>🤖 AI / Report</h1>
<div style="font-size:13px;color:#666;margin-bottom:16px">
  Score Engine: <b id="se-ver">—</b> · Report Prompt: <b id="rp-prod-ver">—</b>
</div>

<h2>📌 Production Prompt</h2>
<div class="card"><div class="kv" id="prod-view">Загрузка…</div></div>

<h2>📜 История версий</h2>
<div class="card" id="hist-list">Загрузка…</div>

<h2>✏️ Редактор prompt</h2>
<div class="card">
  <div class="kv">
    <b>Name</b><input id="ed-name" placeholder="Report Prompt vN">
    <b>Description</b><input id="ed-desc" placeholder="описание">
    <b>System prompt</b><textarea id="ed-system" rows="10"></textarea>
    <b>User prompt template</b><textarea id="ed-user" rows="10"></textarea>
  </div>
  <div style="margin-top:10px">
    <button class="btn" onclick="savePrompt()">💾 Сохранить как новую версию</button>
  </div>
  <details>
    <summary>Доступные переменные (placeholders)</summary>
    <div class="mono" id="placeholders"></div>
  </details>
</div>

<h2>🧪 Test Report (Playground)</h2>
<div class="card">
  <div class="grid">
    <div>
      <div style="margin-bottom:8px"><b>Profile (пользователь)</b></div>
      <select id="prof-select" onchange="loadDeterministic()"><option value="">— выберите —</option></select>
    </div>
    <div>
      <div style="margin-bottom:8px"><b>Product</b></div>
      <select id="prod-select" onchange="loadDeterministic()"><option value="">— выберите —</option></select>
    </div>
    <div>
      <div style="margin-bottom:8px"><b>Prompt version</b></div>
      <select id="prompt-select" onchange="loadDeterministic()"><option value="">production</option></select>
    </div>
  </div>
  <div style="margin-top:12px">
    <button class="btn" id="gen-btn" onclick="generateTest()">⚡ Сгенерировать тестовый отчёт</button>
  </div>
</div>

<div class="card" id="deterministic-view" style="display:none">
  <h2 style="margin-top:0">Deterministic result</h2>
  <div id="det-body"></div>
  <details><summary>Показать данные, переданные AI</summary><div class="mono" id="raw-input"></div></details>
</div>

<div class="card" id="ai-view" style="display:none">
  <h2 style="margin-top:0">AI result</h2>
  <div id="report-preview"></div>
  <details><summary>AI output (raw)</summary><div class="mono" id="ai-output"></div></details>
</div>
</div>

<script>
let PROD = null, PROMPTS = [];
function esc(s){return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
async function j(method,url,body){
  const r = await fetch(url,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
  const d = await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(d.detail||('HTTP '+r.status));
  return d;
}
async function loadPrompts(){
  const d = await j('GET','/admin/report/api/prompts');
  PROMPTS = d.prompts||[]; PROD = d.production||null;
  document.getElementById('rp-prod-ver').textContent = PROD ? ('v'+PROD.version) : '—';
  renderProd(); renderHistory(); renderPromptSelect();
  document.getElementById('placeholders').textContent = (d.placeholders||[]).map(p=>'{{'+p+'}}').join('\\n');
}
function renderProd(){
  if(!PROD){document.getElementById('prod-view').innerHTML='<span>—</span>';return}
  document.getElementById('prod-view').innerHTML =
    '<b>Версия</b><span>Report Prompt v'+PROD.version+' <span class="badge prod">production</span></span>'+
    '<b>Name</b><span>'+esc(PROD.name)+'</span>'+
    '<b>Создано</b><span>'+esc(PROD.created_at)+' · '+esc(PROD.created_by)+'</span>'+
    '<b>Description</b><span>'+esc(PROD.description||'—')+'</span>';
}
function renderHistory(){
  const el = document.getElementById('hist-list');
  el.innerHTML = PROMPTS.map(p=>
    '<div class="hist-row"><span><b>v'+p.version+'</b> '+esc(p.name)+(p.is_production?' <span class="badge prod">production</span>':'')+'</span>'+
    '<span style="color:#888">'+esc(p.created_at||'')+'</span>'+
    '<span><button class="btn secondary" onclick="loadVersion('+p.id+')">Preview</button>'+
    '<button class="btn green" onclick="publish('+p.id+')">Make production</button>'+
    '<button class="btn secondary" onclick="testVersion('+p.id+')">Test</button></span></div>'
  ).join('');
}
function renderPromptSelect(){
  const el = document.getElementById('prompt-select');
  el.innerHTML = '<option value="">production</option>' + PROMPTS.map(p=>'<option value="'+p.id+'">v'+p.version+'</option>').join('');
}
function loadVersion(id){
  const p = PROMPTS.find(x=>x.id===id); if(!p) return;
  document.getElementById('ed-name').value = p.name;
  document.getElementById('ed-desc').value = p.description||'';
  document.getElementById('ed-system').value = p.system_prompt||'';
  document.getElementById('ed-user').value = p.user_prompt_template||'';
}
async function savePrompt(){
  const body = {
    name: document.getElementById('ed-name').value,
    description: document.getElementById('ed-desc').value,
    system_prompt: document.getElementById('ed-system').value,
    user_prompt_template: document.getElementById('ed-user').value,
    created_by: 'admin',
  };
  const p = await j('POST','/admin/report/api/prompts',body);
  alert('Сохранено: Report Prompt v'+p.version);
  await loadPrompts();
}
async function publish(id){
  const p = PROMPTS.find(x=>x.id===id); if(!p) return;
  if(!confirm('Вы действительно хотите сделать Report Prompt v'+p.version+' production?')) return;
  await j('POST','/admin/report/api/prompts/'+id+'/publish',{});
  await loadPrompts();
  alert('Production prompt: v'+p.version);
}
function testVersion(id){document.getElementById('prompt-select').value = id; loadDeterministic();}

async function loadProfiles(){
  const d = await j('GET','/admin/report/api/profiles');
  const el = document.getElementById('prof-select');
  el.innerHTML = '<option value="">— выберите —</option>' + (d.profiles||[]).map(p=>
    '<option value="'+p.id+'">#'+p.id+' '+esc(p.email)+' ('+esc(p.skin_type||'—')+')</option>').join('');
}
async function loadProducts(){
  const d = await j('GET','/admin/report/api/products');
  const el = document.getElementById('prod-select');
  el.innerHTML = '<option value="">— выберите —</option>' + (d.products||[]).map(p=>
    '<option value="'+p.slug+'">'+esc(p.name)+'</option>').join('');
}
async function loadDeterministic(){
  const uid = document.getElementById('prof-select').value;
  const slug = document.getElementById('prod-select').value;
  if(!uid || !slug) return;
  const pid = document.getElementById('prompt-select').value || null;
  const d = await j('POST','/admin/report/api/deterministic',{user_id:parseInt(uid),slug,prompt_id:pid});
  document.getElementById('deterministic-view').style.display='block';
  document.getElementById('ai-view').style.display='none';
  renderDeterministic(d);
}
function renderDeterministic(d){
  const det = d.deterministic||{};
  const sc = det.score ?? 0;
  const v = det.verdict||'';
  const cls = sc>=70?'verdict-good':(sc>=40?'verdict-caution':'verdict-bad');
  document.getElementById('det-body').innerHTML =
    '<div class="kv">'+
    '<b>Score</b><span><b>'+sc+'%</b></span>'+
    '<b>Verdict</b><span class="'+cls+'">'+esc(v)+'</span>'+
    '<b>Score Engine</b><span>'+esc(d.score_engine_version||'—')+'</span>'+
    '<b>Product type</b><span>'+esc(d.product_type||'—')+'</span>'+
    '</div>';
  document.getElementById('raw-input').textContent =
    'PROFILE\\n'+JSON.stringify(d.profile, null, 2)+
    '\\n\\nDETERMINISTIC RESULT\\n'+JSON.stringify(det, null, 2)+
    '\\n\\nRAW LLM INPUT\\nSYSTEM:\\n'+(d.input&&d.input.system||'')+'\\n\\nUSER:\\n'+(d.input&&d.input.user||'');
}
async function generateTest(){
  const uid = document.getElementById('prof-select').value;
  const slug = document.getElementById('prod-select').value;
  if(!uid || !slug){alert('Выберите профиль и продукт');return}
  const pid = document.getElementById('prompt-select').value || null;
  const btn = document.getElementById('gen-btn');
  btn.disabled = true; btn.textContent = 'Генерируем…';
  try{
    const d = await j('POST','/admin/report/api/test',{user_id:parseInt(uid),slug,prompt_id:pid});
    document.getElementById('deterministic-view').style.display='block';
    document.getElementById('ai-view').style.display='block';
    renderDeterministic(d);
    const rep = d.report||{};
    document.getElementById('report-preview').innerHTML =
      '<div class="kv">'+
      '<b>Score</b><span><b>'+((d.deterministic&&d.deterministic.score) ?? 0)+'%</b></span>'+
      '<b>Verdict</b><span>'+esc((d.deterministic&&d.deterministic.verdict)||'')+'</span>'+
      '<b>Prompt</b><span>v'+esc((d.prompt&&d.prompt.version)||'—')+'</span>'+
      '<b>Объяснение</b><span>'+esc(rep.explanation||'—')+'</span>'+
      '<b>Чего ожидать</b><span>'+esc(JSON.stringify(rep.expectations))+'</span>'+
      '</div>';
    document.getElementById('ai-output').textContent = d.ai_output || '(пусто)';
  }catch(e){
    alert('Ошибка: '+e.message);
  }finally{
    btn.disabled = false; btn.textContent = '⚡ Сгенерировать тестовый отчёт';
  }
}
loadPrompts(); loadProfiles(); loadProducts();
</script>
</body>
</html>
"""
