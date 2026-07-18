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
from .admin_routes import setup_admin_routes

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

# Регистрируем админ-роуты
setup_admin_routes(app)

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