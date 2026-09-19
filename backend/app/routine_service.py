# routine_service.py
# Движок подбора ухода: определяет цель ухода, строит схему из шагов
# с процентными весами и подбирает продукты из каталога по составу.

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .database import get_connection, PRODUCTS_DB
from .services import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_API_URL,
    DEEPSEEK_MODEL_FALLBACKS,
    extract_json_from_response,
)

# ---------------------------------------------------------------------------
# ЦЕЛИ УХОДА (детекция по запросу пользователя)
# ---------------------------------------------------------------------------

GOALS: Dict[str, Dict[str, Any]] = {
    "hydration": {
        "title": "Интенсивное увлажнение",
        "default_name": "Увлажняющий уход",
        "description": "Схема с упором на восстановление и удержание влаги: увлажняющие тонер, сыворотка и крем в приоритете.",
        "keywords": [
            "увлажн", "гидрат", "обезвож", "сух", "влаг", "влагу",
            "hydrat", "moistur", "dry", "dehydrat",
        ],
        "steps": [
            {"step": "Очищение", "category": "Очищение", "weight": 15, "actives": ["glycerin", "hyaluronic", "ceramide", "panthenol", "allantoin", "betaine", "amino", "oat", "aloe"]},
            {"step": "Тонер", "category": "Тонер", "weight": 10, "actives": ["hyaluronic", "sodium hyaluronate", "glycerin", "panthenol", "beta-glucan", "ceramide", "aloe", "allantoin", "niacinamide"]},
            {"step": "Сыворотка", "category": "Сыворотка", "weight": 30, "actives": ["hyaluronic", "sodium hyaluronate", "glycerin", "panthenol", "ceramide", "squalane", "beta-glucan", "trehalose", "niacinamide", "polyglutamic"]},
            {"step": "Крем", "category": "Крем", "weight": 30, "actives": ["ceramide", "glycerin", "squalane", "shea butter", "panthenol", "hyaluronic", "urea", "cholesterol", "niacinamide", "allantoin"]},
            {"step": "SPF", "category": "Защита", "weight": 15, "actives": ["titanium dioxide", "zinc oxide", "octocrylene", "avobenzone", "glycerin", "hyaluronic"]},
        ],
    },
    "sun": {
        "title": "Защита от солнца",
        "default_name": "Солнцезащитный уход",
        "description": "Уход с максимальным акцентом на SPF-защиту и мягкое очищение, чтобы не повредить барьер кожи.",
        "keywords": [
            "солнц", "spf", "защит", "санскрин", "ультрафиолет", "uv", "загар",
            "sun", "sunscreen",
        ],
        "steps": [
            {"step": "Очищение", "category": "Очищение", "weight": 10, "actives": ["glycerin", "panthenol", "allantoin", "niacinamide", "ceramide"]},
            {"step": "Тонер", "category": "Тонер", "weight": 5, "actives": ["glycerin", "niacinamide", "panthenol", "hyaluronic"]},
            {"step": "Сыворотка", "category": "Сыворотка", "weight": 15, "actives": ["niacinamide", "vitamin c", "ascorbic", "hyaluronic", "glycerin", "ceramide"]},
            {"step": "Крем", "category": "Крем", "weight": 20, "actives": ["ceramide", "glycerin", "panthenol", "niacinamide", "allantoin"]},
            {"step": "SPF", "category": "Защита", "weight": 50, "actives": ["titanium dioxide", "zinc oxide", "octocrylene", "avobenzone", "homosalate", "octisalate", "octinoxate", "mexoryl", "tinosorb", "uvinul"]},
        ],
    },
    "acne": {
        "title": "Лечение акне",
        "default_name": "Уход против акне",
        "description": "Схема с упором на отшелушивание и контроль себума: салициловая кислота, ниацинамид и цинк в приоритете.",
        "keywords": [
            "акне", "прыщ", "угр", "черн", "комедон", "воспален", "жирн", "себо",
            "acne", "pimple", "breakout", "blemish",
        ],
        "steps": [
            {"step": "Очищение", "category": "Очищение", "weight": 25, "actives": ["salicylic acid", "bha", "tea tree", "zinc", "glycolic acid", "niacinamide", "aha", "azelaic acid"]},
            {"step": "Тонер", "category": "Тонер", "weight": 15, "actives": ["salicylic acid", "bha", "witch hazel", "niacinamide", "tea tree", "glycolic acid", "aha"]},
            {"step": "Сыворотка", "category": "Сыворотка", "weight": 30, "actives": ["salicylic acid", "niacinamide", "zinc", "azelaic acid", "retinol", "tea tree", "benzoyl peroxide", "glycolic acid", "succinic"]},
            {"step": "Крем", "category": "Крем", "weight": 15, "actives": ["niacinamide", "ceramide", "panthenol", "zinc", "tea tree", "salicylic acid"]},
            {"step": "SPF", "category": "Защита", "weight": 15, "actives": ["zinc oxide", "titanium dioxide", "niacinamide"]},
        ],
    },
    "antiage": {
        "title": "Антивозрастной уход",
        "default_name": "Антивозрастной уход",
        "description": "Схема с упором на ретинол, пептиды и витамин C для борьбы с морщинами и потерей упругости.",
        "keywords": [
            "возраст", "морщин", "стар", "антивозраст", "омолож", "лифтинг", "упруг", "коллаген",
            "anti-age", "antiage", "aging", "wrinkle", "retinol",
        ],
        "steps": [
            {"step": "Очищение", "category": "Очищение", "weight": 10, "actives": ["glycerin", "ceramide", "panthenol", "aha", "glycolic"]},
            {"step": "Тонер", "category": "Тонер", "weight": 10, "actives": ["aha", "glycolic", "niacinamide", "glycerin", "panthenol"]},
            {"step": "Сыворотка", "category": "Сыворотка", "weight": 35, "actives": ["retinol", "retinal", "retinyl", "bakuchiol", "peptide", "collagen", "vitamin c", "ascorbic", "niacinamide", "adenosine", "matrixyl", "q10"]},
            {"step": "Крем", "category": "Крем", "weight": 30, "actives": ["peptide", "collagen", "retinol", "ceramide", "adenosine", "niacinamide", "squalane", "shea butter", "q10"]},
            {"step": "SPF", "category": "Защита", "weight": 15, "actives": ["titanium dioxide", "zinc oxide"]},
        ],
    },
    "brightening": {
        "title": "Осветление и сияние",
        "default_name": "Осветляющий уход",
        "description": "Схема с упором на витамин C, ниацинамид и арбутин для ровного тона и борьбы с пигментацией.",
        "keywords": [
            "пигмент", "осветл", "сиян", "тускл", "пятн", "ровн", "веснушк",
            "bright", "brightening", "pigment", "dark spot",
        ],
        "steps": [
            {"step": "Очищение", "category": "Очищение", "weight": 15, "actives": ["vitamin c", "ascorbic", "niacinamide", "glycolic", "aha", "kojic"]},
            {"step": "Тонер", "category": "Тонер", "weight": 10, "actives": ["niacinamide", "glycolic", "vitamin c", "ascorbic", "tranexamic", "arbutin"]},
            {"step": "Сыворотка", "category": "Сыворотка", "weight": 35, "actives": ["vitamin c", "ascorbic", "niacinamide", "arbutin", "alpha arbutin", "kojic", "tranexamic", "licorice", "azelaic"]},
            {"step": "Крем", "category": "Крем", "weight": 25, "actives": ["niacinamide", "vitamin c", "arbutin", "ceramide", "glycerin", "tranexamic"]},
            {"step": "SPF", "category": "Защита", "weight": 15, "actives": ["titanium dioxide", "zinc oxide"]},
        ],
    },
    "soothing": {
        "title": "Успокаивающий уход",
        "default_name": "Успокаивающий уход",
        "description": "Схема для чувствительной и реактивной кожи: центелла, пантенол и церамиды для снятия покраснений.",
        "keywords": [
            "успока", "чувствитель", "покрасн", "купероз", "раздраж", "краснот",
            "sensitive", "soothe", "calm", "redness",
        ],
        "steps": [
            {"step": "Очищение", "category": "Очищение", "weight": 20, "actives": ["glycerin", "panthenol", "allantoin", "oat", "aloe", "ceramide"]},
            {"step": "Тонер", "category": "Тонер", "weight": 15, "actives": ["panthenol", "allantoin", "beta-glucan", "glycerin", "aloe", "oat", "centella"]},
            {"step": "Сыворотка", "category": "Сыворотка", "weight": 25, "actives": ["centella", "cica", "madecassoside", "panthenol", "beta-glucan", "allantoin", "azulene", "niacinamide"]},
            {"step": "Крем", "category": "Крем", "weight": 30, "actives": ["centella", "cica", "panthenol", "ceramide", "allantoin", "squalane", "shea butter", "oat"]},
            {"step": "SPF", "category": "Защита", "weight": 10, "actives": ["zinc oxide", "titanium dioxide"]},
        ],
    },
    "general": {
        "title": "Универсальный уход",
        "default_name": "Базовый уход",
        "description": "Сбалансированная схема на каждый день: очищение, тонизирование, сыворотка, крем и защита от солнца.",
        "keywords": [],
        "steps": [
            {"step": "Очищение", "category": "Очищение", "weight": 20, "actives": ["glycerin", "panthenol", "allantoin", "niacinamide", "ceramide"]},
            {"step": "Тонер", "category": "Тонер", "weight": 10, "actives": ["glycerin", "niacinamide", "panthenol", "hyaluronic", "allantoin"]},
            {"step": "Сыворотка", "category": "Сыворотка", "weight": 25, "actives": ["niacinamide", "hyaluronic", "glycerin", "panthenol", "ceramide"]},
            {"step": "Крем", "category": "Крем", "weight": 25, "actives": ["ceramide", "glycerin", "panthenol", "niacinamide", "squalane"]},
            {"step": "SPF", "category": "Защита", "weight": 20, "actives": ["titanium dioxide", "zinc oxide", "niacinamide"]},
        ],
    },
}

