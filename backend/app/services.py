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


def capitalize_name(name: str) -> str:
    """Делает первую букву заглавной, если название начинается с буквы.

    Не меняет регистр остальной части строки (например, «cosrx Advanced Snail»
    -> «Cosrx Advanced Snail», «pH формула» остаётся как есть, т.к. первый символ не буква).
    """
    if not name:
        return name
    for i, ch in enumerate(name):
        if ch.isalpha():
            return name[:i] + ch.upper() + name[i + 1:]
        if not ch.isspace():
            # Первый не-пробельный символ не буква (цифра, символ) — не трогаем.
            return name
    return name

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

    from .decision_engine import DecisionEngine

    engine = DecisionEngine()

    # Фаза 9 — Research Queue: неизвестные ингредиенты дожидаются batch research.
    # Анализ НЕ отдаёт предварительный score, а ждёт завершения Research.
    research_status = None
    if DEEPSEEK_API_KEY:
        try:
            from .ingredient_enrichment import find_unknown_ingredients
            from .research_queue import run_research
            prepared = engine.analysis_service.prepare_product_ingredients(ingredients)
            unknown = find_unknown_ingredients(prepared)
            if unknown:
                research_status = await run_research(unknown_ingredients=unknown)
        except Exception as exc:
            print(f"[CHECK] research failed: {exc!r}")
            research_status = "failed"

    deterministic = engine.analyze(product_name, ingredients, profile, skin_type)

    # AI используется ТОЛЬКО для обогащения (active_ingredients / how_to_use /
    # expectations / ingredient_claims). Финальный score/verdict всегда берётся
    # из deterministic scoring engine.
    enrichment = await _enrich_with_ai(product_name, ingredients, skin_type, profile) if DEEPSEEK_API_KEY else None

    if enrichment:
        from .shelf_service import enrich_ingredient_knowledge
        added = enrich_ingredient_knowledge(enrichment.get("ingredient_claims") or [])
        # Если движок ещё ничего не знал о составе, а AI пополнил базу знаний —
        # пересчитываем детерминированный скор на обогащённых данных.
        if float(deterministic.get("confidence") or 0.0) <= 0 and added > 0:
            deterministic = engine.analyze(product_name, ingredients, profile, skin_type)

    # Итоговое резюме — детерминированное (build_summary). AI-рецензия (summary) НЕ
    # вызывается здесь автоматически: она доступна только по явному запросу через
    # generate_ai_review() / эндпоинт /api/review. Процент всегда детерминированный.
    summary = deterministic.get('summary') or 'Не удалось получить рекомендацию.'

    return {
        'score': int(deterministic.get('score') or 0),
        'verdict': deterministic.get('verdict') or 'Требует внимания',
        'summary': summary,
        'safe_ingredients': deterministic.get('safe_ingredients') or [],
        'caution_ingredients': deterministic.get('caution_ingredients') or [],
        'active_ingredients': (enrichment or {}).get('active_ingredients'),
        'how_to_use': (enrichment or {}).get('how_to_use'),
        'expectations': (enrichment or {}).get('expectations'),
        'ingredient_claims': (enrichment or {}).get('ingredient_claims') or [],
        'research_status': research_status,
    }


async def generate_ai_review(product_name: str, skin_type: str, profile: dict, ingredients: str) -> dict:
    """AI-рецензия ПО ЯВНОМУ ЗАПРОСУ: score считает детерминированный движок,
    а AI только пишет понятное объяснение. Процент не меняет."""
    from .decision_engine import DecisionEngine

    profile = profile or {}
    engine = DecisionEngine()
    deterministic = engine.analyze(product_name, ingredients, profile, skin_type)
    score = int(deterministic.get('score') or 0)

    review = deterministic.get('summary') or ''
    if DEEPSEEK_API_KEY:
        try:
            from .ai_summary import summarize_with_ai
            ai_summary = await summarize_with_ai(product_name, score, deterministic, profile)
            if ai_summary:
                review = ai_summary
        except Exception as exc:
            print(f"[REVIEW] AI failed: {exc!r}")

    return {
        'score': score,
        'verdict': deterministic.get('verdict') or 'Требует внимания',
        'summary': review,
        'safe_ingredients': deterministic.get('safe_ingredients') or [],
        'caution_ingredients': deterministic.get('caution_ingredients') or [],
        'positive_factors': deterministic.get('positive_factors') or [],
        'negative_factors': deterministic.get('negative_factors') or [],
    }


