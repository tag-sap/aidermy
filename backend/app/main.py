from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from .models import CheckRequest, CheckResponse, CheckWithIngredientsRequest
from .services import check_product_with_ai, check_product_with_ingredients
from .database import init_db, get_all_ingredients, get_all_check_history, save_check_result, get_check_stats, get_connection, search_products
from .auth_routes import router as auth_router
import os
from dotenv import load_dotenv

load_dotenv()
init_db()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

app = FastAPI(
    title="Aidermy API",
    version="1.0",
    description="API for cosmetic checking with AI"
)
app.include_router(auth_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBasic()

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != "admin" or credentials.password != "aidermy2026":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True

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
            result.get("verdict", "Neutral"),
            result.get("summary", "Could not get recommendation."),
            "",
            slug
        )
        
        return CheckResponse(
            score=result.get("score", 50),
            verdict=result.get("verdict", "Neutral"),
            summary=result.get("summary", "Could not get recommendation."),
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
        result = await check_product_with_ingredients(
            request.product_name,
            request.skin_type,
            request.profile.dict(),
            request.ingredients
        )

        from .services import generate_slug
        slug = generate_slug(request.product_name)
        
        save_check_result(
            request.product_name,
            request.skin_type,
            result.get("score", 50),
            result.get("verdict", "Use with caution"),
            result.get("summary", "Could not analyze ingredients."),
            request.ingredients,
            slug
        )

        return CheckResponse(
            score=result.get("score", 50),
            verdict=result.get("verdict", "Use with caution"),
            summary=result.get("summary", "Could not analyze ingredients."),
            safe_ingredients=result.get("safe_ingredients", []),
            caution_ingredients=result.get("caution_ingredients", []),
            cached=False,
            slug=slug
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
    products = search_products(q)
    return {"products": products}

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(_: bool = Depends(verify_admin)):
    history = get_all_check_history(limit=100)
    ingredients = get_all_ingredients()
    stats = get_check_stats()
    
    html = "<html><head><title>Admin</title></head><body>"
    html += "<h1>Admin Panel</h1>"
    html += f"<p>Total: {stats['total']}</p>"
    html += f"<p>Unique: {stats['unique_products']}</p>"
    html += f"<p>Average: {stats['avg_score']}</p>"
    html += "</body></html>"
    
    return HTMLResponse(content=html)

@app.delete("/admin/delete/{record_id}")
async def delete_record(record_id: int, table: str = "check_history", _: bool = Depends(verify_admin)):
    conn = get_connection()
    cursor = conn.cursor()
    
    if table not in ["check_history", "ingredients"]:
        raise HTTPException(status_code=400, detail="Invalid table name")
    
    cursor.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    return {"success": True}