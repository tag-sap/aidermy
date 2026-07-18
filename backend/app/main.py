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