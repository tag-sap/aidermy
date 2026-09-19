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
DEEPSEEK_MODEL_FALLBACKS = ["deepseek-chat", "deepseek-v4-flash", "deepseek-flash"]

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
    if not content or not isinstance(content, str):
        raise ValueError("Пустой ответ AI")

    cleaned = content.strip()

    code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', cleaned, re.DOTALL)
    if code_block_match:
        cleaned = code_block_match.group(1).strip()

    json_match = re.search(r'\{[\s\S]*\}', cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)

    cleaned = cleaned.strip()
    if not cleaned:
        raise ValueError("Не найден JSON в ответе AI")

    for candidate in [cleaned, cleaned.strip(','), cleaned.strip('`')]:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        fixed = re.sub(r',\s*}', '}', candidate)
        fixed = re.sub(r',\s*\]', ']', fixed)
        try:
            parsed = json.loads(fixed)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start:end+1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise ValueError("Невалидный JSON")


def is_valid_ai_result(result: dict | None) -> bool:
    if not isinstance(result, dict):
        return False

    summary = str(result.get('summary', '') or '').strip()
    verdict = str(result.get('verdict', '') or '').strip()
    score = result.get('score')

    if not summary:
        return False
    if not verdict:
        return False
    if score is None:
        return False
    try:
        score_num = int(score)
    except (TypeError, ValueError):
        return False

    if score_num < 0 or score_num > 100:
        return False

    return True


