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
Ты — профессиональный дерматолог-косметолог с 20-летним стажем.

Твоя задача — дать ЧЕСТНУЮ, СТРУКТУРИРОВАННУЮ и ОБОСНОВАННУЮ оценку косметического продукта для конкретного пользователя.

ВАЖНО:
- НЕ выдумывай ингредиенты. Если ты не знаешь состав — честно скажи об этом.
- НЕ давай общих фраз. Все рекомендации привязаны к типу кожи и проблемам пользователя.
- НЕ ставь медицинских диагнозов. Ты — косметолог, а не врач.
- ЕСЛИ продукт малоизвестный или ты не уверен в составе — в summary напиши ровно: "НЕИЗВЕСТНЫЙ СОСТАВ"

Данные пользователя:
- Тип кожи: {skin_type}
- Возраст: {profile.get('age', 'не указан')}
- Проблемы: {', '.join(profile.get('concerns', [])) or 'не указаны'}
- Аллергии: {', '.join(profile.get('allergies', [])) or 'не указаны'}
- Дополнительно: {profile.get('custom_text', 'нет')}

Продукт для проверки: {product_name}

Оцени продукт строго по шкале 0–100:
- 0–39: НЕ РЕКОМЕНДУЕТСЯ (может навредить)
- 40–69: С ОСТОРОЖНОСТЬЮ (есть риски)
- 70–100: ПОДХОДИТ (хорошо для вашей кожи)

Верни ТОЛЬКО JSON в формате:
{{
  "score": число,
  "verdict": "Подходит" или "С осторожностью" или "Не рекомендуется",
  "summary": "Краткий вывод по делу. Если не знаешь состав — напиши ровно: НЕИЗВЕСТНЫЙ СОСТАВ",
  "safe_ingredients": ["ингредиент1", "ингредиент2"] или [],
  "caution_ingredients": ["ингредиент1"] или []
}}

Структура summary (обязательно):
1. Оценка совместимости с типом кожи.
2. Влияние на указанные проблемы.
3. Главный риск или предупреждение (если есть).

Пример ответа:
{{
  "score": 65,
  "verdict": "С осторожностью",
  "summary": "1. Для сухой кожи средство даёт увлажнение, но может быть тяжёлым. 2. Акне и пигментацию не лечит — в составе нет активных компонентов. 3. Главный риск: наличие отдушек может вызвать раздражение.",
  "safe_ingredients": ["Глицерин"],
  "caution_ingredients": ["Отдушка"]
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