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

def generate_how_to_use(ingredients: str) -> dict:
    """
    Генерирует рекомендации по применению на основе состава.
    """
    if not ingredients:
        return {
            "application": "По инструкции",
            "time": "По необходимости",
            "note": "Следуйте рекомендациям на упаковке"
        }
    
    i = ingredients.lower()
    note = "Наносите на очищенную кожу."
    
    if "кислота" in i or "ретинол" in i:
        application = "Точечно"
        time = "Вечером"
        note += " Избегайте области вокруг глаз. Используйте SPF днём."
    elif "масло" in i or "сквалан" in i or "ши" in i:
        application = "Тонкий слой"
        time = "Вечером"
        note += " Подходит для массажа."
    elif "гиалурон" in i or "глицерин" in i:
        application = "На влажную кожу"
        time = "Утром и вечером"
        note += " Наносите на слегка влажную кожу для лучшего увлажнения."
    else:
        application = "По инструкции"
        time = "По необходимости"
    
    return {
        "application": application,
        "time": time,
        "note": note
    }

def _apply_fallbacks(result: dict, ingredients: str = ""):
    # Если active_ingredients — массив или None, приводим к объекту
    print(f"🔍 _apply_fallbacks: active_ingredients = {result.get('active_ingredients')}")
    print(f"🔍 _apply_fallbacks: type = {type(result.get('active_ingredients'))}")
    if 'active_ingredients' in result:
        if isinstance(result['active_ingredients'], list):
            result['active_ingredients'] = result['active_ingredients'][0] if result['active_ingredients'] else None
    else:
        result['active_ingredients'] = None
    
    if result.get('active_ingredients') is None:
        result['active_ingredients'] = parse_active_ingredient(ingredients)
    
    if result.get('how_to_use') is None:
        result['how_to_use'] = generate_how_to_use(ingredients)
    
    if result.get('expectations') is None:
        result['expectations'] = {
            "when": "Индивидуально",
            "normal": "Отсутствие раздражения",
            "danger": "Сильное покраснение или жжение"
        }

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
        _apply_fallbacks(result, saved_ingredients)
        return result
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    
    clean_query = ''.join(product_name.split())
    
    cursor.execute('''
        SELECT name, ingredients, slug FROM products
        WHERE REPLACE(REPLACE(REPLACE(name, '\n', ''), '\r', ''), ' ', '') LIKE ?
        LIMIT 1
    ''', (f'%{clean_query.lower()}%',))
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
        _apply_fallbacks(result, saved_ingredients)
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

### Инструкция:
1. Оцени, решает ли состав проблему пользователя.
2. Активный ингредиент — по позиции в составе (1–3 = высокая, 4–6 = средняя, 7+ = низкая).
3. Как применять, чего ожидать, когда бить тревогу.

### Теги:
<good> — позитивные слова
<bad> — негативные слова

### ВАЖНО:
Верни ТОЛЬКО JSON. active_ingredients — ЭТО ОБЪЕКТ, НЕ МАССИВ. Верни ОДИН самый важный активный ингредиент.

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
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 2000
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
    
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
            except:
                result = {
                    "score": 50,
                    "verdict": "Не удалось проанализировать",
                    "summary": "Ошибка обработки ответа AI",
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
                    },
                    "safe_ingredients": [],
                    "caution_ingredients": []
                }
        else:
            result = {
                "score": 50,
                "verdict": "Не удалось проанализировать",
                "summary": "Ошибка обработки ответа AI",
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
                },
                "safe_ingredients": [],
                "caution_ingredients": []
            }

    # 👇 Применяем fallback и возвращаем
    _apply_fallbacks(result, ingredients)
    return result

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