# shelf_service.py
# Логика «Моей полки» как персонального шкафа с секциями (кабинетами).
# Использует существующий deterministic scoring engine (AnalysisService)
# и существующую БД продуктов (products.db). Итоговые проценты не придумываются
# LLM, а рассчитываются существующим движком.

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .database import get_connection, PRODUCTS_DB
from .ingredient_normalizer import canonicalize_ingredient_name
from .services import capitalize_name

# ---------------------------------------------------------------------------
# СТРУКТУРА ШКАФОВ
# ---------------------------------------------------------------------------

# compatibility=True означает, что для шкафа применим существующий
# skin-scoring движок (лицо/волосы/тело). Для макияжа и парфюмерии он
# концептуально неприменим — процент не показывается.
CABINETS: List[Dict[str, Any]] = [
    {
        "key": "face",
        "title": "Лицо",
        "compatibility": True,
        "categories": ["Очищение", "Тонизация", "Сыворотки", "Увлажнение", "SPF", "Маски"],
    },
    {
        "key": "hair",
        "title": "Волосы",
        "compatibility": True,
        "categories": ["Шампуни", "Кондиционеры", "Маски", "Несмываемый уход", "Стайлинг"],
    },
    {
        "key": "body",
        "title": "Тело",
        "compatibility": True,
        "categories": ["Гели для душа", "Кремы / лосьоны", "Скрабы", "Дезодоранты"],
    },
    {
        "key": "makeup",
        "title": "Макияж",
        "compatibility": False,
        "categories": ["Тональные средства", "Консилеры", "Пудры", "Румяна", "Тушь", "Помады"],
    },
    {
        "key": "fragrance",
        "title": "Парфюмерия",
        "compatibility": False,
        "categories": ["Парфюм", "Парфюмерная вода", "Туалетная вода"],
    },
]

CABINET_BY_KEY = {c["key"]: c for c in CABINETS}

# Маппинг старых категорий полки/каталога на (cabinet, категория шкафа).
LEGACY_CATEGORY_MAP: Dict[str, Tuple[str, str]] = {
    "очищение": ("face", "Очищение"),
    "тонер": ("face", "Тонизация"),
    "тоник": ("face", "Тонизация"),
    "сыворотка": ("face", "Сыворотки"),
    "крем": ("face", "Увлажнение"),
    "spf": ("face", "SPF"),
    "защита": ("face", "SPF"),
    "маска": ("face", "Маски"),
}
# Ключевые слова для определения шкафа по названию продукта.
_INFER_RULES: List[Tuple[str, List[str]]] = [
    ("hair", ["шампунь", "shampoo", "кондиционер", "conditioner", "бальзам для волос", "hair balm", "стайлинг", "styling", "мусс", "mousse", "лак для волос", "hairspray", "несмываем", "leave-in", "масло для волос", "hair oil", "hair serum", "маска для волос", "hair mask"]),
    ("body", ["гель для душа", "shower gel", "body wash", "дезодорант", "deodorant", "антиперспирант", "antiperspirant", "скраб для тела", "body scrub", "крем для тела", "body cream", "body lotion", "лосьон", "молочко для тела", "крем для рук", "hand cream", "бальзам для тела", "body balm", "мыло", "soap"]),
    ("makeup", ["тональн", "foundation", "консилер", "concealer", "пудр", "powder", "румян", "blush", "тушь", "mascara", "помад", "lipstick", "блеск для губ", "lip gloss", "бальзам для губ", "lip balm", "карандаш для губ", "lipliner", "хайлайтер", "highlighter", "тени", "eyeshadow", "подводка", "eyeliner", "бров", "brow", "лак для ногтей", "nail polish", "bb крем", "cc крем"]),
    ("fragrance", ["парфюм", "parfum", "туалетная вода", "eau de toilette", "парфюмерная вода", "eau de parfum", "одеколон", "духи", "cologne", "perfume"]),
]

