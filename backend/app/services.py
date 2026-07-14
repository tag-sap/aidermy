import httpx
import os
import json
import re
from dotenv import load_dotenv
from .database import get_ingredients

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")

async def check_product_with_ai(product_name: str, skin_type: str, profile: dict) -> dict:
    # 1. Проверяем ручные составы (aidermy.db)
    saved_ingredients = get_ingredients(product_name)
    if saved_ingredients:
        return await check_product_with_ingredients(
            product_name,
            skin_type,
            profile,
            saved_ingredients
        )
    
    # 2. Проверяем основную базу (products.db) — поиск без учёта пробелов и переносов
    from .database import get_connection, PRODUCTS_DB
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    
    # Убираем ВСЕ пробелы, переносы и лишние символы из запроса
    clean_query = ''.join(product_name.split())
    
    cursor.execute('''
        SELECT name, ingredients FROM products 
        WHERE REPLACE(REPLACE(REPLACE(name, '\n', ''), '\r', ''), ' ', '') LIKE ?
        LIMIT 1
    ''', (f'%{clean_query}%',))
    row = cursor.fetchone()
    conn.close()
    
    if row and row['ingredients']:
        return await check_product_with_ingredients(
            product_name,
            skin_type,
            profile,
            row['ingredients']
        )
    
    # 3. Если нет нигде — возвращаем заглушку
    return {
        "score": 0,
        "verdict": "Неизвестный состав",
        "summary": "НЕИЗВЕСТНЫЙ СОСТАВ",
        "safe_ingredients": [],
        "caution_ingredients": []
    }


async def check_product_with_ingredients(product_name: str, skin_type: str, profile: dict, ingredients: str) -> dict:
    prompt = f"""
Ты — профессиональный дерматолог-косметолог.

Пользователь предоставил точный состав продукта:
{ingredients}

Продукт: {product_name}
Тип кожи: {skin_type}
Возраст: {profile.get('age', 'не указан')}
Проблемы: {', '.join(profile.get('concerns', [])) or 'не указаны'}
Аллергии: {', '.join(profile.get('allergies', [])) or 'не указаны'}
Дополнительно: {profile.get('custom_text', 'нет')}

Оцени продукт по шкале 0–100 и верни ТОЛЬКО JSON:
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
        raise Exception("DeepSeek вернул невалидный JSON")