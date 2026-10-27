import os
import re
import logging
import asyncio
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Пишем диагностические логи в файл (gunicorn --daemon уводит stderr в /dev/null).
logging.basicConfig(
    filename=os.path.join(os.path.dirname(__file__), '..', 'aidermy_app.log'),
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException, Depends, status, Request, Header, File, UploadFile
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from .ingredient_normalizer import split_inci_tokens

from .models import (
    CheckRequest,
    CheckResponse,
    CheckWithIngredientsRequest,
    ImportUrlRequest,
    RecognizeCompositionRequest,
    AnalyzeCompositionRequest,
    CreateProductRequest,
    ProductIdentifyRequest,
    ProductScanRequest,
    ProductWebSearchRequest,
)
from .services import check_product_with_ai, check_product_with_ingredients, search_products, capitalize_name
from .database import init_db, get_all_ingredients, get_all_check_history, save_check_result, get_check_stats, get_connection, PRODUCTS_DB, upsert_imported_product, save_ingredients
from .auth_routes import router as auth_router
from .community_routes import router as community_router
from .billing_routes import router as billing_router
from .admin_routes import setup_admin_routes
from .calibration_routes import setup_calibration_routes
from .report_prompt_routes import setup_report_prompt_routes
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
    identify_product,
)
from .product_identification import (
    find_product_in_db,
    has_reliable_inci,
    web_search_product,
)
from .product_scan import ProductScanError, scan_product_package

# PostgreSQL mode: не создавать и не мигрировать локальные SQLite-базы
# при импорте приложения. Старые SQLite-вызовы должны быть мигрированы отдельно.
_USE_POSTGRES_STORAGE = (
    os.getenv("ANALYSIS_STORAGE", "").strip().lower() in {"postgres", "postgresql", "supabase"}
    and os.getenv("CATALOG_READ_FROM_POSTGRES", "").strip().lower() == "true"
)

if not _USE_POSTGRES_STORAGE:
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

    # Миграция report prompt: добавляем {{category_knowledge}} (база знаний категорий).
    try:
        from .report_prompt import ensure_category_knowledge_prompt
        ensure_category_knowledge_prompt()
    except Exception as exc:
        print(f"[INIT] category knowledge prompt migration failed: {exc!r}")

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
app.include_router(billing_router)

# Регистрируем админ-роуты
setup_admin_routes(app)
setup_calibration_routes(app)
setup_report_prompt_routes(app)

