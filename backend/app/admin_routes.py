from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from .database import (
    get_all_check_history,
    get_check_stats,
    get_connection,
    get_product_by_id,
    get_product_by_slug,
    get_stale_analysis_count,
    get_stale_analysis_records,
    clear_analysis_history,
    PRODUCTS_DB,
)
import os
import logging

# Админка будет подключаться к основному app

security = HTTPBasic()
logger = logging.getLogger(__name__)

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = "admin"
    correct_password = "aidermy2026"
    
    if credentials.username != correct_username or credentials.password != correct_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


def _get_ingredients_admin():
    """Сводка по Ingredient DB для админки (статус, claims, аллергенность, число продуктов)."""
    import re as _re
    from .database import AIDERMY_DB
    from .ingredient_normalizer import normalize_ingredient_name

    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    rows = cursor.execute(
        """
        SELECT i.*,
               (SELECT COUNT(*) FROM ingredient_claims c WHERE c.ingredient_id = i.id) AS claim_count,
               (SELECT c.source_type FROM ingredient_claims c WHERE c.ingredient_id = i.id LIMIT 1) AS source_type,
               a.is_allergen, a.is_sensitizer, a.allergen_level
        FROM ingredients_catalog i
        LEFT JOIN allergen_sensitizer a ON a.ingredient_id = i.id
        ORDER BY i.id DESC
        """
    ).fetchall()
    conn.close()

    # Число продуктов, использующих каждый ингредиент (один проход по Product DB).
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    prods = cursor.execute("SELECT ingredients FROM products WHERE ingredients IS NOT NULL").fetchall()
    conn.close()
    product_counts: dict = {}
    for p in prods:
        seen = set()
        for part in _re.split(r"[,;\n]+", p["ingredients"] or ""):
            n = normalize_ingredient_name(part)
            if n and n not in seen:
                seen.add(n)
        for t in seen:
            product_counts[t] = product_counts.get(t, 0) + 1

    result = []
    for row in rows:
        d = dict(row)
        has_claims = (d.get("claim_count") or 0) > 0
        conf = float(d.get("knowledge_confidence") or 0)
        d["status"] = "known" if (has_claims or conf > 0) else "needs_enrichment"
        d["product_count"] = product_counts.get((d.get("normalized_name") or "").lower(), 0)
        result.append(d)
    return result

