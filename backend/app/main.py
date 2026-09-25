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
from .models import (
    CheckRequest,
    CheckResponse,
    CheckWithIngredientsRequest,
    ImportUrlRequest,
    RecognizeCompositionRequest,
    AnalyzeCompositionRequest,
    CreateProductRequest,
)
from .services import check_product_with_ai, check_product_with_ingredients, search_products, capitalize_name
from .database import init_db, get_all_ingredients, get_all_check_history, save_check_result, get_check_stats, get_connection, PRODUCTS_DB, upsert_imported_product, save_ingredients
from .auth_routes import router as auth_router
from .community_routes import router as community_router
from .admin_routes import setup_admin_routes
from typing import Optional, List
from .auth import get_current_user_optional, get_current_user
from .scraper import ProductImportError, import_product

from .services import search_products
from .vision_service import (
    recognize_composition,
    recognized_normalized_list,
    find_product_matches,
    register_ingredients,
    MATCH_CONFIDENT_THRESHOLD,
)

init_db()

# Бэкфилл таксономии каталога (category/subcategory) по названию + legacy-category.
try:
    from .database import backfill_catalog_taxonomy
    backfill_catalog_taxonomy()
except Exception as exc:
    print(f"[INIT] catalog taxonomy backfill failed: {exc!r}")

# Фаза 4 — инициализация Knowledge Graph (таблицы + seed) НА СТАРТЕ,
# чтобы первый /recommend не нёс seed-нагрузку. Идемпотентно.
try:
    from .ingredient_repository import IngredientRepository
    IngredientRepository().initialize_knowledge_graph()
except Exception as exc:
    print(f"[INIT] knowledge graph init failed: {exc!r}")

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
app.include_router(community_router)

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
    from .database import get_product_by_slug, get_user_shelf
    from .shelf_service import (
        get_personalized_analysis,
        resolve_shelf_cabinet,
        cabinet_applies_scoring,
        infer_cabinet_category,
    )

    product = get_product_by_slug(slug)
    if not product:
        raise HTTPException(status_code=404, detail="Продукт не найден")

    name = (product.get("name") or "").replace("\n", " ").strip()

    score = None
    analysis = None
    on_shelf = None

    if current_user:
        # Определяем шкаф по категории/названию, чтобы понять, применим ли скоринг
        cabinet, _ = infer_cabinet_category(product.get("category"), name)
        if cabinet_applies_scoring(cabinet):
            # История — snapshot: если записи нет, но продукт «подготовлен» (Static Product Model),
            # персональный анализ пересчитывается детерминированно под пользователя.
            score, analysis = get_personalized_analysis(current_user, product)

        for s in get_user_shelf(current_user["id"]):
            if s["product_id"] == product["id"]:
                c_cabinet, c_category = resolve_shelf_cabinet(s.get("category"), s.get("cabinet"), name)
                on_shelf = {
                    "shelf_id": s["id"],
                    "cabinet": c_cabinet,
                    "category": c_category,
                }
                break

    from .community_service import CommunityIntelligenceService
    from .community_routes import _get_profile_for_user
    community_service = CommunityIntelligenceService()
    community = {
        "overall": community_service.get_product_community_rating(product["id"]),
        "personalized": {"available": False, "count": 0, "average": None},
    }
    if current_user:
        community["personalized"] = community_service.get_personalized_community_rating(
            product["id"], _get_profile_for_user(current_user["id"])
        )

    raw_name = product.get("name") or ""
    _parts = [p.strip() for p in raw_name.split("\n") if p.strip()]
    if len(_parts) >= 2:
        display_brand = product.get("brand") or _parts[0]
        display_name = " ".join(_parts[1:])
    else:
        display_brand = product.get("brand") or ""
        display_name = _parts[0] if _parts else raw_name.strip()

    return {
        "product": {
            "id": product.get("id"),
            "name": capitalize_name(display_name),
            "brand": capitalize_name(display_brand),
            "slug": product.get("slug") or slug,
            "image_url": product.get("image_url") or "",
            "category": product.get("category") or "",
            "ingredients": product.get("ingredients") or "",
            "url": product.get("url") or "",
        },
        "score": score,
        "analysis": analysis,
        "on_shelf": on_shelf,
        "community": community,
    }


