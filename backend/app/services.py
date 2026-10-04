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

# ---------------------------------------------------------------------------
# Category-aware «Как применять».
# Категория продукта — обязательный вход генератора отчёта: она определяет
# допустимый тип применения, а LLM лишь оформляет конкретную инструкцию внутри
# этого ограничения. Здесь — детерминированный fallback + guidance для LLM.
# ---------------------------------------------------------------------------
_CATEGORY_APPLICATION: dict = {
    # face
    "patches": {
        "title": "Патчи",
        "guidance": "Это патчи: их наклеивают на нужную область, а НЕ наносят ровным слоем.",
        "how_to_use": {
            "application": "Очистите и высушите кожу, аккуратно наклейте патч на нужную область.",
            "time": "Оставьте на рекомендованное на упаковке время, затем снимите.",
            "note": "Остатки средства распределите или удалите согласно типу патча.",
        },
    },
    "toning": {
        "title": "Тонизирование",
        "guidance": "Тоник/тонер используют ПОСЛЕ очищения; наносят руками или ватным диском; если продукт несмываемый — не смывают.",
        "how_to_use": {
            "application": "После очищения нанесите тоник на кожу руками или ватным диском.",
            "time": "Дайте впитаться.",
            "note": "Если продукт несмываемый — не смывайте.",
        },
    },
    "serums": {
        "title": "Сыворотки",
        "guidance": "Сыворотку наносят небольшим количеством на очищенную кожу, распределяют, затем используют следующий этап ухода.",
        "how_to_use": {
            "application": "Нанесите небольшое количество сыворотки на очищенную кожу и распределите.",
            "time": "Дайте впитаться.",
            "note": "Затем используйте следующий этап ухода.",
        },
    },
    "creams": {
        "title": "Кремы",
        "guidance": "Крем наносят подходящим количеством, распределяют по коже и используют на соответствующем этапе ухода.",
        "how_to_use": {
            "application": "Нанесите подходящее количество крема и распределите по коже.",
            "time": "Используйте на соответствующем этапе ухода.",
            "note": "",
        },
    },
    "masks": {
        "title": "Маски",
        "guidance": "Инструкция зависит от типа маски: тканевая (наложить полотно), смываемая (нанести, выдержать, смыть), ночная (не смывать), глиняная (нанести тонким слоем, смыть до высыхания), патч-маска (наклеить). Не давайте универсальную инструкцию.",
        "how_to_use": {
            "application": "Используйте маску согласно её типу (тканевая, смываемая, ночная, глиняная или патч-маска).",
            "time": "Выдержите рекомендованное время.",
            "note": "Смываемые маски смойте, несмываемые оставьте.",
        },
    },
    "cleansing": {
        "title": "Очищение и демакияж",
        "guidance": "Очищающее средство используют для очищения: наносят на кожу/влажную кожу в зависимости от типа, при необходимости вспенивают и обязательно смывают.",
        "how_to_use": {
            "application": "Нанесите средство на влажную кожу (или согласно типу средства).",
            "time": "При необходимости вспеньте, мягко помассируйте.",
            "note": "Тщательно смойте водой.",
        },
    },
    "lips": {
        "title": "Уход для губ",
        "guidance": "Средство для губ наносят на губы, а не на кожу лица.",
        "how_to_use": {
            "application": "Нанесите средство на губы.",
            "time": "Обновляйте по мере необходимости.",
            "note": "",
        },
    },
    "eyes": {
        "title": "Для кожи вокруг глаз",
        "guidance": "Средство для зоны вокруг глаз наносят на эту зону, а не на всё лицо.",
        "how_to_use": {
            "application": "Нанесите небольшое количество на зону вокруг глаз.",
            "time": "Аккуратно распределите похлопывающими движениями.",
            "note": "",
        },
    },
    "pads": {
        "title": "Пэды",
        "guidance": "Пэды — пропитанные диски: ими протирают кожу, а не наносят крем.",
        "how_to_use": {
            "application": "Протрите кожу пэдом.",
            "time": "Используйте после очищения.",
            "note": "Если пэд отшелушивающий — не трите повреждённую кожу.",
        },
    },
    "scrubs": {
        "title": "Скрабы и пилинги",
        "guidance": "Скраб/пилинг наносят на влажную кожу, массируют и обязательно смывают.",
        "how_to_use": {
            "application": "Нанесите на влажную кожу и мягко помассируйте.",
            "time": "Избегайте области вокруг глаз.",
            "note": "Тщательно смойте.",
        },
    },
    "moisturizing": {
        "title": "Увлажнение и питание",
        "guidance": "Увлажняющее/питательное средство наносят и распределяют по коже.",
        "how_to_use": {
            "application": "Нанесите средство и распределите по коже.",
            "time": "Дайте впитаться.",
            "note": "",
        },
    },
    "special": {
        "title": "Специальный уход",
        "guidance": "Концентрированное/точечное средство наносят точечно или локально.",
        "how_to_use": {
            "application": "Нанесите точечно или локально на проблемную зону.",
            "time": "Следуйте инструкции на упаковке.",
            "note": "",
        },
    },
    "antiage": {
        "title": "Антивозрастной уход",
        "guidance": "Антивозрастное средство наносят и распределяют по коже (крем/сыворотка).",
        "how_to_use": {
            "application": "Нанесите средство и распределите по коже.",
            "time": "Используйте на соответствующем этапе ухода.",
            "note": "",
        },
    },
    # hair
    "shampoos": {
        "title": "Шампуни",
        "guidance": "Шампунь наносят на влажные волосы и кожу головы, вспенивают и смывают.",
        "how_to_use": {
            "application": "Нанесите на влажные волосы и кожу головы, вспеньте.",
            "time": "Помассируйте.",
            "note": "Тщательно смойте.",
        },
    },
    "conditioners": {
        "title": "Бальзамы и кондиционеры",
        "guidance": "Бальзам/кондиционер наносят на длину волос, выдерживают и смывают.",
        "how_to_use": {
            "application": "Нанесите на длину волос, избегая корней.",
            "time": "Выдержите рекомендованное время.",
            "note": "Смойте.",
        },
    },
    "dry_shampoos": {
        "title": "Сухие шампуни",
        "guidance": "Сухой шампунь распыляют на корни, не смывают.",
        "how_to_use": {
            "application": "Распылите на корни волос.",
            "time": "Подождите и расчешите.",
            "note": "Не смывайте.",
        },
    },
    "hair_masks": {
        "title": "Маски для волос",
        "guidance": "Маску для волос наносят на влажные волосы, выдерживают и смывают.",
        "how_to_use": {
            "application": "Нанесите на влажные волосы.",
            "time": "Выдержите рекомендованное время.",
            "note": "Смойте.",
        },
    },
    "hair_scrubs": {
        "title": "Скрабы для кожи головы",
        "guidance": "Скраб наносят на кожу головы, массируют и смывают.",
        "how_to_use": {
            "application": "Нанесите на кожу головы и помассируйте.",
            "time": "Смойте.",
            "note": "",
        },
    },
    # body
    "shower": {
        "title": "Для душа и ванны",
        "guidance": "Средство для душа наносят на влажную кожу, вспенивают и смывают.",
        "how_to_use": {
            "application": "Нанесите на влажную кожу, вспеньте.",
            "time": "Помассируйте.",
            "note": "Смойте.",
        },
    },
    "hands": {
        "title": "Для рук",
        "guidance": "Средство для рук наносят на кожу рук.",
        "how_to_use": {
            "application": "Нанесите на кожу рук и распределите.",
            "time": "Дайте впитаться.",
            "note": "",
        },
    },
    "feet": {
        "title": "Для ног",
        "guidance": "Средство для ног наносят на кожу стоп.",
        "how_to_use": {
            "application": "Нанесите на кожу стоп и распределите.",
            "time": "Дайте впитаться.",
            "note": "",
        },
    },
    "body_creams": {
        "title": "Кремы для тела",
        "guidance": "Крем для тела наносят на кожу тела и распределяют.",
        "how_to_use": {
            "application": "Нанесите на кожу тела и распределите.",
            "time": "Дайте впитаться.",
            "note": "",
        },
    },
}


