import sqlite3
import os
from datetime import datetime

# === ДВЕ БАЗЫ ===
AIDERMY_DB = os.path.join(os.path.dirname(__file__), '..', 'aidermy.db')  # история проверок + ручные составы
PRODUCTS_DB = os.path.join(os.path.dirname(__file__), '..', 'products.db')  # основная база продуктов

def get_connection(db_path=None):
    if db_path is None:
        db_path = AIDERMY_DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    # === aidermy.db ===
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            ingredients TEXT NOT NULL,
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute("PRAGMA table_info(check_history)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'ingredients' not in columns:
        cursor.execute('ALTER TABLE check_history ADD COLUMN ingredients TEXT DEFAULT ""')
    
    conn.commit()
    conn.close()
    
    # === products.db ===
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
    conn.commit()
    conn.close()
    
    print("✅ Базы данных инициализированы")

# === РАБОТА С ИСТОРИЕЙ (aidermy.db) ===

def save_check_result(product_name: str, skin_type: str, score: int, verdict: str, summary: str, ingredients: str = ""):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO check_history (product_name, skin_type, score, verdict, summary, ingredients, created_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (product_name, skin_type, score, verdict, summary, ingredients))
    conn.commit()
    conn.close()
    print(f"📊 Проверка сохранена: {product_name} — {score}%")

def get_all_check_history(limit: int = 100):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM check_history 
        ORDER BY created_at DESC 
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

# === РАБОТА С РУЧНЫМИ СОСТАВАМИ (aidermy.db) ===

def save_ingredients(product_name: str, ingredients: str):
    conn = get_connection(AIDERMY_DB)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO ingredients (product_name, ingredients)
        VALUES (?, ?)
    ''', (product_name.lower().strip(), ingredients))
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

# === ГЛАВНАЯ ФУНКЦИЯ ПОИСКА ПРОДУКТОВ (products.db) ===

def search_products(query: str, limit: int = 10):
    """Поиск продуктов ТОЛЬКО в products.db"""
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT name FROM products
        WHERE name LIKE ?
        ORDER BY name
        LIMIT ?
    ''', (f'%{query.lower().strip()}%', limit))
    rows = cursor.fetchall()
    conn.close()
    return [row['name'] for row in rows]

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