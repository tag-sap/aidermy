import httpx
import os
import json
import re
from typing import List
from dotenv import load_dotenv
from .database import get_ingredients, get_connection, PRODUCTS_DB

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")

def generate_slug(name: str) -> str:
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '', name)
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.lower().strip('-')

async def check_product_with_ai(product_name: str, skin_type: str, profile: dict) -> dict:
    saved_ingredients = get_ingredients(product_name)
    if saved_ingredients:
        result = await check_product_with_ingredients(
            product_name,
            skin_type,
            profile,
            saved_ingredients
        )
        result['slug'] = generate_slug(product_name)
        result['ingredients'] = saved_ingredients  # ← ДОБАВЛЕНО
        return result
    
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    
    clean_query = ''.join(product_name.split())
    
    cursor.execute('''
        SELECT name, ingredients, slug FROM products
        WHERE REPLACE(REPLACE(REPLACE(name, '\n', ''), '\r', ''), ' ', '') LIKE ?
        LIMIT 1
    ''', (f'%{clean_query}%',))
    row = cursor.fetchone()
    conn.close()
    
    if row and row['ingredients']:
        result = await check_product_with_ingredients(
            product_name,
            skin_type,
            profile,
            row['ingredients']
        )
        result['slug'] = row['slug'] or generate_slug(product_name)
        result['ingredients'] = row['ingredients']  # ← ДОБАВЛЕНО
        return result
    
    return {
        "score": 0,
        "verdict": "Неизвестный состав",
        "summary": "НЕИЗВЕСТНЫЙ СОСТАВ",
        "safe_ingredients": [],
        "caution_ingredients": [],
        "slug": generate_slug(product_name),
        "ingredients": ""  # ← ДОБАВЛЕНО
    }

async def check_product_with_ingredients(product_name: str, skin_type: str, profile: dict, ingredients: str) -> dict:
    prompt = f"""
Ты профессиональный дерматолог-косметолог.

Пользователь предоставил точный состав продукта:
{ingredients}

Продукт: {product_name}
Тип кожи: {skin_type}
Возраст: {profile.get('age', 'не указан')}
Проблемы: {', '.join(profile.get('concerns', [])) or 'не указаны'}
Аллергии: {', '.join(profile.get('allergies', [])) or 'не указаны'}
Дополнительно: {profile.get('custom_text', 'нет')}

Оцени продукт по шкале 0-100 и верни ТОЛЬКО JSON на русском языке:
{{
  "score": число,
  "verdict": "Подходит" или "С осторожностью" или "Не рекомендуется",
  "summary": "Краткое пояснение на русском с оценкой состава, влиянием на проблемы и рисками",
  "safe_ingredients": ["ингредиент1", "ингредиент2"],
  "caution_ingredients": ["ингредиент1"]
}}

Ответ должен быть ТОЛЬКО JSON, без пояснений, без воды.
"""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 500
            },
            timeout=30
        )

    if response.status_code != 200:
        raise Exception(f"DeepSeek API error: {response.status_code} - {response.text}")

    data = response.json()
    content = data["choices"][0]["message"]["content"]

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise Exception("DeepSeek returned invalid JSON")
    
def search_products(query: str) -> List[dict]:
    """
    Поиск продуктов по названию с поддержкой частичных совпадений
    """
    from .database import get_connection, PRODUCTS_DB
    
    if not query or len(query.strip()) < 2:
        return []
    
    q = query.strip().lower()
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    
    # Разбиваем запрос на слова для частичного поиска
    q_words = q.split()
    
    # Строим условие LIKE для каждого слова
    like_conditions = []
    params = []
    for word in q_words:
        like_conditions.append("LOWER(name) LIKE ?")
        params.append(f'%{word}%')
    
    # Если слов несколько, ищем по всем
    like_clause = " AND ".join(like_conditions) if len(q_words) > 1 else like_conditions[0]
    
    cursor.execute(f'''
        SELECT name, slug FROM products
        WHERE {like_clause}
        ORDER BY 
            CASE 
                WHEN LOWER(name) = ? THEN 0
                WHEN LOWER(name) LIKE ? THEN 1
                WHEN LOWER(name) LIKE ? THEN 2
                ELSE 3
            END
        LIMIT 20
    ''', tuple(params + [q, f'{q}%', f'%{q}%']))
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]    
# Добавьте в конец файла services.py

def determine_skin_type_from_quiz(quiz_answers: dict) -> str:
    """
    Определяет тип кожи на основе ответов на опросник
    """
    if not quiz_answers:
        return "Не определено"
    
    feel = quiz_answers.get('feel_after_wash', '')
    reaction = quiz_answers.get('skin_reaction', '')
    moisture = quiz_answers.get('moisture_level', '')
    pores = quiz_answers.get('pores', '')
    
    # Логика определения
    if feel == 'tight' and moisture == 'always':
        return "Сухая"
    if feel == 'oily' and moisture == 'oily':
        return "Жирная"
    if feel == 'mixed' and moisture == 'sometimes':
        return "Комбинированная"
    if reaction == 'sensitive':
        return "Чувствительная"
    if feel == 'normal' and moisture == 'rarely':
        return "Нормальная"
    if feel == 'tight' and reaction == 'sensitive':
        return "Сухая чувствительная"
    if feel == 'oily' and pores == 'large':
        return "Жирная с расширенными порами"
    
    return "Нормальная"