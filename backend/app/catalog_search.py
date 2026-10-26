"""Free, dependency-light product search ranking.

The catalog is still the source of truth.  This module only ranks the rows
already returned by the existing SQLite/PostgreSQL queries; it does not create
another catalog or a separate index.
"""
from __future__ import annotations

import html
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Iterable

_CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
# A user may type a Latin product name while the Russian keyboard layout is on.
_RU_KEYBOARD = {
    "й": "q", "ц": "w", "у": "e", "к": "r", "е": "e", "н": "y", "г": "u",
    "ш": "i", "щ": "o", "з": "p", "х": "[", "ъ": "]",
    "ф": "a", "ы": "s", "в": "d", "а": "f", "п": "g", "р": "h", "о": "j",
    "л": "k", "д": "l", "ж": ";", "э": "'",
    "я": "z", "ч": "x", "с": "c", "м": "v", "и": "b", "т": "n", "ь": "m",
    "б": ",", "ю": ".",
}
_STOPWORDS = {
    "the", "and", "with", "for", "de", "la", "le", "a", "an",
    "cream", "serum", "gel", "toner", "lotion", "mask", "emulsion",
    "foam", "cleanser", "cleansing", "spray", "fluid", "balm", "spf",
    "крем", "сыворотка", "гель", "тоник", "тонер", "лосьон", "маска",
    "пенка", "эмульсия", "бальзам", "спрей", "флюид", "для", "уход",
}
_VOLUME_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:ml|мл|g|г|гр|oz|l)\b", re.I)


def _fold(value: Any) -> str:
    text = html.unescape(str(value or "")).casefold()
    text = unicodedata.normalize("NFKC", text).replace("ё", "е")
    text = _VOLUME_RE.sub(" ", text)
    return re.sub(r"[^0-9a-zа-я]+", " ", text).strip()


def _translit(value: str) -> str:
    return "".join(_CYR_TO_LAT.get(char, char) for char in value.casefold())


def _keyboard(value: str) -> str:
    return "".join(_RU_KEYBOARD.get(char, char) for char in value.casefold())


def _variants(value: str) -> set[str]:
    """Return normalized spellings that should be compared to the catalog."""
    folded = _fold(value)
    if not folded:
        return set()
    variants = {folded, _fold(_translit(folded)), _fold(_keyboard(folded))}
    return {item for item in variants if item}


def _tokens(value: str) -> list[str]:
    return [token for token in _fold(value).split() if len(token) > 1 and token not in _STOPWORDS]


def _ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _row_text(row: dict[str, Any]) -> str:
    name = str(row.get("name") or "").replace("\n", " ")
    return " ".join(
        value for value in (
            row.get("brand"), name, row.get("variant"), row.get("volume"),
            row.get("category"), row.get("subcategory"),
        ) if value
    )


def _score_row(query_variants: set[str], query_tokens: list[str], row: dict[str, Any]) -> float:
    text = _row_text(row)
    candidate_variants = _variants(text)
    if not candidate_variants:
        return 0.0

    best = 0.0
    for query in query_variants:
        candidate = max(candidate_variants, key=lambda value: _ratio(query, value))
        phrase = _ratio(query, candidate)
        candidate_tokens = _tokens(candidate)
        if not candidate_tokens:
            continue
        token_scores = [
            max((_ratio(token, other) for other in candidate_tokens), default=0.0)
            for token in query_tokens
        ]
        # Tokens matching a whole candidate token are much stronger than a
        # coincidental fuzzy character match.
        exact = sum(1 for token in query_tokens if token in candidate_tokens) / max(1, len(query_tokens))
        typo = sum(token_scores) / max(1, len(token_scores))
        coverage = exact
        brand = _fold(str(row.get("brand") or ""))
        brand_bonus = 0.12 if brand and any(token == brand for token in query_tokens) else 0.0
        score = 0.48 * phrase + 0.32 * coverage + 0.20 * typo + brand_bonus
        if query == candidate:
            score += 0.30
        elif query in candidate or candidate in query:
            score += 0.12
        best = max(best, score)
    return best


def rank_products(
    rows: Iterable[dict[str, Any]],
    query: str,
    *,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Rank catalog rows for a human query and return (page, total)."""
    query = " ".join(str(query or "").split())
    if len(query) < 2:
        return [], 0
    variants = _variants(query)
    tokens = _tokens(query)
    if not variants or not tokens:
        return [], 0

    scored: list[tuple[float, int, dict[str, Any]]] = []
    for row in rows:
        score = _score_row(variants, tokens, row)
        # A low confidence match is worse than an honest empty result.
        if score < 0.32:
            continue
        scored.append((score, int(row.get("id") or 0), row))
    scored.sort(key=lambda item: (-item[0], item[1]))
    seen: set[Any] = set()
    unique: list[dict[str, Any]] = []
    for _, _, row in scored:
        key = row.get("id") if row.get("id") is not None else row.get("slug")
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    start = max(0, int(offset))
    return unique[start:start + max(1, int(limit))], len(unique)
