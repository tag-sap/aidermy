import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from .auth import get_current_user
from .database import get_balance, change_balance, set_user_plan, PLAN_MONTHLY_POINTS
from .plans import shelf_limit

router = APIRouter(prefix="/api", tags=["billing"])

# --- Оплата: подготовка к ЮKassa -------------------------------------------
# Провайдер и цены НЕ заданы в коде. Цены утверждает владелец; пока словарь
# пуст, оформление заказа заблокировано, чтобы нельзя было продать услугу без
# проверяемой цены.
PLAN_PRICES: dict = {}
PACKAGE_PRICES: dict = {}

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")


def payments_configured() -> bool:
    return bool(YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY)


def prices_defined() -> bool:
    return bool(PLAN_PRICES)


class TopupRequest(BaseModel):
    amount: int


class SubscriptionRequest(BaseModel):
    plan: str


class OrderRequest(BaseModel):
    kind: str = "subscription"
    plan: str = ""
    package_id: str = ""
    offer_version: Optional[str] = None


@router.get("/balance")
async def balance(current_user: dict = Depends(get_current_user)):
    return get_balance(current_user["id"])


@router.post("/balance/topup")
async def topup(request: TopupRequest, current_user: dict = Depends(get_current_user)):
    if request.amount <= 0:
        raise HTTPException(status_code=422, detail="Сумма пополнения должна быть положительной")
    # В реальной интеграции здесь был бы платёжный шлюз; для демо — просто начисляем.
    new_balance = change_balance(current_user["id"], request.amount, "topup", "Пополнение баланса")
    if new_balance is None:
        raise HTTPException(status_code=500, detail="Не удалось пополнить баланс")
    return get_balance(current_user["id"])


@router.post("/subscription")
async def subscription(request: SubscriptionRequest, current_user: dict = Depends(get_current_user)):
    if request.plan not in PLAN_MONTHLY_POINTS:
        raise HTTPException(status_code=422, detail="Неизвестный тариф")
    return set_user_plan(current_user["id"], request.plan)


@router.get("/billing/catalog")
async def billing_catalog():
    """Тарифы и цены. Пока цены не утверждены — available=false."""
    from .legal_documents import document_version

    plans = [
        {
            "key": key,
            "title": key.capitalize(),
            "monthly_points": points,
            "shelf_limit": shelf_limit(key),
            "price": PLAN_PRICES.get(key),
            "available": key in PLAN_PRICES,
        }
        for key, points in PLAN_MONTHLY_POINTS.items()
    ]
    return {
        "provider": "yookassa",
        "currency": "RUB",
        "prices_defined": prices_defined(),
        "payments_configured": payments_configured(),
        "plans": plans,
        "packages": [
            {"id": pid, "title": data.get("title", pid), "checks": data.get("checks"), "price": data.get("price")}
            for pid, data in PACKAGE_PRICES.items()
        ],
        "offer_version": document_version("offer"),
        "note": (
            "Цены ещё не утверждены, поэтому покупка недоступна."
            if not prices_defined()
            else "Цены утверждены; приём платежей включается после подключения провайдера."
        ),
    }


@router.post("/billing/orders")
async def create_order(request: OrderRequest, current_user: dict = Depends(get_current_user)):
    """Создание заказа. Реальный платёж здесь НЕ инициируется.

    Заказ не создаётся, если: цена не утверждена, не принята актуальная
    оферта или провайдер не настроен. Это защищает от продажи услуги без
    проверяемой цены и без согласия пользователя.
    """
    from .consents import has_current_consent
    from .legal_documents import document_version

    if request.kind != "subscription":
        raise HTTPException(status_code=422, detail="Неизвестный тип заказа")
    if request.plan not in PLAN_MONTHLY_POINTS:
        raise HTTPException(status_code=422, detail="Неизвестный тариф")

    price = PLAN_PRICES.get(request.plan)
    if not price:
        raise HTTPException(
            status_code=409,
            detail="Цена тарифа ещё не утверждена. Оформление заказа недоступно.",
        )

    if request.offer_version and request.offer_version != document_version("offer"):
        raise HTTPException(
            status_code=409,
            detail="Версия оферты устарела. Обновите страницу и подтвердите условия заново.",
        )

    if not has_current_consent(current_user["id"], "offer"):
        raise HTTPException(
            status_code=409,
            detail="Примите условия публичной оферты перед оплатой.",
        )

    if not payments_configured():
        raise HTTPException(
            status_code=503,
            detail="Приём платежей ещё не подключён. Заказ не создан.",
        )

    # Заглушка на случай, если ключи появятся раньше кода интеграции:
    # реальная платёжная операция здесь не создаётся.
    raise HTTPException(
        status_code=503,
        detail="Интеграция с ЮKassa ещё не включена. Заказ не создан.",
    )
