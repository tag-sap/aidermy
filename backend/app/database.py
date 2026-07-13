import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'aidermy.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Таблица для составов (ручной ввод)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            ingredients TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица для истории всех проверок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS check_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            skin_type TEXT NOT NULL,
            score INTEGER NOT NULL,
            verdict TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Добавляем колонку ingredients, если её нет
    cursor.execute("PRAGMA table_info(check_history)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'ingredients' not in columns:
        cursor.execute('ALTER TABLE check_history ADD COLUMN ingredients TEXT DEFAULT ""')
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

def save_ingredients(product_name: str, ingredients: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO ingredients (product_name, ingredients)
        VALUES (?, ?)
    ''', (product_name.lower().strip(), ingredients))
    conn.commit()
    conn.close()
    print(f"💾 Состав сохранён в БД: {product_name}")

def get_ingredients(product_name: str) -> str | None:
    conn = get_connection()
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM ingredients ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# === ИСТОРИЯ ПРОВЕРОК ===

def save_check_result(product_name: str, skin_type: str, score: int, verdict: str, summary: str, ingredients: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO check_history (product_name, skin_type, score, verdict, summary, ingredients, created_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (product_name, skin_type, score, verdict, summary, ingredients))
    conn.commit()
    conn.close()
    print(f"📊 Проверка сохранена: {product_name} — {score}%")

def get_all_check_history(limit: int = 100):
    conn = get_connection()
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
    conn = get_connection()
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

def search_products(query: str, limit: int = 10):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT product_name FROM ingredients
        WHERE product_name LIKE ?
        ORDER BY product_name
        LIMIT ?
    ''', (f'%{query.lower().strip()}%', limit))
    rows = cursor.fetchall()
    conn.close()
    return [row['product_name'] for row in rows]