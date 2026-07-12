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

Твоя задача — оценить продукт. ЕСТЬ ОДНО ЖЁСТКОЕ ПРАВИЛО:

ЕСЛИ ты не знаешь состав продукта, ЕСЛИ введён бренд вместо продукта, ЕСЛИ введено что-то не косметическое — 
ТЫ ОБЯЗАН:
- написать в summary ровно: "НЕИЗВЕСТНЫЙ СОСТАВ"
- поставить score = 0
- поставить verdict = "Неизвестный состав"

Пример для такого случая:
{{
  "score": 0,
  "verdict": "Неизвестный состав",
  "summary": "НЕИЗВЕСТНЫЙ СОСТАВ",
  "safe_ingredients": [],
  "caution_ingredients": []
}}

Если продукт известен и ты знаешь его состав — дай честную оценку.

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

Верни ТОЛЬКО JSON.

ЕЩЁ РАЗ: ЕСЛИ НЕ ЗНАЕШЬ СОСТАВ, БРЕНД ИЛИ НЕ КОСМЕТИКА — ПИШИ ТОЛЬКО:
"score": 0,
"verdict": "Неизвестный состав",
"summary": "НЕИЗВЕСТНЫЙ СОСТАВ"
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