def _category_application_hint(product_type: str) -> dict:
    """Category-aware подсказка применения по canonical category (title)."""
    from .catalog_taxonomy import subcategory_key_for_title

    if not product_type:
        return {}
    hit = subcategory_key_for_title(product_type)
    if not hit:
        return {}
    _body_area, key = hit
    return _CATEGORY_APPLICATION.get(key, {})


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
    # Layer 2 — internal ingredient interactions (по ACTUAL normalized composition + KB).
    interactions = None
    try:
        from .product_model import get_internal_interactions
        interactions = get_internal_interactions({"ingredients": ingredients}) or None
    except Exception:
        interactions = None
    deterministic = engine.analyze(product_name, ingredients, profile, skin_type, interactions=interactions)

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
    # report здесь — plain string (для /api/check). generate_ai_report возвращает
    # список fragments [{text, sentiment}] — склеиваем в текст.
    if isinstance(report, list):
        report_text = " ".join(str(f.get("text") or "") for f in report if isinstance(f, dict)).strip()
    else:
        report_text = report

    return {
        'score': int(deterministic.get('score') or 0),
        'verdict': deterministic.get('verdict') or 'Требует внимания',
        'summary': summary,
        'report': report_text or summary,
        'safe_ingredients': deterministic.get('safe_ingredients') or [],
        'caution_ingredients': deterministic.get('caution_ingredients') or [],
        'active_ingredients': active_ingredients,
        'how_to_use': sections.get('how_to_use'),
        'expectations': sections.get('expectations'),
        'ingredient_claims': ingredient_claims or [],
        'research_status': research_status,
        # Полный deterministic-результат Score Engine — источник истины для Report.
        'deterministic': deterministic,
    }


