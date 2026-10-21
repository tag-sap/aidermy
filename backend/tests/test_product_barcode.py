"""Постоянное хранение barcode/variant и безопасные конфликты штрихкодов."""

import asyncio
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.database as database
from app.product_dedup import ProductConflictError, find_or_create_canonical_product


def _legacy_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, slug TEXT UNIQUE, brand TEXT, "
        "ingredients TEXT, url TEXT, incidecoder_url TEXT, saved_at TEXT)"
    )
    conn.execute(
        "INSERT INTO products (name, slug, brand, ingredients) VALUES (?, ?, ?, ?)",
        ("Legacy\nCream", "legacy-cream", "Legacy", "Aqua, Glycerin"),
    )
    conn.commit()
    conn.close()


def _schema_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, slug TEXT UNIQUE, brand TEXT, manufacturer TEXT, "
        "ingredients TEXT, url TEXT, incidecoder_url TEXT, image_url TEXT, category TEXT, volume TEXT, "
        "barcode TEXT, variant TEXT, description TEXT, sku TEXT, price REAL, currency TEXT, source_type TEXT, "
        "contributed_by INTEGER, normalized_name TEXT, is_canonical INTEGER DEFAULT 1, canonical_id INTEGER, saved_at TEXT)"
    )
    conn.commit()
    conn.close()


@pytest.fixture()
def products_db(tmp_path):
    path = tmp_path / "products.db"
    _schema_db(path)
    old = database.PRODUCTS_DB
    database.PRODUCTS_DB = str(path)
    try:
        yield path
    finally:
        database.PRODUCTS_DB = old


def test_init_db_adds_barcode_and_variant_to_legacy_products(tmp_path):
    old_products, old_aidermy = database.PRODUCTS_DB, database.AIDERMY_DB
    products = tmp_path / "products.db"
    _legacy_db(products)
    database.PRODUCTS_DB = str(products)
    database.AIDERMY_DB = str(tmp_path / "aidermy.db")
    try:
        database.init_db()
        conn = sqlite3.connect(products)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(products)").fetchall()}
        row = conn.execute(
            "SELECT barcode, variant, is_canonical FROM products WHERE slug = 'legacy-cream'"
        ).fetchone()
        conn.close()
    finally:
        database.PRODUCTS_DB, database.AIDERMY_DB = old_products, old_aidermy

    assert {"barcode", "variant"} <= columns
    assert row == (None, None, 1)


def test_barcode_with_leading_zero_is_stored_as_string(products_db):
    saved = find_or_create_canonical_product({
        "name": "COSRX\nLow pH Cleanser",
        "brand": "COSRX",
        "ingredients": "Water, Glycerin",
        "barcode": "0123456789012",
        "variant": "150 ml",
        "source_type": "scan",
    })
    conn = sqlite3.connect(products_db)
    row = conn.execute("SELECT barcode, variant FROM products WHERE id = ?", (saved["id"],)).fetchone()
    conn.close()
    assert row == ("0123456789012", "150 ml")


def test_repeated_scan_same_barcode_does_not_create_duplicate(products_db):
    payload = {
        "name": "COSRX\nAc Collection Cleanser",
        "brand": "COSRX",
        "ingredients": "Water, Glycerin",
        "barcode": "8809598450135",
        "variant": "150 ml",
        "source_type": "scan",
    }
    first = find_or_create_canonical_product(payload)
    second = find_or_create_canonical_product(payload)
    conn = sqlite3.connect(products_db)
    count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    barcode = conn.execute("SELECT barcode FROM products WHERE id = ?", (first["id"],)).fetchone()[0]
    conn.close()
    assert first["is_new"] is True
    assert second["is_new"] is False
    assert first["id"] == second["id"]
    assert count == 1
    assert barcode == "8809598450135"


def test_barcode_belonging_to_another_product_is_a_safe_conflict(products_db):
    find_or_create_canonical_product({
        "name": "Brand\nProduct A",
        "brand": "Brand",
        "ingredients": "Water, Glycerin",
        "barcode": "1111111111111",
        "source_type": "scan",
    })
    with pytest.raises(ProductConflictError) as exc:
        find_or_create_canonical_product({
            "name": "Completely Different Serum",
            "brand": "Other Brand",
            "ingredients": "Water, Niacinamide",
            "barcode": "1111111111111",
            "source_type": "scan",
        })
    assert exc.value.product.get("name") == "Brand\nProduct A"
    conn = sqlite3.connect(products_db)
    count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    names = [row[0] for row in conn.execute("SELECT name FROM products").fetchall()]
    conn.close()
    assert count == 1
    assert names == ["Brand\nProduct A"]


def test_product_detail_returns_barcode_and_variant(products_db):
    saved = find_or_create_canonical_product({
        "name": "Brand\nProduct A",
        "brand": "Brand",
        "ingredients": "Water, Glycerin",
        "barcode": "0000000000017",
        "variant": "Night",
        "source_type": "scan",
    })
    from app.database import get_product_by_slug

    product = get_product_by_slug(saved["slug"])
    assert product["barcode"] == "0000000000017"
    assert product["variant"] == "Night"


def test_create_endpoint_returns_409_on_barcode_conflict(products_db):
    import app.report_prompt_routes as report_routes

    report_routes.setup_report_prompt_routes = lambda _app: None
    import app.main as main
    from app.models import CreateProductRequest

    find_or_create_canonical_product({
        "name": "Brand\nProduct A",
        "brand": "Brand",
        "ingredients": "Water, Glycerin",
        "barcode": "2222222222222",
        "source_type": "scan",
    })
    request = CreateProductRequest(
        brand="Other",
        name="Completely Different Product",
        ingredients=["Water", "Niacinamide"],
        barcode="2222222222222",
    )
    with patch("app.main.register_ingredients"), \
         patch("app.shelf_service.normalize_imported_category", return_value="Очищение"):
        response = asyncio.run(main.create_product_endpoint(request, None))
    assert response.status_code == 409
    assert b"conflict" in response.body




def test_reliable_inci_is_not_overwritten_by_longer_scanner_inci(products_db):
    first = find_or_create_canonical_product({
        "name": "Brand\nBarrier Cream",
        "brand": "Brand",
        "ingredients": "Water, Glycerin",
        "source_type": "official",
    })
    merged = find_or_create_canonical_product({
        "name": "Brand\nBarrier Cream",
        "brand": "Brand",
        "ingredients": "Water, Glycerin, Alcohol, Parfum, Limonene, Linalool",
        "source_type": "scan",
    })
    assert merged["id"] == first["id"]
    assert merged["ingredients"] == "Water, Glycerin"
