from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from .models import CheckRequest, CheckResponse, CheckWithIngredientsRequest
from .services import check_product_with_ai, check_product_with_ingredients
from .database import init_db, get_all_ingredients, get_all_check_history, save_check_result, get_check_stats, get_connection, search_products, PRODUCTS_DB
import os
from dotenv import load_dotenv
from .auth_routes import router as auth_router

load_dotenv()
init_db()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

app = FastAPI(
    title="Aidermy API",
    version="1.0",
    description="API для проверки косметики с помощью AI"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("JWT_SECRET_KEY", "your-secret-key")
)

app.include_router(auth_router)

@app.get("/api/health")
async def health():
    return {"status": "ok", "deepseek": "connected" if DEEPSEEK_API_KEY else "missing"}

@app.get("/api/products")
async def get_products(q: str = ""):
    products = search_products(q)
    return {"products": products}

@app.post("/api/check", response_model=CheckResponse)
async def check_product(request: CheckRequest):
    try:
        result = await check_product_with_ai(
            request.product_name,
            request.skin_type,
            request.profile.dict()
        )
        
        slug = result.get('slug')
        
        # Сохраняем только если есть состав
        if result.get("ingredients"):
            save_check_result(
                request.product_name,
                request.skin_type,
                result.get("score", 50),
                result.get("verdict", "Нейтрально"),
                result.get("summary", "Не удалось получить рекомендацию."),
                result.get("ingredients", ""),
                slug
            )
        
        return CheckResponse(
            score=result.get("score", 50),
            verdict=result.get("verdict", "Нейтрально"),
            summary=result.get("summary", "Не удалось получить рекомендацию."),
            safe_ingredients=result.get("safe_ingredients", []),
            caution_ingredients=result.get("caution_ingredients", []),
            cached=False,
            slug=slug
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")

@app.post("/api/check-with-ingredients", response_model=CheckResponse)
async def check_with_ingredients(request: Request, check_request: CheckWithIngredientsRequest):
    try:
        from .services import generate_slug, check_product_with_ingredients
        from .auth_routes import save_pending_product
        from .auth import get_current_user_from_token
        
        result = await check_product_with_ingredients(
            check_request.product_name,
            check_request.skin_type,
            check_request.profile.dict(),
            check_request.ingredients
        )
        
        slug = generate_slug(check_request.product_name)
        
        # Сохраняем в историю (только если есть состав)
        save_check_result(
            check_request.product_name,
            check_request.skin_type,
            result.get("score", 50),
            result.get("verdict", "С осторожностью"),
            result.get("summary", "Не удалось проанализировать состав."),
            check_request.ingredients,
            slug
        )
        
        user_id = None
        auth_header = request.headers.get("Authorization")
        if auth_header:
            token = auth_header.split(" ")[1] if " " in auth_header else auth_header
            user = await get_current_user_from_token(token)
            if user:
                user_id = user['id']
        
        # Отправляем в модерацию только если есть состав и скор > 0
        if check_request.ingredients and result.get("score", 0) > 0:
            save_pending_product(
                product_name=check_request.product_name,
                ingredients=check_request.ingredients,
                user_id=user_id
            )
        
        return CheckResponse(
            score=result.get("score", 50),
            verdict=result.get("verdict", "С осторожностью"),
            summary=result.get("summary", "Не удалось проанализировать состав."),
            safe_ingredients=result.get("safe_ingredients", []),
            caution_ingredients=result.get("caution_ingredients", []),
            cached=False,
            slug=slug
        )
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка проверки: {str(e)}")

# === АДМИН-ПАНЕЛЬ ===
security = HTTPBasic()

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

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(_: bool = Depends(verify_admin)):
    # Получаем данные
    history = get_all_check_history(limit=100)
    stats = get_check_stats()
    
    # Только проверки с составом (не нулевые)
    filtered_history = [h for h in history if h.get('ingredients') and h['ingredients'].strip()]
    
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
    
    # Получаем пользователей
    users = []
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, email, name, is_verified, created_at 
            FROM users 
            ORDER BY created_at DESC
            LIMIT 50
        ''')
        users = cursor.fetchall()
        conn.close()
    except:
        pass
    
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
            </div>

            <!-- Вкладка: История -->
            <div id="tab-history" class="tab-content active">
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
                    <div class="table-header"><span>📦 Продукты на модерацию ({len(pending)})</span></div>
                    <table>
                        <thead><tr><th>ID</th><th>Название</th><th>Состав</th><th>Отправил</th><th>Дата</th><th>Действия</th></tr></thead>
                        <tbody>
    """
    
    if pending:
        for p in pending:
            row = dict(p)
            user_email = row.get('user_email', 'Аноним')
            html += f"""
                            <tr>
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
        html += """<tr><td colspan="6" class="empty-state">🎉 Нет продуктов на модерацию</td></tr>"""
    
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
            
            <div class="footer"><p>🟢 База данных работает</p></div>
        </div>

        <script>
        function switchTab(tab) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            document.getElementById('tab-' + tab).classList.add('active');
            document.querySelector(`.tab-btn[onclick="switchTab('${tab}')"]`).classList.add('active');
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

@app.post("/api/admin/approve-product/{product_id}")
async def approve_product(product_id: int, _: bool = Depends(verify_admin)):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pending_products WHERE id = ? AND status = 'pending'", (product_id,))
    pending = cursor.fetchone()
    
    if not pending:
        conn.close()
        raise HTTPException(status_code=404, detail="Продукт не найден или уже обработан")
    
    conn_products = get_connection(PRODUCTS_DB)
    cursor_products = conn_products.cursor()
    cursor_products.execute('''
        INSERT INTO products (name, ingredients, slug, saved_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ''', (pending['product_name'], pending['ingredients'], pending['slug']))
    conn_products.commit()
    conn_products.close()
    
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

# === АДМИН: УДАЛИТЬ ПРОДУКТ ===
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