@app.post("/api/products/import-url")
async def import_product_from_url(request: ImportUrlRequest, current_user: dict = Depends(get_current_user_optional)):
    try:
        imported = await import_product(request.url)
        if not imported.name:
            raise ProductImportError("Товар на странице не найден.")
        # Нормализуем категорию к канонической категории каталога (не храним сырую/название продукта).
        from .shelf_service import normalize_imported_category
        imported.category = normalize_imported_category(imported.category, imported.name)
        payload = imported.to_dict()
        payload["contributed_by"] = current_user.get("id") if current_user else None
        saved = upsert_imported_product(payload)
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

@app.post("/api/composition/recognize")
async def recognize_composition_endpoint(request: RecognizeCompositionRequest):
    try:
        recognition = await recognize_composition(request.images)
        normalized = recognized_normalized_list(recognition)
        matches = find_product_matches(normalized, limit=5)
        return {
            "recognition": recognition,
            "normalized_ingredients": normalized,
            "matches": matches,
            "confident_threshold": int(MATCH_CONFIDENT_THRESHOLD * 100),
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        print(f"❌ Ошибка распознавания состава: {exc!r}")
        raise HTTPException(status_code=500, detail="Не удалось распознать состав") from exc


@app.post("/api/composition/analyze")
async def analyze_composition_endpoint(
    request: AnalyzeCompositionRequest,
    current_user: dict = Depends(get_current_user_optional),
):
    try:
        from .services import generate_slug, check_product_with_ingredients
        from .auth_routes import save_pending_product

        ingredient_items = [
            {"raw": name, "normalized": name, "confidence": None}
            for name in request.ingredients
        ]
        registered = register_ingredients(ingredient_items)
        normalized = [r["normalized"] for r in registered]
        ingredients_str = ", ".join(normalized)

        result = await check_product_with_ingredients(
            request.product_name,
            request.skin_type,
            request.profile.dict(),
            ingredients_str,
        )

        slug = (request.slug or generate_slug(request.product_name)).strip() or generate_slug(request.product_name)

        # Сохраняем состав, чтобы повторный поиск по имени/составу находил продукт.
        if ingredients_str:
            save_ingredients(request.product_name, ingredients_str, slug)

        user_id = current_user.get("id") if current_user else None
        if ingredients_str and result.get("score", 0) > 0:
            save_pending_product(
                product_name=request.product_name,
                ingredients=ingredients_str,
                user_id=user_id,
            )

        return {
            "score": result.get("score", 50),
            "verdict": result.get("verdict", "Нейтрально"),
            "summary": result.get("summary", "Не удалось получить рекомендацию."),
            "safe_ingredients": result.get("safe_ingredients", []),
            "caution_ingredients": result.get("caution_ingredients", []),
            "active_ingredients": result.get("active_ingredients"),
            "how_to_use": result.get("how_to_use"),
            "expectations": result.get("expectations"),
            "slug": slug,
            "image_url": result.get("image_url") or "",
            "ingredients": ingredients_str,
            "normalized_ingredients": normalized,
            "ingredient_ids": [r["id"] for r in registered],
        }
    except Exception as exc:
        print(f"❌ Ошибка анализа состава: {exc!r}")
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(exc)}") from exc


@app.post("/api/products/create")
async def create_product_endpoint(
    request: CreateProductRequest,
    current_user: dict = Depends(get_current_user_optional),
):
    try:
        from .ingredient_normalizer import canonicalize_ingredient_name
        from .shelf_service import normalize_imported_category
        from .product_dedup import find_or_create_canonical_product

        brand = (request.brand or "").strip()
        name = (request.name or "").strip()

        normalized: list = []
        for ing in request.ingredients:
            canonical = canonicalize_ingredient_name(ing)
            if canonical and canonical not in normalized:
                normalized.append(canonical)
        ingredients_str = ", ".join(normalized)

        # Регистрируем ингредиенты в Ingredient DB (идемпотентно, без дублей).
        if normalized:
            register_ingredients([{"raw": n, "normalized": n} for n in normalized])

        slug = (request.slug or "").strip()
        category = normalize_imported_category("", name)

        saved = find_or_create_canonical_product({
            "name": name,
            "brand": brand or None,
            "ingredients": ingredients_str,
            "category": category,
            "slug": slug or None,
            "source_type": "manual",
        })

        return {
            "success": True,
            "product": {
                "id": saved.get("id"),
                "name": saved.get("name"),
                "slug": saved.get("slug"),
                "brand": saved.get("brand"),
                "image_url": saved.get("image_url"),
                "category": saved.get("category"),
                "ingredients": saved.get("ingredients"),
            },
            "duplicate": not saved.get("is_new", True),
        }
    except Exception as exc:
        print(f"❌ Ошибка создания продукта: {exc!r}")
        raise HTTPException(status_code=500, detail=f"Ошибка создания продукта: {str(exc)}") from exc


