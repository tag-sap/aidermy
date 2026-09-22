# product_dedup.py
# Детерминированная дедупликация товаров (БЕЗ AI/LLM).
#
# Пайплайн: Normalization -> Similarity -> Product Matching -> Canonical Merge.
# Один и тот же физический товар может попасть в БД из разных источников
# (каталог, URL, OCR, ручное добавление). Здесь он определяется обычным алгоритмом
# и сводится к одной canonical-записи C = объединение лучших данных A и B.
#
# Приоритет источников для выбора полей (без AI):
#   official/verified > structured > retailer/catalog > ocr/user
# Если у более приоритетного источника поле отсутствует — берём поле из
# менее приоритетного источника.

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 1. Normalization
# ---------------------------------------------------------------------------

_CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def transliterate(text: str) -> str:
    result: List[str] = []
    for char in (text or "").lower():
        result.append(_CYR_TO_LAT.get(char, char))
    return "".join(result)


# Служебные/родовые слова, которые не помогают отличить один продукт от другого.
_STOPWORDS = {
    # рус
    "крем", "сыворотка", "гель", "тоник", "тонер", "маска", "лосьон", "молочко",
    "эмульсия", "бальзам", "пенка", "скраб", "мист", "спрей", "флюид",
    "для", "уход", "ухода", "лица", "тела", "волос", "кожи", "спф", "защита",
    "увлажняющий", "увлажнение", "питательный", "очищающий", "выравнивающий",
    "восстанавливающий", "солнцезащитный", "солнцезащитное",
    # eng
    "cream", "serum", "gel", "toner", "lotion", "mask", "emulsion", "balm",
    "foam", "scrub", "mist", "spray", "fluid", "for", "care", "face", "body",
    "hair", "skin", "spf", "sunscreen", "sun", "moisturizing", "nourishing",
    "cleansing", "hydrating", "restoring", "correcting", "the", "and", "with",
    "de", "la", "le", "a", "an",
}

_VOLUME_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:мл|ml|гр|г|g|л|l|oz|fl\.?\s*oz|kg|кг)\b",
    re.IGNORECASE,
)


def normalize_volume(value: Any) -> Optional[str]:
    """Приводит объём к каноническому виду: '40ml', '50g' и т.п."""
    if value is None:
        return None
    text = transliterate(str(value)).strip().lower()
    match = _VOLUME_RE.search(text)
    if not match:
        return None
    number = re.search(r"\d+(?:[.,]\d+)?", match.group(0))
    unit_match = re.search(r"[a-zа-я]+", match.group(0))
    if not number:
        return None
    unit = unit_match.group(0) if unit_match else ""
    unit = unit.replace("мл", "ml").replace("гр", "g").replace("г", "g").replace("л", "l").replace("кг", "kg")
    return f"{number.group(0).replace(',', '.')}{unit}"


def normalize_name(value: Any) -> str:
    """Нормализованное имя для сравнения: lower, транслит, без пунктуации/объёма/стоп-слов."""
    if not value:
        return ""
    text = transliterate(str(value))
    text = text.replace("\n", " ").replace("\r", " ")
    text = _VOLUME_RE.sub(" ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [t for t in text.split() if t and t not in _STOPWORDS]
    return " ".join(tokens)


def name_tokens(value: Any) -> List[str]:
    return [t for t in normalize_name(value).split() if t]


def normalize_brand(value: Any) -> str:
    if not value:
        return ""
    text = transliterate(str(value))
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split()).strip()


def normalize_inci(value: Any) -> List[str]:
    """Нормализованные токены INCI для дополнительного сигнала совпадения."""
    if not value:
        return []
    from .ingredient_normalizer import normalize_ingredient_name

    tokens: List[str] = []
    for part in re.split(r"[,;\n]+", str(value)):
        norm = normalize_ingredient_name(part)
        if norm and norm not in {"water", "aqua"}:
            tokens.append(norm)
    return tokens


# ---------------------------------------------------------------------------
# 2. Similarity / Matching
# ---------------------------------------------------------------------------

def _similarity(a: List[str], b: List[str]) -> Tuple[float, float]:
    if not a or not b:
        return 0.0, 0.0
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    containment = inter / min(len(sa), len(sb))
    jaccard = inter / len(sa | sb)
    return containment, jaccard


def _row_signature(row: Dict[str, Any]) -> Tuple[List[str], str, Optional[str]]:
    return (
        name_tokens(row.get("name") or ""),
        normalize_brand(row.get("brand") or ""),
        normalize_volume(row.get("volume") or row.get("name") or ""),
    )


