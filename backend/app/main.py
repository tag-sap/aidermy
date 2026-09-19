import os
import re
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from fastapi import FastAPI, HTTPException, Depends, status, Request, Header
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from .models import CheckRequest, CheckResponse, CheckWithIngredientsRequest, ImportUrlRequest
from .services import check_product_with_ai, check_product_with_ingredients, search_products
from .database import init_db, get_all_ingredients, get_all_check_history, save_check_result, get_check_stats, get_connection, PRODUCTS_DB, upsert_imported_product
from .auth_routes import router as auth_router
from .admin_routes import setup_admin_routes
from typing import Optional, List
from .auth import get_current_user_optional, get_current_user
from .scraper import ProductImportError, import_product

from .services import search_products

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


@app.get("/api/products/{slug}")
async def get_product_detail(slug: str, current_user: dict = Depends(get_current_user_optional)):
    from .database import get_product_by_slug, get_user_shelf, get_user_check_history
    from .shelf_service import score_product, resolve_shelf_cabinet, cabinet_applies_scoring

    product = get_product_by_slug(slug)
    if not product:
        raise HTTPException(status_code=404, detail="Продукт не найден")

    name = (product.get("name") or "").replace("\n", " ").strip()

    score = None
    analysis = None
    on_shelf = None

    if current_user:
        applicable = True
        # Определяем шкаф по категории/названию, чтобы понять, применим ли скоринг
        from .shelf_service import infer_cabinet_category
        cabinet, _ = infer_cabinet_category(product.get("category"), name)
        applicable = cabinet_applies_scoring(cabinet)

        if applicable:
            score, analysis = score_product(current_user, product)

        for s in get_user_shelf(current_user["id"]):
            if s["product_id"] == product["id"]:
                c_cabinet, c_category = resolve_shelf_cabinet(s.get("category"), s.get("cabinet"), name)
                on_shelf = {
                    "shelf_id": s["id"],
                    "cabinet": c_cabinet,
                    "category": c_category,
                }
                break

        if analysis is None:
            cleaned = name.strip().lower()
            for h in get_user_check_history(current_user["id"], limit=200):
                h_name = (h.get("product_name") or "").replace("\n", " ").strip().lower()
                if h_name == cleaned or h_name in cleaned or cleaned in h_name or (h.get("slug") and h.get("slug") == slug):
                    analysis = h
                    break

    return {
        "product": {
            "id": product.get("id"),
            "name": name,
            "brand": product.get("brand") or "",
            "slug": product.get("slug") or slug,
            "image_url": product.get("image_url") or "",
            "category": product.get("category") or "",
            "ingredients": product.get("ingredients") or "",
            "url": product.get("url") or "",
        },
        "score": score,
        "analysis": analysis,
        "on_shelf": on_shelf,
    }


@app.post("/api/products/import-url")
async def import_product_from_url(request: ImportUrlRequest):
    try:
        imported = await import_product(request.url)
        if not imported.name:
            raise ProductImportError("Товар на странице не найден.")
        saved = upsert_imported_product(imported.to_dict())
        product = {
            "name": saved.get("name"),
            "brand": saved.get("brand"),
            "image_url": saved.get("image_url"),
            "price": imported.price,
            "currency": imported.currency,
            "volume": imported.volume,
            "category": saved.get("category"),
            "description": imported.description,
            "ingredients_raw": saved.get("ingredients"),
            "source_url": saved.get("url"),
            "slug": saved.get("slug"),
            "id": saved.get("id"),
        }
        return {"success": True, "product": product}
    except ProductImportError as exc:
        print(f"[SCRAPER] Import failed: {exc.technical}")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        print(f"[SCRAPER] Import failed unexpectedly: {exc!r}")
        raise HTTPException(status_code=502, detail="Не удалось автоматически получить данные товара. Проверьте ссылку или добавьте состав вручную.") from exc