# Evaluation V2: новая механика анализа. Хранилище/провайдер/загрузчик подключаются
# из окружения; отсутствие Supabase или ключа не роняет приложение — эндпоинты
# честно отвечают 503, а схема БД только проверяется (миграции не применяются).
try:
    from .evaluation.runtime import configure_evaluation, evaluation_schema_status

    if os.getenv("AIDERMY_EVALUATION_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        logger.info("[EVALUATION] disabled by AIDERMY_EVALUATION_ENABLED")
    else:
        configure_evaluation(app)
        _evaluation_schema = evaluation_schema_status()
        if _evaluation_schema.get("configured") and not _evaluation_schema.get("ready"):
            logger.warning(
                "[EVALUATION] schema is not ready, missing tables: %s",
                ", ".join(_evaluation_schema.get("missing_tables") or []),
            )
except Exception as exc:  # noqa: BLE001 - readiness must not break the app
    logger.exception("[EVALUATION] setup failed: %s", exc)

# Compatibility sets/tasks reuse the Evaluation V2 service after it is wired.
try:
    from .compat_routes import setup_compat_routes

    setup_compat_routes(app)
except Exception as exc:  # noqa: BLE001 - compatibility must not break the existing app
    logger.exception("[COMPAT] routes are unavailable: %s", exc)

@app.get("/api/health")
async def health():
    return {"status": "ok", "deepseek": "connected" if DEEPSEEK_API_KEY else "missing"}


def _verified_product_ids(product_ids: list[int]) -> set[int]:
    """Read-only composition marker; a broken evaluation store never hides products."""
    try:
        store = getattr(app.state, "evaluation_store", None)
        if store is None or not hasattr(store, "verified_product_ids"):
            return set()
        return set(store.verified_product_ids(product_ids))
    except Exception:  # noqa: BLE001 - catalog must remain available
        return set()


@app.get("/api/products")
async def get_products(q: str = ""):
    products = search_products(q)
    verified = _verified_product_ids(
        [int(p["id"]) for p in products if p.get("id") is not None]
    )
    for product in products:
        product["composition_verified"] = product.get("id") in verified
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
            "barcode": product.get("barcode") or "",
            "variant": product.get("variant") or "",
            "composition_verified": bool(
                product.get("id")
                and int(product["id"]) in _verified_product_ids([int(product["id"])])
            ),
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
        # Если сканер не определил бренд/название корректно (например, положил INCI
        # в поле name), ищем существующий товар по составу и используем его
        # canonical name/brand — чтобы не создавать дубликат.
        if imported.ingredients_raw and (not imported.brand or len(imported.name or "") > 150):
            try:
                import re as _re
                from .vision_service import find_product_matches
                raw_parts = [p.strip().replace("\u200b", "").replace("\u200c", "").replace("\ufeff", "") for p in split_inci_tokens(imported.ingredients_raw) if p.strip()]
                matches = find_product_matches(raw_parts, limit=1)
                if matches and matches[0].get("match_percent", 0) >= 85:
                    m = matches[0]
                    imported.name = m.get("name") or imported.name
                    imported.brand = m.get("brand") or imported.brand
            except Exception:
                pass
        # Нормализуем категорию к канонической категории каталога (не храним сырую/название продукта).
        from .shelf_service import normalize_imported_category
        imported.category = normalize_imported_category(imported.category, imported.name)
        payload = imported.to_dict()
        payload["contributed_by"] = current_user.get("id") if current_user else None
        saved = upsert_imported_product(payload)
        # Фоновая обработка изображения: удаление белого фона + публикация в S3.
        if saved.get("image_url") and saved.get("slug"):
            try:
                from .image_storage import process_product_image_sync
                asyncio.create_task(asyncio.to_thread(
                    process_product_image_sync,
                    saved.get("id"),
                    saved.get("slug"),
                    saved.get("image_url"),
                ))
            except Exception:
                pass
        saved_ingredients = saved.get("ingredients") or ""
        product = {
            "name": saved.get("name"),
            "brand": saved.get("brand"),
            "manufacturer": saved.get("manufacturer"),
            "image_url": saved.get("image_url"),
            "price": imported.price,
            "currency": imported.currency,
            "volume": imported.volume,
            "category": saved.get("category"),
            "description": imported.description,
            "ingredients_raw": saved_ingredients,
            "has_inci": has_reliable_inci({"ingredients": saved_ingredients}),
            "ingredients_source": (
                "page" if imported.ingredients_raw
                else "database" if saved_ingredients
                else "missing"
            ),
            "composition_verified": bool(
                saved.get("id")
                and int(saved["id"]) in _verified_product_ids([int(saved["id"])])
            ),
            "source_url": saved.get("url"),
            "slug": saved.get("slug"),
            "id": saved.get("id"),
        }
        return {"success": True, "product": product}
    except ProductImportError as exc:
        # Preserve classification: timeout -> 504, invalid URL -> 400,
        # access/anti-bot/no content -> 422, missing page -> 404.
        logger.info(
            "[SCRAPER] Import classified code=%s provider=%s status=%s",
            getattr(exc, "code", "import_failed"),
            getattr(exc, "provider", None),
            getattr(exc, "status_code", 422),
        )
        raise HTTPException(
            status_code=int(getattr(exc, "status_code", 422)),
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("[SCRAPER] Import failed unexpectedly")
        raise HTTPException(status_code=502, detail="Не удалось автоматически получить данные товара. Проверьте ссылку или найдите товар по названию.") from exc

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


# Таймауты внешних операций в pipeline идентификации: гарантируют, что пользовательский
# запрос никогда не зависнет бесконечно (Vision / Web Search / scraper).
VISION_TIMEOUT = 90.0
WEB_SEARCH_TIMEOUT = 180.0
SCAN_TIMEOUT = 300.0


@app.post("/api/product/identify")
async def identify_product_endpoint(request: ProductIdentifyRequest):
    """Этап 1: фото продукта -> бренд/название -> поиск в собственной БД."""
    try:
        logger.info("[IDENTIFY] PHOTO_RECEIVED images=%d", len(request.images or []))
        identified = await asyncio.wait_for(identify_product(request.images), timeout=VISION_TIMEOUT)
        logger.info("[IDENTIFY] VISION_DONE brand=%r product_name=%r", identified.get("brand"), identified.get("product_name") or identified.get("name"))
        product_name = identified.get("product_name") or identified.get("name") or ""
        logger.info("[IDENTIFY] DB_LOOKUP_START brand=%r name=%r", identified.get("brand"), product_name)
        product = find_product_in_db(identified.get("brand") or "", product_name)
        logger.info("[IDENTIFY] DB_LOOKUP_DONE -> %s", "FOUND" if product else "MISS")
        return {
            "identified": identified,
            "product": product,
            "has_inci": has_reliable_inci(product),
        }
    except asyncio.TimeoutError:
        logger.error("[IDENTIFY] IDENTIFICATION_ERROR vision_timeout")
        raise HTTPException(status_code=504, detail="Не удалось определить продукт: распознавание не завершилось вовремя.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[IDENTIFY] IDENTIFICATION_ERROR")
        print(f"❌ Ошибка идентификации продукта: {exc!r}")
        raise HTTPException(status_code=500, detail="Не удалось определить продукт") from exc


@app.post("/api/product/scan")
async def product_scan_endpoint(request: ProductScanRequest):
    """Единый скан: две обязательные фотографии -> карточка/черновик без записи в БД."""
    try:
        from . import product_scan as product_scan_module

        back_images = list(getattr(request, "back_images", None) or [])
        back_image = getattr(request, "back_image", None)
        if back_image and back_image not in back_images:
            back_images.insert(0, back_image)
        # A front photo alone is a valid identification attempt. If the
        # product/INCI cannot be found, the response asks for a back photo or
        # manual/link input instead of rejecting the request up front.
        return await asyncio.wait_for(
            product_scan_module.scan_product_package(request.front_image, back_images),
            timeout=SCAN_TIMEOUT,
        )
    except ProductScanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except asyncio.TimeoutError:
        logger.error("[SCAN] IDENTIFICATION_ERROR scan_timeout")
        raise HTTPException(
            status_code=504,
            detail="Распознавание не завершилось вовремя. Попробуйте ещё раз.",
        ) from None
    except RuntimeError as exc:
        logger.exception("[SCAN] IDENTIFICATION_ERROR vision_runtime")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[SCAN] IDENTIFICATION_ERROR")
        print(f"❌ Ошибка сканирования продукта: {exc!r}")
        raise HTTPException(status_code=500, detail="Не удалось распознать продукт по фото") from exc


@app.post("/api/product/web-search")
async def product_web_search_endpoint(request: ProductWebSearchRequest):
    """Автоматический Web Search: search -> URL -> scraper -> INCI -> сохранить canonical."""
    try:
        logger.info("[WEBSEARCH] WEB_SEARCH_START brand=%r name=%r", request.brand, request.name)
        found = await asyncio.wait_for(
            web_search_product(request.brand, request.name, request.variant),
            timeout=WEB_SEARCH_TIMEOUT,
        )
        logger.info("[WEBSEARCH] WEB_SEARCH_DONE found=%s", bool(found))
        if not found:
            return {"found": False, "product": None}
        from .product_dedup import find_or_create_canonical_product

        saved = find_or_create_canonical_product({
            "name": found["name"],
            "brand": found["brand"],
            "manufacturer": found.get("manufacturer") or "",
            "ingredients": found["ingredients"],
            "url": found.get("source_url") or "",
            "image_url": found.get("image_url") or "",
            "category": found.get("category") or "",
            "volume": found.get("volume") or "",
            "description": found.get("description") or "",
            "source_type": "web_search",
        })
        logger.info("[WEBSEARCH] IDENTIFICATION_DONE slug=%s", saved.get("slug"))
        return {
            "found": True,
            "product": {
                "slug": saved.get("slug") or "",
                "name": saved.get("name") or "",
                "brand": saved.get("brand") or "",
                "ingredients": saved.get("ingredients") or "",
                "image_url": saved.get("image_url") or "",
            },
            "source_url": found.get("source_url") or "",
        }
    except asyncio.TimeoutError:
        logger.error("[WEBSEARCH] IDENTIFICATION_ERROR web_search_timeout")
        return {"found": False, "product": None}
    except Exception as exc:
        logger.exception("[WEBSEARCH] IDENTIFICATION_ERROR")
        print(f"❌ Ошибка web-search продукта: {exc!r}")
        return {"found": False, "product": None}


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
        # Списание балла за проверку: тот же учёт, что и в /api/check.
        _charge_check(user_id, request.product_name)

        conn_products = get_connection(PRODUCTS_DB)
        existing_product = conn_products.execute(
            "SELECT id, slug FROM products WHERE name = ? OR slug = ?",
            (request.product_name, slug),
        ).fetchone()
        conn_products.close()
        product_id = existing_product["id"] if existing_product else None
        if existing_product and existing_product["slug"]:
            slug = existing_product["slug"]

        if ingredients_str and result.get("score") is not None:
            save_pending_product(
                product_name=request.product_name,
                ingredients=ingredients_str,
                user_id=user_id,
            )

        analysis_id = None
        if user_id:
            saved = _save_system_analysis(
                current_user,
                product_id=product_id,
                slug=slug,
                result=result,
                profile_snapshot=request.profile.dict(),
            )
            analysis_id = saved.get("id") if saved else None

        pending = bool(result.get("pending"))
        return {
            "score": result.get("score") if result.get("phase1_status") in {"passed", "blocked"} else None,
            "verdict": "Требуется время" if pending else (result.get("verdict") or "Неизвестный состав"),
            "summary": (
                "Исследование ингредиентов ещё не завершено — это займёт больше времени, возвращайтесь позже."
                if pending
                else (result.get("summary") or "")
            ),
            "safe_ingredients": result.get("safe_ingredients", []),
            "caution_ingredients": result.get("caution_ingredients", []),
            "active_ingredients": None,
            "how_to_use": None,
            "expectations": None,
            "goal_evidence": result.get("goal_evidence") or [],
            "slug": slug,
            "image_url": result.get("image_url") or "",
            "ingredients": ingredients_str,
            "normalized_ingredients": normalized,
            "ingredient_ids": [r["id"] for r in registered],
            "analysis_id": analysis_id,
            "report": None,
            "phase1_status": result.get("phase1_status"),
            "recommendation_status": result.get("recommendation_status"),
            "pending": pending,
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
        from .product_dedup import ProductConflictError, find_or_create_canonical_product

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
        category = (request.category or "").strip() or normalize_imported_category("", name)

        # Лицевое фото из единого сканирования сохраняем в постоянное хранилище.
        # При ошибке S3 карточку без фото не создаём и успех не выдаём.
        front_image_url = ""
        if request.image_data_url:
            try:
                from .image_storage import upload_product_source_image

                front_image_url = await asyncio.to_thread(
                    upload_product_source_image,
                    request.image_data_url,
                    f"{brand}-{name}",
                )
            except Exception as exc:
                print(f"❌ Ошибка сохранения лицевого фото: {exc!r}")
                raise HTTPException(
                    status_code=502,
                    detail="Не удалось сохранить фото продукта. Попробуйте ещё раз.",
                ) from exc

        saved = find_or_create_canonical_product({
            "name": name,
            "brand": brand or None,
            "ingredients": ingredients_str,
            "category": category,
            "slug": slug or None,
            "image_url": front_image_url or None,
            "url": (request.source_url or "").strip() or None,
            "volume": (request.volume or "").strip() or None,
            "variant": (request.variant or "").strip() or None,
            "barcode": (request.barcode or "").strip() or None,
            "source_type": (request.source_type or "").strip() or "manual",
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
                "source_url": saved.get("url"),
                "volume": saved.get("volume"),
                "variant": saved.get("variant") or (request.variant or "").strip() or None,
                "barcode": saved.get("barcode") or (request.barcode or "").strip() or None,
            },
            "duplicate": not saved.get("is_new", True),
        }
    except ProductConflictError as exc:
        return JSONResponse(
            status_code=409,
            content={
                "status": "conflict",
                "message": str(exc),
                "barcode": exc.barcode,
                "product": exc.product,
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        print(f"❌ Ошибка создания продукта: {exc!r}")
        raise HTTPException(status_code=500, detail=f"Ошибка создания продукта: {str(exc)}") from exc


@app.post("/api/uploads/product-image")
async def upload_product_image(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Загрузка фото продукта при ручном добавлении.

    Безопасность:
      * размер ограничен 8 МБ;
      * формат определяется по СОДЕРЖИМОМУ (Pillow), а не по MIME клиента;
      * допускаются только JPEG/PNG/WebP;
      * EXIF удаляется, изображение перекодируется и уменьшается до 1600px;
      * файл кладётся в S3 (Yandex Object Storage) под user-uploads/<user_id>/,
        а не в отдельное поле продукта.
    """
    import io
    import uuid

    from PIL import Image, ImageOps

    from .image_storage import upload_image

    MAX_BYTES = 8 * 1024 * 1024
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Пустой файл")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Файл больше 8 МБ")

    try:
        probe = Image.open(io.BytesIO(data))
        probe.verify()
        real_format = (probe.format or "").upper()
    except Exception:
        raise HTTPException(status_code=400, detail="Не удалось распознать изображение")

    if real_format not in {"JPEG", "PNG", "WEBP"}:
        raise HTTPException(status_code=400, detail="Поддерживаются только JPEG, PNG и WebP")

    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        if img.mode not in {"RGB", "L"}:
            img = img.convert("RGB")
        img.thumbnail((1600, 1600))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=88, optimize=True)
        payload = out.getvalue()
    except Exception:
        raise HTTPException(status_code=400, detail="Не удалось обработать изображение")

    key = f"user-uploads/{current_user['id']}/{uuid.uuid4().hex}.jpg"
    try:
        url = upload_image(key, payload, content_type="image/jpeg")
    except Exception as exc:
        print(f"[UPLOAD] s3 failed: {exc!r}")
        raise HTTPException(status_code=502, detail="Хранилище изображений недоступно")

    return {"url": url, "key": key, "content_type": "image/jpeg", "bytes": len(payload)}


@app.get("/api/legal/meta")
async def legal_meta_endpoint():
    """Версии юридических документов и статус реквизитов для фронтенда."""
    from .legal_documents import legal_meta

    return legal_meta()


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
    guest_session = None
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
            "SELECT id, slug FROM products WHERE name = ? OR slug = ?",
            (request.product_name, slug)
        )
        existing_product = cursor_products.fetchone()
        conn_products.close()
        
        user_id = current_user.get('id') if current_user else None
        product_id = existing_product['id'] if existing_product else None

        # Без авторизации проверка доступна только внутри гостевого сеанса
        # (одна проверка на сеанс, ограничение проверяется на сервере).
        if not user_id:
            guest_session = _guest_gate(getattr(request, "guest_token", None) or "")

        # Пользовательское фото (если приложено при ручном добавлении).
        request_image_url = (getattr(request, "image_url", None) or "").strip()
        if user_id and slug and request_image_url:
            try:
                from .database import save_user_product_image
                save_user_product_image(user_id, slug, request_image_url)
            except Exception as exc:
                print(f"[IMAGE] save failed: {exc!r}")

        # Списание балла за проверку (Слой 1).
        _charge_check(user_id, request.product_name)

        # Сохраняем СИСТЕМНУЮ проверку (Слой 1) в актуальный User Analysis.
        # Описание (report) НЕ сохраняется здесь — оно запрашивается отдельно.
        analysis_id = None
        if user_id:
            saved = _save_system_analysis(
                current_user,
                product_id=product_id,
                slug=slug or "",
                result=result,
                profile_snapshot=request.profile.dict(),
            )
            analysis_id = saved.get("id") if saved else None
        elif guest_session is not None:
            _store_guest_check_result(
                guest_session,
                result=result,
                product_name=request.product_name,
                profile=request.profile.dict(),
                slug=slug or "",
                product_id=product_id,
            )

        pending = bool(result.get("pending"))
        return CheckResponse(
            score=result.get("score") if not pending and result.get("phase1_status") in {"passed", "blocked"} else None,
            verdict="Требуется время" if pending else (result.get("verdict") or "Неизвестный состав"),
            summary=("Исследование ингредиентов ещё не завершено — это займёт больше времени, возвращайтесь позже." if pending else (result.get("summary") or "")),
            safe_ingredients=result.get("safe_ingredients", []),
            caution_ingredients=result.get("caution_ingredients", []),
            cached=False,
            slug=slug,
            image_url=request_image_url or result.get("image_url"),
            active_ingredients=result.get("active_ingredients"),
            how_to_use=result.get("how_to_use"),
            expectations=result.get("expectations"),
            goal_evidence=result.get("goal_evidence") or [],
            report=None,
            analysis_id=analysis_id,
            phase1_status=result.get("phase1_status"),
            recommendation_status=result.get("recommendation_status"),
            interaction_replacement=result.get("interaction_replacement"),
            score_scope=result.get("score_scope"),
            pending=pending,
        )
    except HTTPException:
        _refund_guest_check(guest_session)
        raise
    except Exception as e:
        _refund_guest_check(guest_session)
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")
    
@app.post("/api/check-with-ingredients", response_model=CheckResponse)
async def check_with_ingredients(
    request: Request, 
    check_request: CheckWithIngredientsRequest,
    current_user: dict = Depends(get_current_user_optional)  # <-- ТЕПЕРЬ РАБОТАЕТ
):
    guest_session = None
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
            "SELECT id, slug FROM products WHERE name = ? OR slug = ?",
            (check_request.product_name, slug)
        )
        existing_product = cursor_products.fetchone()
        conn_products.close()
        if existing_product and existing_product["slug"]:
            slug = existing_product["slug"]
        
        user_id = current_user.get('id') if current_user else None
        product_id = existing_product['id'] if existing_product else None

        # Без авторизации проверка доступна только внутри гостевого сеанса
        # (одна проверка на сеанс, ограничение проверяется на сервере).
        if not user_id:
            guest_session = _guest_gate(getattr(check_request, "guest_token", None) or "")

        # Пользовательское фото (если приложено при ручном добавлении).
        request_image_url = (getattr(check_request, "image_url", None) or "").strip()
        if user_id and slug and request_image_url:
            try:
                from .database import save_user_product_image
                save_user_product_image(user_id, slug, request_image_url)
            except Exception as exc:
                print(f"[IMAGE] save failed: {exc!r}")

        # Списание балла за проверку (Слой 1): то же правило, что и в /api/check,
        # чтобы второй вход не стал бесплатным обходом лимита.
        _charge_check(user_id, check_request.product_name)

        # Отправляем в модерацию
        if check_request.ingredients and result.get("score") is not None:
            save_pending_product(
                product_name=check_request.product_name,
                ingredients=check_request.ingredients,
                user_id=user_id
            )
        
        # Сохраняем СИСТЕМНУЮ проверку (Слой 1) в актуальный User Analysis,
        # чтобы отчёт открывался по analysis_id (как в /api/check).
        analysis_id = None
        if user_id:
            saved = _save_system_analysis(
                current_user,
                product_id=product_id,
                slug=slug or "",
                result=result,
                profile_snapshot=check_request.profile.dict(),
            )
            analysis_id = saved.get("id") if saved else None
        elif guest_session is not None:
            _store_guest_check_result(
                guest_session,
                result=result,
                product_name=check_request.product_name,
                profile=check_request.profile.dict(),
                slug=slug or "",
                product_id=product_id,
                ingredients_raw=check_request.ingredients or "",
            )
        
        pending = bool(result.get("pending"))
        return CheckResponse(
            score=result.get("score") if not pending and result.get("phase1_status") in {"passed", "blocked"} else None,
            verdict="Требуется время" if pending else (result.get("verdict") or "Неизвестный состав"),
            summary=("Исследование ингредиентов ещё не завершено — это займёт больше времени, возвращайтесь позже." if pending else (result.get("summary") or "")),
            safe_ingredients=result.get("safe_ingredients", []),
            caution_ingredients=result.get("caution_ingredients", []),
            cached=False,
            slug=slug,
            image_url=request_image_url or result.get("image_url"),
            active_ingredients=result.get("active_ingredients"),
            how_to_use=result.get("how_to_use"),
            expectations=result.get("expectations"),
            goal_evidence=result.get("goal_evidence") or [],
            report=None,
            analysis_id=analysis_id,
            phase1_status=result.get("phase1_status"),
            recommendation_status=result.get("recommendation_status"),
            interaction_replacement=result.get("interaction_replacement"),
            score_scope=result.get("score_scope"),
            pending=pending,
        )
        
    except HTTPException:
        _refund_guest_check(guest_session)
        raise
    except Exception as e:
        _refund_guest_check(guest_session)
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
    catalog_category: Optional[str] = None,
    catalog_subcategory: Optional[str] = None,
    brand: Optional[str] = None,
    cat: Optional[str] = None,
    search: Optional[str] = None,
    letter: Optional[str] = None,
    shelf_category: Optional[str] = None,
    cabinet: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    sort: str = "popular",
    current_user: dict = Depends(get_current_user_optional),
):
    # Переключение только чтения каталога; по умолчанию используется SQLite.
    use_postgres = os.getenv("CATALOG_READ_FROM_POSTGRES", "").strip().lower() == "true"

    if use_postgres:
        from .postgres_catalog import get_catalog_page

        search_query = (search or "").strip()
        if search_query:
            # Fetch a bounded candidate pool with all non-search filters, then
            # rank in Python. This supports typos/transliteration without
            # changing the catalog or adding a search server.
            pool = get_catalog_page(
                category=category,
                subcategory=subcategory,
                catalog_category=catalog_category,
                catalog_subcategory=catalog_subcategory,
                brand=brand,
                cat=cat,
                letter=letter,
                shelf_category=shelf_category,
                cabinet=cabinet,
                limit=5000,
                offset=0,
                sort=sort,
            )
            from .catalog_search import rank_products

            products, total = rank_products(
                [dict(row) for row in pool["products"]],
                search_query,
                limit=limit,
                offset=offset,
            )
        else:
            result = get_catalog_page(
                category=category,
                subcategory=subcategory,
                catalog_category=catalog_category,
                catalog_subcategory=catalog_subcategory,
                brand=brand,
                cat=cat,
                search=None,
                letter=letter,
                shelf_category=shelf_category,
                cabinet=cabinet,
                limit=limit,
                offset=offset,
                sort=sort,
            )
            products = [dict(row) for row in result["products"]]
            total = result["total"]
    else:
        conn = get_connection(PRODUCTS_DB)
        cursor = conn.cursor()

        where = ["is_canonical = 1"]
        params = []

        if category:
            where.append("taxonomy_category = ?")
            params.append(category)
        if subcategory:
            where.append("subcategory = ?")
            params.append(subcategory)
        if cat:
            where.append("category = ?")
            params.append(cat)

        if shelf_category and cabinet:
            from .shelf_service import RECOMMEND_RULES
            rule = (RECOMMEND_RULES.get(cabinet) or {}).get(shelf_category) or {}
            shelf_cats = rule.get("categories") or []
            shelf_kws = rule.get("keywords") or []
            shelf_conds = []
            if shelf_cats:
                ph = ",".join(["?"] * len(shelf_cats))
                shelf_conds.append(f"category IN ({ph})")
                params.extend(shelf_cats)
            if shelf_kws:
                kw_conds = []
                for kw in shelf_kws:
                    kw_conds.append("lower_ru(name) LIKE ?")
                    params.append(f"%{kw.lower()}%")
                shelf_conds.append("(" + " OR ".join(kw_conds) + ")")
            if shelf_conds:
                where.append("(" + " OR ".join(shelf_conds) + ")")

        if brand:
            where.append("lower_ru(name) LIKE ?")
            params.append(f"{brand.lower()}%")
        search_query = (search or "").strip()
        # Search is ranked in Python below; keeping the SQL search in this
        # branch would make a single missing word exclude every result.
        if not search_query:
            if letter:
                where.append(f"lower_ru(SUBSTR({TITLE_SQL}, 1, 1)) = ?")
                params.append(letter.lower())
        elif letter:
            where.append(f"lower_ru(SUBSTR({TITLE_SQL}, 1, 1)) = ?")
            params.append(letter.lower())

        where_sql = " AND ".join(where)
        order_sql = f"{TITLE_SQL} COLLATE NOCASE_RU ASC" if sort == "alpha" else "name ASC"

        query_limit = 5000 if search_query else limit
        query_offset = 0 if search_query else offset
        cursor.execute(
            f"SELECT id, name, slug, image_url, ingredients, category, subcategory, taxonomy_category, brand, barcode, variant "
            f"FROM products WHERE {where_sql} ORDER BY {order_sql} LIMIT ? OFFSET ?",
            params + [query_limit, query_offset],
        )
        rows = [dict(row) for row in cursor.fetchall()]
        if search_query:
            from .catalog_search import rank_products

            products, total = rank_products(rows, search_query, limit=limit, offset=offset)
        else:
            products = rows
            cursor.execute(f"SELECT COUNT(*) FROM products WHERE {where_sql}", params)
            total = cursor.fetchone()[0]
        conn.close()

    try:
        from .community_service import CommunityIntelligenceService
        ratings = CommunityIntelligenceService().get_products_community_rating(
            [p["id"] for p in products]
        )
    except Exception:
        ratings = {}

    for p in products:
        rating = ratings.get(p.get("id")) or {}
        p["rating"] = rating.get("average")
        p["rating_count"] = rating.get("count", 0)

    verified = _verified_product_ids(
        [int(p["id"]) for p in products if p.get("id") is not None]
    )
    for p in products:
        p["composition_verified"] = p.get("id") in verified

    # Отсутствие User Analysis не скрывает продукт из каталога.
    if current_user:
        try:
            from .database import get_current_analyses_map
            analyses = get_current_analyses_map(
                current_user["id"], [p["id"] for p in products]
            )
            for p in products:
                analysis = analyses.get(p.get("id"))
                p["score"] = analysis.get("score") if analysis else None
                p["analysis"] = analysis
        except Exception:
            for p in products:
                p["score"] = None
                p["analysis"] = None

    return {
        "products": products,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/catalog/letters")
async def get_catalog_letters():
    """Первые буквы названий продуктов для алфавитной навигации."""
    use_postgres = os.getenv("CATALOG_READ_FROM_POSTGRES", "").strip().lower() == "true"

    if use_postgres:
        from .postgres_catalog import TITLE_SQL as POSTGRES_TITLE_SQL
        from .postgres_connection import get_postgres_connection

        with get_postgres_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute(f"""
                    SELECT letter
                    FROM (
                        SELECT DISTINCT
                            lower(substring(({POSTGRES_TITLE_SQL}) from 1 for 1)) AS letter
                        FROM public.products
                        WHERE is_canonical = 1 AND name IS NOT NULL AND name <> ''
                    ) AS distinct_letters
                    ORDER BY letter COLLATE "C"
                """)
                letters = [
                    row["letter"] for row in cursor.fetchall()
                    if row["letter"] and row["letter"].isalnum()
                ]
            conn.rollback()
        return {"letters": letters}

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
    """Каноническая таксономия ухода за лицом (10 категорий) + бренды."""
    from .face_taxonomy import MAIN_FACE_TAXONOMY
    from .postgres_connection import get_postgres_connection

    with get_postgres_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(
                "SELECT catalog_category, COUNT(*) AS c FROM products "
                "WHERE is_canonical = 1 AND catalog_category IS NOT NULL AND btrim(catalog_category) <> '' "
                "GROUP BY catalog_category"
            )
            counts = {row["catalog_category"]: row["c"] for row in cursor.fetchall()}
            cursor.execute(
                "SELECT DISTINCT brand FROM products "
                "WHERE is_canonical = 1 AND catalog_category IS NOT NULL "
                "AND brand IS NOT NULL AND btrim(brand) <> '' ORDER BY brand"
            )
            brands = [row["brand"] for row in cursor.fetchall()]
        conn.rollback()

    taxonomy = [
        {
            "key": c["key"],
            "title": c["title"],
            "subcategories": list(c["subcategories"]),
            "count": counts.get(c["title"], 0),
        }
        for c in MAIN_FACE_TAXONOMY
    ]
    return {"taxonomy": taxonomy, "categories": [], "brands": brands}
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
    """Секции каталога из Supabase/PostgreSQL."""
    from .postgres_connection import get_postgres_connection

    def fetch(conn, section):
        base = """
            SELECT name, slug, image_url, category, brand, ingredients
            FROM public.products
            WHERE is_canonical = 1 AND catalog_category IS NOT NULL AND btrim(catalog_category) <> '' AND catalog_category <> 'Уход за губами'
              AND image_url IS NOT NULL
              AND image_url <> ''
        """
        params = []

        if section["type"] == "categories":
            cats = section["categories"]
            placeholders = ", ".join(["%s"] * len(cats))
            sql = base + f" AND category IN ({placeholders}) ORDER BY id DESC LIMIT 10"
            params.extend(cats)
        elif section["type"] == "keywords":
            conditions = []
            for keyword in section["keywords"]:
                conditions.append(
                    "(LOWER(COALESCE(name, '')) LIKE %s "
                    "OR LOWER(COALESCE(ingredients, '')) LIKE %s)"
                )
                params.extend([f"%{keyword.lower()}%", f"%{keyword.lower()}%"])
            sql = base + " AND (" + " OR ".join(conditions) + ") ORDER BY id DESC LIMIT 10"
        else:
            sql = base + " ORDER BY id DESC LIMIT 10"

        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    sections = []
    with get_postgres_connection() as conn:
        for section in CATALOG_SECTIONS:
            products = fetch(conn, section)
            cleaned = []

            for product in products:
                name = product.get("name") or ""
                parts = [part.strip() for part in name.split("\n") if part.strip()]
                brand = parts[0] if len(parts) >= 2 else (product.get("brand") or "")
                title = " ".join(parts[1:]) if len(parts) >= 2 else (
                    parts[0] if parts else name
                )
                cleaned.append({
                    "name": title,
                    "brand": brand,
                    "slug": product.get("slug") or "",
                    "image_url": product.get("image_url") or "",
                    "category": product.get("category") or "",
                })

            sections.append({
                "key": section["key"],
                "title": section["title"],
                "products": cleaned,
            })

    return {"sections": sections}

# ============================================================
# МОЯ ПОЛКА (SHELF)
# ============================================================

class ShelfAddRequest(BaseModel):
    slug: str
    category: str = ""
    cabinet: str = "face"
    state: str = "using"


class ShelfUpdateRequest(BaseModel):
    category: str = ""


class ShelfStateRequest(BaseModel):
    state: str = "using"


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
    analysis_id: Optional[int] = None


class ShelfRefreshRequest(BaseModel):
    product_ids: List[int] = []
    idempotency_key: str = ""
    quoted_cost: Optional[int] = None


# Unified Aidermy categories (same taxonomy as catalogue and recommendations).
SHELF_CATEGORIES = [
    "Очищение",
    "Тонизация",
    "Сыворотки и концентраты",
    "Увлажнение",
    "Восстановление кожного барьера",
    "Маски",
    "Эксфолиация",
    "Защита от солнца",
    "Уход за глазами",
    "Уход за губами",
]


def _profile_from_user(user: dict) -> dict:
    """Skin Profile из канонического источника (user_profiles, затем users)."""
    from .database import get_structured_profile, get_user_profile

    profile = get_user_profile(user["id"])
    result = {
        "skin_type": profile.get("skin_type") or "",
        "age": profile.get("age") or "",
        "concerns": [c.strip() for c in (profile.get("concerns") or "").split(",") if c.strip()],
        "allergies": [a.strip() for a in (profile.get("allergies") or "").split(",") if a.strip()],
        "custom_text": profile.get("custom_text") or "",
    }
    # Structured profile (therapy/procedures) — чтобы Score Engine реально их использовал.
    try:
        structured = get_structured_profile(user["id"])
    except Exception:
        structured = None
    if structured:
        result["structured"] = structured
        result["age"] = result.get("age") or structured.get("age") or ""
    return result


def _charge_check(user_id, product_name: str) -> None:
    """Списывает один балл за системную проверку (Слой 1).

    Списание атомарное: две параллельные проверки не могут израсходовать один
    и тот же балл, баланс не уходит в минус. Если баллов нет, проверка не
    блокируется — бесплатный доступ сохраняется как прежде.
    """
    if not user_id:
        return
    try:
        from .database import change_balance
        change_balance(user_id, -1, "spend", f"Проверка: {(product_name or '')[:60]}")
    except Exception as exc:
        print(f"[BILLING] spend failed: {exc!r}")


def _guest_gate(guest_token: str) -> dict:
    """Расходует единственную гостевую проверку (запрос без авторизации).

    Ограничение проверяется на сервере: гостевой токен обязателен, живёт
    ограниченное время и допускает ровно одну проверку.
    """
    from .guest_service import GuestSessionError, consume_guest_check

    try:
        return consume_guest_check(guest_token or "")
    except GuestSessionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


def _refund_guest_check(session: dict | None) -> None:
    if not session:
        return
    try:
        from .guest_service import refund_guest_check

        refund_guest_check(session["id"])
    except Exception:
        pass


def _store_guest_check_result(
    session: dict,
    *,
    result: dict,
    product_name: str,
    profile: dict,
    slug: str,
    product_id: int | None,
    ingredients_raw: str = "",
) -> None:
    """Сохраняет настоящий результат проверки в гостевой сеанс (отчёт и перенос)."""
    from .guest_service import store_guest_result

    deterministic = result.get("deterministic") or {}
    normalized = deterministic.get("normalized_ingredients") or []
    ingredients = (ingredients_raw or "").strip() or ", ".join(normalized)
    store_guest_result(
        session["id"],
        {
            "score": result.get("score"),
            "verdict": result.get("verdict") or "",
            "summary": result.get("summary") or "",
            "safe_ingredients": result.get("safe_ingredients") or [],
            "caution_ingredients": result.get("caution_ingredients") or [],
            "active_ingredients": result.get("active_ingredients"),
            "how_to_use": result.get("how_to_use"),
            "expectations": result.get("expectations"),
            "deterministic": deterministic,
            "phase1_status": result.get("phase1_status"),
            "recommendation_status": result.get("recommendation_status"),
            "product_name": product_name or "",
            "ingredients": ingredients,
            "profile": profile or {},
            "slug": slug or "",
            "product_id": product_id,
        },
    )


def _save_system_analysis(user: dict, product_id: int | None, slug: str, result: dict, profile_snapshot: dict | None = None) -> dict | None:
    """Сохраняет СИСТЕМНУЮ проверку (Слой 1) в актуальный User Analysis.

    Score/verdict приходят из scoring engine; описание (report) НЕ сохраняется
    здесь — оно запрашивается отдельно («Получить описание»). Возвращает
    сохранённый analysis или None (если score не валиден / сохранение не удалось).
    """
    import json as _json
    from .database import upsert_analysis

    deterministic = result.get("deterministic")
    if not isinstance(deterministic, dict) or not deterministic.get("normalized_ingredients"):
        return None
    raw_score = result.get("score")
    phase1_status = (
        result.get("phase1_status")
        or deterministic.get("phase1_status")
        or (deterministic.get("phase1") or {}).get("status")
    )
    if raw_score is None:
        if phase1_status not in {"blocked", "insufficient_data"}:
            return None
        score = None
    else:
        score = int(raw_score)
        if not 0 <= score <= 100:
            return None

    try:
        return upsert_analysis(
            user_id=user["id"],
            product_id=product_id,
            slug=slug or "",
            score=score,
            verdict=result.get("verdict") or "",
            summary=result.get("summary") or "",
            safe_ingredients=result.get("safe_ingredients") or [],
            caution_ingredients=result.get("caution_ingredients") or [],
            active_ingredients=result.get("active_ingredients"),
            how_to_use=result.get("how_to_use"),
            expectations=result.get("expectations"),
            profile_snapshot=_json.dumps(profile_snapshot or {}, ensure_ascii=False),
            deterministic_json=_json.dumps(result.get("deterministic") or {}, ensure_ascii=False),
        )
    except Exception as exc:
        print(f"[ANALYSIS] save failed: {exc!r}")
        return None


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
    from .score_version import SCORE_ENGINE_VERSION

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

    if not result or result.get("score") is None:
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
                "safe_ingredients, caution_ingredients, goal_evidence, profile_snapshot, score_engine_version, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
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
                    json.dumps(result.get("goal_evidence") or [], ensure_ascii=False),
                    json.dumps(profile, ensure_ascii=False),
                    SCORE_ENGINE_VERSION,
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
        "goal_evidence": result.get("goal_evidence") or [],
    }
    return int(result.get("score") or 0), analysis


def _compute_compatibility(products: list) -> dict:
    """Комплексная оценка набора продуктов по движку (без ИИ)."""
    from .ingredient_normalizer import canonicalize_ingredient_name

    def parse_ingredients(raw: str) -> set:
        out = set()
        for part in split_inci_tokens(raw or ''):
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

    from .plans import normalize_plan, shelf_limit, compatibility_set_limit

    plan = normalize_plan(current_user.get("plan"))
    return {
        "cabinets": cabinets,
        "plan": plan,
        "limit": shelf_limit(plan),
        "set_limit": compatibility_set_limit(plan),
        "count": len(shelf),
    }


def _shelf_refresh_candidates(current_user: dict) -> list[dict]:
    """Only products whose current saved Match is invalid need a refresh."""
    from .database import get_user_shelf
    from .shelf_service import build_cabinet_payload

    shelf = get_user_shelf(current_user["id"])
    cabinets = build_cabinet_payload(current_user, shelf)
    out: list[dict] = []
    seen: set[int] = set()
    for cabinet in cabinets:
        for category in cabinet.get("categories") or []:
            for item in category.get("items") or []:
                pid = item.get("product_id")
                if item.get("needs_recheck") and pid is not None and pid not in seen:
                    seen.add(pid)
                    out.append({
                        "product_id": pid,
                        "name": item.get("name") or "",
                        "slug": item.get("slug") or "",
                    })
    return out


@app.get("/api/shelf/refresh/preview")
async def preview_shelf_refresh(current_user: dict = Depends(get_current_user)):
    """Show the exact products and package price before any paid operation."""
    from .database import get_balance
    from .shelf_refresh import refresh_quote

    candidates = _shelf_refresh_candidates(current_user)
    cost = refresh_quote(len(candidates))
    balance = get_balance(current_user["id"])
    return {
        "needs_refresh": candidates,
        "count": len(candidates),
        "cost": cost,
        "currency": "points",
        "individual_cost": len(candidates),
        "discount_applied": bool(candidates) and cost < len(candidates),
        "balance": balance.get("balance", 0),
        "remaining": max(0, int(balance.get("balance", 0)) - cost),
    }


@app.post("/api/shelf/refresh")
async def refresh_shelf(request: ShelfRefreshRequest, current_user: dict = Depends(get_current_user)):
    """Recalculate only stale products, after a fixed-price user approval."""
    from .database import (
        AIDERMY_DB,
        change_balance,
        get_balance,
        get_connection,
        get_product_by_id,
    )
    from .shelf_refresh import refresh_quote
    from .shelf_service import recheck_product

    candidates = _shelf_refresh_candidates(current_user)
    requested = {int(pid) for pid in (request.product_ids or [])}
    if requested:
        candidates = [item for item in candidates if int(item["product_id"]) in requested]
    cost = refresh_quote(len(candidates))
    if request.quoted_cost is not None and int(request.quoted_cost) != cost:
        raise HTTPException(
            status_code=409,
            detail=(
                "Стоимость обновления изменилась после расчёта. "
                "Проверьте новый расчёт перед подтверждением."
            ),
        )
    if not candidates:
        return {
            "status": "ok",
            "updated": 0,
            "failed": 0,
            "cost": 0,
            "charged": 0,
            "needs_refresh": [],
        }

    balance = get_balance(current_user["id"])
    if int(balance.get("balance", 0)) < cost:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Для обновления нужно {cost} баллов, сейчас доступно "
                f"{balance.get('balance', 0)}. Обновление не запущено."
            ),
        )

    import hashlib
    import json

    key = (request.idempotency_key or "").strip()
    if not key:
        key = "shelf-refresh:" + hashlib.sha256(
            json.dumps(
                {
                    "user": current_user["id"],
                    "ids": sorted(int(item["product_id"]) for item in candidates),
                    "profile": current_user.get("profile_updated_at") or "",
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
    else:
        key = f"shelf-refresh:{current_user['id']}:{key}"

    conn = get_connection(AIDERMY_DB)
    try:
        cursor = conn.cursor()
        prior = cursor.execute(
            "SELECT 1 FROM balance_transactions WHERE idempotency_key = ? LIMIT 1",
            (f"{current_user['id']}:{key}",),
        ).fetchone()
    finally:
        conn.close()
    if prior:
        return {
            "status": "ok",
            "already_processed": True,
            "updated": 0,
            "failed": 0,
            "cost": cost,
            "charged": 0,
            "needs_refresh": candidates,
        }

    updated = 0
    failed: list[int] = []
    for item in candidates:
        product = get_product_by_id(int(item["product_id"]))
        if not product:
            failed.append(int(item["product_id"]))
            continue
        score, _analysis = recheck_product(current_user, product)
        if score is None:
            failed.append(int(item["product_id"]))
        else:
            updated += 1

    charged = refresh_quote(updated)
    if charged:
        new_balance = change_balance(
            current_user["id"], -charged, "shelf_refresh", "Обновление полки", idempotency_key=key
        )
    else:
        new_balance = get_balance(current_user["id"]).get("balance", 0)
    return {
        "status": "ok",
        "updated": updated,
        "failed": failed,
        "cost": charged,
        "quoted_cost": cost,
        "charged": charged,
        "balance": new_balance,
        "needs_refresh": [],
    }


@app.post("/api/shelf")
async def add_to_shelf(request: ShelfAddRequest, current_user: dict = Depends(get_current_user)):
    from .database import (
        get_product_by_slug,
        get_user_shelf,
        add_product_to_shelf,
        ShelfLimitError,
    )
    from .plans import normalize_plan, shelf_limit
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
        legacy_cat = (product.get("category") or "").strip()
        if legacy_cat.lower() in {"другое", "other", ""}:
            legacy_cat = (product.get("subcategory") or product.get("taxonomy_category") or "").strip()
        cabinet, category = infer_cabinet_category(legacy_cat, product.get("name"))
    else:
        cabinet = (request.cabinet or "face").strip().lower()
        if cabinet not in CABINET_BY_KEY:
            cabinet = "face"
        category = canonical_category(cabinet, request.category)

    ok, reason = is_product_compatible(product, cabinet, category)
    if not ok:
        raise HTTPException(status_code=422, detail=reason)

    shelf = get_user_shelf(current_user["id"])
    for s in shelf:
        if s["product_id"] == product["id"]:
            return {"status": "ok", "duplicate": True, "item": {"id": s["id"], "product_id": product["id"]}}

    # Cheap pre-check keeps the normal path from doing score work when the shelf
    # is already full. The database insert repeats this check under a write lock.
    plan = normalize_plan(current_user.get("plan"))
    limit = shelf_limit(plan)
    if len(shelf) >= limit:
        raise HTTPException(
            status_code=409,
            detail=(
                f"На тарифе {plan.capitalize()} можно хранить до {limit} продуктов. "
                "Освободите место или перейдите на подходящий тариф."
            ),
        )

    # При добавлении на полку score = история (snapshot) → пересчёт из Static Product Model.
    score = None
    if cabinet_applies_scoring(cabinet):
        score = get_personalized_score(current_user, product)

    try:
        item = add_product_to_shelf(current_user["id"], product["id"], category, cabinet=cabinet, score=score, shelf_status=request.state)
    except ShelfLimitError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=500, detail="Не удалось сохранить продукт на полке")
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

    recommendations = await recommend_products(
        current_user, cabinet, category, exclude_slugs,
        catalog_category=(request.category or "").strip() or None,
    )
    return {"cabinet": cabinet, "category": category, "recommendations": recommendations}


@app.post("/api/shelf/recheck/{product_id}")
async def recheck_shelf_product(product_id: int, current_user: dict = Depends(get_current_user)):
    """Перепроверка одного продукта полки (детерминированный scoring, БЕЗ LLM).

    Используется фронтендом для поэлементной перепроверки неактуальных Analysis.
    Score/verdict пересчитываются движком, report сбрасывается в NULL — карточка
    после перепроверки показывает «Получить описание», а не старый report.
    """
    from .database import get_product_by_id, get_user_shelf
    from .shelf_service import recheck_product

    product = get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Продукт не найден")

    # Перепроверяем только товары, которые реально лежат на полке пользователя.
    on_shelf = any(s["product_id"] == product_id for s in get_user_shelf(current_user["id"]))
    if not on_shelf:
        raise HTTPException(status_code=404, detail="Продукт не найден на полке")

    score, analysis = recheck_product(current_user, product)
    if score is None:
        raise HTTPException(status_code=422, detail="Не удалось перепроверить продукт")

    return {"score": score, "analysis": analysis}


@app.post("/api/shelf/analyze")
async def analyze_shelf_product(request: ShelfAnalyzeRequest, current_user: dict = Depends(get_current_user)):
    """Запускает анализ продукта (существующий pipeline) и сохраняет результат в историю.
    Если анализ уже есть — возвращает готовый результат без повторного запуска."""
    import json
    from .database import get_product_by_slug, get_connection, AIDERMY_DB
    from .shelf_service import score_product
    from .services import check_product_with_ai
    from .score_version import SCORE_ENGINE_VERSION

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

    if result and result.get("pending"):
        return {"status": "pending", "cached": False, "score": None, "analysis": None, "detail": "Исследование ингредиентов ещё не завершено — это займёт больше времени, возвращайтесь позже."}

    if not result or result.get("score") is None:
        phase1_status = (result or {}).get("phase1_status")
        recommendation_status = (result or {}).get("recommendation_status")

        if phase1_status == "blocked":
            status = "blocked"
            detail = (
                (result or {}).get("summary")
                or "Обычная оценка совместимости не рассчитана: первая фаза проверки не пройдена."
            )
        elif phase1_status == "insufficient_data":
            status = "insufficient_data"
            detail = (
                (result or {}).get("summary")
                or "Для расчёта совместимости недостаточно подтверждённых данных."
            )
        else:
            status = "error"
            detail = "Состав продукта неизвестен"

        saved = None
        if phase1_status in {"blocked", "insufficient_data"}:
            saved = _save_system_analysis(
                current_user,
                product_id=product.get("id"),
                slug=product.get("slug") or request.slug,
                result=result,
                profile_snapshot=profile,
            )
        analysis = None
        if saved:
            analysis = {
                "id": saved.get("id"),
                "score": None,
                "verdict": (result or {}).get("verdict") or "",
                "summary": (result or {}).get("summary") or detail,
                "phase1_status": phase1_status,
                "recommendation_status": recommendation_status,
            }
        return {
            "status": status,
            "cached": False,
            "score": None,
            "analysis": analysis,
            "analysis_id": (saved or {}).get("id"),
            "detail": detail,
            "phase1_status": phase1_status,
            "recommendation_status": recommendation_status,
        }

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
                    safe_ingredients, caution_ingredients, goal_evidence, profile_snapshot, score_engine_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
                json.dumps(result.get("goal_evidence") or [], ensure_ascii=False),
                json.dumps(profile, ensure_ascii=False),
                SCORE_ENGINE_VERSION,
            ))
            conn.commit()
    finally:
        conn.close()

    # Обогащение базы знаний ингредиентов уже выполнено внутри
    # check_product_with_ai -> check_product_with_ingredients (не дублируем).

    # Сохраняем СИСТЕМНУЮ проверку (Слой 1) в актуальный User Analysis.
    saved = _save_system_analysis(
        current_user,
        product_id=product.get("id"),
        slug=product.get("slug") or request.slug,
        result=result,
        profile_snapshot=profile,
    )

    analysis = {
        "id": (saved or {}).get("id"),
        "verdict": result.get("verdict") or "",
        "summary": result.get("summary") or "",
        "score": int(result.get("score") or 0),
        "safe_ingredients": result.get("safe_ingredients") or [],
        "caution_ingredients": result.get("caution_ingredients") or [],
        "active_ingredients": result.get("active_ingredients"),
        "how_to_use": result.get("how_to_use"),
        "expectations": result.get("expectations"),
        "goal_evidence": result.get("goal_evidence") or [],
        "report": (saved or {}).get("report"),
    }
    return {"status": "ok", "cached": False, "score": int(result.get("score") or 0), "analysis": analysis}


def _fragments_to_text(fragments) -> str:
    """Склеивает fragments [{text, sentiment}] в plain text (для кэша check_history)."""
    if not fragments:
        return ""
    if isinstance(fragments, str):
        return fragments
    return " ".join(str(f.get("text") or "") for f in fragments if isinstance(f, dict)).strip()


def _fragments_from_value(value) -> list:
    """Десериализует сохранённые fragments [{text, sentiment}] (JSON или legacy string)."""
    if not value:
        return []
    if isinstance(value, list):
        return [f for f in value if isinstance(f, dict)]
    if isinstance(value, str):
        import json as _json
        try:
            parsed = _json.loads(value)
            if isinstance(parsed, list):
                return [f for f in parsed if isinstance(f, dict)]
        except Exception:
            pass
        return [{"text": value, "sentiment": "positive"}]
    return []


@app.post("/api/shelf/review")
async def review_shelf_product(request: ShelfAnalyzeRequest, current_user: dict = Depends(get_current_user)):
    """AI-отчёт («Показать отчёт») ПО ЯВНОМУ ЗАПРОСУ.

    Требует существующий актуальный User Analysis (история проверок).
    Score НЕ пересчитывается — AI только пишет человеческое объяснение
    уже рассчитанного результата.
    """
    import json as _json
    from .database import get_product_by_slug, save_ai_report, save_analysis_details
    from .shelf_service import recalculate_stale_analysis, score_product
    from .score_version import SCORE_ENGINE_VERSION
    from .report_version import REPORT_GENERATOR_VERSION
    from .services import generate_full_report
    from .catalog_taxonomy import classify_product

    from .database import get_analysis_by_id
    if request.analysis_id:
        analysis = get_analysis_by_id(current_user["id"], request.analysis_id)
        if not analysis:
            raise HTTPException(status_code=404, detail="Анализ не найден")
        score = analysis.get("score")
        slug = analysis.get("slug") or request.slug
        product = get_product_by_slug(slug) if slug else None
        if analysis.get("score_engine_version") != SCORE_ENGINE_VERSION:
            analysis = recalculate_stale_analysis(current_user, analysis, product)
            if not analysis:
                raise HTTPException(status_code=409, detail="Не удалось обновить устаревший анализ")
            score = analysis.get("score")
    else:
        product = get_product_by_slug(request.slug)
        if not product:
            raise HTTPException(status_code=404, detail="Продукт не найден")
        score, analysis = score_product(current_user, product)
        slug = product.get("slug") or request.slug
    deterministic = (analysis or {}).get("deterministic") or {}
    phase1_status = (
        (analysis or {}).get("phase1_status")
        or deterministic.get("phase1_status")
        or ((analysis or {}).get("phase1") or {}).get("status")
    )

    # Phase 1 is a hard gate: saved legacy scores must never leak into
    # reports when the current analysis is blocked or lacks sufficient data.
    if phase1_status == "insufficient_data":
        score = None
        deterministic = dict(deterministic) if isinstance(deterministic, dict) else {}
        deterministic["score"] = None
        analysis = analysis or {}
        analysis["score"] = None
        analysis["deterministic"] = deterministic
        analysis["verdict"] = (
            analysis.get("recommendation_status") or "Недостаточно данных"
        )

    if score is None:
        raise HTTPException(status_code=409, detail="Анализ ещё не выполнен — сначала проверьте совместимость.")
    name = (
        (product.get("name") or "").replace("\n", " ").strip()
        if product
        else str(deterministic.get("product_name") or slug or "").strip()
    )
    product_type = classify_product(product).get("canonical_category") or "" if product else ""
    ingredients = (
        product.get("ingredients") or ", ".join(deterministic.get("normalized_ingredients") or [])
        if product
        else ", ".join(deterministic.get("normalized_ingredients") or [])
    )

    # Наличие report означает, что отдельный объект отчёта уже был сохранён.
    # Остальные блоки опциональны и не должны провоцировать повторную генерацию.
    if (
        analysis
        and analysis.get("report")
        and analysis.get("report_score_engine_version") == analysis.get("score_engine_version")
        and analysis.get("score_engine_version") == SCORE_ENGINE_VERSION
        and analysis.get("report_generator_version") == REPORT_GENERATOR_VERSION
    ):
        from .report_details import build_report_details
        review = _fragments_from_value(analysis.get("report"))
        profile = _profile_from_user(current_user)
        details = build_report_details(
            name,
            product_type,
            (analysis.get("deterministic") or deterministic or {}),
            profile,
        )
        return {
            "score": score,
            "verdict": analysis.get("verdict") or "",
            "explanation": _fragments_to_text(review),
            "review": review,
            "expectations": analysis.get("expectations"),
            "phase1_status": phase1_status,
            "recommendation_status": (analysis or {}).get("recommendation_status"),
            "report_ready": True,
            "details": details,
        }

    profile = _profile_from_user(current_user)
    skin_type = profile.get("skin_type") or "Нормальная"
    try:
        full = await generate_full_report(
            name,
            ingredients,
            profile,
            skin_type,
            product_type,
            saved_analysis=analysis,
        )
    except Exception as exc:
        print(f"[REVIEW] failed: {exc!r}")
        raise HTTPException(status_code=502, detail="Не удалось сформировать отчёт") from exc

    review_fragments = full.get("review") or []
    review_text = _fragments_to_text(review_fragments) or analysis.get("summary") or ""

    save_analysis_details(
        current_user["id"],
        product.get("id") if product else (analysis or {}).get("product_id"),
        slug,
        report=_json.dumps(review_fragments, ensure_ascii=False),
        active_ingredients=None,
        expectations=full.get("expectations"),
        what_good="",
        what_caution="",
        report_score_engine_version=analysis.get("score_engine_version"),
        report_prompt_version=full.get("report_prompt_version"),
        report_generator_version=REPORT_GENERATOR_VERSION,
    )
    save_ai_report(current_user["id"], slug, review_text)

    return {
        "score": analysis.get("score"),
        "verdict": analysis.get("verdict") or "",
        "explanation": _fragments_to_text(review_fragments),
        "review": review_fragments,
        "expectations": full.get("expectations"),
        "phase1_status": phase1_status,
        "recommendation_status": (analysis or {}).get("recommendation_status"),
        "report_ready": True,
        "details": full.get("details"),
    }


@app.post("/api/analysis/report")
async def generate_analysis_report(request: ShelfAnalyzeRequest, current_user: dict = Depends(get_current_user)):
    """Слой 2 — «Получить описание»: генерирует и сохраняет подробное описание
    к актуальному User Analysis. Score/verdict не пересчитываются."""
    return await review_shelf_product(request, current_user)


class GuestSessionRequest(BaseModel):
    profile: dict = {}


class GuestTokenRequest(BaseModel):
    guest_token: str = ""


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.post("/api/guest/session")
async def create_guest_session_endpoint(payload: GuestSessionRequest, request: Request):
    """Создаёт гостевой сеанс после заполнения анкеты (одна проверка на сеанс)."""
    from .guest_service import GuestSessionError, create_guest_session, rate_limit_sessions

    if not rate_limit_sessions(_client_ip(request)):
        raise HTTPException(
            status_code=429,
            detail="Слишком много гостевых сеансов. Попробуйте позже или войдите в аккаунт.",
        )
    try:
        return create_guest_session(payload.profile or {})
    except GuestSessionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.post("/api/guest/report")
async def guest_report_endpoint(payload: GuestTokenRequest):
    """Полный отчёт по единственной гостевой проверке.

    Используется тот же генератор, что и у авторизованного пользователя;
    score/verdict берутся из уже посчитанного результата и не пересчитываются.
    """
    from .database import get_product_by_slug
    from .guest_service import (
        GuestSessionError,
        get_cached_guest_report,
        get_guest_result,
        save_guest_report,
    )
    from .services import generate_full_report

    try:
        cached = get_cached_guest_report(payload.guest_token)
        if cached:
            return cached
        result = get_guest_result(payload.guest_token)
    except GuestSessionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    score = result.get("score")
    if score is None:
        raise HTTPException(status_code=409, detail="Недостаточно данных для отчёта")

    deterministic = result.get("deterministic") or {}
    profile = result.get("profile") or {}
    skin_type = profile.get("skin_type") or "Нормальная"
    product_type = ""
    try:
        from .catalog_taxonomy import classify_product

        product = get_product_by_slug(result.get("slug") or "")
        if product:
            product_type = classify_product(product).get("canonical_category") or ""
    except Exception:
        product_type = ""

    try:
        full = await generate_full_report(
            result.get("product_name") or "",
            result.get("ingredients") or "",
            profile,
            skin_type,
            product_type,
            saved_analysis={
                "deterministic": deterministic,
                "score": score,
                "verdict": result.get("verdict") or "",
            },
        )
    except Exception as exc:
        print(f"[GUEST REPORT] failed: {exc!r}")
        raise HTTPException(status_code=502, detail="Не удалось сформировать отчёт") from exc

    review_fragments = full.get("review") or []
    response = {
        "score": score,
        "verdict": result.get("verdict") or "",
        "explanation": _fragments_to_text(review_fragments) or result.get("summary") or "",
        "review": review_fragments,
        "expectations": full.get("expectations"),
        "phase1_status": result.get("phase1_status"),
        "recommendation_status": result.get("recommendation_status"),
        "report_ready": True,
        "details": full.get("details"),
    }
    try:
        save_guest_report(payload.guest_token, response)
    except Exception as exc:
        print(f"[GUEST REPORT] cache failed: {exc!r}")
    return response


@app.post("/api/guest/claim")
async def guest_claim_endpoint(
    payload: GuestTokenRequest,
    current_user: dict = Depends(get_current_user),
):
    """Сохраняет единственный гостевой результат в аккаунт пользователя.

    Идемпотентно: повторный вызов не создаёт второй анализ. Привязать результат
    к другому аккаунту нельзя — захват атомарный.
    """
    import json as _json

    from .database import save_analysis_details, upsert_analysis
    from .guest_service import (
        GuestSessionError,
        claim_guest_result,
        finalize_guest_claim,
        get_cached_guest_report,
        release_guest_claim,
    )
    from .report_version import REPORT_GENERATOR_VERSION

    try:
        claim = claim_guest_result(payload.guest_token, current_user["id"])
    except GuestSessionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    if claim.get("already_claimed"):
        return {
            "status": "ok",
            "analysis_id": claim.get("analysis_id"),
            "already_claimed": True,
        }

    data = claim.get("payload") or {}
    try:
        saved = upsert_analysis(
            user_id=current_user["id"],
            product_id=data.get("product_id"),
            slug=data.get("slug") or "",
            score=data.get("score"),
            verdict=data.get("verdict") or "",
            summary=data.get("summary") or "",
            safe_ingredients=data.get("safe_ingredients") or [],
            caution_ingredients=data.get("caution_ingredients") or [],
            active_ingredients=data.get("active_ingredients"),
            how_to_use=data.get("how_to_use"),
            expectations=data.get("expectations"),
            profile_snapshot=_json.dumps(data.get("profile") or {}, ensure_ascii=False),
            deterministic_json=_json.dumps(data.get("deterministic") or {}, ensure_ascii=False),
        )
    except Exception as exc:
        release_guest_claim(claim["session_id"])
        print(f"[GUEST CLAIM] save failed: {exc!r}")
        raise HTTPException(status_code=500, detail="Не удалось сохранить результат") from exc

    analysis_id = saved.get("id") if isinstance(saved, dict) else None

    # Сохранённый результат должен быть виден в кабинете: добавляем товар на полку
    # (идемпотентно), чтобы оценка отображалась в разделе «Моя полка».
    if data.get("product_id"):
        try:
            from .database import add_product_to_shelf

            add_product_to_shelf(current_user["id"], int(data["product_id"]))
        except Exception as exc:
            print(f"[GUEST CLAIM] shelf add failed: {exc!r}")

    # Если гость успел открыть отчет — переносим и его, без повторной генерации.
    try:
        report = get_cached_guest_report(payload.guest_token)
        if report and analysis_id:
            save_analysis_details(
                current_user["id"],
                data.get("product_id"),
                data.get("slug") or "",
                report=_json.dumps(report.get("review") or [], ensure_ascii=False),
                expectations=report.get("expectations"),
                report_generator_version=REPORT_GENERATOR_VERSION,
            )
    except Exception as exc:
        print(f"[GUEST CLAIM] report transfer failed: {exc!r}")

    finalize_guest_claim(claim["session_id"], analysis_id)
    return {"status": "ok", "analysis_id": analysis_id, "already_claimed": False}


@app.patch("/api/shelf/{shelf_id}/state")
async def update_shelf_state(shelf_id: int, request: ShelfStateRequest, current_user: dict = Depends(get_current_user)):
    from .database import update_shelf_product_status
    updated = update_shelf_product_status(current_user["id"], shelf_id, request.state)
    if not updated:
        raise HTTPException(status_code=404, detail="Не найдено")
    return {"status": "ok", "state": updated.get("shelf_status") or "using"}


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
        replacement = await recommend_products(
            current_user, cabinet, category, {request.slug},
            catalog_category=(request.category or "").strip() or None,
        )

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
        c_cabinet, c_category = resolve_shelf_cabinet(s.get("category"), s.get("cabinet"), p.get("name") or "", p.get("subcategory") or "")
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
    from .database import (
        get_product_by_slug,
        get_user_shelf,
        add_product_to_shelf,
        create_routine,
        ShelfLimitError,
    )

    existing = {s["product_id"] for s in get_user_shelf(current_user["id"])}
    routine_id = create_routine(current_user["id"], request.name)
    added = 0
    skipped = 0
    limit_reached = False
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
        try:
            add_product_to_shelf(current_user["id"], product["id"], category, request.name, routine_id)
        except ShelfLimitError:
            limit_reached = True
            break
        existing.add(product["id"])
        added += 1
    return {
        "status": "ok",
        "added": added,
        "skipped": skipped,
        "routine_id": routine_id,
        "limit_reached": limit_reached,
    }