# catalog_taxonomy.py
# Система категорий и подкатегорий каталога Aidermy.
# Реальный источник истины для фильтрации: продукт резолвится в
# (категория, подкатегория) по названию + legacy-категории products.db,
# результат сохраняется в колонку subcategory и используется SQL-фильтром
# /api/catalog (точное совпадение). Поэтому «Serum» попадает в «Сыворотки»,
# а не теряется из-за расхождения названия и старого поля.

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

TAXONOMY: List[Dict[str, Any]] = [
    {
        "key": "face",
        "title": "Уход для лица",
        "categories": [
            {"key": "all", "title": "Все товары категории", "keywords": []},
            {"key": "eyes", "title": "Для кожи вокруг глаз", "keywords": [
                "eye cream", "eye serum", "eye gel", "eye contour", "вокруг глаз", "для глаз",
                "eye balm", "eye patch", "eye mask", "under eye",
            ]},
            {"key": "lips", "title": "Уход для губ", "keywords": [
                "lip balm", "lip mask", "lip scrub", "для губ", "бальзам для губ", "lip oil",
            ]},
            {"key": "cleansing", "title": "Очищение и демакияж", "keywords": [
                "cleanser", "cleansing", "очищени", "демакияж", "micellar", "мицеллярн",
                "пенка", "makeup remover", "снятие макияжа", "purifying", "face wash", "умывалк",
            ]},
            {"key": "toning", "title": "Тонизирование", "keywords": [
                "toner", "тоник", "тонер", "tonique", "toning", "essence", "тонер-мист",
            ]},
            {"key": "serums", "title": "Сыворотки", "keywords": [
                "serum", "сыворотк", "сыворот",
            ]},
            {"key": "masks", "title": "Маски", "keywords": [
                "mask", "маск", "masque", "маска",
            ]},
            {"key": "patches", "title": "Патчи", "keywords": [
                "patch", "патч", "hydrogel", "патчи",
            ]},
            {"key": "pads", "title": "Пэды", "keywords": [
                "pad", "пэд", "toner pad", "exfoliating pad",
            ]},
            {"key": "scrubs", "title": "Скрабы и пилинги", "keywords": [
                "scrub", "скраб", "peeling", "пилинг", "exfoliat", "эксфоли", "gommage",
            ]},
            {"key": "creams", "title": "Кремы", "keywords": [
                "cream", "крем", "creme", "crème", "night cream", "day cream",
            ]},
            {"key": "moisturizing", "title": "Увлажнение и питание", "keywords": [
                "moisturiz", "moisturis", "увлажн", "питани", "hydra", "hydrating",
                "emulsion", "эмульсия", "lotion", "лосьон", "гель-крем", "крем-гель",
            ]},
            {"key": "special", "title": "Специальный уход", "keywords": [
                "spot treatment", "точечно", "blemish", "акне", "acne", "ампул", "ampoule",
                "бустер", "booster", "концентрат",
            ]},
            {"key": "antiage", "title": "Антивозрастной уход", "keywords": [
                "anti-age", "антивозраст", "wrinkle", "морщин", "retinol", "ретинол",
                "firming", "лифтинг", "aging", "пептид", "peptide", "collagen", "коллаген",
            ]},
        ],
    },
    {
        "key": "body",
        "title": "Уход для тела",
        "categories": [
            {"key": "all", "title": "Все товары категории", "keywords": []},
            {"key": "basic", "title": "Основной уход", "keywords": [
                "body lotion", "body milk", "body cream", "body moistur", "для тела", "body butter",
            ]},
            {"key": "shower", "title": "Для душа и ванны", "keywords": [
                "shower gel", "shower", "bath", "ванн", "душ", "body wash", "гель для душа",
            ]},
            {"key": "hands", "title": "Для рук", "keywords": [
                "hand cream", "hand balm", "для рук", "hand lotion", "hand serum",
            ]},
            {"key": "feet", "title": "Для ног", "keywords": [
                "foot cream", "foot balm", "для ног", "foot scrub", "foot mask",
            ]},
            {"key": "body_creams", "title": "Кремы для тела", "keywords": [
                "body cream", "крем для тела", "body butter", "крем-масло для тела",
            ]},
            {"key": "body_scrubs", "title": "Скрабы и пилинги", "keywords": [
                "body scrub", "скраб для тела", "body exfoliat", "body peeling",
            ]},
            {"key": "corrective", "title": "Корректирующие средства", "keywords": [
                "firming", "корректир", "антицеллюлит", "anti-cellulite", "моделирующ",
            ]},
            {"key": "deodorants", "title": "Дезодоранты", "keywords": [
                "deodorant", "дезодорант", "antiperspirant", "антиперспирант",
            ]},
            {"key": "body_oils", "title": "Масла для тела", "keywords": [
                "body oil", "масло для тела", "dry oil", "сухое масло",
            ]},
            {"key": "depilation", "title": "Депиляция и эпиляция", "keywords": [
                "depilat", "эпиляц", "депиляц", "shaving", "брит", "wax", "воск",
            ]},
            {"key": "soap", "title": "Мыло", "keywords": [
                "soap", "мыло", "savon",
            ]},
            {"key": "sponges", "title": "Мочалки и губки", "keywords": [
                "sponge", "губк", "мочалк", "konjac", "конжак",
            ]},
            {"key": "massagers", "title": "Массажёры и щётки", "keywords": [
                "massager", "массажёр", "массажер", "brush", "щётк", "щетк", "gua sha",
            ]},
        ],
    },
    {
        "key": "hair",
        "title": "Волосы",
        "categories": [
            {"key": "all", "title": "Все товары категории", "keywords": []},
            {"key": "shampoos", "title": "Шампуни", "keywords": [
                "shampoo", "шампунь", "шампун", "scalp",
            ]},
            {"key": "conditioners", "title": "Бальзамы и кондиционеры", "keywords": [
                "conditioner", "кондиционер", "бальзам для волос", "hair balm", "бальзам",
            ]},
            {"key": "dry_shampoos", "title": "Сухие шампуни", "keywords": [
                "dry shampoo", "сухой шампунь",
            ]},
            {"key": "hair_masks", "title": "Маски", "keywords": [
                "hair mask", "маска для волос", "hair treatment",
            ]},
            {"key": "hair_scrubs", "title": "Скрабы", "keywords": [
                "scalp scrub", "скраб для кожи головы", "hair scrub",
            ]},
            {"key": "hair_oils", "title": "Масла", "keywords": [
                "hair oil", "масло для волос", "hair serum", "несмываем", "leave-in", "сыворотка для волос",
            ]},
        ],
    },
    {
        "key": "makeup",
        "title": "Макияж",
        "categories": [
            {"key": "all", "title": "Все товары категории", "keywords": []},
            {"key": "foundation", "title": "Тональные средства", "keywords": [
                "foundation", "тональн", "bb cream", "cc cream", "bb крем", "cc крем",
            ]},
            {"key": "concealers", "title": "Консилеры", "keywords": [
                "concealer", "консилер", "корректор", "corrector",
            ]},
            {"key": "powders", "title": "Пудры", "keywords": [
                "powder", "пудр", "setting powder",
            ]},
            {"key": "blush", "title": "Румяна", "keywords": [
                "blush", "румян", "rouge",
            ]},
            {"key": "mascara", "title": "Тушь", "keywords": [
                "mascara", "тушь", "туш", "lash",
            ]},
            {"key": "lipstick", "title": "Помады", "keywords": [
                "lipstick", "помад", "lip gloss", "блеск для губ", "lip tint", "тинт", "lip liner",
            ]},
            {"key": "eyes", "title": "Для глаз", "keywords": [
                "eyeshadow", "тени", "eyeliner", "подводка", "brow", "бров",
            ]},
        ],
    },
    {
        "key": "fragrance",
        "title": "Парфюмерия",
        "categories": [
            {"key": "all", "title": "Все товары категории", "keywords": []},
            {"key": "perfume", "title": "Парфюм", "keywords": [
                "parfum", "парфюм", "perfume", "духи",
            ]},
            {"key": "eau_de_parfum", "title": "Парфюмерная вода", "keywords": [
                "eau de parfum", "парфюмерная вода", "edp",
            ]},
            {"key": "eau_de_toilette", "title": "Туалетная вода", "keywords": [
                "eau de toilette", "туалетная вода", "edt", "одеколон", "cologne",
            ]},
        ],
    },
]

