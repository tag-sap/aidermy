from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from .models import CheckRequest, CheckResponse, CheckWithIngredientsRequest
from .services import check_product_with_ai, check_product_with_ingredients
from .cache import save_ingredients
from .database import init_db, get_all_ingredients, get_connection
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
        return CheckResponse(
            score=result.get("score", 50),
            verdict=result.get("verdict", "Нейтрально"),
            summary=result.get("summary", "Не удалось получить рекомендацию."),
            safe_ingredients=result.get("safe_ingredients", []),
            caution_ingredients=result.get("caution_ingredients", []),
            cached=False
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

# === АДМИНКА ===

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(_: bool = Depends(verify_admin)):
    ingredients = get_all_ingredients()
    
    # Статистика
    product_stats = {}
    for row in ingredients:
        name = row['product_name']
        product_stats[name] = product_stats.get(name, 0) + 1
    
    sorted_stats = sorted(product_stats.items(), key=lambda x: x[1], reverse=True)
    total_checks = len(ingredients)
    unique_products = len(product_stats)
    top_count = sorted_stats[0][1] if sorted_stats else 0
    top_products = sorted_stats[:5]
    
    # Генерируем строки таблицы
    table_rows = ""
    for row in ingredients:
        text = row['ingredients']
        short_text = text[:100] + "..." if len(text) > 100 else text
        table_rows += f"""
                        <tr>
                            <td>{row['id']}</td>
                            <td><span class="product-name">{row['product_name']}</span></td>
                            <td class="ingredients-cell" onclick="toggleIngredients(this)">
                                <span class="short">{short_text}</span>
                                <span class="full">{text}</span>
                                <button class="toggle-btn">показать всё</button>
                            </td>
                            <td>{row['created_at']}</td>
                            <td><a href="#" class="delete-btn" data-id="{row['id']}">🗑️</a></td>
                        </tr>
        """
    
    # Генерируем топ-5 продуктов
    top_html = ""
    if top_products:
        top_html = """
            <div style="background: white; border-radius: 12px; padding: 16px 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 20px;">
                <h3>🏆 Топ-5 популярных продуктов</h3>
                <ul class="top-products">
        """
        for i, (name, count) in enumerate(top_products):
            top_html += f"""
                    <li>
                        <span>{i+1}. {name}</span>
                        <span class="badge">{count} проверок</span>
                    </li>
            """
        top_html += """
                </ul>
            </div>
        """
    
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
            .table-wrap {{ background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-top: 20px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th {{ background: #FF4F00; color: white; padding: 12px 16px; text-align: left; font-size: 14px; }}
            td {{ padding: 12px 16px; border-bottom: 1px solid #eee; font-size: 14px; vertical-align: middle; }}
            tr:hover {{ background: #f9f9f9; }}
            .product-name {{ font-weight: 600; }}
            .ingredients-cell {{ max-width: 400px; word-break: break-word; font-size: 13px; color: #444; cursor: pointer; }}
            .ingredients-cell .short {{ display: inline; }}
            .ingredients-cell .full {{ display: none; }}
            .ingredients-cell .full.show {{ display: inline; }}
            .ingredients-cell .short.hide {{ display: none; }}
            .toggle-btn {{ color: #FF4F00; cursor: pointer; background: none; border: none; font-size: 13px; text-decoration: underline; padding: 0; margin-left: 8px; }}
            .badge {{ background: #FF4F00; color: white; padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; display: inline-block; }}
            .delete-btn {{ color: #e74c3c; cursor: pointer; font-size: 16px; text-decoration: none; }}
            .delete-btn:hover {{ color: #c0392b; }}
            .footer {{ margin-top: 30px; text-align: center; color: #999; font-size: 13px; }}
            .refresh-btn {{ background: #FF4F00; color: white; border: none; padding: 8px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; }}
            .refresh-btn:hover {{ opacity: 0.9; }}
            .top-products {{ list-style: none; padding: 0; margin: 0; }}
            .top-products li {{ padding: 4px 0; border-bottom: 1px solid #f0f0f0; display: flex; justify-content: space-between; }}
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
                    <div class="number">{total_checks}</div>
                    <div class="label">📊 Всего проверок</div>
                </div>
                <div class="stat-card">
                    <div class="number">{unique_products}</div>
                    <div class="label">🧴 Уникальных продуктов</div>
                </div>
                <div class="stat-card">
                    <div class="number">{total_checks}</div>
                    <div class="label">💾 Сохранённых составов</div>
                </div>
                <div class="stat-card">
                    <div class="number">{top_count}</div>
                    <div class="label">🏆 Самый частый продукт</div>
                </div>
            </div>

            {top_html}

            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Продукт</th>
                            <th>Состав</th>
                            <th>Дата</th>
                            <th>Действие</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_rows}
                    </tbody>
                </table>
            </div>
            <div class="footer">
                <p>🟢 База данных работает · Всего записей: {total_checks}</p>
            </div>
        </div>
        <script>
            function toggleIngredients(cell) {{
                const short = cell.querySelector('.short');
                const full = cell.querySelector('.full');
                const btn = cell.querySelector('.toggle-btn');
                if (full.classList.contains('show')) {{
                    full.classList.remove('show');
                    short.classList.remove('hide');
                    btn.textContent = 'показать всё';
                }} else {{
                    full.classList.add('show');
                    short.classList.add('hide');
                    btn.textContent = 'свернуть';
                }}
            }}
            
            document.querySelectorAll('.delete-btn').forEach(btn => {{
                btn.addEventListener('click', async (e) => {{
                    e.preventDefault();
                    const id = btn.dataset.id;
                    if (confirm('Удалить этот состав?')) {{
                        const res = await fetch('/admin/delete/' + id, {{ method: 'DELETE' }});
                        if (res.ok) location.reload();
                    }}
                }});
            }});
        </script>
    </body>
    </html>
    """
    
    # Подставляем данные
    html = html.replace("{total_checks}", str(total_checks))
    html = html.replace("{unique_products}", str(unique_products))
    html = html.replace("{top_count}", str(top_count))
    html = html.replace("{top_html}", top_html)
    html = html.replace("{table_rows}", table_rows)
    
    return HTMLResponse(content=html)

@app.delete("/admin/delete/{ingredient_id}")
async def delete_ingredient(ingredient_id: int, _: bool = Depends(verify_admin)):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ingredients WHERE id = ?", (ingredient_id,))
    conn.commit()
    conn.close()
    return {"success": True}