# Правила подбора продуктов для категории шкафа.
RECOMMEND_RULES: Dict[str, Dict[str, Dict[str, List[str]]]] = {
    "face": {
        "Очищение": {"categories": ["Очищение"], "keywords": ["очищ", "cleans", "cleanser", "micellar", "мицелл", "пенк", "foam", "гель для умывания"]},
        "Тонизация": {"categories": ["Тонер"], "keywords": ["тонер", "тоник", "toner", "tonic"]},
        "Сыворотки": {"categories": ["Сыворотка"], "keywords": ["сыворотк", "serum"]},
        "Увлажнение": {"categories": ["Крем"], "keywords": ["увлажн", "moistur", "крем", "cream", "гидрат", "гиалурон", "hyaluronic"]},
        "SPF": {"categories": ["Защита"], "keywords": ["spf", "защит", "sunscreen", "солнц", "санскрин"]},
        "Маски": {"categories": ["Маска"], "keywords": ["маск", "mask"]},
    },
    "hair": {
        "Шампуни": {"categories": [], "keywords": ["шампун", "shampoo"]},
        "Кондиционеры": {"categories": [], "keywords": ["кондиционер", "conditioner"]},
        "Маски": {"categories": [], "keywords": ["маска для волос", "hair mask"]},
        "Несмываемый уход": {"categories": [], "keywords": ["несмываем", "leave-in", "сыворотка для волос", "масло для волос", "hair oil", "hair serum"]},
        "Стайлинг": {"categories": [], "keywords": ["стайлинг", "styling", "мусс", "mousse", "лак для волос", "hairspray", "гель для волос", "hair gel"]},
    },
    "body": {
        "Гели для душа": {"categories": [], "keywords": ["гель для душа", "shower gel", "body wash", "душ"]},
        "Кремы / лосьоны": {"categories": [], "keywords": ["крем для тела", "body cream", "body lotion", "лосьон", "молочко для тела", "body butter"]},
        "Скрабы": {"categories": [], "keywords": ["скраб", "scrub", "exfoliat", "пилинг"]},
        "Дезодоранты": {"categories": [], "keywords": ["дезодорант", "deodorant", "антиперспирант"]},
    },
    "makeup": {
        "Тональные средства": {"categories": [], "keywords": ["тональн", "foundation", "bb крем", "cc крем", "bb cream", "cc cream"]},
        "Консилеры": {"categories": [], "keywords": ["консилер", "concealer"]},
        "Пудры": {"categories": [], "keywords": ["пудр", "powder"]},
        "Румяна": {"categories": [], "keywords": ["румян", "blush"]},
        "Тушь": {"categories": [], "keywords": ["тушь", "mascara"]},
        "Помады": {"categories": [], "keywords": ["помад", "lipstick", "блеск для губ", "lip gloss", "бальзам для губ", "lip balm", "блеск", "gloss"]},
    },
    "fragrance": {
        "Парфюм": {"categories": [], "keywords": ["парфюм", "parfum", "духи"]},
        "Парфюмерная вода": {"categories": [], "keywords": ["парфюмерная вода", "eau de parfum"]},
        "Туалетная вода": {"categories": [], "keywords": ["туалетная вода", "eau de toilette"]},
    },
}


def _split_name(name: str) -> Tuple[str, str]:
    parts = [p.strip() for p in (name or "").split("\n") if p.strip()]
    if len(parts) >= 2:
        return capitalize_name(parts[0]), capitalize_name(" ".join(parts[1:]))
    if parts:
        return "", capitalize_name(parts[0])
    return "", capitalize_name((name or "").strip())


def _formula_signature(ingredients: str) -> str:
    """Сигнатура формулы по первым ингредиентам (для diversity в подборе).

    Два продукта с одинаковым набором ключевых первых ингредиентов считаются
    почти дубликатами — чтобы не показывать пользователю одинаковые варианты.
    """
    if not ingredients or not str(ingredients).strip():
        return ""
    try:
        from .ingredient_normalizer import canonicalize_ingredient_name
    except Exception:
        return ""
    parts = [canonicalize_ingredient_name(p) for p in re.split(r"[,;\n]+", str(ingredients))]
    keys = [p for p in parts if p and p not in {"water", "aqua"}][:5]
    return "|".join(keys)


def cabinet_applies_scoring(cabinet: str) -> bool:
    return bool((CABINET_BY_KEY.get(cabinet) or {}).get("compatibility"))


