import pytest

from app.postgres_catalog import _build_catalog_query, get_catalog_page


@pytest.mark.parametrize(
    ("limit", "offset"),
    [
        (0, 0),
        (-1, 0),
        (20, -1),
    ],
)
def test_catalog_rejects_invalid_pagination(limit, offset):
    with pytest.raises(ValueError):
        get_catalog_page(limit=limit, offset=offset)


def test_catalog_query_uses_parameterized_filters():
    sql, params, count_sql, count_params = _build_catalog_query(
        category="Уход для лица",
        subcategory="Кремы",
        brand="ARAVIA",
        search="hydra therapy",
        letter="А",
        limit=10,
        offset=20,
    )

    assert "taxonomy_category = %s" in sql
    assert "subcategory = %s" in sql
    assert "lower(name) LIKE %s" in sql
    assert "LIMIT %s OFFSET %s" in sql
    assert "COUNT(*) AS total" in count_sql

    assert params == [
        "Уход для лица",
        "Кремы",
        "aravia%",
        "%hydra%",
        "%therapy%",
        "а",
        10,
        20,
    ]
    assert count_params == params[:-2]


def test_catalog_query_does_not_interpolate_search_input():
    hostile_input = "'; DROP TABLE products; --"

    sql, params, _, _ = _build_catalog_query(search=hostile_input)

    assert hostile_input not in sql
    assert params[:5] == ["%';%", "%drop%", "%table%", "%products;%", "%--%"]
    assert all(isinstance(value, (str, int)) for value in params)


def test_catalog_query_preserves_default_sort_behavior():
    sql, _, _, _ = _build_catalog_query(sort="popular")

    # В текущем каталоге popular сохраняет сортировку по name.
    assert 'ORDER BY name COLLATE "C" ASC, id ASC' in sql


def test_catalog_alpha_sort_uses_title_and_stable_id():
    sql, _, _, _ = _build_catalog_query(sort="alpha")

    assert 'ORDER BY lower((' in sql
    assert 'COLLATE "C" ASC, id ASC' in sql


def test_catalog_shelf_filter_uses_parameterized_conditions(monkeypatch):
    import sys
    from types import SimpleNamespace

    fake_rules = {
        "morning": {
            "face": {
                "categories": ["Крем"],
                "keywords": ["увлажнение"],
            }
        }
    }
    monkeypatch.setitem(
        sys.modules,
        "app.shelf_service",
        SimpleNamespace(RECOMMEND_RULES=fake_rules),
    )

    sql, params, count_sql, count_params = _build_catalog_query(
        shelf_category="face",
        cabinet="morning",
    )

    assert "category IN (%s)" in sql
    assert "lower(name) LIKE %s" in sql
    assert params == ["Крем", "%увлажнение%", 20, 0]
    assert count_params == ["Крем", "%увлажнение%"]
    assert "DROP TABLE" not in sql


def test_catalog_query_requires_canonical_categories_and_filters_by_them():
    sql, params, count_sql, count_params = _build_catalog_query(
        catalog_category="Уход для лица",
        catalog_subcategory="Сыворотки",
        limit=20,
        offset=0,
    )

    for condition in (
        "catalog_category IS NOT NULL",
        "btrim(catalog_category) <> ''",
        "catalog_subcategory IS NOT NULL",
        "btrim(catalog_subcategory) <> ''",
        "catalog_category = %s",
        "catalog_subcategory = %s",
    ):
        assert condition in sql
        assert condition in count_sql

    assert params == ["Уход для лица", "Сыворотки", 20, 0]
    assert count_params == ["Уход для лица", "Сыворотки"]