def _category_key(value: Any) -> str:
    return transliterate(str(value or "")).strip().lower()


def match_score(a: Dict[str, Any], b: Dict[str, Any]) -> Optional[float]:
    """Уверенность совпадения [0..1] или None, если это точно НЕ дубль.

    Консервативно: разные бренд/объём/тип (при наличии обоих значений) блокируют
    слияние. Совпадение определяется в основном по пересечению токенов названия.
    """
    a_tokens, a_brand, a_vol = _row_signature(a)
    b_tokens, b_brand, b_vol = _row_signature(b)
    if not a_tokens or not b_tokens:
        return None

    containment, jaccard = _similarity(a_tokens, b_tokens)

    if a_brand and b_brand and a_brand != b_brand:
        return None
    if a_vol and b_vol and a_vol != b_vol:
        return None

    a_cat = _category_key(a.get("category"))
    b_cat = _category_key(b.get("category"))
    if a_cat and b_cat and a_cat != b_cat:
        return None

    a_inci = normalize_inci(a.get("ingredients"))
    b_inci = normalize_inci(b.get("ingredients"))
    inci_boost = 0.0
    if a_inci and b_inci:
        _, inci_jac = _similarity(a_inci, b_inci)
        inci_boost = (inci_jac - 0.5) * 0.2

    if containment < 0.6 and jaccard < 0.5:
        return None

    score = 0.75 * containment + 0.25 * jaccard + inci_boost
    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# 3. Canonical merge (приоритеты источников, без AI)
# ---------------------------------------------------------------------------

_SOURCE_PRIORITY = {
    "official": 5,
    "verified": 5,
    "structured": 4,
    "retailer": 3,
    "catalog": 3,
    "manual": 2,
    "url": 2,
    "ocr": 1,
    "user": 1,
}


def source_priority(source_type: Any) -> int:
    return _SOURCE_PRIORITY.get(str(source_type or "").strip().lower(), 1)


_MERGE_FIELDS = [
    "name", "brand", "ingredients", "image_url", "url", "category",
    "volume", "description", "sku", "price", "currency", "incidecoder_url",
]