def setup_admin_routes(app: FastAPI):
    """Регистрирует все админ-роуты в приложении"""
    
    @app.get("/admin", response_class=HTMLResponse)
    async def admin_panel(_: bool = Depends(verify_admin)):
        # Получаем данные
        history = get_all_check_history(limit=100)
        stats = get_check_stats()
        
        # Только проверки с составом (не нулевые)
        filtered_history = [h for h in history if h.get('score', 0) > 0]
        
        pending = []
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT p.*, u.email as user_email 
                FROM pending_products p
                LEFT JOIN users u ON p.user_id = u.id
                WHERE p.status = 'pending'
                ORDER BY p.created_at DESC
                LIMIT 50
            ''')
            pending = cursor.fetchall()
            conn.close()
        except:
            pass
        
        # Получаем пользователей с профилями
        users = []
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    u.id,
                    u.email,
                    u.name,
                    u.is_verified,
                    u.created_at,
                    p.skin_type,
                    p.age,
                    p.concerns,
                    p.allergies,
                    p.custom_text,
                    p.updated_at as profile_updated
                FROM users u
                LEFT JOIN user_profiles p ON u.id = p.user_id
                ORDER BY u.created_at DESC
                LIMIT 50
            ''')
            users = cursor.fetchall()
            conn.close()
        except:
            pass

        # Ингредиенты (Ingredient DB) — контроль качества данных.
        try:
            ingredients = _get_ingredients_admin()
        except Exception:
            ingredients = []
        unknown_ingredients = [i for i in ingredients if i.get("status") == "needs_enrichment"]

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Aidermy Admin</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                * {{ box-sizing: border-box; }}
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }}
                .container {{ max-width: 1400px; margin: 0 auto; }}
                .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; flex-wrap: wrap; gap: 10px; }}
                h1 {{ color: #1a1a1a; font-size: 28px; margin: 0; }}
                .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 30px; }}
                .stat-card {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
                .stat-card .number {{ font-size: 32px; font-weight: 700; color: #FF4F00; }}
                .stat-card .label {{ font-size: 14px; color: #666; margin-top: 4px; }}
                .tabs {{ display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }}
                .tab-btn {{ padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; background: #e0e0e0; transition: 0.3s; }}
                .tab-btn.active {{ background: #FF4F00; color: white; }}
                .tab-btn:hover {{ opacity: 0.8; }}
                .tab-content {{ display: none; }}
                .tab-content.active {{ display: block; }}
                .table-wrap {{ background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 30px; }}
                .table-header {{ padding: 16px 20px; background: #FFF3E0; border-bottom: 2px solid #FF4F00; font-weight: 600; color: #FF4F00; display: flex; justify-content: space-between; align-items: center; }}
                .bulk-actions {{ display: flex; gap: 8px; }}
                .btn-bulk-approve {{ background: #4CAF50; color: white; border: none; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: 500; }}
                .btn-bulk-reject {{ background: #f44336; color: white; border: none; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: 500; }}
                .btn-bulk-delete {{ background: #ff9800; color: white; border: none; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: 500; }}
                .btn-bulk-approve:hover, .btn-bulk-reject:hover, .btn-bulk-delete:hover {{ opacity: 0.8; }}
                table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
                th {{ background: #FF4F00; color: white; padding: 12px 16px; text-align: left; font-weight: 600; }}
                td {{ padding: 12px 16px; border-bottom: 1px solid #eee; }}
                tr:hover {{ background: #f9f9f9; }}
                .badge {{ background: #FF4F00; color: white; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; display: inline-block; }}
                .badge-green {{ background: #4CAF50; color: white; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; display: inline-block; }}
                .badge-red {{ background: #f44336; color: white; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; display: inline-block; }}
                .btn-approve {{ background: #4CAF50; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; margin-right: 4px; font-size: 14px; }}
                .btn-approve:hover {{ opacity: 0.8; }}
                .btn-reject {{ background: #f44336; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 14px; }}
                .btn-reject:hover {{ opacity: 0.8; }}
                .btn-delete {{ background: #ff9800; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 14px; }}
                .btn-delete:hover {{ opacity: 0.8; }}
                .footer {{ text-align: center; color: #999; font-size: 13px; margin-top: 30px; }}
                .refresh-btn {{ background: #FF4F00; color: white; border: none; padding: 10px 24px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; }}
                .refresh-btn:hover {{ opacity: 0.9; }}
                .empty-state {{ text-align: center; padding: 30px; color: #999; }}
                @media (max-width: 600px) {{ .stats-grid {{ grid-template-columns: 1fr 1fr; }} .table-wrap {{ overflow-x: auto; }} td, th {{ padding: 8px 10px; font-size: 12px; }} }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🧴 Aidermy Admin</h1>
                    <button class="refresh-btn" onclick="location.reload()">🔄 Обновить</button>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-card"><div class="number">{stats['total']}</div><div class="label">📊 Всего проверок</div></div>
                    <div class="stat-card"><div class="number">{stats['unique_products']}</div><div class="label">🧴 Уникальных продуктов</div></div>
                    <div class="stat-card"><div class="number">{stats['avg_score']}</div><div class="label">⭐ Средний балл</div></div>
                </div>

                <!-- Вкладки -->
                <div class="tabs">
                    <button class="tab-btn active" onclick="switchTab('history')">📋 История ({len(filtered_history)})</button>
                    <button class="tab-btn" onclick="switchTab('moderation')">📦 Модерация ({len(pending)})</button>
                    <button class="tab-btn" onclick="switchTab('users')">👤 Пользователи ({len(users)})</button>
                    <button class="tab-btn" onclick="switchTab('ingredients')">🧪 Ингредиенты ({len(ingredients)})</button>
                    <button class="tab-btn" onclick="switchTab('scoreengine')">⚙️ Score Engine</button>
                    <a class="tab-btn" href="/admin/report" style="text-decoration:none;color:inherit;display:inline-block">🤖 AI / Report</a>
                </div>

                <!-- Вкладка: История -->
                <div id="tab-history" class="tab-content active">
                    <div class="table-wrap">
                        <div class="table-header"><span>🧮 История анализов</span></div>
                        <div style="padding: 18px 20px">
                            <div id="stale-analysis-count" style="margin-bottom: 14px">Устаревших результатов: загружаем…</div>
                            <div id="analysis-history-message" role="status" style="margin-bottom: 14px"></div>
                            <div style="display:flex;gap:8px;flex-wrap:wrap">
                                <button class="btn-bulk-approve" id="recalculate-stale-button" onclick="recalculateStaleAnalyses()">Пересчитать устаревшие</button>
                                <button class="btn-bulk-delete" id="clear-analysis-history-button" onclick="clearAnalysisHistory()">Очистить историю</button>
                            </div>
                        </div>
                    </div>
                    <div class="table-wrap">
                        <div class="table-header"><span>📋 История проверок</span></div>
                        <table>
                            <thead><tr><th>ID</th><th>Продукт</th><th>Тип кожи</th><th>Оценка</th><th>Вердикт</th><th>Резюме</th><th>Дата</th></tr></thead>
                            <tbody>
        """
        
        if filtered_history:
            for row in filtered_history[:50]:
                html += f"""
                                <tr>
                                    <td>{row['id']}</td>
                                    <td><strong>{row['product_name']}</strong></td>
                                    <td>{row['skin_type']}</td>
                                    <td><span class="badge">{row['score']}%</span></td>
                                    <td>{row['verdict']}</td>
                                    <td style="font-size: 12px; max-width: 250px; word-break: break-word;">{row['summary'][:60]}{'...' if len(row['summary']) > 60 else ''}</td>
                                    <td style="font-size: 12px;">{row['created_at']}</td>
                                </tr>
                """
        else:
            html += """<tr><td colspan="7" class="empty-state">📭 Нет проверок с составом</td></tr>"""
        
        html += """
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Вкладка: Модерация -->
                <div id="tab-moderation" class="tab-content">
                    <div class="table-wrap">
                        <div class="table-header">
                            <span>📦 Продукты на модерацию ({len(pending)})</span>
                            <div class="bulk-actions">
                                <button class="btn-bulk-approve" onclick="bulkAction('approve')">✅ Одобрить выбранные</button>
                                <button class="btn-bulk-reject" onclick="bulkAction('reject')">❌ Отклонить выбранные</button>
                                <button class="btn-bulk-delete" onclick="bulkAction('delete')">🗑️ Удалить выбранные</button>
                            </div>
                        </div>
                        <table>
                            <thead>
                                <tr>
                                    <th><input type="checkbox" id="select-all" onchange="toggleAll(this.checked)"></th>
                                    <th>ID</th>
                                    <th>Название</th>
                                    <th>Состав</th>
                                    <th>Отправил</th>
                                    <th>Дата</th>
                                    <th>Действия</th>
                                </tr>
                            </thead>
                            <tbody>
        """
        
        if pending:
            for p in pending:
                row = dict(p)
                user_email = row.get('user_email', 'Аноним')
                html += f"""
                                <tr>
                                    <td><input type="checkbox" class="product-checkbox" value="{row['id']}"></td>
                                    <td>{row['id']}</td>
                                    <td><strong>{row['product_name']}</strong></td>
                                    <td style="font-size: 12px; max-width: 200px; word-break: break-word;">{row['ingredients'][:80]}{'...' if len(row['ingredients']) > 80 else ''}</td>
                                    <td>{user_email}</td>
                                    <td style="font-size: 12px;">{row['created_at']}</td>
                                    <td>
                                        <button class="btn-approve" onclick="approve({row['id']})">✅</button>
                                        <button class="btn-reject" onclick="reject({row['id']})">❌</button>
                                        <button class="btn-delete" onclick="deleteProduct({row['id']})">🗑️</button>
                                    </td>
                                </tr>
                """
        else:
            html += """<tr><td colspan="7" class="empty-state">🎉 Нет продуктов на модерацию</td></tr>"""
        
        html += """
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Вкладка: Пользователи -->
                <div id="tab-users" class="tab-content">
                    <div class="table-wrap">
                        <div class="table-header"><span>👤 Зарегистрированные пользователи ({len(users)})</span></div>
                        <table>
                            <thead><tr><th>ID</th><th>Email</th><th>Имя</th><th>Верифицирован</th><th>Дата регистрации</th></tr></thead>
                            <tbody>
        """
        
        if users:
            for u in users:
                row = dict(u)
                verified_badge = '<span class="badge-green">✅ Да</span>' if row.get('is_verified') else '<span class="badge-red">❌ Нет</span>'
                html += f"""
                    <tr>
                        <td>{row['id']}</td>
                        <td><strong>{row['email']}</strong></td>
                        <td>{row.get('name', '—')}</td>
                        <td>{row.get('skin_type', '—')}</td>
                        <td>{row.get('age', '—')}</td>
                        <td>{verified_badge}</td>
                        <td style="font-size: 12px;">{row['created_at']}</td>
                    </tr>
                """
        else:
            html += """<tr><td colspan="5" class="empty-state">👤 Нет зарегистрированных пользователей</td></tr>"""
        
        html += """
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Вкладка: Ингредиенты -->
                <div id="tab-ingredients" class="tab-content">
                    <div class="table-wrap">
                        <div class="table-header">
                            <span>🧪 Ingredient DB — всего {len(ingredients)}, unknown/needs_enrichment: {len(unknown_ingredients)}</span>
                            <input id="ingredient-search" type="text" placeholder="Поиск по названию…" oninput="filterIngredients()" style="padding:6px 12px;border-radius:6px;border:1px solid #ddd;width:220px;">
                        </div>
                        <table>
                            <thead><tr><th>ID</th><th>Ингредиент</th><th>Статус</th><th>Claims</th><th>Аллерген</th><th>Источник</th><th>Продуктов</th><th>Обновлён</th><th>Enrich</th></tr></thead>
                            <tbody>
        """

        for ing in ingredients:
            status_badge = '<span class="badge-green">known</span>' if ing.get("status") == "known" else '<span class="badge-red">needs_enrichment</span>'
            allergen = ('⚠️ ' + str(ing.get("allergen_level") or "?")) if ing.get("is_allergen") else "—"
            norm = str(ing.get("normalized_name") or "")
            inci = str(ing.get("inci_name") or norm)
            html += f"""
                                <tr class="ingredient-row" data-name="{norm}" data-status="{ing.get('status')}">
                                    <td>{ing['id']}</td>
                                    <td><strong>{inci}</strong><br><span style="font-size:11px;color:#999;">{norm}</span></td>
                                    <td>{status_badge}</td>
                                    <td>{ing.get('claim_count', 0)}</td>
                                    <td>{allergen}</td>
                                    <td style="font-size:12px;">{ing.get('source_type') or ing.get('research_status') or '—'}</td>
                                    <td>{ing.get('product_count', 0)}</td>
                                    <td style="font-size:12px;">{ing.get('updated_at') or ing.get('created_at') or '—'}</td>
                                    <td><button class="btn-approve" onclick="enrichIngredient({ing['id']}, this)">🔬</button></td>
                                </tr>
            """
        html += """
                            </tbody>
                        </table>
                    </div>
                </div>

                <div id="tab-scoreengine" class="tab-content">
                    <style>
                    .se-sub{display:none}.se-sub.active{display:block}
                    .se-subtabs{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
                    .mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
                    .cal-run{padding:8px 10px;border-bottom:1px solid #eee;cursor:pointer}
                    .cal-run:hover{background:#FFF3E0}
                    .cal-run.sel{background:#FFE0B2}
                    .kv{display:grid;grid-template-columns:180px 1fr;gap:2px 10px;font-size:13px}
                    .kv b{color:#FF4F00}
                    .se-card{background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.08);padding:16px;margin-bottom:16px}
                    .se-card h3{margin:0 0 10px;font-size:15px;color:#1a1a1a}
                    .metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
                    .metric{background:#FFF3E0;border-radius:8px;padding:10px}
                    .metric .v{font-size:20px;font-weight:700;color:#FF4F00}
                    .metric .l{font-size:12px;color:#666}
                    .drift-row{display:flex;justify-content:space-between;gap:10px;padding:6px 0;border-bottom:1px solid #f0f0f0;font-size:13px}
                    .case-row{padding:8px 0;border-bottom:1px solid #f0f0f0;font-size:13px;cursor:pointer}
                    .case-row:hover{background:#fafafa}
                    .status-badge{padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600;display:inline-block;color:#fff}
                    .st-good{background:#4CAF50}.st-drift{background:#ff9800}.st-bad{background:#f44336}
                    .axis-table{width:100%;border-collapse:collapse;font-size:12px}
                    .axis-table th{background:#FF4F00;color:#fff;padding:6px 8px;text-align:left}
                    .axis-table td{padding:5px 8px;border-bottom:1px solid #eee}
                    input[type=range]{width:200px;vertical-align:middle}
                    .diff-pair{display:flex;gap:12px;font-size:13px;padding:3px 0}
                    .diff-pair .from{color:#888;text-decoration:line-through}
                    .diff-pair .to{color:#4CAF50;font-weight:600}
                    .modal-bg{position:fixed;inset:0;background:rgba(0,0,0,0.45);display:none;align-items:center;justify-content:center;z-index:9999}
                    .modal{background:#fff;border-radius:14px;max-width:760px;width:92%;max-height:88vh;overflow:auto;padding:22px}
                    .modal h3{margin-top:0}
                    .btn{background:#FF4F00;color:#fff;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;margin-right:8px}
                    .btn.secondary{background:#666}
                    .btn.danger{background:#f44336}
                    .btn.green{background:#4CAF50}
                    .btn:disabled{opacity:.5;cursor:not-allowed}
                    .se-btn{padding:10px 20px;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:600;background:#e0e0e0;transition:0.3s}
                    .se-btn.active{background:#FF4F00;color:#fff}
                    .se-btn:hover{opacity:0.8}
                    </style>
                    <div class="se-subtabs">
                        <button class="se-btn active" onclick="switchSeTab('production')">🏭 Production</button>
                        <button class="se-btn" onclick="switchSeTab('calibration')">🧪 Calibration</button>
                    </div>
                    <div id="se-production" class="se-sub active">
                        <div class="se-card"><h3>🏭 Production Score Engine</h3><div id="prod-view">Загрузка…</div></div>
                    </div>
                    <div id="se-calibration" class="se-sub">
                        <div style="display:grid;grid-template-columns:290px 1fr;gap:16px;align-items:start">
                            <div class="se-card" style="padding:0">
                                <div class="table-header" style="border-radius:12px 12px 0 0"><span>📜 Run History</span></div>
                                <div id="cal-runs"></div>
                            </div>
                            <div>
                                <div id="cal-summary"><div class="se-card">Выберите завершённый run слева.</div></div>
                                <div id="cand-editor"></div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="modal-bg" id="case-modal" onclick="if(event.target===this)closeModal()">
                    <div class="modal"><div style="display:flex;justify-content:space-between;align-items:center"><h3>🔍 Case Trace</h3><button class="btn secondary" onclick="closeModal()">✕</button></div><div id="case-body"></div></div>
                </div>

                <div class="footer"><p>🟢 База данных работает</p></div>
            </div>

            <script>
            function switchTab(tab) {
                document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
                document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
                document.getElementById('tab-' + tab).classList.add('active');
                document.querySelector(`.tab-btn[onclick="switchTab('${tab}')"]`).classList.add('active');
            }

            async function historyAdminRequest(method, url) {
                const response = await fetch(url, {method: method});
                const data = await response.json();
                if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
                return data;
            }

            async function loadAnalysisHistoryStatus() {
                const count = document.getElementById('stale-analysis-count');
                try {
                    const data = await historyAdminRequest('GET', '/api/admin/history/status');
                    count.dataset.value = data.stale_count;
                    count.textContent = `Устаревших результатов: ${data.stale_count}`;
                } catch (error) {
                    count.dataset.value = '';
                    count.textContent = `Не удалось загрузить количество устаревших результатов: ${error.message}`;
                }
            }

            async function recalculateStaleAnalyses() {
                const button = document.getElementById('recalculate-stale-button');
                const message = document.getElementById('analysis-history-message');
                const count = document.getElementById('stale-analysis-count');
                const staleCount = Number(count.dataset.value || 0);
                if (!staleCount) {
                    alert('Нет известных устаревших результатов. Обновите страницу и попробуйте снова.');
                    return;
                }
                if (!confirm(`Найдено устаревших результатов: ${staleCount}. Пересчитать их сейчас?\\n\\nЭто не запускает AI/LLM.`)) return;
                button.disabled = true;
                button.textContent = 'Пересчитываем…';
                message.textContent = 'Выполняется deterministic-пересчёт…';
                try {
                    const data = await historyAdminRequest('POST', '/api/admin/history/recalculate-stale');
                    message.textContent = `Пересчёт завершён. Обработано: ${data.processed}; обновлено: ${data.updated}; ошибок: ${data.failed}.`;
                    if (data.errors && data.errors.length) {
                        message.textContent += ' ' + data.errors.map(item => `ID ${item.analysis_id}: ${item.error}`).join(' ');
                    }
                    await loadAnalysisHistoryStatus();
                } catch (error) {
                    message.textContent = `Ошибка пересчёта: ${error.message}`;
                } finally {
                    button.disabled = false;
                    button.textContent = 'Пересчитать устаревшие';
                }
            }

            async function clearAnalysisHistory() {
                const button = document.getElementById('clear-analysis-history-button');
                if (!confirm(
                    'Будет удалена пользовательская история проверок: сохранённые analysis/Match и связанные с ними отчёты, а также пользовательские записи legacy history.\\n\\n' +
                    'НЕ будут удалены: пользователи, профили, ответы опроса, skin type, concerns, allergies, полки, продукты и ingredient knowledge.\\n\\nПродолжить?'
                )) return;
                button.disabled = true;
                button.textContent = 'Очищаем…';
                try {
                    const data = await historyAdminRequest('POST', '/api/admin/history/clear');
                    alert(`История очищена. Удалено analysis: ${data.analyses_deleted}; legacy-записей: ${data.legacy_history_deleted}.`);
                    location.reload();
                } catch (error) {
                    alert(`Не удалось очистить историю: ${error.message}`);
                    button.disabled = false;
                    button.textContent = 'Очистить историю';
                }
            }

            loadAnalysisHistoryStatus();
            
            function toggleAll(checked) {
                document.querySelectorAll('.product-checkbox').forEach(cb => cb.checked = checked);
            }

            function getSelectedIds() {
                return Array.from(document.querySelectorAll('.product-checkbox:checked')).map(cb => cb.value);
            }

            async function bulkAction(action) {
                const ids = getSelectedIds();
                if (ids.length === 0) {
                    alert('Выберите хотя бы один продукт');
                    return;
                }
                
                const messages = {
                    'approve': 'Одобрить выбранные продукты?',
                    'reject': 'Отклонить выбранные продукты?',
                    'delete': 'Удалить выбранные продукты?'
                };
                
                if (!confirm(messages[action])) return;
                
                const endpoints = {
                    'approve': '/api/admin/bulk-approve',
                    'reject': '/api/admin/bulk-reject',
                    'delete': '/api/admin/bulk-delete'
                };
                
                try {
                    const response = await fetch(endpoints[action], {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ids: ids})
                    });
                    const data = await response.json();
                    alert(data.message);
                    location.reload();
                } catch (error) {
                    alert('Ошибка: ' + error.message);
                }
            }
            
            function approve(id) {
                if (!confirm('Одобрить этот продукт?')) return;
                fetch('/api/admin/approve-product/' + id, { method: 'POST' })
                    .then(r => r.json())
                    .then(data => { alert(data.message || '✅ Одобрено!'); location.reload(); })
                    .catch(() => alert('Ошибка'));
            }
            function reject(id) {
                if (!confirm('Отклонить этот продукт?')) return;
                fetch('/api/admin/reject-product/' + id, { method: 'POST' })
                    .then(r => r.json())
                    .then(data => { alert(data.message || '❌ Отклонено!'); location.reload(); })
                    .catch(() => alert('Ошибка'));
            }
            function deleteProduct(id) {
                if (!confirm('🗑️ Удалить этот продукт навсегда?')) return;
                fetch('/api/admin/delete-product/' + id, { method: 'DELETE' })
                    .then(r => r.json())
                    .then(data => { alert(data.message || '🗑️ Удалено!'); location.reload(); })
                    .catch(() => alert('Ошибка'));
            }
            function filterIngredients() {
                const q = (document.getElementById('ingredient-search').value || '').toLowerCase();
                document.querySelectorAll('.ingredient-row').forEach(tr => {
                    const name = (tr.getAttribute('data-name') || '').toLowerCase();
                    tr.style.display = (!q || name.includes(q)) ? '' : 'none';
                });
            }
            async function enrichIngredient(id, btn) {
                if (!confirm('🔬 Запустить AI enrichment для этого ингредиента?')) return;
                btn.disabled = true; btn.textContent = '⏳';
                try {
                    const r = await fetch('/api/admin/enrich-ingredient/' + id, { method: 'POST' });
                    const data = await r.json();
                    alert(data.message || 'Готово');
                } catch (e) { alert('Ошибка: ' + e.message); }
                location.reload();
            }
            // ===== Score Engine: Production + Calibration SPA =====
            const SE = { run: null, prod: null, cand: null, summary: null, cmp: null, candId: null };
            async function j(method, url, body){
                const o = { method: method, headers: {'Content-Type':'application/json'} };
                if (body) o.body = JSON.stringify(body);
                const r = await fetch(url, o);
                return r.json();
            }
            function switchSeTab(tab){
                document.querySelectorAll('.se-sub').forEach(el => el.classList.remove('active'));
                document.querySelectorAll('.se-btn').forEach(el => el.classList.remove('active'));
                document.getElementById('se-' + tab).classList.add('active');
                document.querySelector(`.se-btn[onclick="switchSeTab('${tab}')"]`).classList.add('active');
                if (tab === 'production') loadProduction();
                if (tab === 'calibration') loadCalRuns();
            }
            async function loadProduction(){
                const d = await j('GET', '/admin/calibration/api/production');
                const p = d.production || {};
                SE.prod = p;
                const hist = (d.history || []).map(h => `<tr><td>${h.version}</td><td>${h.event}</td><td>${h.note||''}</td><td>${h.applied_at||''}</td></tr>`).join('');
                document.getElementById('prod-view').innerHTML =
                    `<div class="kv"><b>Version</b><span>${p.version}</span>` +
                    `<b>Saturation scale</b><span>${p.saturation_scale}</span>` +
                    `<b>Config</b><span class="mono">${JSON.stringify(p.config||{})}</span>` +
                    `<b>Applied</b><span>${p.applied_at||''} · ${p.applied_by||''}</span></div>` +
                    `<h3 style="margin-top:16px">Release / change history</h3>` +
                    `<table style="font-size:12px"><tr><th>Version</th><th>Event</th><th>Note</th><th>When</th></tr>${hist}</table>`;
            }
            async function loadCalRuns(){
                const o = await j('GET', '/admin/calibration/api/overview');
                const runs = (o.runs || []).filter(r => r.status === 'completed');
                document.getElementById('cal-runs').innerHTML = runs.map(r =>
                    `<div class="cal-run" id="run-${r.run_key}" onclick="selectRun('${r.run_key}')">` +
                    `<b>${r.run_key}</b><br>products=${r.product_count} profiles=${r.profile_count} cases=${r.case_count}<br>` +
                    `<span class="mono">${r.created_at||''}</span></div>`).join('') ||
                    '<div style="padding:12px">Нет завершённых runs.</div>';
                if (runs.length && !SE.run) selectRun(runs[0].run_key);
            }
            async function selectRun(key){
                SE.run = key;
                document.querySelectorAll('.cal-run').forEach(el => el.classList.remove('sel'));
                const b = document.getElementById('run-' + key); if (b) b.classList.add('sel');
                const s = await j('GET', '/admin/calibration/api/summary/' + key);
                SE.summary = s;
                renderSummary(s);
                loadCandidates();
            }
            function renderSummary(s){
                const st = s.overall_status;
                const cls = st === 'ХОРОШАЯ КАЛИБРОВКА' ? 'st-good' : (st === 'СИЛЬНЫЙ ДРЕЙФ' ? 'st-bad' : 'st-drift');
                const v = s.verdict || {};
                const drifts = (s.drift_groups || []).map(d =>
                    `<div class="drift-row"><span>${d.group}</span><span>${d.cases} кейсов · signed ${d.signed_error}</span><span><b>${d.verdict}</b></span></div>`).join('');
                const cases = (s.top_cases || []).map(c =>
                    `<div class="case-row" onclick="openCase('${s.run_key}',${c.product_id},'${c.profile_id}')">` +
                    `<b>${c.product}</b> + ${c.profile}<br>AI ${c.estimate} (${c.range_min}–${c.range_max}) → Score ${c.score} → Δ ${c.difference>0?'+':''}${c.difference}</div>`).join('');
                document.getElementById('cal-summary').innerHTML =
                    `<div class="se-card"><h3>📊 Overview — ${s.run_key}</h3>` +
                    `<div style="margin-bottom:10px"><span class="status-badge ${cls}">${st}</span></div>` +
                    `<div class="metric-grid">` +
                    `<div class="metric"><div class="v">${v.cases}</div><div class="l">Cases</div></div>` +
                    `<div class="metric"><div class="v">${v.mae}</div><div class="l">MAE</div></div>` +
                    `<div class="metric"><div class="v">${v.median_error}</div><div class="l">Median error</div></div>` +
                    `<div class="metric"><div class="v">${v.mean_signed_error}</div><div class="l">Signed error</div></div>` +
                    `<div class="metric"><div class="v">${v.coverage_pct}%</div><div class="l">Coverage</div></div>` +
                    `<div class="metric"><div class="v">${v.overestimated_pct}%</div><div class="l">Over</div></div>` +
                    `<div class="metric"><div class="v">${v.underestimated_pct}%</div><div class="l">Under</div></div>` +
                    `</div></div>` +
                    `<div class="se-card"><h3>🧭 Top Drift</h3>${drifts || '<div class="mono">—</div>'}</div>` +
                    `<div class="se-card"><h3>⚠️ Worst Cases (кликните для trace)</h3>${cases || '<div class="mono">—</div>'}</div>`;
            }
            async function openCase(runKey, pid, prid){
                const d = await j('GET', `/admin/calibration/api/case/${runKey}/${pid}/${prid}`);
                if (d.error) { alert('Кейс не найден'); return; }
                renderCaseDetail(d);
                document.getElementById('case-modal').style.display = 'flex';
            }
            function renderCaseDetail(d){
                const axes = (d.axis_breakdown||[]).map(a =>
                    `<tr><td>${a.axis}</td><td>${a.raw}</td><td>${a.weight}</td><td>${a.weighted}</td><td>${a.saturation_factor}</td><td>${a.contribution}</td></tr>`).join('');
                const st = d.profile_structured || {};
                const interactions = (d.interaction_breakdown||[]).length ? JSON.stringify(d.interaction_breakdown) : '—';
                const f = d.final_aggregation || {};
                document.getElementById('case-body').innerHTML =
                    `<div class="kv"><b>Product</b><span>${d.product}</span><b>Profile</b><span>${d.profile}</span>` +
                    `<b>Category</b><span>${d.category||'—'}</span>` +
                    `<b>AI estimate</b><span>${d.reference.estimate} (${d.reference.range_min}–${d.reference.range_max})</span>` +
                    `<b>Score Engine</b><span><b>${d.score}</b> · ${d.verdict}</span><b>Drift</b><span>${d.drift>0?'+':''}${d.drift}</span></div>` +
                    `<h3>Profile</h3><div class="mono">skin_type=${st.skin_type} · concerns=${(st.concerns||[]).join(',')||'—'} · therapy=${(st.therapy||[]).map(t=>t.id).join(',')||'—'} · procedures=${(st.procedures||[]).map(p=>p.id).join(',')||'—'}</div>` +
                    `<h3>Score Engine Trace (raw → weight → weighted → saturation → contribution)</h3>` +
                    `<table class="axis-table"><tr><th>Axis</th><th>raw</th><th>weight</th><th>weighted</th><th>sat</th><th>contrib</th></tr>${axes}</table>` +
                    `<h3>Profile Interactions</h3><div class="mono">${interactions}</div>` +
                    `<h3>Final aggregation</h3><div class="kv"><b>Saturation</b><span>${f.saturation_scale}</span><b>Weighted total</b><span>${f.weighted_total}</span><b>Sum weights</b><span>${f.sum_weights}</span><b>Final score</b><span><b>${f.final_score}</b></span></div>` +
                    `<h3>AI reason</h3><div class="mono">${d.reference.reason||'—'}</div>`;
            }
            function closeModal(){ document.getElementById('case-modal').style.display = 'none'; }

            async function loadCandidates(){
                const d = await j('GET', '/admin/calibration/api/candidates');
                SE.prod = d.production || SE.prod;
                const p = SE.prod;
                const hist = (d.candidates||[]).map(c =>
                    `<div class="drift-row"><span><b>${c.name}</b> <span class="status-badge ${c.status==='Applied'||c.status==='Approved'?'st-good':(c.status==='Rejected'?'st-bad':'st-drift')}">${c.status||'Draft'}</span></span><span class="mono">${JSON.stringify(c.config)}</span><span class="mono">${c.created_at||''}</span></div>`).join('');
                const ss = p.config ? p.config.saturation_scale : p.saturation_scale;
                document.getElementById('cand-editor').innerHTML =
                    `<div class="se-card"><h3>🧪 Candidate</h3>` +
                    `<div class="kv"><b>Production</b><span>Score Engine ${p.version} · saturation_scale=${ss}</span><b>Candidate</b><span>Draft</span></div>` +
                    `<div style="margin:12px 0"><label>Saturation scale: <input type="range" id="cand-ss" min="0.2" max="8" step="0.1" value="${ss}" oninput="candSSChanged()"> <b id="cand-ss-val">${ss}</b></label></div>` +
                    `<div id="cand-diff" class="mono"></div>` +
                    `<div style="margin:12px 0">` +
                    `<button class="btn" onclick="runCandidate()">▶ RUN CANDIDATE</button>` +
                    `<button class="btn green" onclick="applyCandidate()">✅ APPLY TO PRODUCTION</button>` +
                    `<button class="btn secondary" onclick="resetCandidate()">↺ Reset</button>` +
                    `<button class="btn secondary" onclick="toggleJson()">View JSON</button></div>` +
                    `<pre id="cand-json" class="mono" style="display:none;background:#fafafa;padding:8px;overflow:auto"></pre>` +
                    `<div id="cand-cmp"></div>` +
                    `<div style="margin-top:10px"><h3>Candidate history</h3>${hist || '<div class="mono">—</div>'}</div></div>`;
                SE.cand = { saturation_scale: ss };
                document.getElementById('cand-json').textContent = JSON.stringify(SE.cand, null, 2);
            }
            function candSSChanged(){
                const v = parseFloat(document.getElementById('cand-ss').value);
                document.getElementById('cand-ss-val').textContent = v;
                SE.cand = { saturation_scale: v };
                const p = SE.prod;
                const prodSS = p.config ? p.config.saturation_scale : p.saturation_scale;
                document.getElementById('cand-diff').innerHTML = (prodSS !== v) ?
                    `<div class="diff-pair"><span class="from">saturation_scale: ${prodSS}</span><span class="to">→ ${v}</span></div>` :
                    '<div>без изменений относительно Production</div>';
                document.getElementById('cand-json').textContent = JSON.stringify(SE.cand, null, 2);
            }
            function resetCandidate(){
                const p = SE.prod;
                const ss = p.config ? p.config.saturation_scale : p.saturation_scale;
                document.getElementById('cand-ss').value = ss;
                candSSChanged();
            }
            function toggleJson(){ const e = document.getElementById('cand-json'); e.style.display = e.style.display==='none'?'block':'none'; }
            async function runCandidate(){
                if (!SE.run) { alert('Сначала выберите run'); return; }
                const d = await j('POST','/admin/calibration/api/candidates', { name: 'Candidate', run_key: SE.run, config: SE.cand });
                if (d.error) { alert(d.error); return; }
                document.getElementById('cand-cmp').innerHTML = 'Запуск candidate…';
                const r = await j('POST', `/admin/calibration/api/candidates/${d.id}/run`, { run_key: SE.run });
                if (r.error) { alert(r.error); return; }
                SE.cmp = r; SE.candId = d.id;
                renderCompare(r);
            }
            function renderCompare(r){
                const dlt = (a,b)=> (typeof a==='number' && typeof b==='number') ? ((b-a>0?'+':'') + (Math.round((b-a)*100)/100)) : '';
                const row = (name,p,c)=> `<tr><td>${name}</td><td>${p}</td><td>${c}</td><td>${dlt(p,c)}</td></tr>`;
                const prod = r.production, cand = r.candidate;
                const top = (r.top_cases||[]).map(c=>`<div class="case-row">${c.product} + ${c.profile}<br>AI ${c.estimate} · Prod ${c.prod_score} (Δ ${c.prod_drift>0?'+':''}${c.prod_drift}) → Cand ${c.cand_score} (Δ ${c.cand_drift>0?'+':''}${c.cand_drift})</div>`).join('');
                document.getElementById('cand-cmp').innerHTML =
                    `<h3>Production vs Candidate</h3>` +
                    `<table class="axis-table"><tr><th>Metric</th><th>Production</th><th>Candidate</th><th>Δ</th></tr>` +
                    row('MAE', prod.mae, cand.mae) + row('Median error', prod.median_abs_error, cand.median_abs_error) +
                    row('Signed error', prod.mean_signed_error, cand.mean_signed_error) +
                    row('Coverage', (prod.range_coverage*100).toFixed(1)+'%', (cand.range_coverage*100).toFixed(1)+'%') +
                    row('Over', (prod.overestimation_rate*100).toFixed(1)+'%', (cand.overestimation_rate*100).toFixed(1)+'%') +
                    row('Under', (prod.underestimation_rate*100).toFixed(1)+'%', (cand.underestimation_rate*100).toFixed(1)+'%') +
                    `</table>` +
                    `<div style="margin-top:10px">Улучшено ${r.improved_cases} · Ухудшено ${r.worsened_cases}</div>` +
                    `<h3 style="margin-top:12px">Candidate case comparison (TOP-5)</h3>${top}`;
            }
            async function applyCandidate(){
                if (!SE.cand) { alert('Нет candidate'); return; }
                const p = SE.prod;
                const prodCfg = p.config || {};
                const changes = Object.keys(SE.cand).filter(k => SE.cand[k] !== prodCfg[k]);
                if (!changes.length) { alert('Нет изменений для применения'); return; }
                const msg = 'Применить Candidate в Production?\\n\\nProduction: ' + p.version + '\\nChanges:\\n' + changes.map(k => `${k}: ${prodCfg[k]} → ${SE.cand[k]}`).join('\\n');
                if (!confirm(msg)) return;
                const r = await j('POST','/admin/calibration/api/production/apply', { config: SE.cand, note: 'apply candidate', author: 'admin' });
                if (r.error) { alert(r.error); return; }
                alert('Применено. Новая версия: ' + r.version);
                loadProduction(); loadCandidates();
            }
            async function rollbackProduction(){
                if (!confirm('Откатить к предыдущей production версии?')) return;
                const r = await j('POST','/admin/calibration/api/production/rollback', { note: 'manual rollback', author: 'admin' });
                if (r.error) { alert(r.error); return; }
                alert('Откачено. Версия: ' + r.version);
                loadProduction(); loadCandidates();
            }
            </script>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html)

    # === АДМИН: ЭНДПОИНТЫ С BASIC AUTH ===
    @app.get("/api/admin/pending-products")
    async def get_pending_products(_: bool = Depends(verify_admin)):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.*, u.email as user_email 
            FROM pending_products p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE p.status = 'pending'
            ORDER BY p.created_at DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
        return {"products": [dict(row) for row in rows]}

    @app.get("/api/admin/history/status")
    async def admin_analysis_history_status(_: bool = Depends(verify_admin)):
        from .score_version import SCORE_ENGINE_VERSION
        return {
            "stale_count": get_stale_analysis_count(),
            "score_engine_version": SCORE_ENGINE_VERSION,
        }

    @app.post("/api/admin/history/recalculate-stale")
    async def admin_recalculate_stale_analysis(_: bool = Depends(verify_admin)):
        from .ingredient_repository import IngredientRepository
        from .shelf_service import _build_user_profile, recalculate_stale_analysis

        stale = get_stale_analysis_records()
        processed = updated = 0
        errors = []
        if not stale:
            return {"processed": 0, "updated": 0, "failed": 0, "errors": []}

        user_ids = sorted({int(row["user_id"]) for row in stale if row.get("user_id") is not None})
        conn = get_connection()
        try:
            users = {
                int(row["id"]): dict(row)
                for row in conn.execute(
                    f"""
                    SELECT id, skin_type, age, concerns, allergies, custom_text
                    FROM users
                    WHERE id IN ({",".join("?" for _ in user_ids)})
                    """,
                    user_ids,
                ).fetchall()
            } if user_ids else {}
        finally:
            conn.close()

        try:
            knowledge = IngredientRepository().get_canonical_knowledge_map()
        except Exception:
            logger.exception("Admin stale analysis recalculation could not load ingredient knowledge")
            knowledge = None

        profile_cache = {}
        product_cache = {}
        for analysis in stale:
            processed += 1
            analysis_id = analysis.get("id")
            user_id = analysis.get("user_id")
            try:
                if user_id is None or int(user_id) not in users:
                    raise ValueError("Пользователь анализа не найден")
                user_id = int(user_id)
                user = users[user_id]
                if user_id not in profile_cache:
                    profile_cache[user_id] = _build_user_profile(user)
                if analysis.get("product_id") is not None:
                    product_key = ("id", int(analysis["product_id"]))
                    if product_key not in product_cache:
                        product_cache[product_key] = get_product_by_id(product_key[1])
                elif analysis.get("slug"):
                    product_key = ("slug", analysis["slug"])
                    if product_key not in product_cache:
                        product_cache[product_key] = get_product_by_slug(product_key[1])
                else:
                    product_key = None
                product = product_cache.get(product_key) if product_key else None
                if knowledge is None:
                    raise RuntimeError("Не удалось загрузить ingredient knowledge")

                refreshed = recalculate_stale_analysis(
                    user,
                    analysis,
                    product,
                    scoring_profile=profile_cache[user_id],
                    knowledge=knowledge,
                )
                if not refreshed:
                    raise ValueError("Score Engine не вернул корректный результат")
                updated += 1
            except Exception as exc:
                logger.exception("Admin failed to recalculate analysis %s", analysis_id)
                message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "Внутренняя ошибка пересчёта"
                errors.append({"analysis_id": analysis_id, "error": message})

        return {
            "processed": processed,
            "updated": updated,
            "failed": len(errors),
            "errors": errors,
        }

    @app.post("/api/admin/history/clear")
    async def admin_clear_analysis_history(_: bool = Depends(verify_admin)):
        return clear_analysis_history()

    @app.post("/api/admin/bulk-approve")
    async def bulk_approve(request: Request, _: bool = Depends(verify_admin)):
        """Массовое одобрение продуктов"""
        data = await request.json()
        product_ids = data.get('ids', [])
        
        if not product_ids:
            raise HTTPException(status_code=400, detail="Нет IDs для обработки")
        
        conn = get_connection()
        cursor = conn.cursor()
        
        approved_count = 0
        for product_id in product_ids:
            cursor.execute("SELECT * FROM pending_products WHERE id = ? AND status = 'pending'", (product_id,))
            pending = cursor.fetchone()
            
            if pending:
                from .product_dedup import find_or_create_canonical_product
                find_or_create_canonical_product({
                    "name": pending['product_name'],
                    "ingredients": pending['ingredients'],
                    "slug": pending['slug'],
                    "source_type": "catalog",
                })
                
                cursor.execute('''
                    UPDATE pending_products 
                    SET status = 'approved', reviewed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (product_id,))
                approved_count += 1
        
        conn.commit()
        conn.close()
        
        return {"message": f"✅ Одобрено {approved_count} продуктов"}

    @app.post("/api/admin/bulk-reject")
    async def bulk_reject(request: Request, _: bool = Depends(verify_admin)):
        """Массовое отклонение продуктов"""
        data = await request.json()
        product_ids = data.get('ids', [])
        
        if not product_ids:
            raise HTTPException(status_code=400, detail="Нет IDs для обработки")
        
        conn = get_connection()
        cursor = conn.cursor()
        
        rejected_count = 0
        for product_id in product_ids:
            cursor.execute('''
                UPDATE pending_products 
                SET status = 'rejected', reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'pending'
            ''', (product_id,))
            if cursor.rowcount > 0:
                rejected_count += 1
        
        conn.commit()
        conn.close()
        
        return {"message": f"❌ Отклонено {rejected_count} продуктов"}

    @app.post("/api/admin/bulk-delete")
    async def bulk_delete(request: Request, _: bool = Depends(verify_admin)):
        """Массовое удаление продуктов"""
        data = await request.json()
        product_ids = data.get('ids', [])
        
        if not product_ids:
            raise HTTPException(status_code=400, detail="Нет IDs для обработки")
        
        conn = get_connection()
        cursor = conn.cursor()
        
        deleted_count = 0
        for product_id in product_ids:
            cursor.execute("DELETE FROM pending_products WHERE id = ?", (product_id,))
            if cursor.rowcount > 0:
                deleted_count += 1
        
        conn.commit()
        conn.close()
        
        return {"message": f"🗑️ Удалено {deleted_count} продуктов"}

    @app.post("/api/admin/approve-product/{product_id}")
    async def approve_product(product_id: int, _: bool = Depends(verify_admin)):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pending_products WHERE id = ? AND status = 'pending'", (product_id,))
        pending = cursor.fetchone()
        
        if not pending:
            conn.close()
            raise HTTPException(status_code=404, detail="Продукт не найден или уже обработан")
        
        from .product_dedup import find_or_create_canonical_product
        find_or_create_canonical_product({
            "name": pending['product_name'],
            "ingredients": pending['ingredients'],
            "slug": pending['slug'],
            "source_type": "catalog",
        })
        
        cursor.execute('''
            UPDATE pending_products 
            SET status = 'approved', reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (product_id,))
        conn.commit()
        conn.close()
        
        return {"message": "Продукт одобрен и добавлен в базу! ✅"}

    @app.post("/api/admin/reject-product/{product_id}")
    async def reject_product(product_id: int, _: bool = Depends(verify_admin)):
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE pending_products 
            SET status = 'rejected', reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (product_id,))
        
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Продукт не найден")
        
        conn.commit()
        conn.close()
        
        return {"message": "Продукт отклонён ❌"}

    @app.delete("/api/admin/delete-product/{product_id}")
    async def delete_product(product_id: int, _: bool = Depends(verify_admin)):
        # Проверяем в pending
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pending_products WHERE id = ?", (product_id,))
        pending = cursor.fetchone()
        
        if pending:
            cursor.execute("DELETE FROM pending_products WHERE id = ?", (product_id,))
            conn.commit()
            conn.close()
            return {"message": "Продукт удалён из модерации 🗑️"}
        
        conn.close()
        
        # Проверяем в основной базе
        conn_products = get_connection(PRODUCTS_DB)
        cursor_products = conn_products.cursor()
        cursor_products.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = cursor_products.fetchone()
        
        if product:
            cursor_products.execute("DELETE FROM products WHERE id = ?", (product_id,))
            conn_products.commit()
            conn_products.close()
            return {"message": "Продукт удалён из базы 🗑️"}
        
        conn_products.close()
        
        raise HTTPException(status_code=404, detail="Продукт не найден")

    @app.post("/api/admin/enrich-ingredient/{ingredient_id}")
    async def enrich_ingredient(ingredient_id: int, _: bool = Depends(verify_admin)):
        """Ручной запуск AI enrichment для конкретного ингредиента."""
        from .database import AIDERMY_DB
        from .ingredient_enrichment import enrich_unknown_ingredients

        conn = get_connection(AIDERMY_DB)
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT inci_name, canonical_name, normalized_name FROM ingredients_catalog WHERE id = ?",
            (ingredient_id,),
        ).fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Ингредиент не найден")

        name = row["inci_name"] or row["normalized_name"]
        saved = await enrich_unknown_ingredients([name])
        if saved:
            return {"message": f"🔬 Ингредиент «{name}» обогащён"}
        return {"message": f"Не удалось обогатить «{name}» (нет AI-ключа или не удалось распознать)"}