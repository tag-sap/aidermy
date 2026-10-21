"""Тесты единого сценария «Скан по фото» (лицевая + задняя стороны)."""

import asyncio
import base64
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.product_scan import ProductScanError, scan_product_package

def _import_main():
    # Production main registers admin/report routes at import time. Those routes
    # require a live Supabase table, so unit tests stub only the setup hook.
    import app.report_prompt_routes as report_routes
    report_routes.setup_report_prompt_routes = lambda _app: None
    import app.main as main_module
    return main_module



IDENTIFIED = {
    "brand": "COSRX",
    "product_name": "Ac Collection Calming Foam Cleanser",
    "name": "Ac Collection Calming Foam Cleanser",
    "manufacturer": "COSRX",
    "category": "Очищение",
    "variant": None,
    "type": "cleanser",
    "volume": "150 ml",
    "barcode": "8809598450135",
    "confidence": 0.92,
}

RECOGNITION = {
    "is_inci": True,
    "raw_text": "Water, Glycerin, Salicylic Acid",
    "ingredients": [
        {"raw": "Water", "normalized": "Water", "confidence": 0.99},
        {"raw": "Glycerin", "normalized": "Glycerin", "confidence": 0.99},
        {"raw": "Salicylic Acid", "normalized": "Salicylic Acid", "confidence": 0.9},
    ],
    "uncertain_items": [],
    "overall_confidence": 0.9,
}

LOCAL_PRODUCT = {
    "id": 974,
    "slug": "cosrx-ac-collection-calming-foam-cleanser",
    "name": "Ac Collection Calming Foam Cleanser",
    "brand": "COSRX",
    "image_url": "https://example.invalid/974.png",
    "category": "Очищение",
    "ingredients": "Water, Glycerin, Salicylic Acid, Centella Asiatica Extract",
    "source_url": "",
    "match_score": 0.95,
    "has_inci": True,
}


def _run(identified=None, recognition=None, candidates=None, web=None):
    ident = identified if identified is not None else IDENTIFIED
    rec = recognition if recognition is not None else RECOGNITION
    cands = candidates if candidates is not None else []
    with patch("app.product_scan.identify_product", new=AsyncMock(return_value=ident)), \
         patch("app.product_scan.recognize_composition", new=AsyncMock(return_value=rec)), \
         patch("app.product_scan.find_product_candidates", return_value=cands), \
         patch("app.product_scan.web_search_product", new=AsyncMock(return_value=web)) as web_mock:
        result = asyncio.run(scan_product_package("data:image/jpeg;base64,front", "data:image/jpeg;base64,back"))
    return result, web_mock


def test_both_photos_are_required():
    with pytest.raises(ProductScanError):
        asyncio.run(scan_product_package("", "data:image/jpeg;base64,back"))
    with pytest.raises(ProductScanError):
        asyncio.run(scan_product_package("data:image/jpeg;base64,front", ""))


def test_existing_product_with_reliable_inci_is_reused_without_web_search():
    result, web_mock = _run(candidates=[LOCAL_PRODUCT])
    assert result["status"] == "ready"
    assert result["product"]["id"] == 974
    assert result["product"]["ingredients_source"] == "local"
    assert "Salicylic Acid" in result["product"]["ingredients"]
    web_mock.assert_not_awaited()


def test_vision_runtime_error_is_not_reported_as_bad_photo():
    with patch("app.product_scan.identify_product", new=AsyncMock(side_effect=RuntimeError("DEEPSEEK_API_KEY не настроен"))), \
         patch("app.product_scan.recognize_composition", new=AsyncMock(return_value=RECOGNITION)):
        with pytest.raises(RuntimeError):
            asyncio.run(scan_product_package("front", "back"))


def test_multiple_matches_are_not_chosen_randomly():
    second = {**LOCAL_PRODUCT, "id": 956, "slug": "cosrx-calming-foam-cleanser", "name": "Calming Foam Cleanser"}
    result, web_mock = _run(candidates=[LOCAL_PRODUCT, second])
    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) == 2
    assert result["draft"]["ingredients_source"] == "back_photo"
    web_mock.assert_not_awaited()


