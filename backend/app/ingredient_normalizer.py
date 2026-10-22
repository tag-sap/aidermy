import re
from typing import Iterable, List


def split_inci_tokens(raw_text: str) -> List[str]:
    """Split an INCI string on separators outside round brackets.

    Cosmetic INCI often contains a parenthetical synonym with commas, e.g.
    ``Aqua (Water, Eau), Glycerin``.  Splitting on every comma turns that into
    two fake ingredients (``Aqua (Water`` and ``Eau)``).  This parser keeps the
    parenthetical group intact while preserving the original ingredient order.

    Unbalanced opening brackets fall back to the legacy delimiter split: this
    is deterministic and avoids swallowing the rest of a damaged INCI string
    into one giant token.  An unmatched closing bracket is kept as literal text.
    """
    text = str(raw_text or "")
    if not text.strip():
        return []

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    parts: List[str] = []
    buf: List[str] = []
    depth = 0

    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            if depth > 0:
                depth -= 1
            # An unmatched closing bracket is harmless content; keep it.
        if char in ",;\n" and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(char)

    parts.append("".join(buf))
    if depth != 0:
        # Damaged input: use the previous predictable behavior rather than
        # silently joining the remainder into one ingredient.
        parts = re.split(r"[,;\n]+", text)

    return [part.strip() for part in parts if part.strip()]


def normalize_ingredient_name(name: str) -> str:
    text = (name or '').strip()
    if not text:
        return ''

    text = text.replace('\n', ' ')
    text = text.replace('\t', ' ')
    text = re.sub(r'\s+', ' ', text)
    text = text.split('(', 1)[0].strip()
    text = text.split('/', 1)[0].strip()
    text = text.replace('·', ' ')
    text = re.sub(r'[^a-zA-Z0-9\s\-]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip().lower()
    return text


def parse_inci_list(raw_text: str) -> List[str]:
    if not raw_text:
        return []
    ingredients = []
    for part in split_inci_tokens(raw_text):
        cleaned = canonicalize_ingredient_name(part)
        if cleaned and cleaned != "water":
            ingredients.append(cleaned)
    return ingredients


def canonicalize_ingredient_name(name: str) -> str:
    normalized = normalize_ingredient_name(name)

    # Варианты воды: нормализуются к единому ключу «water» (вода нейтральна,
    # но без этого разные написания считались бы «неизвестным» ингредиентом).
    if normalized in {
        "aqua", "purified water", "deionized water", "distilled water",
        "aqua water", "water aqua", "water aqua eau", "aqua water eau", "eau",
    }:
        normalized = "water"

    # Нано-формы УФ-фильтров — тот же ингредиент, что и обычная форма.
    if normalized in {"titanium dioxide nano", "zinc oxide nano"}:
        normalized = normalized.replace(" nano", "")

    aliases = {
        'niacinamide': 'niacinamide',
        'vitamin b3': 'niacinamide',
        'glycerin': 'glycerin',
        'glycerine': 'glycerin',
        'salicylic acid': 'salicylic acid',
        'bha': 'salicylic acid',
        'retinol': 'retinol',
        'ceramide': 'ceramide',
        'sodium hyaluronate': 'sodium hyaluronate',
        'hyaluronic acid': 'hyaluronic acid',
        'panthenol': 'panthenol',
        'tocopherol': 'tocopherol',
        'fragrance': 'fragrance',
        'parfum': 'fragrance',
        'salix alba': 'salix alba bark extract',
    }
    return aliases.get(normalized, normalized)