# Соответствие «проблем кожи» из профиля -> цель ухода
CONCERN_TO_GOAL: Dict[str, str] = {
    "акне": "acne",
    "пигментация": "brightening",
    "морщины": "antiage",
    "покраснения": "soothing",
    "расширенные поры": "acne",
    "тусклость": "brightening",
    "обезвоженность": "hydration",
    "купероз": "soothing",
}

# Аллергии из профиля -> INCI-ключевые слова для исключения
ALLERGY_KEYWORDS: Dict[str, List[str]] = {
    "отдушки": ["fragrance", "parfum", "limonene", "linalool", "citronellol", "geraniol", "citral", "eugenol"],
    "спирт": ["alcohol denat", "sd alcohol", "ethanol", "denatured alcohol"],
    "эфирные масла": ["essential oil", "lavandula", "citrus aurantium", "mentha", "eucalyptus", "melaleuca", "citrus limon", "citrus sinensis"],
    "ретиноиды": ["retinol", "retinal", "retinyl", "tretinoin", "adapalene", "retinoate"],
    "кислоты": ["salicylic acid", "glycolic acid", "lactic acid", "mandelic acid", "aha", "bha", "citric acid"],
}


def detect_goal(query: str, concerns: Optional[List[str]] = None) -> str:
    q = (query or "").lower()
    best_key: Optional[str] = None
    best_score = 0
    for key, goal in GOALS.items():
        score = sum(1 for kw in goal["keywords"] if kw in q)
        if score > best_score:
            best_score = score
            best_key = key
    if best_key and best_score > 0:
        return best_key
    for concern in concerns or []:
        goal_key = CONCERN_TO_GOAL.get(str(concern).strip().lower())
        if goal_key:
            return goal_key
    return "general"


