# community_service.py
# Community Intelligence: рейтинги, отзывы, helpful votes и персональный
# рейтинг по похожести профилей.

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .database import get_connection
from .profile_similarity import (
    ProfileSimilarityService,
    COMMUNITY_SIMILARITY_THRESHOLD,
    COMMUNITY_MIN_PERSONALIZED_REVIEWS,
)

VISIBILITIES = {"ANONYMOUS", "NAME", "PUBLIC_PROFILE"}
DURATIONS = {"LESS_THAN_WEEK", "ONE_TO_FOUR_WEEKS", "ONE_TO_THREE_MONTHS", "THREE_PLUS_MONTHS"}
TAGS = {"HYDRATION", "TEXTURE", "ABSORPTION", "COMFORT", "SCENT", "EFFECT", "IRRITATION"}

_similarity = ProfileSimilarityService()


def _parse_tags(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x) for x in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except Exception:
            pass
        return [x.strip() for x in value.split(",") if x.strip()]
    return []


def _parse_snapshot(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def _display_name(user_name: str, visibility: str) -> str:
    name = (user_name or "").strip()
    if visibility == "NAME":
        return name or "Пользователь Aidermy"
    if visibility == "PUBLIC_PROFILE":
        return (name or "Пользователь") + " · профиль Aidermy"
    return "Пользователь Aidermy"


def _snapshot_from_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "skin_type": profile.get("skin_type") or profile.get("skinType") or "",
        "age": profile.get("age") or "",
        "concerns": profile.get("concerns") or [],
        "allergies": profile.get("allergies") or [],
    }


