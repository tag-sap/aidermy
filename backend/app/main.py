from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .models import CheckRequest, CheckResponse, CheckWithIngredientsRequest
from .services import check_product_with_ai, check_product_with_ingredients
from .cache import save_ingredients
import os
from .database import init_db
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

        # Сохраняем состав в кеш (позже — в БД)
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