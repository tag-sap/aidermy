from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from .models import CheckRequest, CheckResponse, CheckWithIngredientsRequest
from .services import check_product_with_ai, check_product_with_ingredients
from .cache import save_ingredients
from .database import init_db, get_all_ingredients, get_all_check_history, save_check_result, get_check_stats, get_connection
import os
from dotenv import load_dotenv

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

# === ЗАЩИТА ===
security = HTTPBasic()

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != "admin" or credentials.password != "aidermy2026":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True

# === ЭНДПОИНТЫ ===

@app.post("/api/check", response_model=CheckResponse)
async def check_product(request: CheckRequest):
    try:
        result = await check_product_with_ai(
            request.product_name,
            request.skin_type,
            request.profile.dict()
        )
        
        slug = result.get('slug')  # <- получаем slug
        
        save_check_result(
            request.product_name,
            request.skin_type,
            result.get("score", 50),
            result.get("verdict", "Нейтрально"),
            result.get("summary", "Не удалось получить рекомендацию."),
            "",
            slug  # <- сохраняем
        )
        
        return CheckResponse(
            score=result.get("score", 50),
            verdict=result.get("verdict", "Нейтрально"),
            summary=result.get("summary", "Не удалось получить рекомендацию."),
            safe_ingredients=result.get("safe_ingredients", []),
            caution_ingredients=result.get("caution_ingredients", []),
            cached=False,
            slug=slug  # <- возвращаем
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")
@app.post("/api/check-with-ingredients", response_model=CheckResponse)
async def check_with_ingredients(request: CheckWithIngredientsRequest):
    try:
        result = await check_product_with_ingredients(
            request.product_name,
            request.skin_type,
            request.profile.dict(),
            request.ingredients
        )

        save_ingredients(request.product_name, request.ingredients)
        
        save_check_result(
            request.product_name,
            request.skin_type,
            result.get("score", 50),
            result.get("verdict", "С осторожностью"),
            result.get("summary", "Не удалось проанализировать состав."),
            request.ingredients  # состав передан
        )

        return CheckResponse(
            score=result.get("score", 50),
            verdict=result.get("verdict", "С осторожностью"),
            summary=result.get("summary", "Не удалось проанализировать состав."),
            safe_ingredients=result.get("safe_ingredients", []),
            caution_ingredients=result.get("caution_ingredients", []),
            cached=False
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "deepseek": "connected" if DEEPSEEK_API_KEY else "missing"
    }
@app.get("/api/products")
async def get_products(q: str = ""):
    from .database import search_products
    products = search_products(q)
    return {"products": products}
# === АДМИНКА ===

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(_: bool = Depends(verify_admin)):
    # Получаем данные из обеих таблиц
    history = get_all_check_history(limit=100)
    ingredients = get_all_ingredients()
    stats = get_check_stats()
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Aidermy Admin</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{ font-family: -apple-system, sans-serif; padding: 20px; background: #f4f4f4; margin: 0; }}
            .container {{ max-width: 1400px; margin: 0 auto; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin: 20px 0; }}
            .stat-card {{ background: white; padding: 16px 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
            .stat-card .number {{ font-size: 28px; font-weight: 700; color: #FF4F00; }}
            .stat-card .label {{ font-size: 14px; color: #666; margin-top: 4px; }}
            .tabs {{ display: flex; gap: 8px; margin: 20px 0; }}
            .tab-btn {{ padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; background: #e0e0e0; }}
            .tab-btn.active {{ background: #FF4F00; color: white; }}
            .tab-content {{ display: none; }}
            .tab-content.active {{ display: block; }}
            .table-wrap {{ background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-top: 20px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th {{ background: #FF4F00; color: white; padding: 12px 16px; text-align: left; font-size: 14px; }}
            td {{ padding: 12px 16px; border-bottom: 1px solid #eee; font-size: 14px; vertical-align: middle; }}
            tr:hover {{ background: #f9f9f9; }}
            .product-name {{ font-weight: 600; }}
            .badge {{ background: #FF4F00; color: white; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; display: inline-block; }}
            .delete-btn {{ color: #e74c3c; cursor: pointer; font-size: 16px; text-decoration: none; }}
            .delete-btn:hover {{ color: #c0392b; }}
            .footer {{ margin-top: 30px; text-align: center; color: #999; font-size: 13px; }}
            .refresh-btn {{ background: #FF4F00; color: white; border: none; padding: 8px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; }}
            .refresh-btn:hover {{ opacity: 0.9; }}
            @media (max-width: 600px) {{
                .stats-grid {{ grid-template-columns: 1fr 1fr; }}
                .table-wrap {{ overflow-x: auto; }}
                td, th {{ padding: 8px 10px; font-size: 12px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🧴 Aidermy Admin</h1>
                <div>
                    <button class="refresh-btn" onclick="location.reload()">🔄 Обновить</button>
                </div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="number">{stats['total']}</div>
                    <div class="label">📊 Всего проверок</div>
                </div>
                <div class="stat-card">
                    <div class="number">{stats['unique_products']}</div>
                    <div class="label">🧴 Уникальных продуктов</div>
                </div>
                <div class="stat-card">
                    <div class="number">{stats['avg_score']}</div>
                    <div class="label">⭐ Средний балл</div>
                </div>
            </div>

            <div class="tabs">
                <button class="tab-btn active" onclick="switchTab('history')">📋 История проверок ({len(history)})</button>
                <button class="tab-btn" onclick="switchTab('ingredients')">📦 Составы ({len(ingredients)})</button>
            </div>

            <!-- Вкладка: История проверок -->
            <div id="tab-history" class="tab-content active">
                <div class="table-wrap">
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Продукт</th>
                                <th>Тип кожи</th>
                                <th>Оценка</th>
                                <th>Вердикт</th>
                                <th>Резюме</th>
                                <th>Состав</th>
                                <th>Дата</th>
                                <th>Действие</th>
                            </tr>
                        </thead>
                        <tbody>
    """
    
    for row in history:
        ingredients_display = row.get('ingredients', '') or '—'
        if len(ingredients_display) > 100:
            ingredients_display = ingredients_display[:100] + '...'
        
        html += f"""
                            <tr>
                                <td>{row['id']}</td>
                                <td><span class="product-name">{row['product_name']}</span></td>
                                <td>{row['skin_type']}</td>
                                <td><span class="badge">{row['score']}%</span></td>
                                <td>{row['verdict']}</td>
                                <td style="font-size: 12px; max-width: 250px; word-break: break-word;">{row['summary'][:80]}{'...' if len(row['summary']) > 80 else ''}</td>
                                <td style="font-size: 12px; max-width: 200px; word-break: break-word;">{ingredients_display}</td>
                                <td style="font-size: 12px;">{row['created_at']}</td>
                                <td><a href="#" class="delete-btn" data-id="{row['id']}" data-table="check_history">🗑️</a></td>
                            </tr>
        """
    
    html += """
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Вкладка: Составы (ingredients) -->
            <div id="tab-ingredients" class="tab-content">
                <div class="table-wrap">
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Продукт</th>
                                <th>Состав (INCI)</th>
                                <th>Дата</th>
                                <th>Действие</th>
                            </tr>
                        </thead>
                        <tbody>
    """
    
    for row in ingredients:
        html += f"""
                            <tr>
                                <td>{row['id']}</td>
                                <td><span class="product-name">{row['product_name']}</span></td>
                                <td style="font-size: 12px; max-width: 400px; word-break: break-word;">{row['ingredients']}</td>
                                <td style="font-size: 12px;">{row['created_at']}</td>
                                <td><a href="#" class="delete-btn" data-id="{row['id']}" data-table="ingredients">🗑️</a></td>
                            </tr>
        """
    
    html += """
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="footer">
                <p>🟢 База данных работает · Показано последних {len(history)} проверок · {len(ingredients)} составов</p>
            </div>
        </div>
        <script>
            function switchTab(tab) {
                document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
                document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
                document.getElementById('tab-' + tab).classList.add('active');
                document.querySelector(`.tab-btn[onclick="switchTab('${tab}')"]`).classList.add('active');
            }
            
            document.querySelectorAll('.delete-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    e.preventDefault();
                    const id = btn.dataset.id;
                    const table = btn.dataset.table || 'check_history';
                    if (confirm('Удалить эту запись?')) {
                        const res = await fetch('/admin/delete/' + id + '?table=' + table, { method: 'DELETE' });
                        if (res.ok) location.reload();
                    }
                });
            });
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)

@app.delete("/admin/delete/{record_id}")
async def delete_record(record_id: int, table: str = "check_history", _: bool = Depends(verify_admin)):
    conn = get_connection()
    cursor = conn.cursor()
    
    # Проверяем, что таблица существует и безопасна
    if table not in ["check_history", "ingredients"]:
        raise HTTPException(status_code=400, detail="Invalid table name")
    
    cursor.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    return {"success": True}