# ---------------------------------------------------------------------------
# Резолв продукта -> (категория, подкатегория).
# ---------------------------------------------------------------------------

# Шкаф по названию (проверяется ДО «лица», чтобы «hair serum» не попал в «Сыворотки»).
_CABINET_HINTS: List[Tuple[str, List[str]]] = [
    ("hair", ["шампунь", "shampoo", "кондиционер", "conditioner", "hair", "волос", "для волос",
              "бальзам для волос", "маска для волос", "стайлинг", "styling", "несмываем", "leave-in",
              "мусс", "mousse", "лак для волос", "hairspray", "scalp", "кожа головы"]),
    ("body", ["body", "для тела", "тело", "shower", "душ", "ванн", "bath", "hand cream", "для рук",
              "foot", "для ног", "дезодорант", "deodorant", "антиперспирант", "soap", "мыло",
              "body scrub", "скраб для тела", "body lotion", "body cream", "body oil", "масло для тела",
              "body wash", "гель для душа", "depilat", "эпиляц", "мочалк", "губк", "массажёр", "массажер"]),
    ("makeup", ["тональн", "foundation", "консилер", "concealer", "пудр", "powder", "румян", "blush",
                "тушь", "mascara", "помад", "lipstick", "блеск для губ", "lip gloss", "lip tint",
                "тинт", "подводка", "eyeliner", "тени", "eyeshadow", "бров", "brow", "bb крем", "cc крем",
                "bb cream", "cc cream", "корректор", "corrector", "лак для ногтей", "nail polish"]),
    ("fragrance", ["парфюм", "parfum", "perfume", "туалетная вода", "eau de toilette", "одеколон",
                   "cologne", "духи", "eau de parfum", "парфюмерная вода"]),
]

