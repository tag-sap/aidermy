# shelf_compatibility.py
# Детерминированный Shelf Compatibility Engine (БЕЗ AI).
#
# Отвечает на вопрос: «Насколько продукты, собранные вместе в полке/шкафу,
# совместимы МЕЖДУ СОБОЙ как система ухода?»
#
# Это НЕ среднее арифметическое индивидуальных процентов и не сумма.
#
# Формула:
#   Shelf Score = Base Compatibility − Combination Penalties + Compatibility Bonuses
#
#   Base        — средняя индивидуальная совместимость продуктов с профилем.
#   Combination — pairwise-конфликты активов, дублирование функций,
#                 нагрузка на кожу (ирританты), по правилам ниже.
#   Bonuses     — покрытие этапов ухода (Очищение → ... → SPF).
#
# Итог нормализуется в 0–100 и полностью объясним (возвращаются причины).

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from .ingredient_normalizer import canonicalize_ingredient_name

# ---------------------------------------------------------------------------
# Данные (детерминированные правила комбинаций).
# Это задел под отдельную Combination DB: правила можно вынести в таблицу,
# но сейчас их немного и они заданы явно.
# ---------------------------------------------------------------------------

CONFLICT_RULES: List[Dict[str, Any]] = [
    {
        "label": "Ретиноиды + AHA/BHA-кислоты",
        "a": ["retinol", "retinal", "tretinoin", "retinyl", "adapalene", "tazarotene"],
        "b": ["glycolic acid", "salicylic acid", "lactic acid", "mandelic acid", "malic acid", "aha", "bha"],
    },
    {
        "label": "Ниацинамид + L-аскорбиновая кислота (витамин C)",
        "a": ["niacinamide"],
        "b": ["ascorbic acid", "vitamin c", "ascorbyl"],
    },
    {
        "label": "Ретиноиды + бензоилпероксид",
        "a": ["retinol", "retinal", "retinyl"],
        "b": ["benzoyl peroxide"],
    },
    {
        "label": "AHA + BHA (двойное отшелушивание)",
        "a": ["glycolic acid", "lactic acid", "mandelic acid", "aha"],
        "b": ["salicylic acid", "bha"],
    },
]

COMMON_ACTIVES: Set[str] = {
    "niacinamide", "hyaluronic acid", "sodium hyaluronate", "salicylic acid",
    "glycolic acid", "lactic acid", "retinol", "retinal", "retinyl", "bakuchiol",
    "vitamin c", "ascorbic acid", "azelaic acid", "ceramide", "panthenol",
    "centella", "madecassoside", "peptide", "collagen", "adenosine",
    "tranexamic acid", "arbutin", "alpha arbutin", "kojic acid", "zinc", "tea tree",
}

SENSITIZING_ACTIVES: Set[str] = {
    "fragrance", "parfum", "perfume", "alcohol denat", "denatured alcohol",
    "ethanol", "essential oil", "citrus limon", "lavandula", "eucalyptus",
    "menthol", "retinol", "retinal", "retinyl", "glycolic acid", "salicylic acid",
    "lactic acid", "benzoyl peroxide",
}

CORE_STEPS: List[str] = ["Очищение", "Тонизация", "Сыворотки", "Увлажнение", "SPF"]

_CONFLICT_PENALTY = 12
_CONFLICT_CAP = 40
_DUPLICATE_PENALTY = 2
_DUPLICATE_CAP = 12
_IRRITATION_PENALTY = 4
_IRRITATION_CAP = 16
_COVERAGE_BONUS = {0: 0, 1: 0, 2: 2, 3: 4, 4: 6, 5: 8}


def _matches(ingredient: str, token: str) -> bool:
    return token in ingredient or ingredient in token


def parse_inci(raw: Any) -> Set[str]:
    out: Set[str] = set()
    for part in re.split(r"[,;\n]+", str(raw or "")):
        c = canonicalize_ingredient_name(part)
        if c:
            out.add(c)
    return out


