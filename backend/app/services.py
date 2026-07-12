import httpx
import os
import json
import re
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")

async def check_product_with_ai(product_name: str, skin_type: str, profile: dict) -> dict:
    prompt = f"""
Ты — профессиональный дерматолог-косметолог.

Твоя задача — оценить продукт. НО ЕСТЬ ОДНО ГЛАВНОЕ ПРАВИЛО:

ЕСЛИ ТЫ НЕ ЗНАЕШЬ СОСТАВ ПРОДУКТА — ТЫ ОБЯЗАН НАПИСАТЬ В SUMMARY РОВНО ЭТУ ФРАЗУ:
"НЕИЗВЕСТНЫЙ СОСТАВ"

НИКАКИХ ДРУГИХ ВАРИАНТОВ. ТОЛЬКО ЭТА ФРАЗА.
ЕСЛИ НАПИШЕШЬ ЧТО-ТО ДРУГОЕ — ЭТО БУДЕТ ОШИБКОЙ.

Данные пользователя:
- Тип кожи: {skin_type}
- Возраст: {profile.get('age', 'не указан')}
- Проблемы: {', '.join(profile.get('concerns', [])) or 'не указаны'}
- Аллергии: {', '.join(profile.get('allergies', [])) or 'не указаны'}
- Дополнительно: {profile.get('custom_text', 'нет')}

Продукт: {product_name}

Оцени по шкале 0–100:
- 0–39: НЕ РЕКОМЕНДУЕТСЯ
- 40–69: С ОСТОРОЖНОСТЬЮ
- 70–100: ПОДХОДИТ

Верни ТОЛЬКО JSON:
{{
  "score": число,
  "verdict": "Подходит" или "С осторожностью" или "Не рекомендуется",
  "summary": "ТВОЙ ВЫВОД. ЕСЛИ НЕ ЗНАЕШЬ СОСТАВ — НАПИШИ РОВНО: НЕИЗВЕСТНЫЙ СОСТАВ",
  "safe_ingredients": ["ингредиент1", "ингредиент2"] или [],
  "caution_ingredients": ["ингредиент1"] или []
}}

ЕЩЁ РАЗ: ЕСЛИ НЕ ЗНАЕШЬ СОСТАВ — ПИШИ ТОЛЬКО "НЕИЗВЕСТНЫЙ СОСТАВ".
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
  "summary": "Краткое пояснение на русском",
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
        raise Exception("DeepSeek вернул невалидный JSON")