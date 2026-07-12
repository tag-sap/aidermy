from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
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
templates = Jinja2Templates(directory="templates")

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

# === АДМИНКА (БЕЗ JINJA2) ===

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(_: bool = Depends(verify_admin)):
    ingredients = get_all_ingredients()
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Aidermy Admin</title>
        <style>
            body { font-family: sans-serif; padding: 20px; background: #f4f4f4; }
            table { border-collapse: collapse; width: 100%; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
            th { background: #FF4F00; color: white; }
            tr:hover { background: #f9f9f9; }
            .status { padding: 10px 20px; background: #27ae60; color: white; border-radius: 8px; margin-bottom: 20px; display: inline-block; }
            .container { max-width: 1200px; margin: 0 auto; }
            .delete-btn { color: red; cursor: pointer; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🧴 Aidermy Admin</h1>
            <div class="status">✅ База данных работает</div>
            <h2>📋 Сохранённые составы (""" + str(len(ingredients)) + """)</h2>
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
    """

    for row in ingredients:
        html += f"""
                    <tr>
                        <td>{row['id']}</td>
                        <td><strong>{row['product_name']}</strong></td>
                        <td style="font-size: 13px; max-width: 400px; word-break: break-word;">{row['ingredients']}</td>
                        <td>{row['created_at']}</td>
                        <td><a href="#" class="delete-btn" data-id="{row['id']}">🗑️</a></td>
                    </tr>
        """

    html += """
                </tbody>
            </table>
            <p style="margin-top: 20px;"><a href="/">← На главную</a></p>
        </div>
        <script>
            document.querySelectorAll('.delete-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    e.preventDefault();
                    const id = btn.dataset.id;
                    if (confirm('Удалить этот состав?')) {
                        const res = await fetch('/admin/delete/' + id, { method: 'DELETE' });
                        if (res.ok) location.reload();
                    }
                });
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.delete("/admin/delete/{ingredient_id}")
async def delete_ingredient(ingredient_id: int, _: bool = Depends(verify_admin)):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ingredients WHERE id = ?", (ingredient_id,))
    conn.commit()
    conn.close()
    return {"success": True}