def _ingredient_matches_any(ingredients: Set[str], tokens: List[str]) -> List[str]:
    matched: List[str] = []
    for ing in ingredients:
        for token in tokens:
            if _matches(ing, token):
                matched.append(ing)
                break
    return matched


def compute_shelf_compatibility(products: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Совместимость ухода для списка продуктов.

    products: список dict с ключами name, category, ingredients, score (score м.б. None).
    """
    if not products:
        return {"score": None, "base": None, "conflicts": [], "duplicate_actives": [],
                "irritation": [], "coverage": {"present": [], "missing": CORE_STEPS[:], "steps_covered": 0}}

    ingredient_sets: List[Set[str]] = [parse_inci(p.get("ingredients") or "") for p in products]

    scores = [p.get("score") for p in products if isinstance(p.get("score"), int)]
    base = int(round(sum(scores) / len(scores))) if scores else None

    # Pairwise конфликты активов между разными продуктами.
    conflicts: List[Dict[str, Any]] = []
    n = len(products)
    for i in range(n):
        for j in range(i + 1, n):
            for rule in CONFLICT_RULES:
                a_i = _ingredient_matches_any(ingredient_sets[i], rule["a"])
                b_j = _ingredient_matches_any(ingredient_sets[j], rule["b"])
                a_j = _ingredient_matches_any(ingredient_sets[j], rule["a"])
                b_i = _ingredient_matches_any(ingredient_sets[i], rule["b"])
                if (a_i and b_j) or (a_j and b_i):
                    conflicts.append({
                        "label": rule["label"],
                        "a": sorted(set(a_i + a_j)),
                        "b": sorted(set(b_i + b_j)),
                        "products": [
                            str(products[i].get("name") or ""),
                            str(products[j].get("name") or ""),
                        ],
                    })

    # Дублирование функций: один актив в нескольких продуктах.
    active_counts: Dict[str, int] = {}
    for s in ingredient_sets:
        for act in COMMON_ACTIVES:
            if any(_matches(ing, act) for ing in s):
                active_counts[act] = active_counts.get(act, 0) + 1
    duplicate_actives = sorted(
        [{"ingredient": k, "count": v} for k, v in active_counts.items() if v > 1],
        key=lambda x: -x["count"],
    )

    # Нагрузка на кожу: ирританты в 2+ продуктах.
    irrit_counts: Dict[str, int] = {}
    for s in ingredient_sets:
        for act in SENSITIZING_ACTIVES:
            if any(_matches(ing, act) for ing in s):
                irrit_counts[act] = irrit_counts.get(act, 0) + 1
    irritation = sorted(
        [{"ingredient": k, "count": v} for k, v in irrit_counts.items() if v > 1],
        key=lambda x: -x["count"],
    )

    # Покрытие этапов ухода (мягкий бонус).
    present = sorted({str(p.get("category") or "") for p in products if p.get("category")})
    distinct_steps = sum(
        1 for c in CORE_STEPS
        if any(c.lower() in pc.lower() or pc.lower() in c.lower() for pc in present)
    )
    missing = [c for c in CORE_STEPS if c not in present]
    coverage_bonus = _COVERAGE_BONUS.get(distinct_steps, 0)

    if base is None:
        score = None
    else:
        penalty = (
            min(_CONFLICT_CAP, _CONFLICT_PENALTY * len(conflicts))
            + min(_DUPLICATE_CAP, _DUPLICATE_PENALTY * len(duplicate_actives))
            + min(_IRRITATION_CAP, _IRRITATION_PENALTY * max(0, len(irritation)))
        )
        score = max(0, min(100, base - penalty + coverage_bonus))

    return {
        "score": score,
        "base": base,
        "conflicts": conflicts,
        "duplicate_actives": duplicate_actives,
        "irritation": irritation,
        "coverage": {"present": present, "missing": missing, "steps_covered": distinct_steps},
    }