def canonical_category(cabinet: str, category: str) -> str:
    """Приводит категорию к канонической для шкафа (иначе «Другое»)."""
    cabinet_def = CABINET_BY_KEY.get(cabinet) or {}
    allowed = cabinet_def.get("categories", [])
    candidate = (category or "").strip()

    # Старая категория каталога/полки → новая категория шкафа
    if candidate.lower() in LEGACY_CATEGORY_MAP:
        legacy_cab, legacy_cat = LEGACY_CATEGORY_MAP[candidate.lower()]
        if legacy_cab == cabinet:
            return legacy_cat

    for c in allowed:
        if c.lower() == candidate.lower():
            return c
    for c in allowed:
        if candidate.lower() and (candidate.lower() in c.lower() or c.lower() in candidate.lower()):
            return c
    return "Другое"


CATALOG_CATEGORIES = ["Очищение", "Тонер", "Сыворотка", "Крем", "Маска", "Защита"]

_CATALOG_CATEGORY_KEYWORDS = [
    ("Очищение", ["очищ", "cleans", "cleanser", "micellar", "мицелл", "пенк", "foam", "гель для умывания"]),
    ("Тонер", ["тонер", "тоник", "toner", "tonic"]),
    ("Сыворотка", ["сыворотк", "serum", "эссенци", "essence", "ампул", "ampoule"]),
    ("Крем", ["крем", "cream", "увлажн", "moistur", "гидрат", "hydra", "лосьон", "lotion", "молочко", "эмульси", "emulsion", "крем для рук", "hand cream"]),
    ("Маска", ["маск", "mask"]),
    ("Защита", ["spf", "защит", "sunscreen", "солнц", "санскрин"]),
]


def normalize_imported_category(raw_category: Optional[str], name: str) -> str:
    """Приводит сырую категорию импорта к канонической категории каталога.

    Никогда не возвращает само название продукта как категорию: если категория
    с сайта пустая или неоднозначная — определяем по названию, иначе «Другое».
    """
    haystack = f"{raw_category or ''} {name or ''}".lower()
    for cat, keywords in _CATALOG_CATEGORY_KEYWORDS:
        if any(k in haystack for k in keywords):
            return cat
    return "Другое"


def infer_cabinet_category(category: str, name: str) -> Tuple[str, str]:
    """Определяет (cabinet, категория) для продукта без явного указания шкафа.

    Название продукта — самый надёжный сигнал о шкафе («Body Lotion» = тело,
    «Hair Mask» = волосы). Поэтому сначала смотрим на название и только потом —
    на сохранённую категорию каталога (которая при импорте бывает ошибочной).
    """
    name_lower = (name or "").lower()
    cat_key = (category or "").strip().lower()

    # 1. Название определяет шкаф (hair/body/makeup/fragrance) надёжнее категории.
    for cabinet, keywords in _INFER_RULES:
        if any(k in name_lower for k in keywords):
            cat = _infer_category_within_cabinet(name, cabinet) or canonical_category(cabinet, category or "Другое")
            return cabinet, cat

    # 2. Категория каталога (legacy map) — только для лица.
    if cat_key in LEGACY_CATEGORY_MAP:
        return LEGACY_CATEGORY_MAP[cat_key]

    return "face", canonical_category("face", category or "Другое")


def resolve_shelf_cabinet(category: str, cabinet: str, name: str) -> Tuple[str, str]:
    """Возвращает (cabinet, каноническая категория) для записи полки."""
    cab = (cabinet or "").strip().lower()
    if cab in CABINET_BY_KEY:
        return cab, canonical_category(cab, category)
    return infer_cabinet_category(category, name)


def _category_keywords(cabinet: str, category: str) -> List[str]:
    rule = (RECOMMEND_RULES.get(cabinet) or {}).get(category) or {}
    return rule.get("keywords") or []


def _infer_category_within_cabinet(name: str, cabinet: str) -> Optional[str]:
    """Определяет категорию внутри шкафа по ключевым словам в НАЗВАНИИ продукта.

    Тип продукта (пудра, шампунь, тушь и т.д.) указывается в названии, поэтому
    состав (ingredients) здесь НЕ учитываем — иначе «powder» в составе бальзама
    для губ ложно отнесёт его к «Пудрам».
    """
    haystack = (name or "").lower()
    for cat, rule in (RECOMMEND_RULES.get(cabinet) or {}).items():
        for kw in rule.get("keywords") or []:
            if kw in haystack:
                return cat
    return None