@app.get("/api/brands")
async def get_brands(q: str = ""):
    data = await get_categories()
    brands = list(data.get("brands") or [])
    query = (q or "").strip().lower()
    if query:
        brands = [b for b in brands if query in str(b).lower()]
    return {"brands": brands[:30]}



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
            expectations=result.get("expectations"),
            report=result.get("report")
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
            expectations=result.get("expectations"),
            report=result.get("report")
        )
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка проверки: {str(e)}")

@app.post("/api/review")
async def generate_review(request: CheckWithIngredientsRequest):
    """AI-рецензия ПО ЯВНОМУ ЗАПРОСУ пользователя.

    Процент совместимости всегда считает детерминированный Score Engine.
    AI только пишет понятное объяснение по готовому результату и НЕ меняет score.
    """
    try:
        from .services import generate_ai_review

        result = await generate_ai_review(
            request.product_name,
            request.skin_type,
            request.profile.dict(),
            request.ingredients,
        )
        return result
    except Exception as exc:
        print(f"❌ Ошибка AI-рецензии: {exc!r}")
        raise HTTPException(status_code=500, detail="Не удалось сформировать рецензию") from exc


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
            WHERE is_canonical = 1
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

# Выражение для извлечения названия продукта без бренда (бренд хранится до переноса строки)
TITLE_SQL = "REPLACE(TRIM(SUBSTR(name, INSTR(name, CHAR(10)) + 1), CHAR(10) || ' '), CHAR(10), ' ')"


@app.get("/api/catalog")
async def get_catalog(
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    brand: Optional[str] = None,
    cat: Optional[str] = None,
    search: Optional[str] = None,
    letter: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    sort: str = "popular"
):
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    
    where = ["is_canonical = 1"]
    params = []

    # Категория (таксономия, верхний уровень) — точное совпадение по колонке.
    if category:
        where.append("taxonomy_category = ?")
        params.append(category)
    # Подкатегория (таксономия) — точное совпадение по колонке subcategory.
    if subcategory:
        where.append("subcategory = ?")
        params.append(subcategory)
    # Legacy-категория (старое поле category, «Сыворотка» и т.д.) — обратная совместимость.
    if cat:
        where.append("category = ?")
        params.append(cat)
    if brand:
        # бренд хранится первой строкой в name (до переноса строки)
        where.append("lower_ru(name) LIKE ?")
        params.append(f"{brand.lower()}%")
    if search:
        for word in search.strip().lower().split():
            where.append("lower_ru(name) LIKE ?")
            params.append(f"%{word}%")
    if letter:
        where.append(f"lower_ru(SUBSTR({TITLE_SQL}, 1, 1)) = ?")
        params.append(letter.lower())

    where_sql = " AND ".join(where)
    order_sql = f"{TITLE_SQL} COLLATE NOCASE_RU ASC" if sort == "alpha" else "name ASC"

    cursor.execute(
        f"SELECT id, name, slug, image_url, ingredients, category, subcategory, taxonomy_category, brand FROM products WHERE {where_sql} ORDER BY {order_sql} LIMIT ? OFFSET ?",
        params + [limit, offset],
    )
    rows = cursor.fetchall()
    
    cursor.execute(f"SELECT COUNT(*) FROM products WHERE {where_sql}", params)
    total = cursor.fetchone()[0]
    
    conn.close()

    products = [dict(row) for row in rows]
    try:
        from .community_service import CommunityIntelligenceService
        ratings = CommunityIntelligenceService().get_products_community_rating([p["id"] for p in products])
    except Exception:
        ratings = {}
    for p in products:
        r = ratings.get(p.get("id")) or {}
        p["rating"] = r.get("average")
        p["rating_count"] = r.get("count", 0)
    
    return {
        "products": products,
        "total": total,
        "limit": limit,
        "offset": offset
    }

