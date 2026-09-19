import sqlite3
import os
import json
from datetime import datetime

# === ДВЕ БАЗЫ ===
AIDERMY_DB = os.path.join(os.path.dirname(__file__), '..', 'aidermy.db')
PRODUCTS_DB = os.path.join(os.path.dirname(__file__), '..', 'products.db')

def get_connection(db_path=None):
    if db_path is None:
        db_path = AIDERMY_DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.create_function("lower_ru", 1, lambda s: (s or "").lower())
    return conn

def init_db():
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            ingredients TEXT NOT NULL,
            slug TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS check_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            skin_type TEXT NOT NULL,
            score INTEGER NOT NULL,
            verdict TEXT NOT NULL,
            summary TEXT NOT NULL,
            ingredients TEXT DEFAULT '',
            slug TEXT,
            user_id INTEGER,
            profile_snapshot TEXT DEFAULT '{}',
            deleted_at TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        DELETE FROM check_history
        WHERE id IN (
            SELECT id
            FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY user_id, product_name, score, verdict, summary
                           ORDER BY created_at DESC
                       ) AS rn
                FROM check_history
            )
            WHERE rn > 1
        )
    ''')

    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_check_history_unique_user_product
        ON check_history (user_id, product_name, score, verdict, summary)
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            ingredients TEXT NOT NULL,
            slug TEXT,
            user_id INTEGER REFERENCES users(id),
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP,
            review_notes TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shelf_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            product_id INTEGER NOT NULL,
            category TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, product_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS routines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute("PRAGMA table_info(shelf_products)")
    shelf_columns = [col[1] for col in cursor.fetchall()]
    if 'routine_id' not in shelf_columns:
        cursor.execute('ALTER TABLE shelf_products ADD COLUMN routine_id INTEGER')
    
    # Миграция: сгруппировать ранее добавленные продукты (с notes) в подборы
    cursor.execute("SELECT DISTINCT user_id, notes FROM shelf_products WHERE notes IS NOT NULL AND notes != '' AND routine_id IS NULL")
    for row in cursor.fetchall():
        cursor.execute("SELECT id FROM routines WHERE user_id = ? AND name = ?", (row['user_id'], row['notes']))
        existing = cursor.fetchone()
        if existing:
            routine_id = existing['id']
        else:
            cursor.execute("INSERT INTO routines (user_id, name) VALUES (?, ?)", (row['user_id'], row['notes']))
            routine_id = cursor.lastrowid
        cursor.execute("UPDATE shelf_products SET routine_id = ? WHERE user_id = ? AND notes = ? AND routine_id IS NULL", (routine_id, row['user_id'], row['notes']))
    
    cursor.execute("PRAGMA table_info(check_history)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'ingredients' not in columns:
        cursor.execute('ALTER TABLE check_history ADD COLUMN ingredients TEXT DEFAULT ""')
    if 'slug' not in columns:
        cursor.execute('ALTER TABLE check_history ADD COLUMN slug TEXT')
    if 'user_id' not in columns:
        cursor.execute('ALTER TABLE check_history ADD COLUMN user_id INTEGER')
    if 'profile_snapshot' not in columns:
        cursor.execute('ALTER TABLE check_history ADD COLUMN profile_snapshot TEXT DEFAULT "{}"')
    if 'deleted_at' not in columns:
        cursor.execute('ALTER TABLE check_history ADD COLUMN deleted_at TIMESTAMP NULL')
    if 'image_url' not in columns:
        cursor.execute('ALTER TABLE check_history ADD COLUMN image_url TEXT')
    if 'active_ingredients' not in columns:
        cursor.execute('ALTER TABLE check_history ADD COLUMN active_ingredients TEXT')
    if 'how_to_use' not in columns:
        cursor.execute('ALTER TABLE check_history ADD COLUMN how_to_use TEXT')
    if 'expectations' not in columns:
        cursor.execute('ALTER TABLE check_history ADD COLUMN expectations TEXT')
    if 'safe_ingredients' not in columns:
        cursor.execute('ALTER TABLE check_history ADD COLUMN safe_ingredients TEXT')
    if 'caution_ingredients' not in columns:
        cursor.execute('ALTER TABLE check_history ADD COLUMN caution_ingredients TEXT')
    
    conn.commit()
    conn.close()
    
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            slug TEXT UNIQUE,
            brand TEXT,
            ingredients TEXT,
            url TEXT,
            incidecoder_url TEXT,
            saved_at TEXT
        )
    ''')
    product_columns = [col[1] for col in cursor.execute("PRAGMA table_info(products)").fetchall()]
    for column in ("image_url", "category", "brand"):
        if column not in product_columns:
            cursor.execute(f"ALTER TABLE products ADD COLUMN {column} TEXT")
    conn.commit()
    conn.close()
    
    print("✅ Базы данных инициализированы")


