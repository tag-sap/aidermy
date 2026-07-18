from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from .models import CheckRequest, CheckResponse, CheckWithIngredientsRequest
from .services import check_product_with_ai, check_product_with_ingredients
from .database import init_db, get_all_ingredients, get_all_check_history, save_check_result, get_check_stats, get_connection, search_products
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

# === SESSION MIDDLEWARE (для Google OAuth) ===
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("JWT_SECRET_KEY", "your-secret-key")
)

app.include_router(auth_router)

# === HEALTH CHECK ===
@app.get("/api/health")
async def health():
    return {"status": "ok", "deepseek": "connected" if DEEPSEEK_API_KEY else "missing"}

# === PRODUCTS ===
@app.get("/api/products")
async def get_products(q: str = ""):
    products = search_products(q)
    return {"products": products}

# === CHECK ===
@app.post("/api/check", response_model=CheckResponse)
async def check_product(request: CheckRequest):
    try:
        result = await check_product_with_ai(
            request.product_name,
            request.skin_type,
            request.profile.dict()
        )
        
        slug = result.get('slug')
        
        save_check_result(
            request.product_name,
            request.skin_type,
            result.get("score", 50),
            result.get("verdict", "Нейтрально"),
            result.get("summary", "Не удалось получить рекомендацию."),
            "",
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
async def check_with_ingredients(request: CheckWithIngredientsRequest):
    try:
        from .services import generate_slug
        result = await check_product_with_ingredients(
            request.product_name,
            request.skin_type,
            request.profile.dict(),
            request.ingredients
        )
        
        slug = generate_slug(request.product_name)
        
        save_ingredients(request.product_name, request.ingredients, slug)
        
        save_check_result(
            request.product_name,
            request.skin_type,
            result.get("score", 50),
            result.get("verdict", "С осторожностью"),
            result.get("summary", "Не удалось проанализировать состав."),
            request.ingredients,
            slug
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
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")

# === АДМИН-ПАНЕЛЬ ===
# Защита HTTP Basic Auth
security = HTTPBasic()

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = "admin"
    correct_password = "aidermy2026"  # Поменяй на свой пароль!
    
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
    ingredients = get_all_ingredients()
    stats = get_check_stats()
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Aidermy Admin</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #f5f5f5;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 1400px;
                margin: 0 auto;
            }}
            .header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 30px;
                flex-wrap: wrap;
                gap: 10px;
            }}
            h1 {{
                color: #1a1a1a;
                font-size: 28px;
                margin: 0;
            }}
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 16px;
                margin-bottom: 30px;
            }}
            .stat-card {{
                background: white;
                padding: 20px;
                border-radius: 12px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }}
            .stat-card .number {{
                font-size: 32px;
                font-weight: 700;
                color: #FF4F00;
            }}
            .stat-card .label {{
                font-size: 14px;
                color: #666;
                margin-top: 4px;
            }}
            .table-wrap {{
                background: white;
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                margin-bottom: 30px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 14px;
            }}
            th {{
                background: #FF4F00;
                color: white;
                padding: 12px 16px;
                text-align: left;
                font-weight: 600;
            }}
            td {{
                padding: 12px 16px;
                border-bottom: 1px solid #eee;
            }}
            tr:hover {{
                background: #f9f9f9;
            }}
            .badge {{
                background: #FF4F00;
                color: white;
                padding: 2px 10px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 600;
                display: inline-block;
            }}
            .footer {{
                text-align: center;
                color: #999;
                font-size: 13px;
                margin-top: 30px;
            }}
            .refresh-btn {{
                background: #FF4F00;
                color: white;
                border: none;
                padding: 10px 24px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 600;
            }}
            .refresh-btn:hover {{
                opacity: 0.9;
            }}
            @media (max-width: 600px) {{
                .stats-grid {{
                    grid-template-columns: 1fr 1fr;
                }}
                .table-wrap {{
                    overflow-x: auto;
                }}
                td, th {{
                    padding: 8px 10px;
                    font-size: 12px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🧴 Aidermy Admin</h1>
                <button class="refresh-btn" onclick="location.reload()">🔄 Обновить</button>
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
                            <th>Дата</th>
                        </tr>
                    </thead>
                    <tbody>
    """
    
    for row in history[:50]:
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
    
    html += """
                    </tbody>
                </table>
            </div>
            
            <div class="footer">
                <p>🟢 База данных работает · Показано последних {len(history)} проверок</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)

# === АДМИН: СПИСОК PENDING ПРОДУКТОВ ===
from .auth_routes import get_pending_products, approve_product, reject_product

# Подключаем админ-роуты из auth_routes
app.get("/api/admin/pending-products")(get_pending_products)
app.post("/api/admin/approve-product/{product_id}")(approve_product)
app.post("/api/admin/reject-product/{product_id}")(reject_product)