def test_web_product_with_reliable_inci_returns_draft_for_confirmation():
    web_product = {
        "name": "Ac Collection Calming Foam Cleanser",
        "brand": "COSRX",
        "ingredients": "Water, Glycerin, Salicylic Acid, Centella Asiatica Extract",
        "inci_reliable": True,
        "source_url": "https://www.cosrx.com/products/ac-collection-calming-foam-cleanser",
        "image_url": "https://example.invalid/cosrx.png",
        "category": "Очищение",
        "volume": "150 ml",
    }
    result, web_mock = _run(candidates=[], web=web_product)
    assert result["status"] == "needs_confirmation"
    assert result["draft"]["ingredients_source"] == "scraped"
    assert result["draft"]["source_url"].startswith("https://www.cosrx.com/")
    assert result["can_analyze"] is True
    web_mock.assert_awaited_once()
    assert web_mock.await_args.kwargs["allow_unreliable_inci"] is True


def test_scraper_without_inci_falls_back_to_back_photo():
    web_product = {
        "name": "Ac Collection Calming Foam Cleanser",
        "brand": "COSRX",
        "ingredients": "Water",
        "inci_reliable": False,
        "source_url": "https://www.cosrx.com/products/ac-collection-calming-foam-cleanser",
        "image_url": "",
        "category": "Очищение",
        "volume": "150 ml",
    }
    result, _ = _run(candidates=[], web=web_product)
    assert result["status"] == "needs_confirmation"
    assert result["draft"]["ingredients_source"] == "back_photo"
    assert "salicylic acid" in result["draft"]["ingredients"].lower()
    assert any("неполный" in warning for warning in result["warnings"])


def test_external_search_miss_uses_back_photo_without_inventing_url():
    result, _ = _run(candidates=[], web=None)
    assert result["status"] == "needs_confirmation"
    assert result["draft"]["ingredients_source"] == "back_photo"
    assert result["draft"]["source_url"] == ""
    assert result["can_analyze"] is True


def test_unreadable_inci_is_not_presented_as_ready():
    recognition = {"is_inci": False, "ingredients": [], "raw_text": "", "uncertain_items": [], "overall_confidence": None}
    result, _ = _run(candidates=[], recognition=recognition, web=None)
    assert result["status"] == "needs_confirmation"
    assert result["can_analyze"] is False
    assert result["draft"]["ingredients"] == ""
    assert any("не распознан" in warning for warning in result["warnings"])


def test_unreadable_name_returns_not_found():
    result, _ = _run(identified={**IDENTIFIED, "brand": "", "product_name": "", "name": ""}, candidates=[])
    assert result["status"] == "not_found"
    assert result["draft"] is None


def test_local_card_without_inci_needs_confirmation_but_keeps_slug():
    local = {**LOCAL_PRODUCT, "ingredients": "", "has_inci": False}
    result, _ = _run(candidates=[local])
    assert result["status"] == "needs_confirmation"
    assert result["draft"]["slug"] == local["slug"]
    assert result["draft"]["ingredients_source"] == "back_photo"
    assert result["can_analyze"] is True


def test_front_photo_is_uploaded_to_permanent_storage():
    from app.image_storage import upload_product_source_image

    data = base64.b64encode(b"front-image-bytes").decode()
    with patch("app.image_storage.upload_image", return_value="https://storage.example/front.jpg") as upload:
        url = upload_product_source_image(f"data:image/jpeg;base64,{data}", "COSRX-Ac Collection")
    assert url == "https://storage.example/front.jpg"
    args, kwargs = upload.call_args
    assert args[0].startswith("product_source/")
    assert kwargs["content_type"] == "image/jpeg"


def test_scraped_inci_metadata_is_removed():
    from app.product_scan import _clean_scraped_inci

    raw = "Water, Glycerin, [more] Salicylic Acid [less] DETAILS HOW TO USE BENEFITS • Remove impurities"
    assert _clean_scraped_inci(raw) == ["Water", "Glycerin", "Salicylic Acid"]


