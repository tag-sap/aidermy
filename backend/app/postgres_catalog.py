"""Изолированное чтение каталога из PostgreSQL/Supabase."""

from typing import Any, Optional

from .postgres_connection import get_postgres_connection


# Аналог TITLE_SQL из SQLite:
# убрать первую строку (бренд), очистить переносы строк в названии.
TITLE_SQL = """
regexp_replace(
    name,
    '^([^' || chr(10) || ']*' || chr(10) || ')+',
    ''
)
"""


def _build_catalog_query(
    *,
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
) -> tuple[str, list[Any], str, list[Any]]:
    """Строит параметризованные запросы каталога и общего количества."""

    from .face_taxonomy import main_face_category_titles

    _face_titles = main_face_category_titles()
    _face_ph = ", ".join(["%s"] * len(_face_titles))
    where = [
        "is_canonical = 1",
        f"catalog_category IN ({_face_ph})",
        "btrim(catalog_category) <> ''",
        "catalog_subcategory IS NOT NULL",
        "btrim(catalog_subcategory) <> ''",
    ]
    params: list[Any] = list(_face_titles)

    if category:
        where.append("taxonomy_category = %s")
        params.append(category)

    if subcategory:
        where.append("subcategory = %s")
        params.append(subcategory)

    if catalog_category:
        where.append("catalog_category = %s")
        params.append(catalog_category)

    if catalog_subcategory:
        where.append("catalog_subcategory = %s")
        params.append(catalog_subcategory)

    if cat:
        where.append("category = %s")
        params.append(cat)

    if shelf_category and cabinet:
        from .shelf_service import RECOMMEND_RULES

        rule = (RECOMMEND_RULES.get(cabinet) or {}).get(shelf_category) or {}
        shelf_cats = rule.get("categories") or []
        shelf_kws = rule.get("keywords") or []
        shelf_conds = []

        if shelf_cats:
            placeholders = ", ".join(["%s"] * len(shelf_cats))
            shelf_conds.append(f"category IN ({placeholders})")
            params.extend(shelf_cats)

        if shelf_kws:
            keyword_conds = []
            for keyword in shelf_kws:
                keyword_conds.append("lower(name) LIKE %s")
                params.append(f"%{keyword.lower()}%")
            shelf_conds.append("(" + " OR ".join(keyword_conds) + ")")

        if shelf_conds:
            where.append("(" + " OR ".join(shelf_conds) + ")")

    if brand:
        where.append("lower(name) LIKE %s")
        params.append(f"{brand.lower()}%")

    if search:
        for word in search.strip().lower().split():
            where.append("lower(name) LIKE %s")
            params.append(f"%{word}%")

    if letter:
        where.append(f"lower(substring(({TITLE_SQL}) from 1 for 1)) = %s")
        params.append(letter.lower())

    where_sql = " AND ".join(where)

    if sort == "alpha":
        order_sql = f"lower(({TITLE_SQL})) COLLATE \"C\" ASC, id ASC"
    else:
        order_sql = 'name COLLATE "C" ASC, id ASC'

    select_sql = f"""
        SELECT
            id, name, slug, image_url, ingredients,
            category, subcategory, taxonomy_category, brand,
            catalog_category, catalog_subcategory, barcode, variant
        FROM public.products
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT %s OFFSET %s
    """

    count_sql = f"""
        SELECT COUNT(*) AS total
        FROM public.products
        WHERE {where_sql}
    """

    return select_sql, params + [limit, offset], count_sql, params


def get_catalog_page(
    *,
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
) -> dict[str, Any]:
    """Читает одну страницу каталога из PostgreSQL без побочных эффектов."""

    if limit < 1 or offset < 0:
        raise ValueError("limit должен быть больше 0, offset не может быть отрицательным")

    select_sql, select_params, count_sql, count_params = _build_catalog_query(
        category=category,
        subcategory=subcategory,
        catalog_category=catalog_category,
        catalog_subcategory=catalog_subcategory,
        brand=brand,
        cat=cat,
        search=search,
        letter=letter,
        shelf_category=shelf_category,
        cabinet=cabinet,
        limit=limit,
        offset=offset,
        sort=sort,
    )

    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(select_sql, select_params)
            products = cur.fetchall()

            cur.execute(count_sql, count_params)
            total = cur.fetchone()["total"]

        conn.rollback()

    return {
        "products": products,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
