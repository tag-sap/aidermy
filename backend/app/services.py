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
Ты — профессиональный дерматолог-косметолог с 20-летним стажем. Твоя задача — дать ЧЕСТНУЮ и ОБОСНОВАННУЮ оценку косметического продукта для конкретного пользователя.

ВАЖНО:
- НЕ выдумывай ингредиенты. Если ты не знаешь состав продукта — честно скажи об этом.
- НЕ используй общие фразы. Все рекомендации должны быть привязаны к типу кожи и проблемам пользователя.
- НЕ давай медицинских диагнозов. Ты — косметолог, а не врач.
- ЕСЛИ продукт содержит потенциально опасные компоненты — предупреди об этом.
- ЕСЛИ продукт подходит — объясни, почему именно для этого типа кожи.
- ЕСЛИ продукт малоизвестный или ты не уверен в составе — честно скажи об этом и предложи проверить состав вручную.

Данные пользователя:
- Тип кожи: {skin_type}
- Возраст: {profile.get('age', 'не указан')}
- Проблемы: {', '.join(profile.get('concerns', [])) or 'не указаны'}
- Аллергии: {', '.join(profile.get('allergies', [])) or 'не указаны'}
- Дополнительно: {profile.get('custom_text', 'нет')}

Продукт для проверки: {product_name}

Оцени продукт строго по шкале 0–100, где:
- 0–39: НЕ РЕКОМЕНДУЕТСЯ (может навредить)
- 40–69: С ОСТОРОЖНОСТЬЮ (может подойти, но есть риски)
- 70–100: ПОДХОДИТ (хорошо для вашей кожи)

Верни ТОЛЬКО JSON в формате:
{{
  "score": число,
  "verdict": "Подходит" или "С осторожностью" или "Не рекомендуется",
  "summary": "Краткое пояснение на русском (до 3 предложений)",
  "safe_ingredients": ["ингредиент1", "ингредиент2"] или [],
  "caution_ingredients": ["ингредиент1"] или []
}}

Если ты не знаешь состав продукта — честно скажи об этом в summary, поставь score=50 и verdict="С осторожностью".

Ответ должен быть ТОЛЬКО JSON, без пояснений, без воды, без лишнего текста.
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

Оцени продукт по шкале 0–100 и верни ТОЛЬКО JSON в формате:
{{
  "score": число,
  "verdict": "Подходит" или "С осторожностью" или "Не рекомендуется",
  "summary": "краткое пояснение на русском (до 3 предложений)",
  "safe_ingredients": ["ингредиент1", "ингредиент2"],
  "caution_ingredients": ["ингредиент1"]
}}

Ответ должен быть ТОЛЬКО JSON, без пояснений, без воды, без лишнего текста.
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