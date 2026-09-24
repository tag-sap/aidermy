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
    conn.create_collation("NOCASE_RU", lambda a, b: (
        -1 if (a or "").lower() < (b or "").lower()
        else 1 if (a or "").lower() > (b or "").lower()
        else 0
    ))
    # Инструментация (Фаза 0): считаем реальное число SQL-запросов.
    # Не меняет поведение — только устанавливает trace-колбэк.
    try:
        from .instrumentation import METRICS
        conn.set_trace_callback(lambda _stmt: METRICS.increment("db_query_count"))
    except Exception:
        pass
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
    # Миграция: в старых БД таблица ingredients могла существовать без колонки slug.
    ingredients_cols = [r[1] for r in cursor.execute("PRAGMA table_info(ingredients)").fetchall()]
    if "slug" not in ingredients_cols:
        cursor.execute("ALTER TABLE ingredients ADD COLUMN slug TEXT")
    
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
    # Миграция: старые БД могли не иметь колонок, которые читает/пишет текущий код.
    _history_cols = {r[1] for r in cursor.execute("PRAGMA table_info(check_history)").fetchall()}
    for _col, _ddl in [
        ("profile_snapshot", "TEXT DEFAULT '{}'"),
        ("deleted_at", "TIMESTAMP NULL"),
        ("image_url", "TEXT"),
        ("active_ingredients", "TEXT"),
        ("how_to_use", "TEXT"),
        ("expectations", "TEXT"),
        ("safe_ingredients", "TEXT"),
        ("caution_ingredients", "TEXT"),
        ("ai_report", "TEXT"),
    ]:
        if _col not in _history_cols:
            cursor.execute(f"ALTER TABLE check_history ADD COLUMN {_col} {_ddl}")

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
    if 'cabinet' not in shelf_columns:
        cursor.execute("ALTER TABLE shelf_products ADD COLUMN cabinet TEXT DEFAULT 'face'")
    if 'score' not in shelf_columns:
        # Индивидуальный Product Compatibility % (deterministic Score Engine),
        # сохраняемый при добавлении на полку, чтобы не терять уже рассчитанный скор.
        cursor.execute('ALTER TABLE shelf_products ADD COLUMN score INTEGER')
    
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
    if 'ai_report' not in columns:
        cursor.execute('ALTER TABLE check_history ADD COLUMN ai_report TEXT')

    # Аватар и имя пользователя (личный кабинет)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if cursor.fetchone():
        user_columns = [col[1] for col in cursor.execute("PRAGMA table_info(users)").fetchall()]
        if 'avatar_url' not in user_columns:
            cursor.execute('ALTER TABLE users ADD COLUMN avatar_url TEXT')
    
    # === COMMUNITY INTELLIGENCE ===
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL,
            slug TEXT DEFAULT '',
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            text TEXT DEFAULT '',
            usage_duration TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            visibility TEXT DEFAULT 'ANONYMOUS',
            profile_snapshot TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, product_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_reviews_product ON reviews (product_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_reviews_user ON reviews (user_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS review_helpful_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id INTEGER NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(review_id, user_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_review_votes_review ON review_helpful_votes (review_id)')

    # === FEEDBACK ПЕРСОНАЛИЗАЦИИ ===
    # Дизлайк рекомендации (причина важна: категория / процент / состав / пробовал / другое).
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recommendation_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            product_id INTEGER,
            slug TEXT DEFAULT '',
            cabinet TEXT DEFAULT '',
            category TEXT DEFAULT '',
            reason TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rec_feedback_user ON recommendation_feedback (user_id)')

    # Причина удаления продукта с полки.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shelf_removal_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            product_id INTEGER,
            slug TEXT DEFAULT '',
            reason TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_removal_feedback_user ON shelf_removal_feedback (user_id)')

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
    if "contributed_by" not in product_columns:
        cursor.execute("ALTER TABLE products ADD COLUMN contributed_by INTEGER")
    # Поля для дедупликации товаров и canonical-merge.
    for column, ddl in [
        ("volume", "TEXT"),
        ("description", "TEXT"),
        ("sku", "TEXT"),
        ("price", "REAL"),
        ("currency", "TEXT"),
        ("source_type", "TEXT"),
        ("normalized_name", "TEXT"),
        ("is_canonical", "INTEGER DEFAULT 1"),
        ("canonical_id", "INTEGER"),
    ]:
        if column not in product_columns:
            cursor.execute(f"ALTER TABLE products ADD COLUMN {column} {ddl}")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_normalized ON products (normalized_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_canonical ON products (is_canonical, canonical_id)")
    conn.commit()
    conn.close()
    
    print("✅ Базы данных инициализированы")


def upsert_imported_product(product: dict) -> dict:
    """Save an imported product, deduplicating to a single canonical record.

    Делегирует в product_dedup.find_or_create_canonical_product:
    Normalization -> Similarity -> Matching -> Canonical Merge (без AI).
    Возвращает canonical-строку products.
    """
    name = (product.get("name") or "").strip()
    if not name:
        raise ValueError("Imported product has no name")

    from .product_dedup import find_or_create_canonical_product

    payload = {
        "name": name,
        "brand": (product.get("brand") or "").strip() or None,
        "ingredients": product.get("ingredients_raw") or product.get("ingredients"),
        "url": product.get("source_url") or product.get("url"),
        "image_url": product.get("image_url"),
        "category": product.get("category"),
        "volume": product.get("volume"),
        "description": product.get("description"),
        "sku": product.get("sku"),
        "price": product.get("price"),
        "currency": product.get("currency"),
        "incidecoder_url": product.get("incidecoder_url"),
        "contributed_by": product.get("contributed_by"),
        "source_type": product.get("source_type"),
        "slug": product.get("slug"),
    }

    result = find_or_create_canonical_product(payload)
    print(f"[PRODUCT] {'merged' if result.get('was_merged') else 'created'}: {name}")
    return result

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

def get_user_profile(user_id: int):
    """Возвращает актуальный Skin Profile пользователя.

    Канонический источник — таблица user_profiles (её заполняет фронтенд через
    /api/auth/profile). Если записи нет — фолбэк на колонки users (skin_type,
    age, concerns, allergies, custom_text). Возвращает dict с полями профиля.
    """
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='user_profiles'"
    )
    has_profiles = cursor.fetchone() is not None

    if has_profiles:
        profile_cols = {r[1] for r in cursor.execute("PRAGMA table_info(user_profiles)").fetchall()}
        select_cols = "name, skin_type, age, concerns, allergies, custom_text, quiz_answers, skin_type_determined"
        if "structured_profile" in profile_cols:
            select_cols += ", structured_profile"
        cursor.execute(
            f"""
            SELECT {select_cols}
            FROM user_profiles
            WHERE user_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        if row:
            conn.close()
            result = {
                "name": row["name"] or "",
                "skin_type": row["skin_type"] or "",
                "age": row["age"] or "",
                "concerns": row["concerns"] or "",
                "allergies": row["allergies"] or "",
                "custom_text": row["custom_text"] or "",
                "quiz_answers": row["quiz_answers"] or "",
                "skin_type_determined": row["skin_type_determined"] or "",
            }
            if "structured_profile" in profile_cols:
                result["structured_profile"] = row["structured_profile"] or ""
            return result

    cursor.execute(
        "SELECT name, skin_type, age, concerns, allergies, custom_text FROM users WHERE id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {
            "name": "",
            "skin_type": "",
            "age": "",
            "concerns": "",
            "allergies": "",
            "custom_text": "",
            "quiz_answers": "",
            "skin_type_determined": "",
        }
    return {
        "name": row["name"] or "",
        "skin_type": row["skin_type"] or "",
        "age": row["age"] or "",
        "concerns": row["concerns"] or "",
        "allergies": row["allergies"] or "",
        "custom_text": row["custom_text"] or "",
        "quiz_answers": "",
        "skin_type_determined": "",
    }


def get_structured_profile(user_id: int):
    """Возвращает структурированный профиль пользователя (JSON -> dict) или None."""
    from .profile_structuring import deserialize_structured

    profile = get_user_profile(user_id)
    return deserialize_structured(profile.get("structured_profile"))


def save_structured_profile(user_id: int, structured: dict) -> bool:
    """Сохраняет Structured User Profile в колонку user_profiles.structured_profile."""
    from .profile_structuring import serialize_structured

    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_profiles'")
    if not cursor.fetchone():
        conn.close()
        return False
    cols = {r[1] for r in cursor.execute("PRAGMA table_info(user_profiles)").fetchall()}
    if "structured_profile" not in cols:
        cursor.execute("ALTER TABLE user_profiles ADD COLUMN structured_profile TEXT")
    cursor.execute(
        "UPDATE user_profiles SET structured_profile = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
        (serialize_structured(structured), user_id),
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def get_user_check_history(user_id: int, limit: int = 100):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, user_id, product_name, skin_type, score, verdict, summary, 
               ingredients, slug, image_url, active_ingredients, how_to_use, 
               expectations, safe_ingredients, caution_ingredients, ai_report, profile_snapshot, created_at
        FROM check_history 
        WHERE user_id = ? AND deleted_at IS NULL
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_ai_report(user_id: int, slug: str, report: str) -> bool:
    """Сохраняет AI-отчёт к актуальному User Analysis (check_history).

    Отчёт привязан к существующей записи анализа (user + product + slug);
    НЕ создаёт новую запись и НЕ меняет score. Возвращает True, если обновили.
    """
    if not report or not slug:
        return False
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE check_history SET ai_report = ? "
        "WHERE user_id = ? AND slug = ? AND deleted_at IS NULL",
        (report, user_id, slug),
    )
    conn.commit()
    updated = cursor.rowcount
    conn.close()
    return updated > 0


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
        WHERE is_canonical = 1
          AND LOWER(REPLACE(REPLACE(REPLACE(name, '\n', ''), '\r', ''), ' ', '')) LIKE ?
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
        WHERE is_canonical = 1
        ORDER BY id DESC 
        LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_product_count():
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM products WHERE is_canonical = 1')
    row = cursor.fetchone()
    conn.close()
    return row['count'] if row else 0


def _resolve_product_row(conn, row):
    """Если строка — source/merged, возвращает canonical-строку."""
    if row and row["canonical_id"]:
        canon = conn.execute(
            "SELECT * FROM products WHERE id = ?", (row["canonical_id"],)
        ).fetchone()
        if canon:
            return canon
    return row


def get_product_by_slug(slug: str):
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE slug = ?', (slug,))
    row = cursor.fetchone()
    row = _resolve_product_row(conn, row)
    conn.close()
    return dict(row) if row else None

def product_exists_in_products_db(product_name: str) -> bool:
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT id, canonical_id FROM products WHERE name = ? LIMIT 1", (product_name,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

# === ПОЛКА (SHELF) ===
def get_product_by_id(product_id: int):
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE id = ?', (product_id,))
    row = cursor.fetchone()
    row = _resolve_product_row(conn, row)
    conn.close()
    return dict(row) if row else None

def add_product_to_shelf(user_id: int, product_id: int, category: str = "", notes: str = "", routine_id: int = None, cabinet: str = "face", score: int = None):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO shelf_products (user_id, product_id, category, notes, routine_id, cabinet, score)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, product_id, category, notes, routine_id, cabinet or "face", score))
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


def remove_products_from_shelf(user_id: int, shelf_ids: list) -> int:
    """Удаляет связи пользователя с полкой (User→Shelf→Product), НЕ трогая глобальную Product DB."""
    if not shelf_ids:
        return 0
    ids = []
    for i in shelf_ids:
        try:
            ids.append(int(i))
        except (TypeError, ValueError):
            continue
    if not ids:
        return 0
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    placeholders = ",".join(["?"] * len(ids))
    cursor.execute(
        f"DELETE FROM shelf_products WHERE user_id = ? AND id IN ({placeholders})",
        (user_id, *ids),
    )
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


# === FEEDBACK ПЕРСОНАЛИЗАЦИИ ===
def save_recommendation_feedback(user_id: int, product_id: int | None, slug: str, cabinet: str, category: str, reason: str, note: str = ""):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO recommendation_feedback (user_id, product_id, slug, cabinet, category, reason, note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, product_id, slug, cabinet, category, reason, note),
    )
    conn.commit()
    feedback_id = cursor.lastrowid
    conn.close()
    return feedback_id


def save_shelf_removal_feedback(user_id: int, product_id: int | None, slug: str, reason: str, note: str = ""):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO shelf_removal_feedback (user_id, product_id, slug, reason, note) VALUES (?, ?, ?, ?, ?)",
        (user_id, product_id, slug, reason, note),
    )
    conn.commit()
    feedback_id = cursor.lastrowid
    conn.close()
    return feedback_id


def get_user_disliked_slugs(user_id: int) -> set:
    """Slugs продуктов, которые пользователь явно не хочет видеть в подборе."""
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT slug FROM recommendation_feedback WHERE user_id = ? AND slug IS NOT NULL AND slug != ''",
        (user_id,),
    )
    result = {row["slug"] for row in cursor.fetchall()}
    conn.close()
    return result