@app.post("/api/check", response_model=CheckResponse)
async def check_product(
    request: CheckRequest, 
    current_user: dict = Depends(get_current_user_optional)  # <-- ТЕПЕРЬ РАБОТАЕТ
):
    try:
        from .database import get_connection, PRODUCTS_DB
        
        result = await check_product_with_ai(
            request.product_name,
            request.skin_type,
            request.profile.dict()
        )
        
        slug = result.get('slug')
        
        # Проверяем, есть ли продукт в базе
        conn_products = get_connection(PRODUCTS_DB)
        cursor_products = conn_products.cursor()
        cursor_products.execute(
            "SELECT id FROM products WHERE name = ? OR slug = ?",
            (request.product_name, slug)
        )
        existing_product = cursor_products.fetchone()
        conn_products.close()
        
        # История сохраняется только через /api/auth/history, чтобы избежать дублей.
        # Здесь не пишем в БД повторно: это отдельный, единственный путь записи для профиля пользователя.
        user_id = current_user.get('id') if current_user else None
        
        return CheckResponse(
            score=result.get("score", 50),
            verdict=result.get("verdict", "Нейтрально"),
            summary=result.get("summary", "Не удалось получить рекомендацию."),
            safe_ingredients=result.get("safe_ingredients", []),
            caution_ingredients=result.get("caution_ingredients", []),
            cached=False,
            slug=slug,
            image_url=result.get("image_url"),
            active_ingredients=result.get("active_ingredients"),
            how_to_use=result.get("how_to_use"),
            expectations=result.get("expectations")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")
    
@app.post("/api/check-with-ingredients", response_model=CheckResponse)
async def check_with_ingredients(
    request: Request, 
    check_request: CheckWithIngredientsRequest,
    current_user: dict = Depends(get_current_user_optional)  # <-- ТЕПЕРЬ РАБОТАЕТ
):
    try:
        from .services import generate_slug, check_product_with_ingredients
        from .auth_routes import save_pending_product
        from .database import get_connection, PRODUCTS_DB
        
        result = await check_product_with_ingredients(
            check_request.product_name,
            check_request.skin_type,
            check_request.profile.dict(),
            check_request.ingredients
        )
        
        slug = generate_slug(check_request.product_name)
        
        # Проверяем, есть ли продукт уже в базе (одобрен)
        conn_products = get_connection(PRODUCTS_DB)
        cursor_products = conn_products.cursor()
        cursor_products.execute(
            "SELECT id FROM products WHERE name = ? OR slug = ?",
            (check_request.product_name, slug)
        )
        existing_product = cursor_products.fetchone()
        conn_products.close()
        
        user_id = current_user.get('id') if current_user else None
        
        # Отправляем в модерацию
        if check_request.ingredients and result.get("score", 0) > 0:
            save_pending_product(
                product_name=check_request.product_name,
                ingredients=check_request.ingredients,
                user_id=user_id
            )
        
        # История сохраняется только через /api/auth/history, чтобы избежать дублей.
        # Здесь не пишем в БД повторно: результат уже будет сохранён в пользовательской истории после проверки.
        
        return CheckResponse(
            score=result.get("score", 50),
            verdict=result.get("verdict", "Нейтрально"),
            summary=result.get("summary", "Не удалось получить рекомендацию."),
            safe_ingredients=result.get("safe_ingredients", []),
            caution_ingredients=result.get("caution_ingredients", []),
            cached=False,
            slug=slug,
            image_url=result.get("image_url"),
            active_ingredients=result.get("active_ingredients"),
            how_to_use=result.get("how_to_use"),
            expectations=result.get("expectations")
        )
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка проверки: {str(e)}")

@app.get("/api/popular-products")
async def get_popular_products():
    """Возвращает популярные продукты из истории проверок или бренды из БД"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Проверяем, есть ли история проверок
    cursor.execute('''
        SELECT COUNT(DISTINCT product_name) as count 
        FROM check_history 
        WHERE score > 0
    ''')
    result = cursor.fetchone()
    count = result['count'] if result else 0
    
    if count >= 3:
        # Если есть минимум 3 уникальных продукта - берем топ из истории
        cursor.execute('''
            SELECT 
                product_name,
                COUNT(*) as checks,
                AVG(score) as avg_score
            FROM check_history
            WHERE score > 0
            GROUP BY product_name
            ORDER BY checks DESC, avg_score DESC
            LIMIT 8
        ''')
        rows = cursor.fetchall()
        conn.close()
        
        # Для каждого продукта из истории ищем image_url в основной БД
        products = []
        for row in rows:
            product_name = row['product_name']
            conn_products = get_connection(PRODUCTS_DB)
            cursor_products = conn_products.cursor()
            cursor_products.execute(
                "SELECT image_url FROM products WHERE name = ? OR slug LIKE ?",
                (product_name, f'%{product_name.replace(" ", "-").lower()}%')
            )
            img_row = cursor_products.fetchone()
            conn_products.close()
            
            products.append({
                "name": product_name,
                "checks": row['checks'],
                "score": int(row['avg_score']),
                "image_url": img_row['image_url'] if img_row else None
            })
        
        return {
            "source": "history",
            "products": products
        }
    else:
        # Если истории мало - берем бренды из базы продуктов
        conn_products = get_connection(PRODUCTS_DB)
        cursor_products = conn_products.cursor()
        cursor_products.execute('''
            SELECT name, slug, image_url 
            FROM products 
            ORDER BY RANDOM() 
            LIMIT 8
        ''')
        rows = cursor_products.fetchall()
        conn_products.close()
        conn.close()
        return {
            "source": "database",
            "products": [{
                "name": row['name'],
                "slug": row['slug'],
                "image_url": row['image_url']
            } for row in rows]
        }

@app.get("/api/catalog")
async def get_catalog(
    category: Optional[str] = None,
    brand: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    sort: str = "popular"
):
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    
    # Основной запрос
    query = "SELECT name, slug, image_url, ingredients, category, brand FROM products WHERE 1=1"
    params = []
    
    if category:
        query += " AND lower_ru(name) LIKE ?"
        params.append(f"%{category.lower()}%")
    if brand:
        query += " AND brand = ?"
        params.append(brand)
    if search:
        words = search.strip().lower().split()
        if len(words) == 1:
            query += " AND lower_ru(name) LIKE ?"
            params.append(f"%{words[0]}%")
        else:
            for word in words:
                query += " AND lower_ru(name) LIKE ?"
                params.append(f"%{word}%")
    
    query += " ORDER BY name ASC LIMIT ? OFFSET ?"
    params.append(limit)
    params.append(offset)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    # Подсчёт
    count_query = "SELECT COUNT(*) FROM products WHERE 1=1"
    count_params = []
    
    if category:
        count_query += " AND lower_ru(name) LIKE ?"
        count_params.append(f"%{category.lower()}%")
    if brand:
        count_query += " AND brand = ?"
        count_params.append(brand)
    if search:
        words = search.strip().lower().split()
        if len(words) == 1:
            count_query += " AND lower_ru(name) LIKE ?"
            count_params.append(f"%{words[0]}%")
        else:
            for word in words:
                count_query += " AND lower_ru(name) LIKE ?"
                count_params.append(f"%{word}%")
    
    cursor.execute(count_query, count_params)
    total = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        "products": [dict(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset
    }

CATEGORY_KEYWORDS = [
    "Крем", "Сыворотка", "Гель", "Масло", "Тоник", "Тонер", "Лосьон",
    "Молочко", "Маска", "Скраб", "Пилинг", "Шампунь", "Бальзам",
    "Кондиционер", "Пенка", "Эмульсия", "Спрей", "Мист", "Мыло",
]


@app.get("/api/categories")
async def get_categories():
    """Список категорий и брендов для фильтров"""
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT brand FROM products WHERE brand IS NOT NULL AND brand != '' ORDER BY brand")
    brands = {row[0] for row in cursor.fetchall() if row[0]}
    
    # Извлекаем бренды из названий (часть до переноса строки), чтобы не терять бренды
    cursor.execute("SELECT name FROM products WHERE brand IS NULL OR brand = ''")
    category_lower = [kw.lower() for kw in CATEGORY_KEYWORDS]
    for (name,) in cursor.fetchall():
        if not name:
            continue
        first_part = name.split("\n")[0].strip()
        if not first_part or len(first_part) < 2 or len(first_part) > 40:
            continue
        if any(kw in first_part.lower() for kw in category_lower):
            continue
        brands.add(first_part)
    
    conn.close()
    return {"categories": list(CATEGORY_KEYWORDS), "brands": sorted(brands)}


CATALOG_SECTIONS = [
    {"key": "popular", "title": "Популярное", "type": "popular"},
    {"key": "skincare", "title": "Уход за кожей", "type": "categories", "categories": ["Очищение", "Тонер", "Сыворотка", "Крем"]},
    {"key": "acne", "title": "Против акне", "type": "keywords", "keywords": ["acne", "blemish", "azelaic", "salicylic", "pimple", "purifying", "clearing"]},
    {"key": "hydration", "title": "Увлажнение", "type": "keywords", "keywords": ["hydra", "moistur", "hyaluronic", "ceramide"]},
    {"key": "antiage", "title": "Антивозраст", "type": "keywords", "keywords": ["retinol", "anti-age", "wrinkle", "peptide", "collagen"]},
    {"key": "sun", "title": "Защита от солнца", "type": "categories", "categories": ["Защита"]},
    {"key": "cleansing", "title": "Очищение", "type": "categories", "categories": ["Очищение"]},
]


@app.get("/api/catalog/sections")
async def get_catalog_sections():
    """Секции каталога: горизонтальные подборки по категориям/темам."""
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()

    def fetch(section):
        base = "SELECT name, slug, image_url, category, brand, ingredients FROM products WHERE image_url IS NOT NULL AND image_url != ''"
        if section["type"] == "popular":
            cursor.execute(base + " ORDER BY id DESC LIMIT 10")
        elif section["type"] == "categories":
            cats = section["categories"]
            ph = ",".join(["?"] * len(cats))
            cursor.execute(base + f" AND category IN ({ph}) ORDER BY id DESC LIMIT 10", cats)
        else:
            kws = section["keywords"]
            conds = " OR ".join(["LOWER(name) LIKE ? OR LOWER(ingredients) LIKE ?"] * len(kws))
            params = []
            for kw in kws:
                params.append(f"%{kw}%")
                params.append(f"%{kw}%")
            cursor.execute(base + f" AND ({conds}) ORDER BY id DESC LIMIT 10", params)
        return [dict(row) for row in cursor.fetchall()]

    sections = []
    for section in CATALOG_SECTIONS:
        products = fetch(section)
        cleaned = []
        for p in products:
            parts = [x.strip() for x in (p.get("name") or "").split("\n") if x.strip()]
            brand = parts[0] if len(parts) >= 2 else (p.get("brand") or "")
            title = " ".join(parts[1:]) if len(parts) >= 2 else (parts[0] if parts else (p.get("name") or ""))
            cleaned.append({
                "name": title,
                "brand": brand,
                "slug": p.get("slug") or "",
                "image_url": p.get("image_url") or "",
                "category": p.get("category") or "",
            })
        sections.append({"key": section["key"], "title": section["title"], "products": cleaned})

    conn.close()
    return {"sections": sections}


# ============================================================
# МОЯ ПОЛКА (SHELF)
# ============================================================

class ShelfAddRequest(BaseModel):
    slug: str
    category: str = ""
    cabinet: str = "face"


class ShelfUpdateRequest(BaseModel):
    category: str = ""


class ShelfRecommendRequest(BaseModel):
    cabinet: str = "face"
    category: str = ""


SHELF_CATEGORIES = ["Очищение", "Тонер", "Сыворотка", "Крем", "SPF", "Маска"]


def _profile_from_user(user: dict) -> dict:
    return {
        "skin_type": user.get("skin_type") or "",
        "age": user.get("age") or "",
        "concerns": [c.strip() for c in (user.get("concerns") or "").split(",") if c.strip()],
        "allergies": [a.strip() for a in (user.get("allergies") or "").split(",") if a.strip()],
        "custom_text": user.get("custom_text") or "",
    }


def _checked_score_for_product(user_id: int, slug: str, name: str):
    """Оценка из истории проверок, если продукт проверялся пользователем, иначе None."""
    from .database import get_user_check_history
    history = get_user_check_history(user_id, limit=100)
    cleaned_name = (name or "").replace("\n", " ").strip().lower()
    for h in history:
        h_slug = (h.get("slug") or "").strip()
        h_name = (h.get("product_name") or "").replace("\n", " ").strip().lower()
        if slug and h_slug and h_slug == slug:
            return int(h.get("score") or 0)
        if cleaned_name and h_name and (h_name == cleaned_name or h_name in cleaned_name or cleaned_name in h_name):
            return int(h.get("score") or 0)
    return None


def _compute_compatibility(products: list) -> dict:
    """Комплексная оценка набора продуктов по движку (без ИИ)."""
    from .ingredient_normalizer import canonicalize_ingredient_name

    def parse_ingredients(raw: str) -> set:
        out = set()
        for part in re.split(r'[,;\n]+', raw or ''):
            c = canonicalize_ingredient_name(part)
            if c:
                out.add(c)
        return out

    ingredient_sets = [parse_ingredients(p.get("ingredients") or "") for p in products]
    all_ing = set().union(*ingredient_sets) if ingredient_sets else set()

    counts: dict = {}
    for s in ingredient_sets:
        for ing in s:
            counts[ing] = counts.get(ing, 0) + 1
    repeated_ingredients = sorted(
        [{"ingredient": k, "count": v} for k, v in counts.items() if v > 1],
        key=lambda x: -x["count"],
    )[:15]

    common_actives = {
        "niacinamide", "hyaluronic acid", "sodium hyaluronate", "salicylic acid",
        "glycolic acid", "lactic acid", "retinol", "retinal", "retinyl", "bakuchiol",
        "vitamin c", "ascorbic acid", "azelaic acid", "ceramide", "panthenol",
        "centella", "madecassoside", "peptide", "collagen", "adenosine",
        "tranexamic acid", "arbutin", "alpha arbutin", "kojic acid", "zinc", "tea tree",
    }
    active_counts: dict = {}
    for act in common_actives:
        for s in ingredient_sets:
            if act in s:
                active_counts[act] = active_counts.get(act, 0) + 1
    duplicate_actives = sorted(
        [{"ingredient": k, "count": v} for k, v in active_counts.items() if v > 1],
        key=lambda x: -x["count"],
    )[:15]

    conflict_rules = [
        ({"retinol", "retinal", "tretinoin", "retinyl", "adapalene"}, {"glycolic acid", "salicylic acid", "lactic acid", "mandelic acid", "aha", "bha"}),
        ({"niacinamide"}, {"ascorbic acid", "vitamin c", "ascorbyl"}),
        ({"retinol", "retinal", "retinyl"}, {"benzoyl peroxide"}),
    ]
    conflicts = []
    for a_set, b_set in conflict_rules:
        a = all_ing & a_set
        b = all_ing & b_set
        if a and b:
            conflicts.append({"a": sorted(a), "b": sorted(b)})

    core_steps = ["Очищение", "Тонер", "Сыворотка", "Крем", "SPF"]
    present = sorted({p.get("category") for p in products if p.get("category")})
    missing = [c for c in core_steps if c not in present]

    penalty = min(60, 20 * len(conflicts)) + min(25, 5 * len(duplicate_actives))
    overall_score = max(0, 100 - penalty)

    return {
        "overall_score": overall_score,
        "conflicts": conflicts,
        "duplicate_actives": duplicate_actives,
        "repeated_ingredients": repeated_ingredients,
        "coverage": {"present": present, "missing": missing},
    }


@app.get("/api/shelf")
async def get_shelf(current_user: dict = Depends(get_current_user)):
    from .database import get_user_shelf
    from .shelf_service import build_cabinet_payload

    shelf = get_user_shelf(current_user["id"])
    cabinets = build_cabinet_payload(current_user, shelf)
    return {"cabinets": cabinets}


@app.post("/api/shelf")
async def add_to_shelf(request: ShelfAddRequest, current_user: dict = Depends(get_current_user)):
    from .database import get_product_by_slug, get_user_shelf, add_product_to_shelf
    from .shelf_service import canonical_category, CABINET_BY_KEY

    product = get_product_by_slug(request.slug)
    if not product:
        raise HTTPException(status_code=404, detail="Продукт не найден")

    cabinet = (request.cabinet or "face").strip().lower()
    if cabinet not in CABINET_BY_KEY:
        cabinet = "face"
    category = canonical_category(cabinet, request.category)

    for s in get_user_shelf(current_user["id"]):
        if s["product_id"] == product["id"]:
            return {"status": "ok", "duplicate": True, "item": {"id": s["id"], "product_id": product["id"]}}
    item = add_product_to_shelf(current_user["id"], product["id"], category, cabinet=cabinet)
    return {"status": "ok", "duplicate": False, "item": item}


@app.post("/api/shelf/recommend")
async def recommend_for_shelf(request: ShelfRecommendRequest, current_user: dict = Depends(get_current_user)):
    from .database import get_user_shelf
    from .shelf_service import recommend_products, canonical_category, CABINET_BY_KEY

    cabinet = (request.cabinet or "face").strip().lower()
    if cabinet not in CABINET_BY_KEY:
        raise HTTPException(status_code=400, detail="Неизвестный шкаф")
    category = canonical_category(cabinet, request.category)

    existing = {s["product_id"] for s in get_user_shelf(current_user["id"])}
    from .database import get_product_by_id
    exclude_slugs = set()
    for pid in existing:
        p = get_product_by_id(pid)
        if p and p.get("slug"):
            exclude_slugs.add(p["slug"])

    recommendations = recommend_products(current_user, cabinet, category, exclude_slugs)
    return {"cabinet": cabinet, "category": category, "recommendations": recommendations}


@app.patch("/api/shelf/{shelf_id}")
async def update_shelf_product(shelf_id: int, request: ShelfUpdateRequest, current_user: dict = Depends(get_current_user)):
    from .database import update_shelf_product_category
    updated = update_shelf_product_category(current_user["id"], shelf_id, request.category)
    if not updated:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"status": "ok"}


@app.delete("/api/shelf/{shelf_id}")
async def delete_shelf_product(shelf_id: int, current_user: dict = Depends(get_current_user)):
    from .database import remove_product_from_shelf
    deleted = remove_product_from_shelf(current_user["id"], shelf_id)
    return {"status": "ok", "deleted": deleted}


# ============================================================
# ПОДБОР УХОДА (ROUTINE BUILDER)
# ============================================================

class RoutineBuildRequest(BaseModel):
    query: str
    profile: dict = {}


class RoutineToShelfRequest(BaseModel):
    name: str = ""
    items: List[dict] = []


class RoutineCompatibilityRequest(BaseModel):
    slugs: List[str] = []


@app.post("/api/routine/build")
async def build_routine_endpoint(
    request: RoutineBuildRequest,
    current_user: dict = Depends(get_current_user_optional),
):
    from .routine_service import build_routine, ai_refine_routine

    profile = dict(request.profile or {})
    if current_user:
        server_profile = _profile_from_user(current_user)
        for key, value in server_profile.items():
            if not profile.get(key):
                profile[key] = value

    routine = build_routine(request.query, profile)
    routine = await ai_refine_routine(request.query, routine)
    return routine


@app.post("/api/routine/compatibility")
async def routine_compatibility(request: RoutineCompatibilityRequest):
    from .database import get_product_by_slug
    products = []
    for slug in request.slugs:
        p = get_product_by_slug(slug)
        if p and p.get("ingredients"):
            products.append({"ingredients": p.get("ingredients") or "", "category": p.get("category") or ""})
    if not products:
        return {"overall_score": 0, "conflicts": [], "duplicate_actives": [], "repeated_ingredients": [], "coverage": {"present": [], "missing": []}}
    return _compute_compatibility(products)


@app.post("/api/routine/to-shelf")
async def routine_to_shelf(
    request: RoutineToShelfRequest,
    current_user: dict = Depends(get_current_user),
):
    from .database import get_product_by_slug, get_user_shelf, add_product_to_shelf, create_routine

    existing = {s["product_id"] for s in get_user_shelf(current_user["id"])}
    routine_id = create_routine(current_user["id"], request.name)
    added = 0
    skipped = 0
    for item in request.items:
        slug = (item or {}).get("slug")
        category = (item or {}).get("category") or ""
        if not slug:
            continue
        product = get_product_by_slug(slug)
        if not product:
            continue
        if product["id"] in existing:
            skipped += 1
            continue
        add_product_to_shelf(current_user["id"], product["id"], category, request.name, routine_id)
        existing.add(product["id"])
        added += 1
    return {"status": "ok", "added": added, "skipped": skipped, "routine_id": routine_id}