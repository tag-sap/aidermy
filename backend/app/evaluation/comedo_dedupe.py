"""Remove repeated comedogenicity clauses from other user-facing text.

The dedicated comedogenicity block owns ingredient names, ratings and the
potential-risk wording. Other report fields must not repeat it. Independent
risks (irritation, sensitization, barrier damage) are preserved.
"""
from __future__ import annotations

import re
from typing import Mapping, Sequence

COMEDO_RE = re.compile(
    r"комедоген|закупор\w*\s+пор|забива\w*\s+пор|пор\w*\s+забива|комендон",
    re.IGNORECASE,
)


def comedo_ingredient_names(comedo: Mapping | None) -> tuple[str, ...]:
    names: list[str] = []
    seen: set[str] = set()
    for item in (comedo or {}).get("ingredients") or []:
        name = str((item or {}).get("name") or "").strip()
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return tuple(names)


def _is_comedo_clause(clause: str, names: Sequence[str]) -> bool:
    # The dedicated block already carries the ingredient/rating list. Drop both
    # ingredient-specific and generic comedogenicity clauses from other fields.
    return bool(COMEDO_RE.search(clause))


def dedupe_comedogenicity_text(text: object, names: Sequence[str]) -> str:
    """Keep independent clauses; remove only repeated comedogenicity wording."""
    clean = " ".join(str(text or "").replace("\n", " ").split())
    if not clean or not COMEDO_RE.search(clean):
        return clean
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    kept_sentences: list[str] = []
    for sentence in sentences:
        if not COMEDO_RE.search(sentence):
            kept_sentences.append(sentence)
            continue
        clauses = re.split(r"\s*[,;]\s*|\s+(?:и|но|а)\s+", sentence)
        kept = [
            clause.strip()
            for clause in clauses
            if clause.strip() and not _is_comedo_clause(clause, names)
        ]
        if not kept:
            continue
        rebuilt = ", ".join(kept)
        if sentence.rstrip().endswith((".", "!", "?")) and not rebuilt.endswith((".", "!", "?")):
            rebuilt += sentence.rstrip()[-1]
        kept_sentences.append(rebuilt[:1].upper() + rebuilt[1:])
    return " ".join(kept_sentences).strip()


def scrub_comedo_fields(
    item: dict,
    names: Sequence[str],
    *,
    fields: Sequence[str] = (
        "reason",
        "explanation",
        "cause",
        "risk",
        "recommendation",
        "display_text",
        "scope_note",
    ),
) -> dict:
    """Mutate a user-facing row, removing duplicated comedogenicity text."""
    if not COMEDO_RE.search(" ".join(str(item.get(field) or "") for field in fields)):
        return item
    for field in fields:
        if field not in item:
            continue
        value = dedupe_comedogenicity_text(item.get(field), names)
        if value:
            item[field] = value
        elif field in {"reason", "display_text"}:
            item[field] = ""
        else:
            item.pop(field, None)
    return item
