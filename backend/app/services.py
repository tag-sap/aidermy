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
        result['ingredients'] = saved_ingredients
        
        # === FALLBACK ДЛЯ НОВЫХ ПОЛЕЙ ===
        if 'active_ingredients' not in result or result['active_ingredients'] is None:
            result['active_ingredients'] = {
                "name": "Не определён",
                "position": 0,
                "concentration": "низкая",
                "effectiveness": "минимальная"
            }
        if 'how_to_use' not in result or result['how_to_use'] is None:
            result['how_to_use'] = {
                "application": "По инструкции",
                "time": "По необходимости",
                "note": "Следуйте рекомендациям на упаковке"
            }
        if 'expectations' not in result or result['expectations'] is None:
            result['expectations'] = {
                "when": "Индивидуально",
                "normal": "Отсутствие раздражения",
                "danger": "Сильное покраснение или жжение"
            }
        
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
        
        # === FALLBACK ДЛЯ НОВЫХ ПОЛЕЙ ===
        if 'active_ingredients' not in result or result['active_ingredients'] is None:
            result['active_ingredients'] = {
                "name": "Не определён",
                "position": 0,
                "concentration": "низкая",
                "effectiveness": "минимальная"
            }
        if 'how_to_use' not in result or result['how_to_use'] is None:
            result['how_to_use'] = {
                "application": "По инструкции",
                "time": "По необходимости",
                "note": "Следуйте рекомендациям на упаковке"
            }
        if 'expectations' not in result or result['expectations'] is None:
            result['expectations'] = {
                "when": "Индивидуально",
                "normal": "Отсутствие раздражения",
                "danger": "Сильное покраснение или жжение"
            }
        
        return result
    
    return {
        "score": 0,
        "verdict": "Неизвестный состав",
        "summary": "НЕИЗВЕСТНЫЙ СОСТАВ",
        "safe_ingredients": [],
        "caution_ingredients": [],
        "slug": generate_slug(product_name),
        "ingredients": "",
        "active_ingredients": {
            "name": "Не определён",
            "position": 0,
            "concentration": "низкая",
            "effectiveness": "минимальная"
        },
        "how_to_use": {
            "application": "По инструкции",
            "time": "По необходимости",
            "note": "Следуйте рекомендациям на упаковке"
        },
        "expectations": {
            "when": "Индивидуально",
            "normal": "Отсутствие раздражения",
            "danger": "Сильное покраснение или жжение"
        }
    }
async def check_product_with_ingredients(product_name: str, skin_type: str, profile: dict, ingredients: str) -> dict:
    prompt = f"""
Ты — профессиональный дерматолог-косметолог с 15-летним стажем.

### Данные пользователя:
- Тип кожи: {skin_type}
- Возраст: {profile.get('age', 'не указан')}
- Проблемы: {', '.join(profile.get('concerns', [])) or 'не указаны'}
- Аллергии: {', '.join(profile.get('allergies', [])) or 'не указаны'}
- Жалоба пользователя: {profile.get('custom_text', 'не указана')}

### Продукт:
- Название: {product_name}
- Состав (ингредиенты перечислены в порядке убывания концентрации): {ingredients}

---

### ИНСТРУКЦИЯ ПО АНАЛИЗУ:

#### 1. Концентрация по позиции в составе:
- Ингредиенты в начале списка (позиции 1–3) — высокая концентрация.
- Ингредиенты в середине (позиции 4–6) — средняя концентрация.
- Ингредиенты в конце списка (после консервантов или парфюма, позиции 7+) — низкая концентрация.
- Если активный ингредиент в топ-5 — концентрация рабочая.
- Если активный ингредиент после консервантов — эффект минимальный.

#### 2. Оценка совместимости с пользователем (учти жалобу!):
- Прочитай жалобу пользователя — это САМЫЙ ВАЖНЫЙ фактор.
- Если состав решает проблему — ставь высокий балл.
- Если состав игнорирует проблему — ставь низкий балл (даже если состав «хороший»).

#### 3. Цветовое выделение (ОБЯЗАТЕЛЬНО!):
Используй теги в полях summary, how_to_use.note, expectations.normal, expectations.danger:
- <good>текст</good> — для позитивных слов: "подходит", "рекомендуется", "эффективно", "безопасно", "увлажняет", "восстанавливает", "успокаивает".
- <bad>текст</bad> — для негативных слов: "раздражает", "опасно", "не рекомендуется", "комедогенно", "стягивает", "пересушивает".

---

### ФОРМАТ ОТВЕТА (ТОЛЬКО JSON):

{{
  "score": число от 0 до 100,

  "verdict": "Подходит" | "С осторожностью" | "Не рекомендуется",

  "summary": "текст с <good> и <bad> тегами",

  "active_ingredients": {{
    "name": "название активного ингредиента",
    "position": число (позиция в списке, начиная с 1),
    "concentration": "высокая" | "средняя" | "низкая",
    "effectiveness": "рабочая" | "средняя" | "минимальная"
  }},

  "how_to_use": {{
    "application": "Тонкий слой" | "Точечно" | "Можно много" | "На сухую кожу" | "На влажную кожу",
    "time": "Утром" | "Вечером" | "2 раза в день" | "По необходимости",
    "note": "дополнительная рекомендация с <good> и <bad> тегами"
  }},

  "expectations": {{
    "when": "через 1–2 недели" | "через 3–4 недели" | "через 2 месяца",
    "normal": "нормальная реакция с <good> и <bad> тегами",
    "danger": "когда прекратить использование с <good> и <bad> тегами"
  }},

  "safe_ingredients": ["ингредиент1", "ингредиент2"],
  "caution_ingredients": ["ингредиент1"]
}}

### ВАЖНО:
- Ответ должен быть ТОЛЬКО JSON. Никакого текста до или после.
- Все кавычки и запятые должны быть на месте.
- Теги <good> и <bad> обязательны.
- Оценка должна быть честной и привязана к проблеме пользователя.
⚠️ ВНИМАНИЕ: В ответе ОБЯЗАТЕЛЬНО должны быть поля active_ingredients, how_to_use, expectations. Заполни их даже если продукт простой.
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