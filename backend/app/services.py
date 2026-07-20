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
Ты профессиональный дерматолог-косметолог с 15-летним стажем.

Пользователь описал свою проблему:
«{profile.get('custom_text', 'не указано')}»

Его тип кожи: {skin_type}
Возраст: {profile.get('age', 'не указан')}
Проблемы: {', '.join(profile.get('concerns', [])) or 'не указаны'}
Аллергии: {', '.join(profile.get('allergies', [])) or 'не указаны'}

СОСТАВ ПРОДУКТА:
{ingredients}

ПРОДУКТ: {product_name}

---

### ИНСТРУКЦИЯ ПО ОЦЕНКЕ:

1. **Прочитай жалобу пользователя** — это САМЫЙ ВАЖНЫЙ фактор.
2. Оцени, насколько состав продукта решает ЭТУ КОНКРЕТНУЮ проблему.
3. Если состав игнорирует проблему — ставь низкий балл (даже если сам по себе состав «хороший»).
4. Если состав целенаправленно решает проблему — ставь высокий балл.

### Примеры:
- Проблема: «кожа стягивается» → состав с глицерином, но без масел и церамидов → **40%** (не решает проблему).
- Проблема: «кожа стягивается» → состав с пантенолом, церамидами, маслами → **85%** (решает проблему).
- Проблема: «акне и жирный блеск» → состав с салициловой кислотой, ниацинамидом → **90%**.
- Проблема: «акне и жирный блеск» → состав с маслами и окклюзивами → **20%** (усугубит).

---

Верни ТОЛЬКО JSON:

{{
  "score": число от 0 до 100 (ОБЯЗАТЕЛЬНО учитывай проблему пользователя!),
  "verdict": "Подходит" или "С осторожностью" или "Не рекомендуется",
  "summary": "Разбор: насколько продукт решает проблему пользователя. Честно, без воды.",
  "safe_ingredients": ["ингредиент1", "ингредиент2"],
  "caution_ingredients": ["ингредиент1"]
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
    from .database import get_connection, PRODUCTS_DB
    if not query or len(query.strip()) < 2:
        return []
    q = query.strip().lower()
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    q_words = q.split()
    if len(q_words) == 1:
        cursor.execute("SELECT name, slug, image_url FROM products WHERE LOWER(name) LIKE ? LIMIT 20", (f"%{q}%",))
    else:
        conditions = " AND ".join(["LOWER(name) LIKE ?" for _ in q_words])
        params = [f"%{word}%" for word in q_words]
        cursor.execute(f"SELECT name, slug, image_url FROM products WHERE {conditions} LIMIT 20", params)
    rows = cursor.fetchall()
    conn.close()
    return [{"name": row[0], "slug": row[1], "image_url": row[2]} for row in rows]

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