def is_product_compatible(product: Dict[str, Any], cabinet: str, category: str) -> Tuple[bool, str]:
    """Проверяет, можно ли добавить продукт в выбранный шкаф/категорию.

    Не блокирует продукт глобально — только неподходящую связь User→Shelf.
    Возвращает (ok, reason).
    """
    name = (product.get("name") or "").replace("\n", " ").strip()
    prod_category = product.get("category") or ""
    natural_cabinet, natural_category = infer_cabinet_category(prod_category, name)

    if natural_cabinet != cabinet:
        target_title = CABINET_BY_KEY.get(cabinet, {}).get("title", cabinet)
        natural_title = CABINET_BY_KEY.get(natural_cabinet, {}).get("title", natural_cabinet)
        return False, f"Этот продукт относится к шкафу «{natural_title}», а не «{target_title}»."

    # Внутри шкафа «Лицо» сверяем категорию по маппингу старой категории каталога
    if cabinet == "face" and category and category != "Другое":
        mapped = canonical_category("face", prod_category)
        if mapped != "Другое" and mapped != category:
            return False, f"Этот продукт относится к категории «{mapped}», а не «{category}»."

    # Для остальных шкафов сверяем категорию по ключевым словам названия
    if cabinet != "face" and category and category != "Другое":
        target_kws = _category_keywords(cabinet, category)
        if target_kws and not any(k in name.lower() for k in target_kws):
            natural_cat = _infer_category_within_cabinet(name, cabinet)
            if natural_cat and natural_cat != category:
                return False, f"Этот продукт относится к категории «{natural_cat}», а не «{category}»."
            return False, f"Этот продукт не соответствует категории «{category}»."

    return True, ""
# ---------------------------------------------------------------------------
# СКОРИНГ
# ---------------------------------------------------------------------------

def _deterministic_analysis(profile: Dict[str, Any], ingredients: str) -> Optional[Dict[str, Any]]:
    if not ingredients or not str(ingredients).strip():
        return None
    try:
        from .decision_engine import DecisionEngine
        return DecisionEngine().analyze(
            "",
            ingredients,
            profile,
            (profile or {}).get("skin_type") or "",
        )
    except Exception:
        return None


def _meaningful_score(analysis: Optional[Dict[str, Any]]) -> Optional[int]:
    """Реальный скор только при ненулевой уверенности движка (есть знание об ингредиентах).
    Не возвращает нейтральный floor (например 40) для полностью неизвестных составов."""
    if not analysis:
        return None
    if float(analysis.get("confidence") or 0) <= 0:
        return None
    return int(analysis.get("score") or 0)


def _as_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    if isinstance(value, str):
        import json
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except Exception:
            pass
        return [value] if value.strip() else []
    return [str(value)]


def _parse_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        import json
        try:
            return json.loads(value)
        except Exception:
            return None
    return None


def normalize_history_analysis(h: Dict[str, Any]) -> Dict[str, Any]:
    """Приводит запись истории проверки к единому виду (списки вместо JSON-строк)."""
    return {
        "verdict": h.get("verdict") or "",
        "summary": h.get("summary") or "",
        "score": int(h.get("score") or 0) if h.get("score") is not None else None,
        "safe_ingredients": _as_str_list(h.get("safe_ingredients")),
        "caution_ingredients": _as_str_list(h.get("caution_ingredients")),
        "active_ingredients": _parse_json(h.get("active_ingredients")),
        "how_to_use": _parse_json(h.get("how_to_use")),
        "expectations": _parse_json(h.get("expectations")),
    }


def enrich_ingredient_knowledge(claims: List[Dict[str, Any]]) -> int:
    """AI-обогащение базы знаний ингредиентов (постепенное наполнение).

    Использует существующий IngredientRepository и детерминированный движок.
    Возвращает количество добавленных claims.
    """
    if not claims:
        return 0
    try:
        from .ingredient_repository import IngredientRepository
        from .ingredient_normalizer import canonicalize_ingredient_name
    except Exception:
        return 0

    repo = IngredientRepository()
    repo.ensure_ingredient_tables()

    allowed_props = {"hydration", "barrier_support", "sensitivity", "acne_control", "brightening"}
    added = 0
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        name = str(claim.get("ingredient") or "").strip()
        if not name:
            continue
        canonical = canonicalize_ingredient_name(name)
        if not canonical:
            continue
        property_name = str(claim.get("property") or "").strip().lower()
        if property_name not in allowed_props:
            continue
        direction = str(claim.get("direction") or "positive").strip().lower()
        if direction not in {"positive", "negative", "neutral"}:
            continue
        try:
            strength = max(0.0, min(1.0, float(claim.get("strength") or 0.5)))
            confidence = max(0.0, min(1.0, float(claim.get("confidence") or 0.5)))
        except (TypeError, ValueError):
            strength, confidence = 0.5, 0.5

        ing_id = repo.upsert_ingredient(name, canonical, canonical)
        if ing_id:
            repo.add_claim(ing_id, property_name, direction, strength, confidence, evidence_level="ai")
            added += 1
    return added