def _allergy_keywords(allergies: List[str]) -> List[str]:
    keys: List[str] = []
    for allergy in allergies:
        label = str(allergy).strip().lower()
        keys.extend(ALLERGY_KEYWORDS.get(label, []))
    return keys


def _split_name(name: str) -> tuple:
    parts = [p.strip() for p in (name or "").split("\n") if p.strip()]
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    if parts:
        return "", parts[0]
    return "", (name or "").strip()


def _score_ingredients(ingredients: str, actives: List[str], allergy_keys: List[str]) -> tuple:
    ing = (ingredients or "").lower()
    matched = [a for a in actives if a in ing]
    allergy_hits = [a for a in allergy_keys if a in ing]
    score = len(matched) - 6 * len(allergy_hits)
    return score, matched, allergy_hits


def _fetch_pool(categories: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    if not categories:
        return {}
    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    placeholders = ",".join(["?"] * len(categories))
    cursor.execute(
        f"""
        SELECT id, name, slug, image_url, category, brand, ingredients
        FROM products
        WHERE category IN ({placeholders})
          AND ingredients IS NOT NULL
          AND trim(ingredients) != ''
        """,
        categories,
    )
    rows = cursor.fetchall()
    conn.close()
    pool: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        pool.setdefault(row["category"], []).append(dict(row))
    return pool


def build_routine(query: str, profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    profile = profile or {}
    concerns = [str(c).strip() for c in (profile.get("concerns") or []) if str(c).strip()]
    allergies = [str(a).strip() for a in (profile.get("allergies") or []) if str(a).strip()]
    skin_type = profile.get("skin_type") or profile.get("skin_type_determined") or ""

    goal_key = detect_goal(query, concerns)
    goal = GOALS[goal_key]

    categories = [s["category"] for s in goal["steps"]]
    pool = _fetch_pool(categories)
    allergy_keys = _allergy_keywords(allergies)

    steps: List[Dict[str, Any]] = []
    for step_def in goal["steps"]:
        candidates = pool.get(step_def["category"], [])
        scored = []
        for product in candidates:
            score, matched, allergy_hits = _score_ingredients(
                product.get("ingredients") or "", step_def["actives"], allergy_keys
            )
            scored.append((score, matched, allergy_hits, product))
        # Сортировка: выше совпадений, затем по убыванию id (свежие первыми)
        scored.sort(key=lambda item: (-item[0], -int(item[3].get("id") or 0)))

        products = []
        seen_slugs = set()
        for score, matched, allergy_hits, product in scored:
            slug = product.get("slug") or ""
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            brand, title = _split_name(product.get("name") or "")
            products.append({
                "name": title or (product.get("name") or "").replace("\n", " "),
                "brand": brand,
                "slug": slug,
                "image_url": product.get("image_url") or "",
                "score": max(0, score),
                "matched_actives": matched[:6],
                "allergy_hits": allergy_hits,
            })
            if len(products) >= 3:
                break

        steps.append({
            "step": step_def["step"],
            "category": step_def["category"],
            "weight": step_def["weight"],
            "products": products,
        })

    return {
        "name": goal["default_name"],
        "description": goal["description"],
        "goal": goal_key,
        "goal_title": goal["title"],
        "skin_type": skin_type,
        "steps": steps,
        "total_weight": sum(s["weight"] for s in goal["steps"]),
    }


async def _deepseek_complete(prompt: str) -> Optional[str]:
    if not DEEPSEEK_API_KEY:
        return None
    import httpx

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
                        "max_tokens": 1200,
                    },
                    timeout=30,
                )
            if response.status_code != 200:
                continue
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if content and str(content).strip():
                return content
        except Exception as exc:
            print(f"[ROUTINE] DeepSeek {model_name} failed: {exc}")
            continue
    return None