def test_real_local_db_match_reuses_existing_product(tmp_path):
    import sqlite3
    import app.database as database

    db_path = tmp_path / "products.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, slug TEXT, brand TEXT, "
        "image_url TEXT, category TEXT, ingredients TEXT, barcode TEXT, variant TEXT, is_canonical INTEGER DEFAULT 1)"
    )
    conn.execute(
        "INSERT INTO products (id, name, slug, brand, ingredients, is_canonical) "
        "VALUES (974, 'COSRX\\nAc Collection Calming Foam Cleanser', 'cosrx-ac-collection-calming-foam-cleanser', '', "
        "'Water, Glycerin, Salicylic Acid, Centella Asiatica Extract', 1)"
    )
    conn.commit()
    conn.close()

    old_path = database.PRODUCTS_DB
    database.PRODUCTS_DB = str(db_path)
    try:
        with patch("app.product_scan.identify_product", new=AsyncMock(return_value=IDENTIFIED)), \
             patch("app.product_scan.recognize_composition", new=AsyncMock(return_value=RECOGNITION)), \
             patch("app.product_scan.web_search_product", new=AsyncMock()) as web_mock:
            result = asyncio.run(scan_product_package("front", "back"))
        assert result["status"] == "ready"
        assert result["product"]["id"] == 974
        assert result["product"]["brand"] == "COSRX"
        assert "Salicylic Acid" in result["product"]["ingredients"]
        web_mock.assert_not_awaited()
    finally:
        database.PRODUCTS_DB = old_path


def test_barcode_has_priority_over_name_candidates(tmp_path):
    import sqlite3
    import app.database as database

    db_path = tmp_path / "products.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, slug TEXT, brand TEXT, "
        "image_url TEXT, category TEXT, ingredients TEXT, barcode TEXT, variant TEXT, is_canonical INTEGER DEFAULT 1)"
    )
    conn.execute(
        "INSERT INTO products (id, name, slug, brand, ingredients, barcode, is_canonical) VALUES "
        "(974, 'COSRX\\nAc Collection Calming Foam Cleanser', 'name-match', '', 'Water, Glycerin', NULL, 1), "
        "(975, 'COSRX\\nCompletely Different Product', 'barcode-match', 'COSRX', 'Water, Glycerin, Betaine', '8809598450135', 1)"
    )
    conn.commit()
    conn.close()

    old_path = database.PRODUCTS_DB
    database.PRODUCTS_DB = str(db_path)
    try:
        with patch("app.product_scan.identify_product", new=AsyncMock(return_value=IDENTIFIED)), \
             patch("app.product_scan.recognize_composition", new=AsyncMock(return_value=RECOGNITION)), \
             patch("app.product_scan.web_search_product", new=AsyncMock()) as web_mock:
            result = asyncio.run(scan_product_package("front", "back"))
        assert result["status"] == "ready"
        assert result["product"]["id"] == 975
        assert result["product"]["barcode"] == "8809598450135"
        web_mock.assert_not_awaited()
    finally:
        database.PRODUCTS_DB = old_path



def test_scan_endpoint_rejects_missing_photo_and_returns_service_result():
    from types import SimpleNamespace
    from fastapi import HTTPException
    main = _import_main()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.product_scan_endpoint(SimpleNamespace(front_image="", back_image="data:image/jpeg;base64,back")))
    assert exc.value.status_code == 422

    expected = {"status": "ready", "product": {"id": 974, "slug": "cosrx"}}
    with patch("app.product_scan.scan_product_package", new=AsyncMock(return_value=expected)):
        result = asyncio.run(main.product_scan_endpoint(SimpleNamespace(
            front_image="data:image/jpeg;base64,front",
            back_image="data:image/jpeg;base64,back",
        )))
    assert result == expected


def test_invalid_image_data_is_rejected():
    from app.image_storage import upload_product_source_image

    with pytest.raises(ValueError):
        upload_product_source_image("not-a-data-url")