def _current_skin_type(user: Dict[str, Any]) -> str:
    """Актуальный тип кожи пользователя (из user_profiles, затем users)."""
    try:
        from .database import get_user_profile
        profile = get_user_profile(user["id"])
        return (profile.get("skin_type") or "").strip().lower()
    except Exception:
        return (user.get("skin_type") or "").strip().lower()


def _find_history_score(user: Dict[str, Any], product: Dict[str, Any]) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    from .database import get_user_check_history
    cleaned_name = (product.get("name") or "").replace("\n", " ").strip().lower()
    slug = (product.get("slug") or "").strip()
    current_skin = _current_skin_type(user)
    for h in get_user_check_history(user["id"], limit=200):
        # Пропускаем устаревшие записи, сделанные под другой тип кожи —
        # чтобы не показывать «нормальной кожи», если сейчас «чувствительная».
        h_skin = (h.get("skin_type") or "").strip().lower()
        if current_skin and h_skin and h_skin != current_skin:
            continue
        h_slug = (h.get("slug") or "").strip()
        h_name = (h.get("product_name") or "").replace("\n", " ").strip().lower()
        if slug and h_slug and h_slug == slug:
            return int(h.get("score") or 0), normalize_history_analysis(h)
        if cleaned_name and h_name and (h_name == cleaned_name or h_name in cleaned_name or cleaned_name in h_name):
            return int(h.get("score") or 0), normalize_history_analysis(h)
    return None, None


def score_product(user: Dict[str, Any], product: Dict[str, Any]) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    """Скор продукта ТОЛЬКО из реальной проверки пользователя (история). Без fake-фолбэков."""
    return _find_history_score(user, product)


def _reason_from_analysis(analysis: Optional[Dict[str, Any]]) -> str:
    if not analysis:
        return ""
    # deterministic-анализ: positive/negative/hard factors
    if analysis.get("positive_factors") or analysis.get("negative_factors") or analysis.get("hard_flags"):
        parts: List[str] = []
        hard = analysis.get("hard_flags") or []
        pos = [f.get("ingredient") for f in analysis.get("positive_factors", []) if f.get("ingredient")]
        neg = [f.get("ingredient") for f in analysis.get("negative_factors", []) if f.get("ingredient")]
        if hard:
            parts.append("Содержит аллерген: " + str(hard[0].get("ingredient", "")))
        if pos:
            parts.append("Подходит: " + ", ".join(list(dict.fromkeys(pos))[:3]))
        if neg:
            parts.append("Требует внимания: " + ", ".join(list(dict.fromkeys(neg))[:2]))
        if not parts:
            parts.append("Состав не противоречит профилю.")
        return " • ".join(parts)
    # история проверки: используем summary AI
    summary = (analysis.get("summary") or "").strip()
    return summary[:200] if summary else ""


def _aggregate_scores(items: List[Dict[str, Any]]) -> Optional[int]:
    """Среднее по ВАЛИДНЫМ compatibility score.

    Продукты без валидного score (None) исключаются и НЕ считаются ни нулём,
    ни идеальными. Если валидных оценок нет — возвращает None.
    """
    scores = [it.get("score") for it in items if isinstance(it.get("score"), int)]
    if not scores:
        return None
    return int(round(sum(scores) / len(scores)))


def compute_cabinet_compatibility(user: Dict[str, Any], items: List[Dict[str, Any]]) -> Optional[int]:
    """Агрегированная оценка шкафа в совокупности.

    Использует существующие compatibility scores продуктов (см. score_product):
    это реальные оценки из проверок пользователя, а не независимый движок.
    Не подставляет случайное значение при отсутствии анализа.
    """
    return _aggregate_scores(items)