async def generate_ai_report(product_name: str, analysis: dict, profile: dict) -> str:
    """AI-отчёт: человеческое объяснение УЖЕ СУЩЕСТВУЮЩЕГО User Analysis.

    Score НЕ пересчитывается — берётся из переданного analysis (история проверок).
    AI пишет 2-3 предложения по готовым safe/caution ингредиентам.
    """
    from .ai_summary import summarize_with_ai

    analysis = analysis or {}
    score = int(analysis.get("score") or 0)
    pos = [{"ingredient": i} for i in (analysis.get("safe_ingredients") or [])]
    neg = [{"ingredient": i} for i in (analysis.get("caution_ingredients") or [])]
    payload = {**analysis, "positive_factors": pos, "negative_factors": neg}
    summary = await summarize_with_ai(product_name, score, payload, profile or {})
    return summary or (analysis.get("summary") or "")

async def _enrich_with_ai(product_name: str, ingredients: str, skin_type: str, profile: dict) -> dict | None:
    """AI-обогащение данных о составе.

    Возвращает ТОЛЬКО вспомогательные поля (active_ingredients, how_to_use,
    expectations, ingredient_claims). НЕ возвращает score/verdict/summary —
    их всегда считает deterministic scoring engine.
    """
    prompt = f"""
Ты — косметолог-технолог. Обогати данные о составе продукта для базы знаний Aidermy.

### Контекст пользователя (только для понимания, НЕ для оценки):
- Кожа: {skin_type}
- Проблемы: {', '.join(profile.get('concerns', [])) or 'не указаны'}
- Аллергии: {', '.join(profile.get('allergies', [])) or 'не указаны'}

### Продукт:
- {product_name}
- Состав (по убыванию концентрации): {ingredients}

### Задачи:
1. Определи один ключевой активный ингредиент: его позицию в составе, концентрацию и эффективность.
2. Опиши, как применять, чего ожидать и когда стоит насторожиться.
3. Перечисли 3–6 ингредиентов с их свойством для базы знаний.

### Теги для цветовой маркировки (только в полях note, normal, danger):
<good> — позитивный момент
<warning> — предупреждение
<bad> — негативный момент

### ВАЖНО:
Верни ТОЛЬКО JSON без лишнего текста. Поля score, verdict, summary НЕ нужны.

### Формат:
{{
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
  "ingredient_claims": [
    {{"ingredient": "ингредиент", "property": "hydration|barrier_support|sensitivity|acne_control|brightening", "direction": "positive|negative", "strength": 0.8, "confidence": 0.9}}
  ]
}}
"""

    for attempt in range(len(DEEPSEEK_MODEL_FALLBACKS)):
        model_name = DEEPSEEK_MODEL_FALLBACKS[attempt]
        try:
            from .instrumentation import METRICS
            METRICS.increment("ai_call_count")

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    DEEPSEEK_API_URL,
                    headers={
                        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 3000,
                    },
                    timeout=30,
                )

            if response.status_code != 200:
                if attempt == len(DEEPSEEK_MODEL_FALLBACKS) - 1:
                    return None
                continue

            try:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
            except Exception:
                continue

            if not content or not str(content).strip():
                continue

            try:
                result = extract_json_from_response(content)
                if isinstance(result, dict) and (
                    result.get("active_ingredients") or result.get("ingredient_claims")
                ):
                    return result
            except Exception:
                continue

        except Exception:
            continue

    return None

def search_products(query: str) -> List[dict]:
    from .database import get_connection, PRODUCTS_DB
    if not query or len(query.strip()) < 2:
        return []
    
    q = query.strip().lower()
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT name, slug, image_url, ingredients FROM products WHERE is_canonical = 1 AND LOWER(name) = ? LIMIT 1",
        (q,)
    )
    row = cursor.fetchone()
    if row:
        conn.close()
        return [{"name": row[0], "slug": row[1], "image_url": row[2], "ingredients": row[3]}]
    
    words = q.split()
    if len(words) == 1:
        cursor.execute(
            "SELECT name, slug, image_url, ingredients FROM products WHERE is_canonical = 1 AND LOWER(name) LIKE ? LIMIT 20",
            (f"%{q}%",)
        )
    else:
        conditions = ["is_canonical = 1"]
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