@app.get("/api/catalog/letters")
async def get_catalog_letters():
    """Первые буквы названий продуктов для алфавитной навигации."""
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT DISTINCT lower_ru(SUBSTR({TITLE_SQL}, 1, 1)) AS letter
        FROM products
        WHERE is_canonical = 1 AND name IS NOT NULL AND name != ''
        ORDER BY letter
    """)
    letters = [row[0] for row in cursor.fetchall() if row[0] and row[0].isalnum()]
    conn.close()
    return {"letters": letters}



CATEGORY_KEYWORDS = [
    "Крем", "Сыворотка", "Гель", "Масло", "Тоник", "Тонер", "Лосьон",
    "Молочко", "Маска", "Скраб", "Пилинг", "Шампунь", "Бальзам",
    "Кондиционер", "Пенка", "Эмульсия", "Спрей", "Мист", "Мыло",
]


@app.get("/api/categories")
async def get_categories():
    """Список категорий/подкатегорий (таксономия) и брендов для фильтров"""
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT brand FROM products WHERE is_canonical = 1 AND brand IS NOT NULL AND brand != '' ORDER BY brand")
    brands = {row[0] for row in cursor.fetchall() if row[0]}
    
    # Извлекаем бренды из названий (часть до переноса строки), чтобы не терять бренды
    cursor.execute("SELECT name FROM products WHERE is_canonical = 1 AND (brand IS NULL OR brand = '')")
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

    # Таксономия категорий/подкатегорий для каталога.
    try:
        from .catalog_taxonomy import taxonomy_payload
        taxonomy = taxonomy_payload()
    except Exception:
        taxonomy = []

    return {
        "taxonomy": taxonomy,
        "categories": list(CATEGORY_KEYWORDS),
        "brands": sorted(brands),
    }


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
        base = "SELECT name, slug, image_url, category, brand, ingredients FROM products WHERE is_canonical = 1 AND image_url IS NOT NULL AND image_url != ''"
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


class ShelfBatchDeleteRequest(BaseModel):
    ids: List[int] = []


class ShelfClearRequest(BaseModel):
    cabinet: str = "face"
    category: str = ""


class ShelfAnalyzeRequest(BaseModel):
    slug: str = ""


SHELF_CATEGORIES = ["Очищение", "Тонер", "Сыворотка", "Крем", "SPF", "Маска"]


def _profile_from_user(user: dict) -> dict:
    """Skin Profile из канонического источника (user_profiles, затем users)."""
    from .database import get_user_profile

    profile = get_user_profile(user["id"])
    return {
        "skin_type": profile.get("skin_type") or "",
        "age": profile.get("age") or "",
        "concerns": [c.strip() for c in (profile.get("concerns") or "").split(",") if c.strip()],
        "allergies": [a.strip() for a in (profile.get("allergies") or "").split(",") if a.strip()],
        "custom_text": profile.get("custom_text") or "",
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


async def _ensure_product_checked(current_user: dict, product: dict):
    """Возвращает (score, analysis) проверенного продукта.

    Если продукт ещё не проверен — запускает существующий pipeline (check_product_with_ai)
    и сохраняет результат в историю, чтобы на полке не было состояния «не проверен».
    """
    import json
    from .database import get_connection, AIDERMY_DB
    from .shelf_service import score_product
    from .services import check_product_with_ai

    score, analysis = score_product(current_user, product)
    if score is not None:
        return score, analysis

    name = (product.get("name") or "").replace("\n", " ").strip()
    profile = _profile_from_user(current_user)
    skin_type = profile.get("skin_type") or "Нормальная"

    try:
        result = await check_product_with_ai(name, skin_type, profile)
    except Exception as exc:
        print(f"[ENSURE CHECK] failed: {exc!r}")
        return None, None

    if not result or not result.get("score"):
        return None, None

    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    try:
        existing = cursor.execute(
            "SELECT 1 FROM check_history WHERE user_id = ? AND product_name = ? AND score = ? AND verdict = ? AND summary = ? AND deleted_at IS NULL LIMIT 1",
            (current_user["id"], name, result.get("score"), result.get("verdict"), result.get("summary")),
        ).fetchone()
        if not existing:
            cursor.execute(
                "INSERT INTO check_history (user_id, product_name, skin_type, score, verdict, summary, "
                "ingredients, slug, image_url, active_ingredients, how_to_use, expectations, "
                "safe_ingredients, caution_ingredients, profile_snapshot, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (
                    current_user["id"], name, skin_type, int(result.get("score") or 0),
                    result.get("verdict"), result.get("summary"),
                    result.get("ingredients") or (product.get("ingredients") or ""),
                    result.get("slug") or (product.get("slug") or ""),
                    result.get("image_url") or (product.get("image_url") or ""),
                    json.dumps(result.get("active_ingredients")) if result.get("active_ingredients") is not None else None,
                    json.dumps(result.get("how_to_use")) if result.get("how_to_use") is not None else None,
                    json.dumps(result.get("expectations")) if result.get("expectations") is not None else None,
                    json.dumps(result.get("safe_ingredients") or [], ensure_ascii=False),
                    json.dumps(result.get("caution_ingredients") or [], ensure_ascii=False),
                    json.dumps(profile, ensure_ascii=False),
                ),
            )
            conn.commit()
    finally:
        conn.close()

    analysis = {
        "verdict": result.get("verdict") or "",
        "summary": result.get("summary") or "",
        "score": int(result.get("score") or 0),
        "safe_ingredients": result.get("safe_ingredients") or [],
        "caution_ingredients": result.get("caution_ingredients") or [],
        "active_ingredients": result.get("active_ingredients"),
        "how_to_use": result.get("how_to_use"),
        "expectations": result.get("expectations"),
    }
    return int(result.get("score") or 0), analysis


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

    # Рейтинг сообщества для превью на полке (без отдельной системы рейтингов).
    try:
        from .community_service import CommunityIntelligenceService
        ids = [
            item.get("product_id")
            for cab in cabinets
            for cat in cab.get("categories", [])
            for item in cat.get("items", [])
            if item.get("product_id") is not None
        ]
        ratings = CommunityIntelligenceService().get_products_community_rating(ids)
        for cab in cabinets:
            for cat in cab.get("categories", []):
                for item in cat.get("items", []):
                    r = ratings.get(item.get("product_id")) or {}
                    item["rating"] = r.get("average")
                    item["rating_count"] = r.get("count", 0)
    except Exception:
        pass

    return {"cabinets": cabinets}


@app.post("/api/shelf")
async def add_to_shelf(request: ShelfAddRequest, current_user: dict = Depends(get_current_user)):
    from .database import get_product_by_slug, get_user_shelf, add_product_to_shelf
    from .shelf_service import (
        canonical_category,
        CABINET_BY_KEY,
        is_product_compatible,
        infer_cabinet_category,
        cabinet_applies_scoring,
        get_personalized_score,
    )

    product = get_product_by_slug(request.slug)
    if not product:
        raise HTTPException(status_code=404, detail="Продукт не найден")

    # Если полка не указана явно — определяем её автоматически по названию/категории.
    if not (request.category or "").strip():
        cabinet, category = infer_cabinet_category(product.get("category"), product.get("name"))
    else:
        cabinet = (request.cabinet or "face").strip().lower()
        if cabinet not in CABINET_BY_KEY:
            cabinet = "face"
        category = canonical_category(cabinet, request.category)

    ok, reason = is_product_compatible(product, cabinet, category)
    if not ok:
        raise HTTPException(status_code=422, detail=reason)

    for s in get_user_shelf(current_user["id"]):
        if s["product_id"] == product["id"]:
            return {"status": "ok", "duplicate": True, "item": {"id": s["id"], "product_id": product["id"]}}

    # При добавлении на полку score = история (snapshot) → пересчёт из Static Product Model.
    score = None
    if cabinet_applies_scoring(cabinet):
        score = get_personalized_score(current_user, product)

    item = add_product_to_shelf(current_user["id"], product["id"], category, cabinet=cabinet, score=score)
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

    recommendations = await recommend_products(current_user, cabinet, category, exclude_slugs)
    return {"cabinet": cabinet, "category": category, "recommendations": recommendations}


@app.post("/api/shelf/analyze")
async def analyze_shelf_product(request: ShelfAnalyzeRequest, current_user: dict = Depends(get_current_user)):
    """Запускает анализ продукта (существующий pipeline) и сохраняет результат в историю.
    Если анализ уже есть — возвращает готовый результат без повторного запуска."""
    import json
    from .database import get_product_by_slug, get_connection, AIDERMY_DB
    from .shelf_service import score_product
    from .services import check_product_with_ai

    product = get_product_by_slug(request.slug)
    if not product:
        raise HTTPException(status_code=404, detail="Продукт не найден")

    name = (product.get("name") or "").replace("\n", " ").strip()

    existing_score, existing_analysis = score_product(current_user, product)
    if existing_score is not None:
        return {"status": "ok", "cached": True, "score": existing_score, "analysis": existing_analysis}

    profile = _profile_from_user(current_user)
    skin_type = profile.get("skin_type") or "Нормальная"

    try:
        result = await check_product_with_ai(name, skin_type, profile)
    except Exception as exc:
        print(f"[ANALYZE] failed: {exc!r}")
        raise HTTPException(status_code=502, detail="Не удалось выполнить анализ") from exc

    if not result or not result.get("score"):
        return {"status": "error", "cached": False, "score": None, "analysis": None, "detail": "Состав продукта неизвестен"}

    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    try:
        existing = cursor.execute(
            "SELECT 1 FROM check_history WHERE user_id = ? AND product_name = ? AND score = ? AND verdict = ? AND summary = ? AND deleted_at IS NULL LIMIT 1",
            (current_user["id"], name, result.get("score"), result.get("verdict"), result.get("summary")),
        ).fetchone()
        if not existing:
            cursor.execute('''
                INSERT INTO check_history (
                    user_id, product_name, skin_type, score, verdict, summary,
                    ingredients, slug, image_url, active_ingredients, how_to_use, expectations,
                    safe_ingredients, caution_ingredients, profile_snapshot, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                current_user["id"], name, skin_type, int(result.get("score") or 0), result.get("verdict"), result.get("summary"),
                result.get("ingredients") or (product.get("ingredients") or ""),
                result.get("slug") or (product.get("slug") or ""),
                result.get("image_url") or (product.get("image_url") or ""),
                json.dumps(result.get("active_ingredients")) if result.get("active_ingredients") is not None else None,
                json.dumps(result.get("how_to_use")) if result.get("how_to_use") is not None else None,
                json.dumps(result.get("expectations")) if result.get("expectations") is not None else None,
                json.dumps(result.get("safe_ingredients") or [], ensure_ascii=False),
                json.dumps(result.get("caution_ingredients") or [], ensure_ascii=False),
                json.dumps(profile, ensure_ascii=False),
            ))
            conn.commit()
    finally:
        conn.close()

    # Обогащение базы знаний ингредиентов уже выполнено внутри
    # check_product_with_ai -> check_product_with_ingredients (не дублируем).

    analysis = {
        "verdict": result.get("verdict") or "",
        "summary": result.get("summary") or "",
        "score": int(result.get("score") or 0),
        "safe_ingredients": result.get("safe_ingredients") or [],
        "caution_ingredients": result.get("caution_ingredients") or [],
        "active_ingredients": result.get("active_ingredients"),
        "how_to_use": result.get("how_to_use"),
        "expectations": result.get("expectations"),
    }
    return {"status": "ok", "cached": False, "score": int(result.get("score") or 0), "analysis": analysis}


@app.post("/api/shelf/review")
async def review_shelf_product(request: ShelfAnalyzeRequest, current_user: dict = Depends(get_current_user)):
    """AI-отчёт («Показать отчёт») ПО ЯВНОМУ ЗАПРОСУ.

    Требует существующий актуальный User Analysis (история проверок).
    Score НЕ пересчитывается — AI только пишет человеческое объяснение
    уже рассчитанного результата. Отчёт кэшируется в check_history.ai_report.
    """
    from .database import get_product_by_slug, save_ai_report
    from .shelf_service import score_product
    from .services import generate_ai_report

    product = get_product_by_slug(request.slug)
    if not product:
        raise HTTPException(status_code=404, detail="Продукт не найден")

    name = (product.get("name") or "").replace("\n", " ").strip()

    # Источник — актуальный User Analysis (история проверок).
    score, analysis = score_product(current_user, product)
    if score is None:
        raise HTTPException(status_code=409, detail="Анализ ещё не выполнен — сначала проверьте совместимость.")

    # Если отчёт уже сгенерирован для этого актуального анализа — возвращаем сохранённый.
    if analysis and analysis.get("report"):
        return {"score": score, "review": analysis["report"]}

    profile = _profile_from_user(current_user)
    try:
        review = await generate_ai_report(name, analysis, profile)
    except Exception as exc:
        print(f"[REVIEW] failed: {exc!r}")
        raise HTTPException(status_code=502, detail="Не удалось сформировать отчёт") from exc

    save_ai_report(current_user["id"], product.get("slug") or request.slug, review)

    return {"score": score, "review": review}


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


class RecommendationFeedbackRequest(BaseModel):
    slug: str = ""
    cabinet: str = "face"
    category: str = ""
    reason: str = ""
    note: str = ""


class ShelfRemovalFeedbackRequest(BaseModel):
    slug: str = ""
    reason: str = ""
    note: str = ""


@app.post("/api/recommendations/feedback")
async def save_recommendation_feedback(request: RecommendationFeedbackRequest, current_user: dict = Depends(get_current_user)):
    """Сохраняет дизлайк рекомендации и предлагает другой подходящий продукт."""
    from .database import get_product_by_slug, save_recommendation_feedback
    from .shelf_service import recommend_products, canonical_category, CABINET_BY_KEY

    product = get_product_by_slug(request.slug) if request.slug else None
    product_id = product["id"] if product else None

    save_recommendation_feedback(
        current_user["id"], product_id, request.slug,
        request.cabinet, request.category, request.reason, request.note,
    )

    replacement = []
    cabinet = (request.cabinet or "face").strip().lower()
    if cabinet in CABINET_BY_KEY and request.category:
        category = canonical_category(cabinet, request.category)
        replacement = await recommend_products(current_user, cabinet, category, {request.slug})

    return {"status": "ok", "replacement": replacement}


@app.post("/api/shelf/removal-feedback")
async def save_shelf_removal_feedback(request: ShelfRemovalFeedbackRequest, current_user: dict = Depends(get_current_user)):
    """Сохраняет причину удаления продукта с полки."""
    from .database import get_product_by_slug, save_shelf_removal_feedback

    product = get_product_by_slug(request.slug) if request.slug else None
    product_id = product["id"] if product else None

    save_shelf_removal_feedback(current_user["id"], product_id, request.slug, request.reason, request.note)
    return {"status": "ok"}


@app.post("/api/shelf/delete-batch")
async def delete_shelf_batch(request: ShelfBatchDeleteRequest, current_user: dict = Depends(get_current_user)):
    from .database import remove_products_from_shelf
    deleted = remove_products_from_shelf(current_user["id"], request.ids)
    return {"status": "ok", "deleted": deleted}


@app.post("/api/shelf/clear")
async def clear_shelf(request: ShelfClearRequest, current_user: dict = Depends(get_current_user)):
    from .database import get_user_shelf, get_product_by_id, remove_products_from_shelf
    from .shelf_service import resolve_shelf_cabinet, canonical_category, CABINET_BY_KEY

    cabinet = (request.cabinet or "face").strip().lower()
    if cabinet not in CABINET_BY_KEY:
        cabinet = "face"
    category = canonical_category(cabinet, request.category) if request.category.strip() else ""

    ids = []
    for s in get_user_shelf(current_user["id"]):
        p = get_product_by_id(s["product_id"])
        if not p:
            continue
        c_cabinet, c_category = resolve_shelf_cabinet(s.get("category"), s.get("cabinet"), p.get("name") or "")
        if c_cabinet != cabinet:
            continue
        if category and c_category != category:
            continue
        ids.append(s["id"])

    deleted = remove_products_from_shelf(current_user["id"], ids)
    return {"status": "ok", "deleted": deleted}


@app.post("/api/shelf/reset")
async def reset_shelf(current_user: dict = Depends(get_current_user)):
    """Полный сброс пользовательского контекста полки (например, при изменении
    анкеты, влияющей на анализ). НЕ удаляет Static Product Model / Product DB."""
    from .database import clear_user_shelf
    deleted = clear_user_shelf(current_user["id"])
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