# ---------------------------------------------------------------------------
# ПОДБОР (рекомендации)
# ---------------------------------------------------------------------------

def _query_candidates(cabinet: str, category: str) -> List[Dict[str, Any]]:
    rule = (RECOMMEND_RULES.get(cabinet) or {}).get(category) or {}
    categories = rule.get("categories") or []
    keywords = rule.get("keywords") or []

    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()

    select = "SELECT id, name, slug, image_url, category, brand, ingredients FROM products WHERE 1=1"
    params: List[Any] = []
    if cabinet_applies_scoring(cabinet):
        select += " AND ingredients IS NOT NULL AND trim(ingredients) != ''"

    def fetch(where: str, p: List[Any], limit: int) -> List[Dict[str, Any]]:
        cursor.execute(select + where + f" ORDER BY id DESC LIMIT {limit}", p)
        return [dict(r) for r in cursor.fetchall()]

    rows: List[Dict[str, Any]] = []
    seen: set = set()

    # Тир 1 — точное совпадение категории каталога (надёжный сигнал).
    if categories:
        ph = ",".join(["?"] * len(categories))
        for r in fetch(f" AND category IN ({ph})", list(categories), 40):
            if r["slug"] and r["slug"] not in seen:
                seen.add(r["slug"])
                rows.append(r)

    # Тир 2 — совпадение по ключевым словам в названии/составе.
    if keywords:
        conds: List[str] = []
        kw_params: List[Any] = []
        for kw in keywords:
            conds.append("lower_ru(name) LIKE ? OR lower_ru(ingredients) LIKE ?")
            kw_params.append(f"%{kw.lower()}%")
            kw_params.append(f"%{kw.lower()}%")
        for r in fetch(f" AND ({' OR '.join(conds)})", kw_params, 40):
            if r["slug"] and r["slug"] not in seen:
                seen.add(r["slug"])
                rows.append(r)

    conn.close()
    return rows[:60]


# Синонимы категорий непереносимости (пользовательские формулировки -> INCI-термины).
# Значения — конкретные канонические имена ингредиентов. Совпадение идёт по токенам
# (каноническим именам), а НЕ по подстроке: иначе «acid» ловил бы «hyaluronic acid»
# или «stearic acid» и исключал бы почти всю косметику из подбора.
_ALLERGEN_SYNONYMS: Dict[str, List[str]] = {
    "отдушки": ["fragrance", "parfum", "perfume"],
    "спирт": ["alcohol", "alcohol denat", "ethanol", "denatured alcohol", "isopropyl alcohol"],
    "эфирные масла": ["essential oil", "citrus limon peel oil", "lavandula angustifolia oil", "eucalyptus globulus leaf oil", "melaleuca alternifolia leaf oil", "pinus sylvestris leaf oil"],
    "ретиноиды": ["retinol", "retinal", "retinaldehyde", "retinyl palmitate", "retinyl acetate", "retinyl retinoate", "hydroxypinacolone retinoate", "tretinoin", "adapalene", "tazarotene"],
    "кислоты": ["salicylic acid", "glycolic acid", "lactic acid", "mandelic acid", "malic acid", "tartaric acid", "azelaic acid", "ferulic acid", "gluconolactone", "lactobionic acid", "aha", "bha", "pha"],
}


def _allergy_conflict(ingredients: str, allergies: List[str]) -> bool:
    """Жёсткая проверка непереносимости: есть ли в составе запрещённый ингредиент.

    Непереносимость — жёсткое ограничение (не мягкий фактор скорa): продукт
    с конфликтом исключается из рекомендаций целиком. Совпадение идёт по
    каноническим именам ингредиентов (токенам), а не по подстроке.
    """
    if not allergies or not ingredients or not str(ingredients).strip():
        return False
    ing_lower = str(ingredients).lower()
    ing_tokens = {canonicalize_ingredient_name(p) for p in re.split(r"[,;\n]+", ing_lower)}
    ing_tokens.discard("")

    for a in allergies:
        key = str(a or "").strip().lower()
        key = key.replace("непереносимость", " ").replace("аллергия", " ").strip()
        if not key:
            continue
        canon = canonicalize_ingredient_name(key)
        if canon and canon in ing_tokens:
            return True
        for syn in _ALLERGEN_SYNONYMS.get(key, []):
            if canonicalize_ingredient_name(syn) in ing_tokens:
                return True
    return False


