from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .models import CheckRequest, CheckResponse

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
    # Временно мок-ответ
    return CheckResponse(
        score=87,
        verdict="Подходит",
        summary=f"Продукт {request.product_name} подходит для кожи {request.skin_type}.",
        safe_ingredients=["Глицерин", "Вода"],
        caution_ingredients=["Парабены"],
        cached=False
    )

@app.get("/api/health")
async def health():
    return {"status": "ok"}