async def generate_full_report(
    product_name: str,
    ingredients: str,
    profile: dict,
    skin_type: str = "Нормальная",
    product_type: str = "",
    saved_analysis: dict | None = None,
) -> dict:
    """Генерирует ВСЕ блоки отчёта по готовому результату scoring engine.

    Возвращает {report, active_ingredients, how_to_use, expectations}.
    Процент/verdict НЕ пересчитываются — LLM только объясняет готовый результат
    и определяет ключевой ингредиент. canonical_category (product_type) — только
    контекст текста отчёта.

    saved_analysis — уже рассчитанный User Analysis (score + factors). Если
    передан, используется ОН (единый источник истины), а не повторный
    deterministic-пересчёт (который мог бы дать другой процент из-за другого
    профиля и тем самым породить расхождение Match vs Report).
    """
    from .decision_engine import DecisionEngine

    engine = DecisionEngine()
    if saved_analysis and isinstance(saved_analysis.get("deterministic"), dict):
        deterministic = saved_analysis["deterministic"]
    elif saved_analysis:
        deterministic = saved_analysis
    else:
        deterministic = engine.analyze(product_name, ingredients, profile, skin_type)
    has_factors = bool(deterministic.get("positive_factors") or deterministic.get("negative_factors"))

    report = []
    if DEEPSEEK_API_KEY and has_factors:
        report = await generate_ai_report(product_name, deterministic, profile, product_type)

    sections = {"how_to_use": None, "expectations": None}
    if DEEPSEEK_API_KEY and has_factors:
        sections = await generate_ai_report_sections(product_name, deterministic, profile, product_type)

    active_ingredients = build_active_ingredient(deterministic)
    if DEEPSEEK_API_KEY:
        try:
            analysis_inci = deterministic.get("normalized_ingredients") or ingredients
            ai_key = await identify_key_ingredient_with_ai(product_name, analysis_inci)
            if ai_key and ai_key.get("name"):
                active_ingredients = {
                    "name": ai_key["name"],
                    "position": ai_key.get("position") or 1,
                    "concentration": (active_ingredients or {}).get("concentration", "в составе"),
                }
        except Exception as exc:
            print(f"[REPORT] key ingredient AI failed: {exc!r}")

    allowed = _report_allowed_ingredients(deterministic)
    has_neg = bool(deterministic.get("negative_factors"))
    good_bad = {"what_good": [], "what_bad": []}
    if DEEPSEEK_API_KEY and has_factors:
        try:
            good_bad = await generate_ai_good_bad(product_name, deterministic, profile, product_type)
            if not isinstance(good_bad, dict):
                good_bad = {"what_good": [], "what_bad": []}
            good_bad = {
                "what_good": _ground_fragments(good_bad.get("what_good"), allowed, has_neg, deterministic=deterministic),
                "what_bad": _ground_fragments(good_bad.get("what_bad"), allowed, has_neg, deterministic=deterministic),
            }
        except Exception as exc:
            print(f"[REPORT] good/bad AI failed: {exc!r}")
            good_bad = {"what_good": [], "what_bad": []}

    return {
        "review": report,
        "active_ingredients": active_ingredients,
        "what_good": good_bad.get("what_good") or [],
        "what_bad": good_bad.get("what_bad") or [],
        "how_to_use": sections.get("how_to_use"),
        "expectations": sections.get("expectations"),
        "inci": deterministic.get("normalized_ingredients") or [],
        "category": product_type or "",
        "score_breakdown": {
            "dimensions": deterministic.get("dimensions") or {},
            "priorities": deterministic.get("priorities") or {},
        },
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
            if isinstance(ai_summary, list):
                ai_summary = " ".join(str(f.get("text") or "") for f in ai_summary if isinstance(f, dict)).strip()
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




# --- Report grounding (Phase 18): actual INCI is the only source of truth for ingredients. ---
_RU_INGREDIENT_NAMES = {
    "ниацинамид": "niacinamid",
    "гиалуронов": "hyaluronic acid",
    "гиалуронат": "sodium hyaluronate",
    "алоэ": "aloe barbadensis",
    "гликолев": "glycolic acid",
    "пантенол": "panthenol",
    "салицилов": "salicylic acid",
    "молочн": "lactic acid",
    "лимонн": "citric acid",
    "винн": "tartaric acid",
    "гидроксид натрия": "sodium hydroxide",
    "глицерин": "glycerin",
    "ретинол": "retinol",
    "аскорбинов": "ascorbic acid",
    "витамин c": "ascorbic acid",
    "церамид": "ceramide",
    "керамид": "ceramide",
    "аллантоин": "allantoin",
    "бензоилпероксид": "benzoyl peroxide",
    "муцин": "snail secretion filtrate",
    "улитк": "snail secretion filtrate",
    "snail": "snail secretion filtrate",
    "муцином": "snail secretion filtrate",
    "экстракт улитки": "snail secretion filtrate",
    "бетаин": "betaine",
    "мочевина": "urea",
    "аргинин": "arginine",
    "аминокислот": "amino acids",
    "пептид": "peptide",
}

# Человекочитаемые формулировки эффектов → оси Score Engine. Отчёт вправе описывать
# ТОЛЬКО эти 6 осей — любые иные «свойства» (коллаген, регенерация, лифтинг и т.п.)
# не моделируются Score Engine и должны быть отброшены.
_AXIS_CLAIM_WORDS = {
    "hydration": ["увлажн", "увлажня", "hydrat", "moistur", "влагу", "влагоудерж", "увлажнени"],
    "barrier": ["барьер", "barrier", "защитн", "липидн", "восстановл", "целостн"],
    "irritation": ["раздража", "раздражи", "irritat", "успокаив", "sooth", "воспал", "противовоспалит", "покраснен", "красн"],
    "sensitization": ["сенсибилиз", "sensitiz", "чувствительн", "аллерг", "реактивн"],
    "sebum": ["себум", "жирн", "sebum", "матир", "комедоген", "comedo", "блеск", "пор"],
    "pigmentation": ["пигмент", "pigment", "осветл", "отбелив", "тон кожи", "brighten", "постакне", "пятн", "выравнивани", "ровн"],
}

# Эффекты, которые Score Engine НЕ моделирует. Если AI их упоминает — это галлюцинация.
_FORBIDDEN_EFFECT_WORDS = [
    "коллаген", "collagen", "эластин", "elastin", "регенерац", "regenerat",
    "лифтинг", "lifting", "firming", "антивозраст", "anti-age", "anti-ageing", "antiaging",
    "морщин", "wrinkle", "отшелуш", "эксфолиац", "exfoliat", "детокс", "detox",
    "омоложен", "rejuvenat", "подтягив", "tone up", "осветлени",
]

_CONTRADICTION_PHRASES = [
    "агрессивных активов нет",
    "активных компонентов нет",
    "раздражающих компонентов нет",
    "раздражающих факторов нет",
    "проблемных компонентов нет",
    "нет агрессивных",
    "нет раздражающих",
    "нет активных компонентов",
]

# Терапии/классы активов — нельзя упоминать без детерминированного evidence.
_THERAPY_EVIDENCE = {
    "ретиноид": ["retinoid", "retinol", "retinal", "tretinoin", "adapalene", "retinoate"],
    "изотретиноин": ["isotretinoin"],
}


def _deterministic_has_evidence(deterministic: dict, evidences: list) -> bool:
    import json as _json
    if not isinstance(deterministic, dict):
        return False
    blob = _json.dumps({
        "positive": deterministic.get("positive_factors") or [],
        "negative": deterministic.get("negative_factors") or [],
        "interactions": deterministic.get("interaction_breakdown") or [],
        "hard": deterministic.get("hard_flags") or [],
        "filters": deterministic.get("hard_filters") or [],
    }, ensure_ascii=False).lower()
    return any(str(e).lower() in blob for e in evidences)


def _report_allowed_ingredients(deterministic: dict):
    from .ingredient_normalizer import normalize_ingredient_name
    ing = deterministic.get("normalized_ingredients") or []
    allowed = set()
    for i in ing:
        key = normalize_ingredient_name(str(i))
        if key:
            allowed.add(key)
    return allowed


def _allowed_axes(deterministic: dict) -> set:
    """Оси, которые реально задействованы в deterministic factors."""
    axes = set()
    for f in (deterministic.get("positive_factors") or []) + (deterministic.get("negative_factors") or []):
        p = str(f.get("property") or "").strip().lower()
        if p:
            axes.add(p)
    return axes


def _mentioned_axes(text: str) -> set:
    low = text.lower()
    return {axis for axis, words in _AXIS_CLAIM_WORDS.items() if any(w in low for w in words)}


def _has_forbidden_effect(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in _FORBIDDEN_EFFECT_WORDS)


def _ground_report_text(text: str, allowed: set, has_negative_factors: bool, deterministic: dict | None = None):
    if not text:
        return None
    low = text.lower()
    if has_negative_factors:
        for phrase in _CONTRADICTION_PHRASES:
            if phrase in low:
                return None
    for ru, canon in _RU_INGREDIENT_NAMES.items():
        if ru in low and canon not in allowed:
            return None
    if deterministic is not None:
        for stem, evidences in _THERAPY_EVIDENCE.items():
            if stem in low and not _deterministic_has_evidence(deterministic, evidences):
                return None
        # Grounding эффектов: отчёт не должен описывать свойства, которые Score Engine
        # не моделирует, или оси, для которых нет ни одного deterministic factor.
        if _has_forbidden_effect(low):
            return None
        allowed_axes = _allowed_axes(deterministic)
        if allowed_axes:
            mentioned = _mentioned_axes(low)
            for ax in mentioned:
                if ax not in allowed_axes:
                    return None
    return text


def _ground_fragments(fragments, allowed: set, has_negative_factors: bool, deterministic: dict | None = None):
    """Граундинг списка fragments [{text, sentiment}]: каждый текст проверяется отдельно."""
    out = []
    for f in fragments or []:
        if not isinstance(f, dict):
            continue
        text = str(f.get("text") or "").strip()
        grounded = _ground_report_text(text, allowed, has_negative_factors, deterministic)
        if grounded is None:
            continue
        sentiment = str(f.get("sentiment") or "").strip().lower()
        if sentiment not in {"positive", "negative"}:
            sentiment = "positive"
        out.append({"text": grounded, "sentiment": sentiment})
    return out


def _ground_report_sections(sections: dict, allowed: set, has_negative_factors: bool, deterministic: dict | None = None) -> dict:
    if not isinstance(sections, dict):
        return {}

    def _field(value):
        if isinstance(value, str) and value.strip():
            return _ground_report_text(value, allowed, has_negative_factors, deterministic)
        return None

    result = dict(sections)
    for key in ("what_good",):
        if key in result:
            result[key] = _field(result.get(key))
    for key in ("how_to_use", "expectations"):
        block = result.get(key)
        if not isinstance(block, dict):
            continue
        cleaned = {}
        for f, v in block.items():
            if isinstance(v, str):
                gv = _field(v)
                if gv is not None:
                    cleaned[f] = gv
            else:
                cleaned[f] = v
        result[key] = cleaned or None
    return result


async def generate_ai_report(product_name: str, analysis: dict, profile: dict, product_type: str = "") -> list:
    """AI-отчёт: человеческое объяснение УЖЕ СУЩЕСТВУЮЩЕГО User Analysis (fragments).

    Score НЕ пересчитывается — берётся из переданного analysis (история проверок).
    AI получает исходные structured factors (ingredient + axis + direction) и
    объясняет их человеческим языком, НЕ выводя технические идентификаторы.
    canonical_category (product_type) передаётся только как контекст текста.
    """
    from .ai_summary import summarize_with_ai

    analysis = analysis or {}
    score = int(analysis.get("score") or 0)
    fragments = await summarize_with_ai(product_name, score, analysis, profile or {}, product_type)
    if fragments:
        allowed = _report_allowed_ingredients(analysis)
        has_neg = bool(analysis.get("negative_factors"))
        grounded = _ground_fragments(fragments, allowed, has_neg, deterministic=analysis)
        if grounded:
            return grounded
    summary = analysis.get("summary") or ""
    if summary:
        return [{"text": summary, "sentiment": "negative" if score < 60 else "positive"}]
    return []

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


def _ingredient_in_composition(name: str, ingredients: list) -> bool:
    """True, если каноническое имя ингредиента реально присутствует в составе.

    Защита от AI-галлюцинаций: ключевой ингредиент обязан быть в фактическом INCI.
    """
    from .ingredient_normalizer import canonicalize_ingredient_name

    canon_name = canonicalize_ingredient_name(name)
    if not canon_name:
        return False
    canon_set = {canonicalize_ingredient_name(i) for i in ingredients}
    canon_set.discard("")
    return any(canon_name in c or c in canon_name for c in canon_set if c)


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
                    # Защита от галлюцинации: ключевой ингредиент обязан быть в составе.
                    if not _ingredient_in_composition(name, ing_list):
                        continue
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


def _score_balance_text(analysis: dict) -> str:
    """Детерминированное объяснение БАЛАНСА score по осям (для AI-контекста).

    Считает вклад каждой оси в итоговый процент ПО ТОЙ ЖЕ формуле, что и
    scoring engine: contribution = tanh(raw / SATURATION_SCALE) * weight.
    Возвращает текст, из которого AI может объяснить, какие факторы дали
    положительный, а какие — отрицательный вклад, и почему итог такой.
    """
    import math
    from .scoring_config import SATURATION_SCALE
    from .decision_engine import DIMENSION_LABELS

    dims = analysis.get("dimensions") or {}
    prio = analysis.get("priorities") or {}
    axes = ("hydration", "barrier", "irritation", "sensitization", "sebum", "pigmentation")

    pos_lines: List[str] = []
    neg_lines: List[str] = []
    pos_total = 0.0
    neg_total = 0.0
    for axis in axes:
        raw = dims.get(axis)
        if raw is None:
            continue
        w = float(prio.get(axis, 0.0) or 0.0)
        contrib = math.tanh(float(raw) / SATURATION_SCALE) * w * 100.0
        label = DIMENSION_LABELS.get(axis, axis)
        ap = abs(contrib)
        sig = "значимо" if ap >= 5.0 else ("умеренно" if ap >= 2.0 else "слабо")
        if contrib > 0.001:
            pos_lines.append(f"  + {label}: +{contrib:.1f} п.п. [{sig}]")
            pos_total += contrib
        elif contrib < -0.001:
            neg_lines.append(f"  − {label}: {contrib:.1f} п.п. [{sig}]")
            neg_total += contrib

    total_w = sum(float(prio.get(a, 0.0) or 0.0) for a in axes) or 1.0
    net = (pos_total + neg_total) / total_w  # в процентах (нормировка по сумме весов)

    lines: List[str] = ["Вклад осей в итоговый score (положительный «+» / отрицательный «−»):"]
    lines.extend(pos_lines)
    lines.extend(neg_lines)
    lines.append(f"Положительный вклад: +{pos_total / total_w:.1f} п.п.")
    lines.append(f"Отрицательный вклад: {neg_total / total_w:.1f} п.п.")
    lines.append(f"Итог (сумма вкладов): {net:.1f}%")
    return "\n".join(lines)


def _breakdown_text(analysis: dict) -> str:
    """Текстовое deterministic-разложение score по осям (value + weight + вклад)."""
    dims = analysis.get("dimensions") or {}
    prio = analysis.get("priorities") or {}
    lines = []
    for axis in ("hydration", "barrier", "irritation", "sensitization", "sebum", "pigmentation"):
        val = dims.get(axis)
        if val is None:
            continue
        lines.append(f"  - {axis}: value={round(float(val), 3)}, weight={round(float(prio.get(axis) or 0), 4)}")
    return "\n".join(lines) if lines else "  (нет данных по осям)"


def _fragment_list(value) -> list:
    """Нормализует значение в список fragments [{text, sentiment}]."""
    if not value:
        return []
    if isinstance(value, list):
        out = []
        for f in value:
            if isinstance(f, dict):
                text = str(f.get("text") or "").strip()
                sentiment = str(f.get("sentiment") or "").strip().lower()
                if not text:
                    continue
                if sentiment not in {"positive", "negative"}:
                    sentiment = "positive"
                out.append({"text": text, "sentiment": sentiment})
            elif isinstance(f, str) and f.strip():
                out.append({"text": f.strip(), "sentiment": "positive"})
        return out
    if isinstance(value, str) and value.strip():
        return [{"text": value.strip(), "sentiment": "positive"}]
    return []


def build_report_sections_prompt(product_name: str, analysis: dict, profile: dict, product_type: str = "", category_hint: dict = None) -> str:
    """Собирает prompt для how_to_use/expectations ИЗ структурированного анализа.

    AI получает уже готовый результат (score, verdict, factors, safe/caution, hard flags)
    и НЕ имеет права переопределять совместимость или вердикт. Категория продукта
    передаётся явно и задаёт допустимый тип применения.
    """
    score = int(analysis.get("score") or 0)
    verdict = analysis.get("verdict") or ""
    summary = analysis.get("summary") or ""
    pos = "; ".join(_factor_text(f) for f in (analysis.get("positive_factors") or [])[:8]) or "—"
    neg = "; ".join(_factor_text(f) for f in (analysis.get("negative_factors") or [])[:8]) or "—"
    safe = ", ".join(analysis.get("safe_ingredients") or []) or "—"
    caution = ", ".join(analysis.get("caution_ingredients") or []) or "—"
    hard = json.dumps(analysis.get("hard_flags") or analysis.get("hard_filters") or [], ensure_ascii=False) or "нет"
    skin = str((profile or {}).get("skin_type") or (profile or {}).get("skin_type_determined") or "")
    inci = ", ".join(str(i) for i in (analysis.get("normalized_ingredients") or []))

    return (
        "Ты — помощник, который оформляет УЖЕ ГОТОВЫЙ результат анализа косметики в текст. "
        "НЕ выполняй анализ сам и НЕ переоценивай совместимость.\n\n"
        "### Результат анализа (источник истины — НЕ меняй):\n"
        f"- Совместимость (зафиксирована алгоритмом): {score}%\n"
        f"- Вердикт: {verdict}\n"
        f"- Резюме: {summary}\n"
        f"- Положительные факторы (ингредиент → эффект): {pos}\n"
        f"- Отрицательные факторы (ингредиент → эффект): {neg}\n"
        f"- Подходят профилю: {safe}\n"
        f"- Требуют внимания: {caution}\n"
        f"- Жёсткие ограничения: {hard}\n"
        f"- Разложение score по осям (значение + вес):\n{_breakdown_text(analysis)}\n"
        f"- Тип кожи: {skin or 'не указан'}\n"
        f"- Тип продукта (категория): {product_type or 'не указан'}\n"
        f"- Допустимый тип применения: {category_hint.get('guidance') if category_hint else 'определи по категории и типу продукта'}\n"
        f"- Полный состав (нормализованный INCI — единственный источник ингредиентов): {inci or '—'}\n\n"
        "### Правила (строго):\n"
        "- how_to_use и expectations должны соответствовать ТИПУ ПРОДУКТА (категории выше). "
        "НЕ описывай эссенцию/сыворотку как тонер, крем или очищающее средство, и наоборот.\n"
        "- Упоминай ТОЛЬКО ингредиенты из состава и ТОЛЬКО эффекты из факторов выше.\n"
        "- НЕ приписывай ингредиентам свойства, которых нет в факторах.\n"
        "- НЕ пересчитывай процент и НЕ меняй вердикт.\n\n"
        "### Задачи (верни ТОЛЬКО JSON):\n"
        "1. how_to_use: {{application, time, note}} — ОЧЕНЬ короткая практическая инструкция применения "
        "(максимум 1 предложение или 2 коротких пункта), строго по категории и допустимому типу применения. "
        "Без пустых фраз вроде «наносят подходящим количеством» или «используют на соответствующем этапе ухода». "
        "Если конкретных данных недостаточно — верни null.\n"
        "2. expectations: {{when, normal, danger}} — human-описание ожидаемого пользовательского эффекта "
        "продукта, соответствующее категории продукта. normal — 1-2 коротких предложения о том, какой результат разумно ожидать (НЕ список "
        "ingredient claims: не пиши «glycerin увлажняет; niacinamide влияет на пигментацию»). "
        "when и danger оставь null. Если полезного ожидания сформулировать нельзя — верни null.\n\n"
        "### ВАЖНО: не пересчитывай процент, не меняй вердикт, не делай выводов о "
        "совместимости, которых нет в структурированном анализе.\n\n"
        "### Формат:\n"
        "{{\n"
        "  \"how_to_use\": {{\"application\": \"...\", \"time\": \"...\", \"note\": \"...\"}} | null,\n"
        "  \"expectations\": {{\"when\": \"...\", \"normal\": \"...\", \"danger\": \"...\"}} | null\n"
        "}}\n"
    )


async def generate_ai_good_bad(product_name: str, analysis: dict, profile: dict, product_type: str = "") -> dict:
    """AI генерирует «Что хорошего в составе» и «Что плохого в составе».

    Только интерпретация готового deterministic analysis: использует фактические
    positive/negative factors, НЕ придумывает ингредиенты и НЕ пересчитывает score.
    Возвращает {"what_good": [fragments], "what_bad": [fragments]}.
    """
    if not DEEPSEEK_API_KEY:
        return {"what_good": [], "what_bad": []}

    pos = analysis.get("positive_factors") or []
    neg = analysis.get("negative_factors") or []
    if not pos and not neg:
        return {"what_good": [], "what_bad": []}

    skin = str((profile or {}).get("skin_type") or (profile or {}).get("skin_type_determined") or "")
    pos_text = "; ".join(_factor_text(f) for f in pos[:8]) or "—"
    neg_text = "; ".join(_factor_text(f) for f in neg[:8]) or "—"
    breakdown = _breakdown_text(analysis)
    inci = ", ".join(str(i) for i in (analysis.get("normalized_ingredients") or []))

    prompt = (
        "Ты — косметолог. Оформи уже готовый результат анализа косметики в короткие тексты. "
        "НЕ выполняй анализ сам и НЕ меняй совместимость.\n\n"
        f"Продукт: {product_name}\n"
        f"Тип продукта (категория): {product_type or 'не указан'}\n"
        f"Тип кожи: {skin or 'не указан'}\n"
        f"Разложение score по осям:\n{breakdown}\n"
        f"Положительные факторы (ингредиент → эффект): {pos_text}\n"
        f"Отрицательные факторы (ингредиент → эффект): {neg_text}\n"
        f"Полный состав (нормализованный INCI — единственный источник ингредиентов): {inci or '—'}\n\n"
        "### Правила (строго):\n"
        "- Упоминай ТОЛЬКО ингредиенты из состава и ТОЛЬКО эффекты из факторов выше.\n"
        "- НЕ приписывай ингредиентам свойства, которых нет в факторах.\n"
        "- НЕ пересчитывай процент.\n\n"
        "### Задачи (верни ТОЛЬКО JSON):\n"
        "1. what_good: 1-2 коротких предложения о главных преимуществах состава именно для этого профиля "
        "(ТОЛЬКО из положительных факторов). Каждое предложение — отдельный fragment с sentiment \"positive\". "
        "Если значимых плюсов нет — верни пустой список [].\n"
        "2. what_bad: 1-2 коротких предложения о существенных недостатках состава относительно профиля "
        "(ТОЛЬКО из отрицательных факторов). Каждое предложение — отдельный fragment с sentiment \"negative\". "
        "ЕСЛИ отрицательные факторы НЕ пустые (— не равно «—»), ты ОБЯЗАН вернуть хотя бы один negative fragment, "
        "объясняющий главный недостаток. Пустой список допустим ТОЛЬКО если отрицательных факторов действительно нет.\n"
        "НЕ смешивай positive и negative в одном fragment.\n"
        'Формат: {"what_good": [{"text": "...", "sentiment": "positive"}], "what_bad": [{"text": "...", "sentiment": "negative"}]}\n'
    )

    for model_name in DEEPSEEK_MODEL_FALLBACKS:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    DEEPSEEK_API_URL,
                    headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                    json={"model": model_name, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 500},
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
            return {
                "what_good": _fragment_list(parsed.get("what_good")),
                "what_bad": _fragment_list(parsed.get("what_bad")),
            }
        except Exception as exc:
            print(f"[GOOD/BAD] AI failed: {exc!r}")
            continue

    return {"what_good": [], "what_bad": []}


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


async def generate_ai_report_sections(product_name: str, analysis: dict, profile: dict, product_type: str = "") -> dict:
    """Генерирует how_to_use/expectations из СТРУКТУРИРОВАННОГО анализа.

    Вторичное текстовое представление User Analysis, а НЕ второй анализ.
    Возвращает {"how_to_use": ... | None, "expectations": ... | None}.
    Категория (product_type) задаёт допустимый тип применения; при недоступности AI
    или отсутствии structured evidence возвращается детерминированный category-aware
    how_to_use (fallback).
    """
    pos = analysis.get("positive_factors") or []
    neg = analysis.get("negative_factors") or []
    category_hint = _category_application_hint(product_type)

    if not pos and not neg:
        fallback = category_hint.get("how_to_use") if category_hint else None
        return {"how_to_use": fallback, "expectations": None}

    prompt = build_report_sections_prompt(product_name, analysis, profile, product_type, category_hint)

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
            parsed = _ground_report_sections(parsed, _report_allowed_ingredients(analysis), bool(analysis.get("negative_factors")), deterministic=analysis)
            how_to_use = parsed.get("how_to_use")
            if not how_to_use and category_hint:
                how_to_use = category_hint.get("how_to_use")
            return {
                "how_to_use": how_to_use,
                "expectations": parsed.get("expectations"),
            }
        except Exception as exc:
            print(f"[REPORT SECTIONS] AI failed: {exc!r}")
            continue

    fallback = category_hint.get("how_to_use") if category_hint else None
    return {"how_to_use": fallback, "expectations": None}


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