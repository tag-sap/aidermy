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
from functools import lru_cache
from typing import Any, Iterable

_CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
# A user may type a Latin product name while the Russian keyboard layout is on.
# This is the inverse of the standard Russian QWERTY layout.
_RU_KEYBOARD = {
    "й": "q", "ц": "w", "у": "e", "к": "r", "е": "t", "н": "y", "г": "u",
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


@lru_cache(maxsize=100000)
def _fold(value: Any) -> str:
    text = html.unescape(str(value or "")).casefold()
    text = unicodedata.normalize("NFKC", text).replace("ё", "е")
    text = _VOLUME_RE.sub(" ", text)
    return re.sub(r"[^0-9a-zа-я]+", " ", text).strip()


@lru_cache(maxsize=100000)
def _translit(value: str, *, brand_style: bool = False) -> str:
    if brand_style:
        # Russian users commonly transliterate foreign brands with «с» → c
        # (Celimax, CeraVe), while the ordinary BGN-style mapping uses s.
        value = value.replace("с", "c")
    return "".join(_CYR_TO_LAT.get(char, char) for char in value.casefold())


@lru_cache(maxsize=100000)
def _keyboard(value: str) -> str:
    return "".join(_RU_KEYBOARD.get(char, char) for char in value.casefold())


@lru_cache(maxsize=20000)
def _variants(value: str) -> set[str]:
    """Return normalized spellings that should be compared to the catalog."""
    folded = _fold(value)
    if not folded:
        return set()
    variants = {
        folded,
        _fold(_translit(folded)),
        _fold(_translit(folded, brand_style=True)),
        _fold(_keyboard(folded)),
    }
    return {item for item in variants if item}


@lru_cache(maxsize=100000)
def _tokens(value: str) -> list[str]:
    return [token for token in _fold(value).split() if len(token) > 1 and token not in _STOPWORDS]


@lru_cache(maxsize=20000)
def _variant_tokens(value: str) -> frozenset[str]:
    tokens: set[str] = set()
    for variant in _variants(value):
        tokens.update(_tokens(variant))
    return frozenset(tokens)


@lru_cache(maxsize=20000)
def _prefixes(value: str) -> frozenset[str]:
    return frozenset(token[:3] for token in _variant_tokens(value) if len(token) >= 3)


@lru_cache(maxsize=300000)
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


def _query_filter(query_variants: set[str]) -> tuple[frozenset[str], frozenset[str]]:
    tokens: set[str] = set()
    for variant in query_variants:
        tokens.update(_tokens(variant))
    prefixes = frozenset(token[:3] for token in tokens if len(token) >= 3)
    return frozenset(tokens), prefixes


def _quick_match(
    candidate_text: str,
    query_token_set: frozenset[str],
    query_prefix_set: frozenset[str],
) -> bool:
    """Cheap prefix filter before the relatively slow fuzzy comparison.

    Typos almost always preserve the first three letters, while keyboard and
    transliteration variants are already contained in the query profile.
    Rows without a single plausible token are skipped outright.
    """
    if not query_token_set:
        return False
    if not query_prefix_set:
        return True
    return bool(
        _variant_tokens(candidate_text) & query_token_set
        or _prefixes(candidate_text) & query_prefix_set
    )


def _score_row(
    query_variants: set[str],
    row: dict[str, Any],
    *,
    query_token_set: frozenset[str] | None = None,
    query_prefix_set: frozenset[str] | None = None,
) -> float:
    text = _row_text(row)
    candidate_variants = _variants(text)
    if not candidate_variants:
        return 0.0
    if query_token_set is None or query_prefix_set is None:
        query_token_set, query_prefix_set = _query_filter(query_variants)
    if not _quick_match(text, query_token_set, query_prefix_set):
        return 0.0

    best = 0.0
    brand = _fold(str(row.get("brand") or ""))
    for query in query_variants:
        query_tokens = _tokens(query)
        if not query_tokens:
            continue
        for candidate in candidate_variants:
            candidate_tokens = _tokens(candidate)
            if not candidate_tokens:
                continue
            token_scores = [
                max((_ratio(token, other) for other in candidate_tokens), default=0.0)
                for token in query_tokens
            ]
            # Релевантность: почти все значимые токены должны подтвердиться
            # (точное совпадение, вхождение или близкое написание — опечатки,
            # транслит, раскладка). Иначе одно общее слово («barrier», «cream»)
            # затягивает в выдачу посторонние продукты.
            matched = sum(
                1
                for token, score in zip(query_tokens, token_scores)
                if score >= 0.78 or token in candidate
            )
            needed = max(1, (3 * len(query_tokens) + 4) // 5)
            if matched < needed:
                continue
            # A one-word query is usually a brand. Compare it with individual
            # name tokens as well as the full title, otherwise a typo in
            # "celimx" is diluted by the long "celimax dual barrier ..." text.
            phrase = max(
                _ratio(query, candidate),
                max(token_scores) if len(query_tokens) == 1 else 0.0,
            )
            # Tokens matching a whole candidate token are much stronger than a
            # coincidental fuzzy character match.
            exact = sum(1 for token in query_tokens if token in candidate_tokens) / max(1, len(query_tokens))
            typo = sum(token_scores) / max(1, len(token_scores))
            coverage = exact
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
    if not variants or not _tokens(query):
        return [], 0
    query_token_set, query_prefix_set = _query_filter(variants)

    scored: list[tuple[float, int, dict[str, Any]]] = []
    for row in rows:
        score = _score_row(
            variants,
            row,
            query_token_set=query_token_set,
            query_prefix_set=query_prefix_set,
        )
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