async def check_product_with_ai(product_name: str, skin_type: str, profile: dict) -> dict:
    def _lookup_image(name: str) -> str | None:
        conn = get_connection(PRODUCTS_DB)
        cursor = conn.cursor()
        clean_query = ''.join(name.split())
        cursor.execute('''
            SELECT image_url FROM products
            WHERE REPLACE(REPLACE(REPLACE(name, '\n', ''), '\r', ''), ' ', '') LIKE ?
            LIMIT 1
        ''', (f'%{clean_query}%',))
        row = cursor.fetchone()
        conn.close()
        return row['image_url'] if row and row['image_url'] else None

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
        result['image_url'] = _lookup_image(product_name)
        return result
    
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    
    clean_query = ''.join(product_name.split())
    
    cursor.execute('''
        SELECT name, ingredients, slug, image_url FROM products
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
        result['image_url'] = row['image_url']
        return result
    
    return {
        "score": 0,
        "verdict": "Неизвестный состав",
        "summary": "НЕИЗВЕСТНЫЙ СОСТАВ",
        "safe_ingredients": [],
        "caution_ingredients": [],
        "slug": generate_slug(product_name),
        "ingredients": "",
        "image_url": _lookup_image(product_name),
        "active_ingredients": None,
        "how_to_use": None,
        "expectations": None
    }

async def check_product_with_ingredients(product_name: str, skin_type: str, profile: dict, ingredients: str) -> dict:
    if profile is None:
        profile = {}

    if not DEEPSEEK_API_KEY:
        from .analysis_service import AnalysisService

        priorities = {
            'hydration': 0.35,
            'barrier_support': 0.25,
            'sensitivity': 0.2,
            'acne_control': 0.1,
            'brightening': 0.1,
        }
        deterministic = AnalysisService().analyze(product_name, ingredients, profile, priorities)
        score = int(deterministic.get('score', 0))
        if score >= 70:
            verdict = 'Подходит'
        elif score >= 40:
            verdict = 'С осторожностью'
        else:
            verdict = 'Не рекомендуется'
        return {
            'score': score,
            'verdict': verdict,
            'summary': 'Автоматическая оценка по базе ингредиентов. AI-анализ сейчас недоступен.',
            'safe_ingredients': [item['ingredient'] for item in deterministic.get('positive_factors', [])[:8]],
            'caution_ingredients': [item['ingredient'] for item in deterministic.get('negative_factors', [])[:8]],
            'active_ingredients': None,
            'how_to_use': None,
            'expectations': None,
        }

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

### Теги для цветовой маркировки (только в полях summary, note, normal, danger):
<good> — позитивный момент
<warning> — предупреждение, на что обратить внимание
<bad> — негативный момент

### Summary (резюме):
Напиши 1–2 коротких предложения простым человеческим языком, отвечая на вопрос «что это значит лично для пользователя?».
НЕ перечисляй ингредиенты и INCI-названия — они будут показаны отдельно в подробном разборе.
НЕ используй медицинские утверждения.
Используй теги <good>, <warning>, <bad> вокруг коротких фраз.

### ВАЖНО:
Верни ТОЛЬКО JSON без лишнего текста. Все поля обязательны.

### Формат:
{{
  "score": число,
  "verdict": "Подходит" | "С осторожностью" | "Не рекомендуется",
  "summary": "1–2 предложения простым языком с тегами <good>/<warning>/<bad>",
  "active_ingredients": {{
    "name": "название",
    "position": число,
    "concentration": "высокая" | "средняя" | "низкая",
    "effectiveness": "рабочая" | "средняя" | "минимальная"
  }},
  "how_to_use": {{
    "application": "Тонкий слой" | "Точечно" | "Можно много",
    "time": "Утром" | "Вечером" | "2 раза в день",
    "note": "с <good>, <warning> или <bad>"
  }},
  "expectations": {{
    "when": "через 1-2 недели" | "через месяц",
    "normal": "с <good>, <warning> или <bad>",
    "danger": "с <good>, <warning> или <bad>"
  }},
  "safe_ingredients": ["инг1"],
  "caution_ingredients": ["инг1"]
}}
"""

    fallback = {
        "score": 50,
        "verdict": "С осторожностью",
        "summary": "Не удалось получить корректный разбор состава. Попробуйте проверить продукт ещё раз.",
        "safe_ingredients": [],
        "caution_ingredients": [],
        "active_ingredients": None,
        "how_to_use": None,
        "expectations": None,
    }

    for attempt in range(len(DEEPSEEK_MODEL_FALLBACKS)):
        model_name = DEEPSEEK_MODEL_FALLBACKS[attempt]
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    DEEPSEEK_API_URL,
                    headers={
                        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 3000
                    },
                    timeout=30
                )

            if response.status_code != 200:
                print(f"⚠️ DeepSeek model {model_name} failed with status {response.status_code}")
                if attempt == len(DEEPSEEK_MODEL_FALLBACKS) - 1:
                    raise Exception(f"DeepSeek API error: {response.status_code} - {response.text}")
                continue

            try:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
            except Exception:
                if attempt == len(DEEPSEEK_MODEL_FALLBACKS) - 1:
                    return fallback
                continue

            if not content or not str(content).strip():
                print(f"⚠️ DeepSeek model {model_name} returned empty content; trying next model.")
                if attempt == len(DEEPSEEK_MODEL_FALLBACKS) - 1:
                    return fallback
                continue

            print(f"📥 ОТВЕТ AI [{model_name}]:")
            print(content)
            print("---")

            try:
                result = extract_json_from_response(content)
                if is_valid_ai_result(result):
                    return result
            except Exception as e:
                print(f"❌ Ошибка парсинга JSON: {e}")

            if attempt == len(DEEPSEEK_MODEL_FALLBACKS) - 1:
                break
            continue
        except Exception as e:
            print(f"❌ Ошибка модели {model_name}: {e}")
            if attempt == len(DEEPSEEK_MODEL_FALLBACKS) - 1:
                raise
            continue

    return {
        **fallback,
        "summary": fallback.get("summary") or "Состав проверен, но итоговый ответ был пустым. Попробуйте повторить проверку.",
        "verdict": fallback.get("verdict") or "С осторожностью",
        "score": int(fallback.get("score") or 50),
        "safe_ingredients": fallback.get("safe_ingredients") or [],
        "caution_ingredients": fallback.get("caution_ingredients") or [],
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