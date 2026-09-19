# shelf_service.py
# Логика «Моей полки» как персонального шкафа с секциями (кабинетами).
# Использует существующий deterministic scoring engine (AnalysisService)
# и существующую БД продуктов (products.db). Итоговые проценты не придумываются
# LLM, а рассчитываются существующим движком.

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .database import get_connection, PRODUCTS_DB

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

# Приоритеты для deterministic-движка (совпадают с фолбэком в services.py)
DEFAULT_PRIORITIES: Dict[str, float] = {
    "hydration": 0.35,
    "barrier_support": 0.25,
    "sensitivity": 0.2,
    "acne_control": 0.1,
    "brightening": 0.1,
}

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
    ("hair", ["шампунь", "shampoo", "кондиционер", "conditioner", "бальзам", "стайлинг", "styling", "мусс", "mousse", "лак для волос", "hairspray", "несмываем", "leave-in", "масло для волос", "hair oil", "hair serum"]),
    ("body", ["гель для душа", "shower gel", "body wash", "дезодорант", "deodorant", "скраб для тела", "body scrub", "крем для тела", "body cream", "body lotion", "лосьон", "молочко для тела", "мыло", "soap"]),
    ("makeup", ["тональн", "foundation", "консилер", "concealer", "пудр", "powder", "румян", "blush", "тушь", "mascara", "помад", "lipstick", "блеск для губ", "lip gloss", "хайлайтер", "highlighter", "тени"]),
    ("fragrance", ["парфюм", "parfum", "туалетная вода", "eau de toilette", "парфюмерная вода", "eau de parfum", "одеколон", "духи", "cologne"]),
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
        "Помады": {"categories": [], "keywords": ["помад", "lipstick", "блеск для губ", "lip gloss"]},
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
        return parts[0], " ".join(parts[1:])
    if parts:
        return "", parts[0]
    return "", (name or "").strip()


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


def infer_cabinet_category(category: str, name: str) -> Tuple[str, str]:
    """Определяет (cabinet, категория) для продукта без явного указания шкафа."""
    cat_key = (category or "").strip().lower()
    if cat_key in LEGACY_CATEGORY_MAP:
        return LEGACY_CATEGORY_MAP[cat_key]

    haystack = f"{(name or '')} {(category or '')}".lower()
    for cabinet, keywords in _INFER_RULES:
        if any(k in haystack for k in keywords):
            return cabinet, canonical_category(cabinet, category or "Другое")

    return "face", canonical_category("face", category or "Другое")


def resolve_shelf_cabinet(category: str, cabinet: str, name: str) -> Tuple[str, str]:
    """Возвращает (cabinet, каноническая категория) для записи полки."""
    cab = (cabinet or "").strip().lower()
    if cab in CABINET_BY_KEY:
        return cab, canonical_category(cab, category)
    return infer_cabinet_category(category, name)
# ---------------------------------------------------------------------------
# СКОРИНГ
# ---------------------------------------------------------------------------

def _deterministic_analysis(profile: Dict[str, Any], ingredients: str) -> Optional[Dict[str, Any]]:
    if not ingredients or not str(ingredients).strip():
        return None
    try:
        from .analysis_service import AnalysisService
        return AnalysisService().analyze("", ingredients, profile, DEFAULT_PRIORITIES)
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


def normalize_history_analysis(h: Dict[str, Any]) -> Dict[str, Any]:
    """Приводит запись истории проверки к единому виду (списки вместо JSON-строк)."""
    return {
        "verdict": h.get("verdict") or "",
        "summary": h.get("summary") or "",
        "score": int(h.get("score") or 0) if h.get("score") is not None else None,
        "safe_ingredients": _as_str_list(h.get("safe_ingredients")),
        "caution_ingredients": _as_str_list(h.get("caution_ingredients")),
    }


def _find_history_score(user: Dict[str, Any], product: Dict[str, Any]) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    from .database import get_user_check_history
    cleaned_name = (product.get("name") or "").replace("\n", " ").strip().lower()
    slug = (product.get("slug") or "").strip()
    for h in get_user_check_history(user["id"], limit=200):
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
            parts.append("Осторожно: " + ", ".join(list(dict.fromkeys(neg))[:2]))
        if not parts:
            parts.append("Состав не противоречит профилю.")
        return " • ".join(parts)
    # история проверки: используем summary AI
    summary = (analysis.get("summary") or "").strip()
    return summary[:200] if summary else ""


def compute_cabinet_compatibility(user: Dict[str, Any], items: List[Dict[str, Any]]) -> Optional[int]:
    """Агрегированная совместимость шкафа = среднее реальных оценок проверенных продуктов."""
    scores = [it.get("score") for it in items if isinstance(it.get("score"), int)]
    if not scores:
        return None
    return int(round(sum(scores) / len(scores)))
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


def recommend_products(
    user: Dict[str, Any],
    cabinet: str,
    category: str,
    exclude_slugs: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """Возвращает до 3 рекомендаций для конкретной полки шкафа."""
    exclude_slugs = exclude_slugs or set()
    scored = cabinet_applies_scoring(cabinet)

    profile = {
        "skin_type": user.get("skin_type") or "",
        "age": user.get("age") or "",
        "concerns": [c.strip() for c in (user.get("concerns") or "").split(",") if c.strip()],
        "allergies": [a.strip() for a in (user.get("allergies") or "").split(",") if a.strip()],
        "custom_text": user.get("custom_text") or "",
    }

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

        rec: Dict[str, Any] = {
            "id": pid,
            "slug": slug,
            "name": title or (product.get("name") or "").replace("\n", " "),
            "brand": brand or (product.get("brand") or ""),
            "image_url": product.get("image_url") or "",
            "score": None,
            "reason": "",
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
        rated.sort(key=lambda r: -int(r["score"] or 0))
    else:
        rated.sort(key=lambda r: -int(r.get("_relevance", 0)))

    result = rated[:3]
    for r in result:
        r.pop("_relevance", None)
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
            categories.append({"key": cat, "title": cat, "items": cat_items})
        other_items = [it for it in cab_items if it["category"] == "Другое"]
        if other_items:
            categories.append({"key": "Другое", "title": "Другое", "items": other_items})

        compatibility = compute_cabinet_compatibility(user, cab_items) if cab["compatibility"] else None
        cabinets.append({
            "key": cab["key"],
            "title": cab["title"],
            "has_scoring": bool(cab["compatibility"]),
            "compatibility": compatibility,
            "categories": categories,
        })

    return cabinets