async def ai_refine_routine(query: str, routine: Dict[str, Any]) -> Dict[str, Any]:
    """Необязательная доработка результата с помощью ИИ (название, описание, веса)."""
    if not DEEPSEEK_API_KEY:
        return routine

    steps_desc = ", ".join(f"{s['step']} ({s['weight']}%)" for s in routine["steps"])
    prompt = (
        "Ты косметолог. Пользователь запросил подбор ухода. "
        f"Запрос: \"{query}\". Определённая цель: {routine['goal_title']}. "
        f"Схема шагов: {steps_desc}. "
        "Верни ТОЛЬКО JSON без пояснений в формате: "
        '{"name": "короткое название ухода", "description": "1-2 предложения описания", '
        '"weights": {"Очищение": 15, "Тонер": 10, "Сыворотка": 30, "Крем": 30, "SPF": 15}}. '
        "Сумма weights должна быть 100. Отвечай на русском."
    )
    try:
        content = await _deepseek_complete(prompt)
        if not content:
            return routine
        result = extract_json_from_response(content)
        if not isinstance(result, dict):
            return routine
        name = str(result.get("name") or "").strip()
        description = str(result.get("description") or "").strip()
        if name:
            routine["name"] = name
        if description:
            routine["description"] = description
        weights = result.get("weights") or {}
        if isinstance(weights, dict):
            for step in routine["steps"]:
                value = weights.get(step["step"])
                if isinstance(value, (int, float)):
                    step["weight"] = int(round(value))
    except Exception as exc:
        print(f"[ROUTINE] AI refine failed: {exc}")
    return routine
