# community_routes.py
# REST-эндпоинты Community Intelligence (рейтинги, отзывы, helpful votes).

from __future__ import annotations

from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from .auth import get_current_user, get_current_user_optional
from .database import get_connection, AIDERMY_DB, PRODUCTS_DB
from .community_service import (
    CommunityIntelligenceService,
    VISIBILITIES,
    DURATIONS,
    TAGS,
)

router = APIRouter(prefix="/api/community", tags=["community"])

service = CommunityIntelligenceService()

MAX_REVIEW_TEXT = 2000


class ReviewCreate(BaseModel):
    slug: str
    rating: int = Field(..., ge=1, le=5)
    text: Optional[str] = ""
    usage_duration: Optional[str] = ""
    tags: Optional[List[str]] = []
    visibility: Optional[str] = "ANONYMOUS"


class ReviewUpdate(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    text: Optional[str] = None
    usage_duration: Optional[str] = None
    tags: Optional[List[str]] = None
    visibility: Optional[str] = None


def _get_product_by_slug(slug: str) -> Optional[dict]:
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE slug = ?", (slug,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def _get_profile_for_user(user_id: int) -> dict:
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT skin_type, age, concerns, allergies FROM user_profiles WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
            (user_id,),
        )
        row = cursor.fetchone()
        if row:
            conn.close()
            return {
                "skin_type": row["skin_type"] or "",
                "age": row["age"] or "",
                "concerns": [c.strip() for c in (row["concerns"] or "").split(",") if c.strip()],
                "allergies": [a.strip() for a in (row["allergies"] or "").split(",") if a.strip()],
            }
    except Exception:
        pass

    cursor.execute("SELECT skin_type, age, concerns, allergies FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {}
    return {
        "skin_type": row["skin_type"] or "",
        "age": row["age"] or "",
        "concerns": [c.strip() for c in (row["concerns"] or "").split(",") if c.strip()],
        "allergies": [a.strip() for a in (row["allergies"] or "").split(",") if a.strip()],
    }


@router.get("/rating")
async def get_rating(slug: str, current_user: dict = Depends(get_current_user_optional)):
    product = _get_product_by_slug(slug)
    if not product:
        raise HTTPException(status_code=404, detail="Продукт не найден")

    overall = service.get_product_community_rating(product["id"])
    personalized = {"available": False, "count": 0, "average": None}
    if current_user:
        profile = _get_profile_for_user(current_user["id"])
        personalized = service.get_personalized_community_rating(product["id"], profile)

    return {"overall": overall, "personalized": personalized}


@router.get("/reviews")
async def get_reviews(
    slug: str,
    limit: int = 10,
    offset: int = 0,
    current_user: dict = Depends(get_current_user_optional),
):
    product = _get_product_by_slug(slug)
    if not product:
        raise HTTPException(status_code=404, detail="Продукт не найден")

    profile = None
    if current_user:
        profile = _get_profile_for_user(current_user["id"])

    return service.get_community_reviews(
        product_id=product["id"],
        user_id=current_user["id"] if current_user else None,
        profile=profile,
        limit=limit,
        offset=offset,
    )

@router.post("/reviews")
async def create_review(payload: ReviewCreate, current_user: dict = Depends(get_current_user)):
    product = _get_product_by_slug(payload.slug)
    if not product:
        raise HTTPException(status_code=404, detail="Продукт не найден")

    text = (payload.text or "").strip()
    if len(text) > MAX_REVIEW_TEXT:
        raise HTTPException(status_code=422, detail="Текст отзыва слишком длинный")

    usage = payload.usage_duration or ""
    if usage and usage not in DURATIONS:
        raise HTTPException(status_code=422, detail="Некорректный период использования")

    tags = [t for t in (payload.tags or []) if t in TAGS]
    visibility = (payload.visibility or "ANONYMOUS").upper()
    if visibility not in VISIBILITIES:
        visibility = "ANONYMOUS"

    profile = _get_profile_for_user(current_user["id"])
    return service.create_review(
        user=current_user,
        product_id=product["id"],
        slug=payload.slug,
        rating=payload.rating,
        text=text,
        usage_duration=usage,
        tags=tags,
        visibility=visibility,
        profile=profile,
    )


@router.put("/reviews/{review_id}")
async def update_review(review_id: int, payload: ReviewUpdate, current_user: dict = Depends(get_current_user)):
    if payload.text is not None and len((payload.text or "").strip()) > MAX_REVIEW_TEXT:
        raise HTTPException(status_code=422, detail="Текст отзыва слишком длинный")
    if payload.usage_duration and payload.usage_duration not in DURATIONS:
        raise HTTPException(status_code=422, detail="Некорректный период использования")
    if payload.visibility and payload.visibility.upper() not in VISIBILITIES:
        raise HTTPException(status_code=422, detail="Некорректная видимость")

    tags = None
    if payload.tags is not None:
        tags = [t for t in payload.tags if t in TAGS]

    result = service.update_review(
        user=current_user,
        review_id=review_id,
        rating=payload.rating,
        text=payload.text,
        usage_duration=payload.usage_duration,
        tags=tags,
        visibility=payload.visibility.upper() if payload.visibility else None,
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Отзыв не найден")
    return result


@router.delete("/reviews/{review_id}")
async def delete_review(review_id: int, current_user: dict = Depends(get_current_user)):
    result = service.delete_review(user=current_user, review_id=review_id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Отзыв не найден")
    return result


@router.post("/reviews/{review_id}/helpful")
async def toggle_helpful(review_id: int, current_user: dict = Depends(get_current_user)):
    result = service.toggle_helpful_vote(user=current_user, review_id=review_id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Отзыв не найден")
    if result.get("status") == "own_review":
        raise HTTPException(status_code=422, detail="Нельзя голосовать за собственный отзыв")
    return result

