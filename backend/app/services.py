# services.py

import asyncio
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

# Лимиты на вспомогательные AI-шаги при проверке продукта. Детерминированный скор
# считается ДО них и возвращается всегда; AI-обогащение/отчёт — best effort и не
# должен блокировать ответ дольше этих таймаутов (иначе nginx рвёт соединение).
RESEARCH_STEP_TIMEOUT = 12.0
ENRICH_STEP_TIMEOUT = 15.0
REPORT_STEP_TIMEOUT = 20.0
SECTIONS_STEP_TIMEOUT = 20.0
KEY_INGREDIENT_STEP_TIMEOUT = 12.0

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
        SELECT id, name, ingredients, slug, image_url FROM products
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
        # Сохраняем Static Product Model — глобальную объективную модель продукта,
        # НЕ привязанную к пользователю. Она переиспользуется другими пользователями
        # и НЕ удаляется при очистке истории.
        try:
            from .product_model import get_or_build_product_model
            get_or_build_product_model(dict(row))
        except Exception as exc:
            print(f"[PRODUCT_MODEL] save failed: {exc!r}")
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

    # Порядок важен: research → enrichment → deterministic score. Скор нельзя
    # считать по неполной базе ингредиентов, поэтому research/enrichment идут ДО
    # него. Если research не успевает (AI долгий / холодная очередь) — возвращаем
    # «pending»: фронтенд покажет «Это займёт больше времени, возвращайтесь позже».
    research_status = None
    if DEEPSEEK_API_KEY:
        try:
            from .ingredient_enrichment import find_unknown_ingredients
            from .research_queue import run_research
            prepared = engine.analysis_service.prepare_product_ingredients(ingredients)
            unknown = find_unknown_ingredients(prepared)
            if unknown:
                try:
                    research_status = await asyncio.wait_for(
                        run_research(unknown_ingredients=unknown),
                        timeout=RESEARCH_STEP_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    print("[CHECK] research timed out — product pending")
                    return {"pending": True, "research_status": "timeout"}
        except Exception as exc:
            print(f"[CHECK] research failed: {exc!r}")
            research_status = "failed"

    # 1) AI обогащает ТОЛЬКО базу знаний ингредиентов (ingredient_claims) ДО скоринга.
    #    НЕ генерирует how_to_use / expectations / active_ingredients и НЕ оценивает
    #    совместимость — это делает детерминированный движок на обогащённых данных.
    ingredient_claims = None
    if DEEPSEEK_API_KEY:
        try:
            ingredient_claims = await asyncio.wait_for(
                _enrich_knowledge_with_ai(product_name, ingredients),
                timeout=ENRICH_STEP_TIMEOUT,
            )
        except Exception as exc:
            print(f"[CHECK] enrichment failed: {exc!r}")

    if ingredient_claims:
        try:
            from .shelf_service import enrich_ingredient_knowledge
            enrich_ingredient_knowledge(ingredient_claims)
        except Exception as exc:
            print(f"[CHECK] enrichment apply failed: {exc!r}")

    # 2) Детерминированный скор — теперь на полной базе знаний (после research/enrichment).
    deterministic = engine.analyze(product_name, ingredients, profile, skin_type)

    # 3) AI-отчёт (report) — человеческое объяснение причин («Почему»).
    #    Получает structured factors и НЕ переопределяет score/verdict.
    report = None
    if DEEPSEEK_API_KEY and (deterministic.get("positive_factors") or deterministic.get("negative_factors")):
        try:
            report = await asyncio.wait_for(
                generate_ai_report(product_name, deterministic, profile),
                timeout=REPORT_STEP_TIMEOUT,
            )
        except Exception as exc:
            print(f"[CHECK] report failed: {exc!r}")

    # 4) AI-отчёт (how_to_use / expectations) — вторичное текстовое представление
    #    УЖЕ ГОТОВОГО User Analysis. Получает score/verdict/factors/safe/caution и
    #    НЕ имеет права переопределять совместимость.
    sections = {"how_to_use": None, "expectations": None}
    if DEEPSEEK_API_KEY and (deterministic.get("positive_factors") or deterministic.get("negative_factors")):
        try:
            sections = await asyncio.wait_for(
                generate_ai_report_sections(product_name, deterministic, profile),
                timeout=SECTIONS_STEP_TIMEOUT,
            )
        except Exception as exc:
            print(f"[CHECK] report sections failed: {exc!r}")

    # Ключевой ингредиент: сначала детерминированный fallback, затем ИИ определяет
    # реальный актив (Retinol, Niacinamide и т.п.), не путая его с базой (glycerin).
    active_ingredients = build_active_ingredient(deterministic)
    if DEEPSEEK_API_KEY:
        try:
            ai_key = await asyncio.wait_for(
                identify_key_ingredient_with_ai(product_name, ingredients),
                timeout=KEY_INGREDIENT_STEP_TIMEOUT,
            )
            if ai_key and ai_key.get("name"):
                active_ingredients = {
                    "name": ai_key["name"],
                    "position": ai_key.get("position") or 1,
                    "concentration": (active_ingredients or {}).get("concentration", "в составе"),
                }
        except Exception as exc:
            print(f"[CHECK] key ingredient AI failed: {exc!r}")

    # Итоговое резюме — нейтральный детерминированный fallback (build_summary).
    # Пользовательское объяснение причин — это поле report (AI).
    summary = deterministic.get('summary') or 'Не удалось получить рекомендацию.'

    return {
        'score': int(deterministic.get('score') or 0),
        'verdict': deterministic.get('verdict') or 'Требует внимания',
        'summary': summary,
        'report': report or summary,
        'safe_ingredients': deterministic.get('safe_ingredients') or [],
        'caution_ingredients': deterministic.get('caution_ingredients') or [],
        'active_ingredients': active_ingredients,
        'how_to_use': sections.get('how_to_use'),
        'expectations': sections.get('expectations'),
        'ingredient_claims': ingredient_claims or [],
        'research_status': research_status,
    }


async def generate_full_report(
    product_name: str,
    ingredients: str,
    profile: dict,
    skin_type: str = "Нормальная",
) -> dict:
    """Генерирует ВСЕ блоки отчёта по готовому результату scoring engine.

    Возвращает {report, active_ingredients, how_to_use, expectations}.
    Процент/verdict НЕ пересчитываются — LLM только объясняет готовый результат
    и определяет ключевой ингредиент.
    """
    from .decision_engine import DecisionEngine

    engine = DecisionEngine()
    deterministic = engine.analyze(product_name, ingredients, profile, skin_type)
    has_factors = bool(deterministic.get("positive_factors") or deterministic.get("negative_factors"))

    report = None
    if DEEPSEEK_API_KEY and has_factors:
        report = await generate_ai_report(product_name, deterministic, profile)

    sections = {"how_to_use": None, "expectations": None}
    if DEEPSEEK_API_KEY and has_factors:
        sections = await generate_ai_report_sections(product_name, deterministic, profile)

    active_ingredients = build_active_ingredient(deterministic)
    if DEEPSEEK_API_KEY:
        try:
            ai_key = await identify_key_ingredient_with_ai(product_name, ingredients)
            if ai_key and ai_key.get("name"):
                active_ingredients = {
                    "name": ai_key["name"],
                    "position": ai_key.get("position") or 1,
                    "concentration": (active_ingredients or {}).get("concentration", "в составе"),
                }
        except Exception as exc:
            print(f"[REPORT] key ingredient AI failed: {exc!r}")

    return {
        "report": report,
        "active_ingredients": active_ingredients,
        "how_to_use": sections.get("how_to_use"),
        "expectations": sections.get("expectations"),
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
    AI получает исходные structured factors (ingredient + axis + direction) и
    объясняет их человеческим языком, НЕ выводя технические идентификаторы.
    """
    from .ai_summary import summarize_with_ai

    analysis = analysis or {}
    score = int(analysis.get("score") or 0)
    # Передаём исходные structured factors (с axis/direction), а НЕ ingredient-only списки.
    summary = await summarize_with_ai(product_name, score, analysis, profile or {})
    return summary or (analysis.get("summary") or "")

async def _enrich_knowledge_with_ai(product_name: str, ingredients: str) -> list | None:
    """AI-обогащение ТОЛЬКО базы знаний ингредиентов (ingredient_claims).

    НЕ генерирует how_to_use / expectations / active_ingredients и НЕ оценивает
    совместимость продукта с профилем — это делает исключительно deterministic
    scoring engine. Возвращает список claims для enrich_ingredient_knowledge.
    """
    prompt = f"""
Ты — косметолог-технолог. Пополни базу знаний ингредиентов Aidermy.

### Продукт:
- {product_name}
- Состав (по убыванию концентрации): {ingredients}

### Задача:
Перечисли 3–6 ингредиентов с их атомарным свойством (axis-эффектом) для базы знаний.

### ВАЖНО:
- Указывай ТОЛЬКО atomic effects, соответствующие осям: hydration, barrier_support, sensitivity, acne_control, brightening.
- НЕ оценивай, подходит ли продукт какому-либо типу кожи. НЕ пиши вердикт и процент совместимости.
- Верни ТОЛЬКО JSON.

### Формат:
{{
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
                if isinstance(result, dict) and result.get("ingredient_claims"):
                    return result["ingredient_claims"]
            except Exception:
                continue

        except Exception:
            continue

    return None


# Растворители/носители, которые не считаются «ключевым ингредиентом» отчёта.
_SOLVENT_INGREDIENTS = {"water", "aqua", "eau"}


def build_active_ingredient(analysis: dict) -> dict | None:
    """Ключевой ингредиент — тот, который РЕАЛЬНО повлиял на персональный scoring.

    Первый ингредиент INCI (чаще всего вода/aqua) НЕ считается «главным».
    Выбирается фактор с наибольшим вкладом в результат (|strength·confidence·position_weight|),
    исключая растворители. Концентрация НЕ утверждается как точная — даётся лишь
    условная группа по позиции INCI (конвенция «раньше в списке = выше»).
    """
    ingredients = analysis.get("normalized_ingredients") or []
    if not ingredients:
        return None

    def _is_solvent(name: str) -> bool:
        return name.strip().lower() in _SOLVENT_INGREDIENTS

    # 1) Ингредиент, который существенно повлиял на scoring (по модулю вклада).
    scored: list = []
    for f in list(analysis.get("negative_factors") or []) + list(analysis.get("positive_factors") or []):
        if not isinstance(f, dict):
            continue
        name = str(f.get("ingredient") or "").strip()
        if not name or _is_solvent(name):
            continue
        impact = abs(
            float(f.get("strength") or 0)
            * float(f.get("confidence") or 0)
            * float(f.get("position_weight") or 0)
        )
        scored.append((name, impact))
    if scored:
        scored.sort(key=lambda x: -x[1])
        name = scored[0][0]
    else:
        # 2) Fallback: первый значимый ингредиент состава (не растворитель).
        name = next((ing for ing in ingredients if not _is_solvent(ing)), None)
        if not name:
            return None

    # INCI-позиция выбранного ингредиента.
    total = len(ingredients)
    position = 0
    for idx, ing in enumerate(ingredients, start=1):
        if str(ing).strip().lower() == str(name).strip().lower():
            position = idx
            break

    # Условная группа концентрации по позиции INCI (НЕ точное значение).
    if total and position:
        if position <= max(1, total // 3):
            group = "высокая"
        elif position <= max(1, (total * 2) // 3):
            group = "средняя"
        else:
            group = "низкая"
    else:
        group = "в составе"

    return {
        "name": str(name),
        "position": position or 1,
        "concentration": group,
    }


async def identify_key_ingredient_with_ai(product_name: str, ingredients: str | list) -> dict | None:
    """AI определяет КЛЮЧЕВОЙ (активный) ингредиент продукта.

    Детерминированный build_active_ingredient опирается на вклад в scoring и может
    выбрать «базовый» ингредиент (glycerin) вместо реального актива (Retinol).
    LLM смотрит на название продукта + состав и называет актив. Возвращает
    {name, position} или None. НЕ пересчитывает score/verdict.
    """
    if not DEEPSEEK_API_KEY:
        return None

    if isinstance(ingredients, str):
        ing_list = [i.strip() for i in re.split(r'[,;\n]+', ingredients) if i.strip()]
    else:
        ing_list = [str(i).strip() for i in ingredients if str(i).strip()]
    if not ing_list:
        return None
    ing_text = ", ".join(ing_list)

    prompt = (
        "Ты — косметолог-технолог. Определи КЛЮЧЕВОЙ (активный) ингредиент косметического продукта.\n\n"
        f"Продукт: {product_name}\n"
        f"Состав (INCI, по убыванию концентрации): {ing_text}\n\n"
        "Ключевой — это активный компонент, определяющий назначение средства "
        "(Retinol, Retinal, Niacinamide, Salicylic Acid, Glycolic Acid, Vitamin C, "
        "Peptide, Ceramide, Panthenol, Azelaic Acid, Bakuchiol и т.п.), а НЕ база/носитель "
        "(Water/Aqua, Glycerin, Butylene Glycol, Propanediol, Hexanediol, Dipropylene Glycol и т.п.).\n"
        "Верни ТОЛЬКО JSON:\n"
        '{"name": "каноническое INCI-название", "position": номер_позиции_в_списке}\n'
        'Если очевидного актива нет — {"name": null, "position": null}.\n'
    )

    for model_name in DEEPSEEK_MODEL_FALLBACKS:
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
                        "temperature": 0.2,
                        "max_tokens": 200,
                    },
                    timeout=30,
                )
            if response.status_code != 200:
                continue
            data = response.json()
            content = (data["choices"][0]["message"]["content"] or "").strip()
            if not content:
                continue
            try:
                parsed = extract_json_from_response(content)
                if isinstance(parsed, dict) and parsed.get("name"):
                    name = str(parsed["name"]).strip()
                    position_raw = str(parsed.get("position") or "")
                    position = int(position_raw) if position_raw.isdigit() else 1
                    return {"name": name, "position": position}
            except Exception:
                continue
        except Exception:
            continue

    return None


def _factor_text(factor: dict) -> str:
    ing = str(factor.get("ingredient") or "").strip()
    prop = str(factor.get("property") or "").strip()
    return f"{ing} → {prop}" if ing and prop else (ing or prop or "")


def build_report_sections_prompt(product_name: str, analysis: dict, profile: dict) -> str:
    """Собирает prompt для how_to_use/expectations ИЗ структурированного анализа.

    AI получает уже готовый результат (score, verdict, factors, safe/caution, hard flags)
    и НЕ имеет права переопределять совместимость или вердикт.
    """
    score = int(analysis.get("score") or 0)
    verdict = analysis.get("verdict") or ""
    summary = analysis.get("summary") or ""
    pos = "; ".join(_factor_text(f) for f in (analysis.get("positive_factors") or [])[:6]) or "—"
    neg = "; ".join(_factor_text(f) for f in (analysis.get("negative_factors") or [])[:6]) or "—"
    safe = ", ".join(analysis.get("safe_ingredients") or []) or "—"
    caution = ", ".join(analysis.get("caution_ingredients") or []) or "—"
    hard = json.dumps(analysis.get("hard_flags") or analysis.get("hard_filters") or [], ensure_ascii=False) or "нет"
    skin = str((profile or {}).get("skin_type") or (profile or {}).get("skin_type_determined") or "")

    return (
        "Ты — помощник, который оформляет УЖЕ ГОТОВЫЙ результат анализа косметики в текст. "
        "НЕ выполняй анализ сам и НЕ переоценивай совместимость.\n\n"
        "### Результат анализа (источник истины — НЕ меняй):\n"
        f"- Совместимость (зафиксирована алгоритмом): {score}%\n"
        f"- Вердикт: {verdict}\n"
        f"- Резюме: {summary}\n"
        f"- Положительные факторы (ингредиент → эффект): {pos}\n"
        f"- Отрицательные факторы: {neg}\n"
        f"- Подходят профилю: {safe}\n"
        f"- Требуют внимания: {caution}\n"
        f"- Жёсткие ограничения: {hard}\n"
        f"- Тип кожи: {skin or 'не указан'}\n\n"
        "### Задачи (верни ТОЛЬКО JSON):\n"
        "1. how_to_use: {{application, time, note}} — нейтральное описание применения, "
        "следующее из состава. НЕ используй слова «подходит/не подходит/рекомендуется/противопоказан». "
        "Если данных недостаточно — верни null.\n"
        "2. expectations: {{when, normal, danger}} — "
        "normal описывай ТОЛЬКО эффекты из положительных факторов; "
        "danger описывай ТОЛЬКО из отрицательных факторов/«требуют внимания». "
        "НЕ придумывай эффектов, которых нет в списках. Если факторов нет — null.\n"
        "3. Теги: <good>, <warning>, <bad> только для разметки.\n\n"
        "### ВАЖНО: не пересчитывай процент, не меняй вердикт, не делай выводов о "
        "совместимости, которых нет в структурированном анализе.\n\n"
        "### Формат:\n"
        "{{\n"
        "  \"how_to_use\": {{\"application\": \"...\", \"time\": \"...\", \"note\": \"...\"}} | null,\n"
        "  \"expectations\": {{\"when\": \"...\", \"normal\": \"...\", \"danger\": \"...\"}} | null\n"
        "}}\n"
    )


def sanitize_report_sections(verdict: str, sections: dict) -> dict:
    """Защита от «скрытого второго вердикта».

    Если детерминированный вердикт отрицательный («Не рекомендуется»), а AI написал
    в секциях позитивное утверждение о совместимости («подходит»), нейтрализуем
    соответствующее поле. Возвращает очищенный dict.
    """
    if not isinstance(sections, dict):
        return {}
    cleaned = dict(sections)
    if "не рекоменд" not in str(verdict or "").lower():
        return cleaned

    positive_claim = re.compile(r"(?<!не\s)подходит", re.IGNORECASE)

    for key in list(cleaned.keys()):
        value = cleaned.get(key)
        if isinstance(value, str) and positive_claim.search(value):
            cleaned[key] = None
        elif isinstance(value, dict):
            for sub in list(value.keys()):
                sub_value = value.get(sub)
                if isinstance(sub_value, str) and positive_claim.search(sub_value):
                    value[sub] = None

    return cleaned


async def generate_ai_report_sections(product_name: str, analysis: dict, profile: dict) -> dict:
    """Генерирует how_to_use/expectations из СТРУКТУРИРОВАННОГО анализа.

    Вторичное текстовое представление User Analysis, а НЕ второй анализ.
    Возвращает {"how_to_use": ... | None, "expectations": ... | None}.
    При недоступности AI или отсутствии structured evidence возвращает None-поля.
    """
    pos = analysis.get("positive_factors") or []
    neg = analysis.get("negative_factors") or []
    if not pos and not neg:
        return {"how_to_use": None, "expectations": None}

    prompt = build_report_sections_prompt(product_name, analysis, profile)

    for model_name in DEEPSEEK_MODEL_FALLBACKS:
        try:
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
                        "max_tokens": 800,
                    },
                    timeout=30,
                )
            if response.status_code != 200:
                continue
            data = response.json()
            content = (data["choices"][0]["message"]["content"] or "").strip()
            if not content:
                continue
            parsed = extract_json_from_response(content)
            if not isinstance(parsed, dict):
                continue
            parsed = sanitize_report_sections(analysis.get("verdict") or "", parsed)
            return {
                "how_to_use": parsed.get("how_to_use"),
                "expectations": parsed.get("expectations"),
            }
        except Exception as exc:
            print(f"[REPORT SECTIONS] AI failed: {exc!r}")
            continue

    return {"how_to_use": None, "expectations": None}


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