# legacy-категория products.db -> (категория, подкатегория) для лица.
_LEGACY_FACE_MAP: Dict[str, Tuple[str, str]] = {
    "очищение": ("Уход для лица", "Очищение и демакияж"),
    "тонер": ("Уход для лица", "Тонизирование"),
    "тоник": ("Уход для лица", "Тонизирование"),
    "сыворотка": ("Уход для лица", "Сыворотки"),
    "крем": ("Уход для лица", "Кремы"),
    "защита": ("Уход для лица", "Специальный уход"),
    "маска": ("Уход для лица", "Маски"),
}


def _has_any(name: str, kws: List[str]) -> bool:
    if not kws:
        return False
    n = name.lower()
    return any(k in n for k in kws)


def resolve_taxonomy(name: str, legacy_category: str = "") -> Tuple[str, str]:
    """Возвращает (категория, подкатегория) для продукта."""
    name = (name or "").replace("\n", " ").strip()
    legacy = (legacy_category or "").strip().lower()
    n = name.lower()

    # 1. Явный шкаф по названию (hair/body/makeup/fragrance).
    for cabinet, hints in _CABINET_HINTS:
        if _has_any(n, hints):
            return _resolve_within(cabinet, name)

    # 2. Название (богаче, чем legacy) — резолв внутри «лица».
    category, subcategory = _resolve_within("face", name)
    if subcategory != "Все товары категории":
        return category, subcategory

    # 3. Legacy-категория products.db как фолбэк.
    if legacy in _LEGACY_FACE_MAP:
        return _LEGACY_FACE_MAP[legacy]

    return ("Уход для лица", "Все товары категории")


def _resolve_within(cabinet: str, name: str) -> Tuple[str, str]:
    meta = next((c for c in TAXONOMY if c["key"] == cabinet), None)
    if not meta:
        return ("Уход для лица", "Все товары категории")
    n = name.lower()
    for cat in meta["categories"]:
        if cat["key"] == "all":
            continue
        if _has_any(n, cat["keywords"]):
            return (meta["title"], cat["title"])
    return (meta["title"], "Все товары категории")


def taxonomy_payload() -> List[Dict[str, Any]]:
    """Категории/подкатегории для /api/categories."""
    return [
        {
            "key": c["key"],
            "title": c["title"],
            "subcategories": [{"key": s["key"], "title": s["title"]} for s in c["categories"]],
        }
        for c in TAXONOMY
    ]


def resolve_taxonomy_for_product(product: Dict[str, Any]) -> Dict[str, Any]:
    """Резолвит продукт и возвращает его с полями category/subcategory."""
    name = product.get("name") or ""
    legacy = product.get("category") or ""
    category, subcategory = resolve_taxonomy(name, legacy)
    return {**product, "category": category, "subcategory": subcategory}

