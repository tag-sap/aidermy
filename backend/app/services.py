# services.py

import httpx
import os
import json
import re
import unicodedata
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

def clean_json_response(content: str) -> str:
    """Очищает ответ от лишнего текста, оставляя только JSON"""
    # Ищем JSON в ответе
    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if json_match:
        return json_match.group()
    return content

def extract_json_from_response(content: str) -> dict:
    """Извлекает JSON из ответа AI"""
    # Пробуем найти JSON в блоке кода
    code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content, re.DOTALL)
    if code_block_match:
        content = code_block_match.group(1).strip()
    
    # Пробуем найти JSON в тексте
    json_match = re.search(r'\{[\s\S]*\}', content, re.DOTALL)
    if json_match:
        content = json_match.group()
    
    # Очищаем от лишних символов
    content = content.strip()
    
    # Пробуем распарсить
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Если не получилось, пробуем починить
        # Удаляем trailing commas
        content = re.sub(r',\s*}', '}', content)
        content = re.sub(r',\s*\]', ']', content)
        try:
            return json.loads(content)
        except:
            raise Exception("Невалидный JSON")

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
        result['ingredients'] = saved_ingredients
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
        result['ingredients'] = row['ingredients']
        return result
    
    return {
        "score": 0,
        "verdict": "Неизвестный состав",
        "summary": "НЕИЗВЕСТНЫЙ СОСТАВ",
        "safe_ingredients": [],
        "caution_ingredients": [],
        "slug": generate_slug(product_name),
        "ingredients": "",
        "active_ingredients": None,
        "how_to_use": None,
        "expectations": None
    }

async def check_product_with_ingredients(product_name: str, skin_type: str, profile: dict, ingredients: str) -> dict:
    if profile is None:
        profile = {}
    
    prompt = f"""
Ты — дерматолог. Оцени продукт для пользователя.

### Данные:
- Кожа: {skin_type}
- Возраст: {profile.get('age', 'не указан')}
- Проблемы: {', '.join(profile.get('concerns', [])) or 'не указаны'}
- Аллергии: {', '.join(profile.get('allergies', [])) or 'не указаны'}
- Жалоба: {profile.get('custom_text', 'не указана')}

### Продукт:
- {product_name}
- Состав (по убыванию концентрации): {ingredients}

### Шкала оценки (0–100):
- 0–20: продукт вреден или противопоказан
- 21–40: не подходит, может усугубить проблему
- 41–60: нейтрально, не решает проблему, но и не вредит
- 61–80: помогает, хороший выбор
- 81–100: идеально решает проблему пользователя

### Инструкция:
1. Оцени, решает ли состав проблему пользователя.
2. Активный ингредиент — по позиции в составе (1–3 = высокая, 4–6 = средняя, 7+ = низкая).
3. Как применять, чего ожидать, когда бить тревогу.

### Теги:
<good> — позитивные слова
<bad> — негативные слова

### ВАЖНО:
Верни ТОЛЬКО JSON без лишнего текста. Все поля обязательны.

### Формат:
{{
  "score": число,
  "verdict": "Подходит" | "С осторожностью" | "Не рекомендуется",
  "summary": "текст с <good> и <bad>",
  "active_ingredients": {{
    "name": "название",
    "position": число,
    "concentration": "высокая" | "средняя" | "низкая",
    "effectiveness": "рабочая" | "средняя" | "минимальная"
  }},
  "how_to_use": {{
    "application": "Тонкий слой" | "Точечно" | "Можно много",
    "time": "Утром" | "Вечером" | "2 раза в день",
    "note": "с <good> и <bad>"
  }},
  "expectations": {{
    "when": "через 1-2 недели" | "через месяц",
    "normal": "с <good> и <bad>",
    "danger": "с <good> и <bad>"
  }},
  "safe_ingredients": ["инг1"],
  "caution_ingredients": ["инг1"]
}}
"""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-v4-flash",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 3000
            },
            timeout=30
        )

    if response.status_code != 200:
        raise Exception(f"DeepSeek API error: {response.status_code} - {response.text}")

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    print("📥 ОТВЕТ AI:")
    print(content)
    print("---")
    
    # Пробуем извлечь JSON
    try:
        result = extract_json_from_response(content)
        return result
    except Exception as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
        # Возвращаем дефолтный результат
        return {
            "score": 50,
            "verdict": "Нейтрально",
            "summary": "Не удалось получить рекомендацию.",
            "safe_ingredients": [],
            "caution_ingredients": [],
            "active_ingredients": None,
            "how_to_use": None,
            "expectations": None
        }

def search_products(query: str) -> List[dict]:
    from .database import get_connection, PRODUCTS_DB
    if not query or len(query.strip()) < 2:
        return []
    
    q = query.strip().lower()
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT name, slug, image_url, ingredients FROM products WHERE LOWER(name) = ? LIMIT 1",
        (q,)
    )
    row = cursor.fetchone()
    if row:
        conn.close()
        return [{"name": row[0], "slug": row[1], "image_url": row[2], "ingredients": row[3]}]
    
    words = q.split()
    if len(words) == 1:
        cursor.execute(
            "SELECT name, slug, image_url, ingredients FROM products WHERE LOWER(name) LIKE ? LIMIT 20",
            (f"%{q}%",)
        )
    else:
        conditions = []
        params = []
        for word in words:
            conditions.append("LOWER(name) LIKE ?")
            params.append(f"%{word}%")
        cursor.execute(
            f"SELECT name, slug, image_url, ingredients FROM products WHERE {' AND '.join(conditions)} LIMIT 20",
            params
        )
    
    rows = cursor.fetchall()
    conn.close()
    return [{"name": row[0], "slug": row[1], "image_url": row[2], "ingredients": row[3]} for row in rows]

def determine_skin_type_from_quiz(quiz_answers: dict) -> str:
    if not quiz_answers:
        return "Не определено"
    
    feel = quiz_answers.get('feel_after_wash', '')
    reaction = quiz_answers.get('skin_reaction', '')
    moisture = quiz_answers.get('moisture_level', '')
    pores = quiz_answers.get('pores', '')
    
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

def transliterate(text: str) -> str:
    cyrillic_to_latin = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
    }
    result = []
    for char in text.lower():
        if char in cyrillic_to_latin:
            result.append(cyrillic_to_latin[char])
        else:
            result.append(char)
    return ''.join(result)

def normalize_search_query(query: str) -> str:
    query = ' '.join(query.split())
    transliterated = transliterate(query)
    transliterated = re.sub(r'[^a-z0-9\s-]', '', transliterated)
    return transliterated.strip()