def _hard_filter_exclusion(profile: Dict[str, Any], ingredients: str) -> bool:
    """Жёсткие фильтры ДО скоринга: категории непереносимости + structured restrictions.

    Совмещает два механизма:
      1. _allergy_conflict — категории фронтенда («Отдушки», «Спирт»…) по синонимам;
      2. apply_hard_filters — конкретные жёсткие исключения/аллергии из Structured Profile.
    """
    if _allergy_conflict(ingredients, profile.get("allergies") or []):
        return True
    try:
        from .scoring_engine import apply_hard_filters
    except Exception:
        return False
    raw_items = [p.strip() for p in re.split(r"[,;\n]+", ingredients or "") if p.strip()]
    return bool(apply_hard_filters(profile, raw_items))


def recommend_products(
    user: Dict[str, Any],
    cabinet: str,
    category: str,
    exclude_slugs: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """Возвращает до 3 рекомендаций для конкретной полки шкафа."""
    exclude_slugs = set(exclude_slugs or set())
    # Продукты, которые пользователь явно отклонил (дизлайк), не предлагаем снова.
    try:
        from .database import get_user_disliked_slugs
        exclude_slugs |= get_user_disliked_slugs(user["id"])
    except Exception:
        pass
    scored = cabinet_applies_scoring(cabinet)

    try:
        from .database import get_user_profile
        _p = get_user_profile(user["id"])
        _skin = _p.get("skin_type") or user.get("skin_type") or ""
        _age = _p.get("age") or user.get("age") or ""
        _concerns = _p.get("concerns") or user.get("concerns") or ""
        _allergies = _p.get("allergies") or user.get("allergies") or ""
        _custom = _p.get("custom_text") or user.get("custom_text") or ""
    except Exception:
        _skin = user.get("skin_type") or ""
        _age = user.get("age") or ""
        _concerns = user.get("concerns") or ""
        _allergies = user.get("allergies") or ""
        _custom = user.get("custom_text") or ""

    profile = {
        "skin_type": _skin,
        "age": _age,
        "concerns": [c.strip() for c in (_concerns or "").split(",") if c.strip()],
        "allergies": [a.strip() for a in (_allergies or "").split(",") if a.strip()],
        "custom_text": _custom,
    }

    # Structured User Profile (если есть) дополняет raw-поля ограничениями
    # restrictions/intolerances/allergies и personal_weights.
    try:
        from .database import get_structured_profile
        structured = get_structured_profile(user["id"]) or {}
    except Exception:
        structured = {}
    profile["restrictions"] = structured.get("restrictions") or []
    profile["intolerances"] = structured.get("intolerances") or []
    structured_allergies = structured.get("allergies") or []
    for a in structured_allergies:
        if a not in profile["allergies"]:
            profile["allergies"].append(a)

    candidates = _query_candidates(cabinet, category)
    rule = (RECOMMEND_RULES.get(cabinet) or {}).get(category) or {}
    keywords = rule.get("keywords") or []

    rated: List[Dict[str, Any]] = []
    seen_ids: set = set()
    seen_names: set = set()
    for product in candidates:
        pid = product.get("id")
        slug = (product.get("slug") or "").strip()
        if not slug or slug in exclude_slugs:
            continue
        # Дедупликация по стабильному Product ID и по нормализованному имени.
        if pid is not None and pid in seen_ids:
            continue
        brand, title = _split_name(product.get("name") or "")
        norm_name = f"{brand}|{title}".strip().lower()
        if norm_name in seen_names:
            continue
        seen_ids.add(pid)
        seen_names.add(norm_name)

        # Пропускаем продукты, не соответствующие шкафу/категории
        compatible, _compat_reason = is_product_compatible(product, cabinet, category)
        if not compatible:
            continue

        # Жёсткие фильтры ДО скоринга: категории непереносимости + structured restrictions.
        if _hard_filter_exclusion(profile, product.get("ingredients") or ""):
            continue

        rec: Dict[str, Any] = {
            "id": pid,
            "slug": slug,
            "name": title or (product.get("name") or "").replace("\n", " "),
            "brand": brand or (product.get("brand") or ""),
            "image_url": product.get("image_url") or "",
            "score": None,
            "reason": "",
            "_signature": _formula_signature(product.get("ingredients") or ""),
        }
        if scored:
            # 1) уже рассчитанный скор из истории проверок пользователя
            history_score, history_analysis = _find_history_score(user, product)
            if history_score is not None:
                rec["score"] = history_score
                rec["reason"] = _reason_from_analysis(history_analysis)
            else:
                # 2) deterministic-движок, только если есть реальное знание об ингредиентах
                analysis = _deterministic_analysis(profile, product.get("ingredients") or "")
                meaningful = _meaningful_score(analysis)
                if meaningful is not None:
                    rec["score"] = meaningful
                    rec["reason"] = _reason_from_analysis(analysis)
                else:
                    rec["score"] = None
                    rec["reason"] = "Анализ ещё не выполнен"
        else:
            rec["reason"] = f"Подходит для категории «{category}»."
            haystack = f"{product.get('name') or ''} {product.get('ingredients') or ''}".lower()
            rec["_relevance"] = sum(1 for kw in keywords if kw in haystack)
        rated.append(rec)

    # Стабильная сортировка: при равных скорax сохраняется порядок
    # «сначала точная категория, затем ключевые слова».
    if scored:
        # Продукты с валидным score идут первыми, без скорa — в конец.
        rated.sort(key=lambda r: (r["score"] is None, -int(r["score"] or 0)))
    else:
        rated.sort(key=lambda r: -int(r.get("_relevance", 0)))

    # Топ-3 с учётом разнообразия: не выдаём несколько почти одинаковых формул.
    result: List[Dict[str, Any]] = []
    used_signatures: set = set()
    for r in rated:
        sig = r.get("_signature") or ""
        if sig and sig in used_signatures:
            continue
        if sig:
            used_signatures.add(sig)
        result.append(r)
        if len(result) >= 3:
            break

    for r in result:
        r.pop("_relevance", None)
        r.pop("_signature", None)
        r.pop("id", None)
    return result


# ---------------------------------------------------------------------------
# СБОРКА ОТВЕТА ПОЛКИ
# ---------------------------------------------------------------------------

def build_cabinet_payload(user: Dict[str, Any], shelf_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Группирует записи полки по шкафам и категориям, считает совместимость."""
    from .database import get_product_by_id

    enriched: List[Dict[str, Any]] = []
    for s in shelf_items:
        p = get_product_by_id(s["product_id"])
        if not p:
            continue
        cabinet, category = resolve_shelf_cabinet(s.get("category"), s.get("cabinet"), p.get("name") or "")
        score = None
        if cabinet_applies_scoring(cabinet):
            score, _ = score_product(user, p)
        enriched.append({
            "id": s["id"],
            "shelf_id": s["id"],
            "product_id": s["product_id"],
            "cabinet": cabinet,
            "category": category,
            "added_at": s.get("added_at") or "",
            "name": (p.get("name") or "").replace("\n", " "),
            "brand": p.get("brand") or "",
            "image_url": p.get("image_url") or "",
            "slug": p.get("slug") or "",
            "ingredients": p.get("ingredients") or "",
            "score": score,
        })

    cabinets: List[Dict[str, Any]] = []
    for cab in CABINETS:
        cab_items = [it for it in enriched if it["cabinet"] == cab["key"]]
        categories: List[Dict[str, Any]] = []
        for cat in cab["categories"]:
            cat_items = [it for it in cab_items if it["category"] == cat]
            categories.append({
                "key": cat,
                "title": cat,
                "items": cat_items,
                "compatibility": _aggregate_scores(cat_items) if cab["compatibility"] else None,
            })
        other_items = [it for it in cab_items if it["category"] == "Другое"]
        if other_items:
            categories.append({
                "key": "Другое",
                "title": "Другое",
                "items": other_items,
                "compatibility": _aggregate_scores(other_items) if cab["compatibility"] else None,
            })

        compatibility = compute_cabinet_compatibility(user, cab_items) if cab["compatibility"] else None
        cabinets.append({
            "key": cab["key"],
            "title": cab["title"],
            "has_scoring": bool(cab["compatibility"]),
            "compatibility": compatibility,
            "categories": categories,
        })

    return cabinets



