import re
from typing import Iterable, List


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
    raw_text = raw_text.replace('\r', '\n')
    ingredients = []
    for part in re.split(r'[,;\n]+', raw_text):
        cleaned = normalize_ingredient_name(part)
        if cleaned and cleaned not in {'water', 'aqua'}:
            ingredients.append(cleaned)
    return ingredients


def canonicalize_ingredient_name(name: str) -> str:
    normalized = normalize_ingredient_name(name)

    # Варианты воды: нормализуются к единому ключу «water» (вода нейтральна,
    # но без этого разные написания считались бы «неизвестным» ингредиентом).
    if normalized in {
        "purified water", "deionized water", "distilled water",
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