def upsert_imported_product(product: dict) -> dict:
    """Save an imported product while preserving existing non-empty fields."""
    name = (product.get("name") or "").strip()
    if not name:
        raise ValueError("Imported product has no name")

    source_url = product.get("source_url")
    brand = (product.get("brand") or "").strip() or None
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    existing = cursor.execute(
        "SELECT * FROM products WHERE (? IS NOT NULL AND url = ?) OR (LOWER(name) = LOWER(?) AND COALESCE(LOWER(brand), '') = COALESCE(LOWER(?), '')) LIMIT 1",
        (source_url, source_url, name, brand),
    ).fetchone()

    values = {
        "name": name,
        "brand": brand,
        "ingredients": product.get("ingredients_raw"),
        "url": source_url,
        "image_url": product.get("image_url"),
        "category": product.get("category"),
    }
    if existing:
        cursor.execute(
            """UPDATE products SET
                name = COALESCE(NULLIF(name, ''), ?),
                brand = COALESCE(NULLIF(brand, ''), ?),
                ingredients = COALESCE(NULLIF(ingredients, ''), ?),
                url = COALESCE(NULLIF(url, ''), ?),
                image_url = COALESCE(NULLIF(image_url, ''), ?),
                category = COALESCE(NULLIF(category, ''), ?)
            WHERE id = ?""",
            (*values.values(), existing["id"]),
        )
        product_id = existing["id"]
        logger_message = "Existing product found"
    else:
        import re
        slug = re.sub(r"[^a-zA-Z0-9\s-]", "", name)
        slug = re.sub(r"[-\s]+", "-", slug).lower().strip("-") or "product"
        cursor.execute("SELECT 1 FROM products WHERE slug = ?", (slug,))
        if cursor.fetchone():
            slug = f"{slug}-{abs(hash(source_url or name)) % 100000}"
        cursor.execute(
            """INSERT INTO products (name, slug, brand, ingredients, url, image_url, category, saved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (name, slug, values["brand"], values["ingredients"], values["url"], values["image_url"], values["category"]),
        )
        product_id = cursor.lastrowid
        logger_message = "Product normalized"

    conn.commit()
    row = cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    conn.close()
    print(f"[SCRAPER] {logger_message}: {name}")
    return dict(row)

# === РАБОТА С ИСТОРИЕЙ ===
# database.py

def save_check_result(
    product_name: str, 
    skin_type: str, 
    score: int, 
    verdict: str, 
    summary: str, 
    ingredients: str = "", 
    slug: str = None,
    user_id: int = None,
    profile_snapshot: str = "{}",
    image_url: str = None,
    active_ingredients: str = None,
    how_to_use: str = None,
    expectations: str = None,
):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO check_history (
            product_name, skin_type, score, verdict, summary,
            ingredients, slug, user_id, profile_snapshot,
            image_url, active_ingredients, how_to_use, expectations,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (
        product_name,
        skin_type,
        score,
        verdict,
        summary,
        ingredients,
        slug,
        user_id,
        profile_snapshot or "{}",
        image_url,
        json.dumps(active_ingredients) if active_ingredients is not None else None,
        json.dumps(how_to_use) if how_to_use is not None else None,
        json.dumps(expectations) if expectations is not None else None,
    ))
    conn.commit()
    conn.close()
    print(f"📊 Проверка сохранена: {product_name} — {score}% (user_id: {user_id})")

def get_user_check_history(user_id: int, limit: int = 100):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, user_id, product_name, skin_type, score, verdict, summary, 
               ingredients, slug, image_url, active_ingredients, how_to_use, 
               expectations, safe_ingredients, caution_ingredients, profile_snapshot, created_at
        FROM check_history 
        WHERE user_id = ? AND deleted_at IS NULL
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def clear_user_check_history(user_id: int):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE check_history SET deleted_at = CURRENT_TIMESTAMP WHERE user_id = ? AND deleted_at IS NULL',
        (user_id,)
    )
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    return deleted


def delete_user_history_items(user_id: int, item_ids: list[str | int]):
    if not item_ids:
        return 0

    cleaned = []
    for item_id in item_ids:
        try:
            cleaned.append(int(item_id))
        except (TypeError, ValueError):
            continue

    if not cleaned:
        return 0

    placeholders = ', '.join('?' for _ in cleaned)
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute(
        f'UPDATE check_history SET deleted_at = CURRENT_TIMESTAMP WHERE user_id = ? AND deleted_at IS NULL AND id IN ({placeholders})',
        (user_id, *cleaned),
    )
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    return deleted


def get_all_check_history(limit: int = 100):
    """Получить всю историю (для админа)"""
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ch.*, u.email as user_email
        FROM check_history ch
        LEFT JOIN users u ON ch.user_id = u.id
        ORDER BY ch.created_at DESC 
        LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_check_stats():
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as total FROM check_history')
    total = cursor.fetchone()['total']
    cursor.execute('SELECT COUNT(DISTINCT product_name) as unique_products FROM check_history')
    unique = cursor.fetchone()['unique_products']
    cursor.execute('SELECT AVG(score) as avg_score FROM check_history')
    avg = cursor.fetchone()['avg_score'] or 0
    conn.close()
    return {
        'total': total,
        'unique_products': unique,
        'avg_score': round(avg, 1)
    }

# === РАБОТА С ИНГРЕДИЕНТАМИ ===
def save_ingredients(product_name: str, ingredients: str, slug: str = None):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO ingredients (product_name, ingredients, slug)
        VALUES (?, ?, ?)
    ''', (product_name.lower().strip(), ingredients, slug))
    conn.commit()
    conn.close()
    print(f"💾 Состав сохранён в БД: {product_name}")

def get_ingredients(product_name: str) -> str | None:
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ingredients FROM ingredients
        WHERE product_name = ?
        ORDER BY created_at DESC
        LIMIT 1
    ''', (product_name.lower().strip(),))
    row = cursor.fetchone()
    conn.close()
    return row['ingredients'] if row else None

def get_all_ingredients():
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM ingredients ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# === ПОИСК ПРОДУКТОВ ===
def search_products(query: str, limit: int = 10):
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    
    # Очищаем запрос: убираем пробелы, переносы, лишние символы
    clean_query = ''.join(query.split()).lower()
    
    cursor.execute('''
        SELECT DISTINCT name, slug FROM products
        WHERE LOWER(REPLACE(REPLACE(REPLACE(name, '\n', ''), '\r', ''), ' ', '')) LIKE ?
        ORDER BY name
        LIMIT ?
    ''', (f'%{clean_query}%', limit))
    
    rows = cursor.fetchall()
    conn.close()
    return [{'name': row['name'], 'slug': row['slug']} for row in rows]

def get_all_products(limit: int = 100):
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM products 
        ORDER BY id DESC 
        LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_product_count():
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM products')
    row = cursor.fetchone()
    conn.close()
    return row['count'] if row else 0

def get_product_by_slug(slug: str):
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE slug = ?', (slug,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def product_exists_in_products_db(product_name: str) -> bool:
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM products WHERE name = ?", (product_name,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

# === ПОЛКА (SHELF) ===
def get_product_by_id(product_id: int):
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE id = ?', (product_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def add_product_to_shelf(user_id: int, product_id: int, category: str = "", notes: str = "", routine_id: int = None):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO shelf_products (user_id, product_id, category, notes, routine_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, product_id, category, notes, routine_id))
    conn.commit()
    cursor.execute("SELECT * FROM shelf_products WHERE user_id = ? AND product_id = ?", (user_id, product_id))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_routine(user_id: int, name: str = "") -> int:
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO routines (user_id, name) VALUES (?, ?)", (user_id, name))
    conn.commit()
    routine_id = cursor.lastrowid
    conn.close()
    return routine_id


def get_user_routines(user_id: int):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM routines WHERE user_id = ? ORDER BY created_at DESC, id DESC", (user_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_user_shelf(user_id: int):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM shelf_products WHERE user_id = ? ORDER BY added_at DESC, id DESC", (user_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def remove_product_from_shelf(user_id: int, shelf_id: int) -> int:
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM shelf_products WHERE id = ? AND user_id = ?", (shelf_id, user_id))
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    return deleted

def update_shelf_product_category(user_id: int, shelf_id: int, category: str):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute("UPDATE shelf_products SET category = ? WHERE id = ? AND user_id = ?", (category, shelf_id, user_id))
    conn.commit()
    cursor.execute("SELECT * FROM shelf_products WHERE id = ? AND user_id = ?", (shelf_id, user_id))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None