def _non_empty(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _field_priority(row: Dict[str, Any], field: str) -> int:
    return source_priority(row.get("source_type"))


def _extract_brand_from_name(name: Any) -> Optional[str]:
    if not name:
        return None
    parts = [p.strip() for p in str(name).split("\n") if p.strip()]
    return parts[0] if len(parts) >= 2 else None


def _pick_ingredients(a: Any, b: Any) -> Optional[str]:
    a_val = str(a or "").strip() if a else ""
    b_val = str(b or "").strip() if b else ""
    if not a_val:
        return b_val or None
    if not b_val:
        return a_val or None
    a_len = len(normalize_inci(a_val))
    b_len = len(normalize_inci(b_val))
    return a_val if a_len >= b_len else b_val


def build_canonical(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """C = объединение лучших данных A и B по приоритету источников."""
    merged: Dict[str, Any] = {}
    for field in _MERGE_FIELDS:
        a_val = a.get(field)
        b_val = b.get(field)
        if _non_empty(a_val) and (not _non_empty(b_val) or _field_priority(a, field) >= _field_priority(b, field)):
            merged[field] = a_val
        else:
            merged[field] = b_val

    if not _non_empty(merged.get("brand")):
        merged["brand"] = _extract_brand_from_name(merged.get("name")) or a.get("brand") or b.get("brand")

    merged["ingredients"] = _pick_ingredients(a.get("ingredients"), b.get("ingredients"))

    if not _non_empty(merged.get("volume")):
        merged["volume"] = normalize_volume(a.get("name")) or normalize_volume(b.get("name"))

    return merged


# ---------------------------------------------------------------------------
# 4. Поиск/создание canonical-записи (идемпотентно)
# ---------------------------------------------------------------------------

_MATCH_THRESHOLD = 0.62


def _slugify(name: str, salt: str = "") -> str:
    slug = re.sub(r"[^a-z0-9\s-]", "", transliterate(name))
    slug = re.sub(r"[-\s]+", "-", slug).strip("-").lower()
    if not slug:
        slug = "product"
    if salt:
        slug = f"{slug}-{abs(hash(salt)) % 100000}"
    return slug


def _columns(cursor) -> List[str]:
    return [d[0] for d in cursor.description]


def _infer_source_type(payload: Dict[str, Any]) -> str:
    if payload.get("source_url"):
        return "url"
    if payload.get("contributed_by"):
        return "user"
    if payload.get("source_type"):
        return str(payload.get("source_type"))
    return "manual"


def _resolve_canonical(cursor, row: Dict[str, Any]) -> Dict[str, Any]:
    cid = row.get("canonical_id")
    if cid:
        r = cursor.execute("SELECT * FROM products WHERE id = ?", (cid,)).fetchone()
        if r:
            return dict(zip(_columns(cursor), r))
    return row


def find_or_create_canonical_product(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Единая точка входа для всех источников (URL/каталог/OCR/ручное/импорт).

    Возвращает dict строки products (canonical) с полем `is_new` (True/False).
    Гарантирует идемпотентность: A + B -> C, повторное добавление A/B/C не создаст D.
    """
    from .database import get_connection, PRODUCTS_DB

    incoming = dict(payload or {})
    incoming["source_type"] = payload.get("source_type") or _infer_source_type(payload)

    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM products").fetchall()
    cols = _columns(cursor)
    candidates = [dict(zip(cols, row)) for row in rows]
    conn.close()

    best: Optional[Tuple[float, Dict[str, Any]]] = None
    for cand in candidates:
        score = match_score(cand, incoming)
        if score is None or score < _MATCH_THRESHOLD:
            continue
        if best is None or score > best[0]:
            best = (score, cand)

    conn = get_connection(PRODUCTS_DB)
    try:
        cursor = conn.cursor()

        if best is None:
            canonical = _insert_canonical(cursor, incoming)
            conn.commit()
            return {**canonical, "is_new": True}

        matched = best[1]
        canonical = _resolve_canonical(cursor, matched)
        merged_fields = build_canonical(canonical, incoming)
        # In-place merge: обновляем существующий canonical лучшими полями.
        # Новой записи не создаём — повторное добавление A/B/C всегда находит C.
        _update_canonical(cursor, canonical["id"], merged_fields)

        conn.commit()
        refreshed = cursor.execute("SELECT * FROM products WHERE id = ?", (canonical["id"],)).fetchone()
        cols = _columns(cursor)
        result = dict(zip(cols, refreshed)) if refreshed else canonical
        result["is_new"] = False
        result["was_merged"] = True
        return result
    finally:
        conn.close()


def _insert_canonical(cursor, payload: Dict[str, Any]) -> Dict[str, Any]:
    name = (payload.get("name") or "").strip()
    slug = payload.get("slug") or _slugify(name, payload.get("source_url"))
    if cursor.execute("SELECT 1 FROM products WHERE slug = ?", (slug,)).fetchone():
        slug = _slugify(name, payload.get("source_url") or name)
    cursor.execute(
        """INSERT INTO products (
            name, slug, brand, ingredients, url, incidecoder_url, image_url,
            category, volume, description, sku, price, currency,
            source_type, contributed_by, normalized_name, is_canonical, canonical_id, saved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, CURRENT_TIMESTAMP)""",
        (
            name, slug,
            payload.get("brand"), payload.get("ingredients"), payload.get("url"),
            payload.get("incidecoder_url"), payload.get("image_url"),
            payload.get("category"), payload.get("volume"), payload.get("description"),
            payload.get("sku"), payload.get("price"), payload.get("currency"),
            payload.get("source_type"), payload.get("contributed_by"), normalize_name(name),
        ),
    )
    new_id = cursor.lastrowid
    row = cursor.execute("SELECT * FROM products WHERE id = ?", (new_id,)).fetchone()
    return dict(zip(_columns(cursor), row))


def _update_canonical(cursor, canonical_id: int, fields: Dict[str, Any]) -> None:
    cursor.execute(
        """UPDATE products SET
            name = COALESCE(NULLIF(?, ''), name),
            brand = COALESCE(NULLIF(?, ''), brand),
            ingredients = COALESCE(NULLIF(?, ''), ingredients),
            url = COALESCE(NULLIF(?, ''), url),
            incidecoder_url = COALESCE(NULLIF(?, ''), incidecoder_url),
            image_url = COALESCE(NULLIF(?, ''), image_url),
            category = COALESCE(NULLIF(?, ''), category),
            volume = COALESCE(NULLIF(?, ''), volume),
            description = COALESCE(NULLIF(?, ''), description),
            sku = COALESCE(NULLIF(?, ''), sku),
            price = COALESCE(?, price),
            currency = COALESCE(NULLIF(?, ''), currency)
        WHERE id = ?""",
        (
            fields.get("name"), fields.get("brand"), fields.get("ingredients"),
            fields.get("url"), fields.get("incidecoder_url"), fields.get("image_url"),
            fields.get("category"), fields.get("volume"), fields.get("description"),
            fields.get("sku"), fields.get("price"), fields.get("currency"),
            canonical_id,
        ),
    )