class CommunityIntelligenceService:
    def get_product_community_rating(self, product_id: int) -> Dict[str, Any]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) AS n, AVG(rating) AS avg FROM reviews WHERE product_id = ?",
            (product_id,),
        )
        row = cursor.fetchone()
        conn.close()
        count = int(row["n"] or 0)
        average = round(float(row["avg"]), 2) if row["avg"] is not None else None
        return {"average": average, "count": count}

    def get_personalized_community_rating(self, product_id: int, profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not profile:
            return {"available": False, "count": 0, "average": None}
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rating, profile_snapshot FROM reviews WHERE product_id = ?",
            (product_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        similar_ratings: List[int] = []
        for r in rows:
            snap = _parse_snapshot(r["profile_snapshot"])
            if _similarity.similarity(profile, snap) >= COMMUNITY_SIMILARITY_THRESHOLD:
                similar_ratings.append(int(r["rating"]))

        if len(similar_ratings) < COMMUNITY_MIN_PERSONALIZED_REVIEWS:
            return {"available": False, "count": len(similar_ratings), "average": None}

        average = round(sum(similar_ratings) / len(similar_ratings), 2)
        return {"available": True, "count": len(similar_ratings), "average": average}

    def get_community_reviews(
        self,
        product_id: int,
        user_id: Optional[int],
        profile: Optional[Dict[str, Any]],
        limit: int = 10,
        offset: int = 0,
    ) -> Dict[str, Any]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT r.id, r.user_id, r.rating, r.text, r.usage_duration, r.tags,
                   r.visibility, r.profile_snapshot, r.created_at,
                   u.name AS user_name,
                   (SELECT COUNT(*) FROM review_helpful_votes v WHERE v.review_id = r.id) AS helpful_count,
                   (SELECT COUNT(*) FROM review_helpful_votes v WHERE v.review_id = r.id AND v.user_id = ?) AS is_helpful
            FROM reviews r
            JOIN users u ON u.id = r.user_id
            WHERE r.product_id = ?
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id or 0, product_id, limit, offset),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT COUNT(*) AS n FROM reviews WHERE product_id = ?", (product_id,))
        total = int(cursor.fetchone()["n"] or 0)
        conn.close()

        reviews: List[Dict[str, Any]] = []
        for r in rows:
            snap = _parse_snapshot(r.get("profile_snapshot"))
            sim = _similarity.similarity(profile, snap) if profile else None
            reviews.append(
                {
                    "id": r["id"],
                    "displayName": _display_name(r.get("user_name") or "", r.get("visibility") or "ANONYMOUS"),
                    "rating": int(r["rating"]),
                    "text": r["text"] or "",
                    "usageDuration": r["usage_duration"] or "",
                    "tags": _parse_tags(r.get("tags")),
                    "helpfulCount": int(r["helpful_count"] or 0),
                    "isHelpfulByCurrentUser": bool(r["is_helpful"]),
                    "isSimilarProfile": bool(profile and sim is not None and sim >= COMMUNITY_SIMILARITY_THRESHOLD),
                    "isOwn": bool(user_id and int(r["user_id"]) == user_id),
                    "createdAt": r["created_at"],
                }
            )
        return {"reviews": reviews, "total": total, "limit": limit, "offset": offset}


    def create_review(
        self,
        user: Dict[str, Any],
        product_id: int,
        slug: str,
        rating: int,
        text: str,
        usage_duration: str,
        tags: List[str],
        visibility: str,
        profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        conn = get_connection()
        cursor = conn.cursor()
        snapshot = _snapshot_from_profile(profile)
        try:
            cursor.execute(
                """
                INSERT INTO reviews (user_id, product_id, slug, rating, text, usage_duration, tags, visibility, profile_snapshot, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, product_id) DO UPDATE SET
                    rating = excluded.rating,
                    text = excluded.text,
                    usage_duration = excluded.usage_duration,
                    tags = excluded.tags,
                    visibility = excluded.visibility,
                    profile_snapshot = excluded.profile_snapshot,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user["id"],
                    product_id,
                    slug,
                    rating,
                    text,
                    usage_duration,
                    json.dumps(tags, ensure_ascii=False),
                    visibility,
                    json.dumps(snapshot, ensure_ascii=False),
                ),
            )
            conn.commit()
            cursor.execute("SELECT id FROM reviews WHERE user_id = ? AND product_id = ?", (user["id"], product_id))
            row = cursor.fetchone()
            return {"status": "ok", "review_id": row["id"] if row else None}
        finally:
            conn.close()

    def update_review(
        self,
        user: Dict[str, Any],
        review_id: int,
        rating: Optional[int],
        text: Optional[str],
        usage_duration: Optional[str],
        tags: Optional[List[str]],
        visibility: Optional[str],
    ) -> Dict[str, Any]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM reviews WHERE id = ? AND user_id = ?", (review_id, user["id"]))
        if not cursor.fetchone():
            conn.close()
            return {"status": "not_found"}

        fields = []
        params: List[Any] = []
        if rating is not None:
            fields.append("rating = ?")
            params.append(rating)
        if text is not None:
            fields.append("text = ?")
            params.append(text)
        if usage_duration is not None:
            fields.append("usage_duration = ?")
            params.append(usage_duration)
        if tags is not None:
            fields.append("tags = ?")
            params.append(json.dumps(tags, ensure_ascii=False))
        if visibility is not None:
            fields.append("visibility = ?")
            params.append(visibility)

        if fields:
            fields.append("updated_at = CURRENT_TIMESTAMP")
            params.append(review_id)
            cursor.execute(f"UPDATE reviews SET {', '.join(fields)} WHERE id = ?", params)
            conn.commit()
        conn.close()
        return {"status": "ok"}

    def delete_review(self, user: Dict[str, Any], review_id: int) -> Dict[str, Any]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reviews WHERE id = ? AND user_id = ?", (review_id, user["id"]))
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        return {"status": "ok" if deleted else "not_found"}

    def toggle_helpful_vote(self, user: Dict[str, Any], review_id: int) -> Dict[str, Any]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM reviews WHERE id = ?", (review_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return {"status": "not_found"}
        if int(row["user_id"]) == user["id"]:
            conn.close()
            return {"status": "own_review"}

        cursor.execute(
            "SELECT id FROM review_helpful_votes WHERE review_id = ? AND user_id = ?",
            (review_id, user["id"]),
        )
        existing = cursor.fetchone()
        if existing:
            cursor.execute("DELETE FROM review_helpful_votes WHERE id = ?", (existing["id"],))
            conn.commit()
            voted = False
        else:
            cursor.execute(
                "INSERT INTO review_helpful_votes (review_id, user_id, created_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (review_id, user["id"]),
            )
            conn.commit()
            voted = True

        cursor.execute("SELECT COUNT(*) AS n FROM review_helpful_votes WHERE review_id = ?", (review_id,))
        count = int(cursor.fetchone()["n"] or 0)
        conn.close()
        return {"status": "ok", "helpful": voted, "helpfulCount": count}

