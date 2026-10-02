from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from .auth import get_current_user
from .database import get_balance, change_balance, set_user_plan, PLAN_MONTHLY_POINTS

router = APIRouter(prefix="/api", tags=["billing"])


class TopupRequest(BaseModel):
    amount: int


class SubscriptionRequest(BaseModel):
    plan: str


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