def test_create_product_saves_front_photo_in_permanent_storage():
    from app.models import CreateProductRequest
    main = _import_main()

    request = CreateProductRequest(
        brand="COSRX",
        name="Ac Collection Calming Foam Cleanser",
        ingredients=["Water", "Glycerin", "Salicylic Acid"],
        image_data_url="data:image/jpeg;base64,ZnJvbnQ=",
        source_url="https://www.cosrx.com/products/ac-collection-calming-foam-cleanser",
        volume="150 ml",
        barcode="8809598450135",
        variant="Calming",
        category="Очищение",
        source_type="retailer",
    )
    saved = {
        "id": 501,
        "slug": "cosrx-ac-collection-calming-foam-cleanser",
        "name": "COSRX\nAc Collection Calming Foam Cleanser",
        "brand": "COSRX",
        "ingredients": "water, glycerin, salicylic acid",
        "category": "Очищение",
        "image_url": "https://storage.example/front.jpg",
        "url": request.source_url,
        "volume": "150 ml",
        "is_new": True,
    }
    with patch("app.product_dedup.find_or_create_canonical_product", return_value=saved) as save_mock, \
         patch("app.main.register_ingredients"), \
         patch("app.shelf_service.normalize_imported_category", return_value="Очищение"), \
         patch("app.image_storage.upload_product_source_image", return_value="https://storage.example/front.jpg") as upload_mock:
        response = asyncio.run(main.create_product_endpoint(request, None))

    upload_mock.assert_called_once()
    assert upload_mock.call_args.args[0] == request.image_data_url
    payload = save_mock.call_args.args[0]
    assert payload["image_url"] == "https://storage.example/front.jpg"
    assert payload["url"] == request.source_url
    assert payload["volume"] == "150 ml"
    assert payload["barcode"] == "8809598450135"
    assert payload["variant"] == "Calming"
    assert response["product"]["image_url"] == "https://storage.example/front.jpg"
    assert response["product"]["barcode"] == "8809598450135"
    assert response["product"]["variant"] == "Calming"


def test_create_product_fails_if_front_photo_cannot_be_saved():
    from fastapi import HTTPException
    from app.models import CreateProductRequest
    main = _import_main()

    request = CreateProductRequest(
        brand="COSRX",
        name="Ac Collection Calming Foam Cleanser",
        ingredients=["Water", "Glycerin"],
        image_data_url="data:image/jpeg;base64,ZnJvbnQ=",
    )
    with patch("app.main.register_ingredients"), \
         patch("app.shelf_service.normalize_imported_category", return_value="Очищение"), \
         patch("app.image_storage.upload_product_source_image", side_effect=RuntimeError("S3 down")):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(main.create_product_endpoint(request, None))
    assert exc.value.status_code == 502




def test_repeated_scan_save_does_not_create_duplicate(tmp_path):
    import sqlite3
    from app.models import CreateProductRequest
    import app.database as database
    main = _import_main()

    db_path = tmp_path / "products.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, slug TEXT UNIQUE, brand TEXT, manufacturer TEXT, "
        "ingredients TEXT, url TEXT, incidecoder_url TEXT, image_url TEXT, category TEXT, volume TEXT, "
        "description TEXT, sku TEXT, price REAL, currency TEXT, source_type TEXT, contributed_by INTEGER, "
        "normalized_name TEXT, is_canonical INTEGER DEFAULT 1, canonical_id INTEGER, barcode TEXT, variant TEXT, saved_at TEXT)"
    )
    conn.commit()
    conn.close()

    old_path = database.PRODUCTS_DB
    database.PRODUCTS_DB = str(db_path)
    request = CreateProductRequest(
        brand="COSRX",
        name="Ac Collection Calming Foam Cleanser",
        ingredients=["Water", "Glycerin", "Salicylic Acid"],
        source_url="https://www.cosrx.com/products/ac-collection-calming-foam-cleanser",
        source_type="retailer",
    )
    try:
        with patch("app.main.register_ingredients"), \
             patch("app.shelf_service.normalize_imported_category", return_value="Очищение"):
            first = asyncio.run(main.create_product_endpoint(request, None))
            second = asyncio.run(main.create_product_endpoint(request, None))
        assert first["duplicate"] is False
        assert second["duplicate"] is True
        assert first["product"]["id"] == second["product"]["id"]
        check = sqlite3.connect(db_path)
        count = check.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        check.close()
        assert count == 1
    finally:
        database.PRODUCTS_DB = old_path
