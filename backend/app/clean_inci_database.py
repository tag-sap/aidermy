# clean_inci_database.py
# Очистка INCI во всей production БД продуктов от очевидного web-мусора.
#
# Консервативный подход: удаляем ТОЛЬКО явный мусор (HTML/JS, URL, email, телефон,
# JSON-фрагменты, русский текст/переводы), разбираем длинные строки, убираем
# дубликаты, нормализуем, сохраняем порядок. НЕ удаляем реальные ингредиенты
# только потому, что их нет в ingredient DB.
#
# Безопасность: по умолчанию --dry-run (ничего не пишет). Для применения — --apply.

from __future__ import annotations

import argparse
import re
import sqlite3
from typing import List, Set, Tuple

from .database import AIDERMY_DB, PRODUCTS_DB, get_connection
from .ingredient_normalizer import normalize_ingredient_name

# ---------------------------------------------------------------------------
# Паттерны мусора
# ---------------------------------------------------------------------------
_CYR_RE = re.compile(r"[А-Яа-яЁё]")
_RUSSIAN_PAREN_RE = re.compile(r"\([^()]*[А-Яа-яЁё][^()]*\)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITY_RE = re.compile(r"&(?:nbsp|amp|lt|gt|quot|apos|#\d+);", re.I)
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
_EMAIL_RE = re.compile(r"\S+@\S+")
_PHONE_RE = re.compile(r"\+?\d[\d\s().\-]{7,}\d")
_WS_RE = re.compile(r"\s+")


def _cut_html_comment(s: str) -> str:
    """Отрезает всё от HTML-комментария/JS-вставки (<!-- ... -->)."""
    idx = s.find("<!--")
    if idx != -1:
        s = s[:idx]
    return s


def _strip_russian_parens(t: str) -> str:
    """Удаляет вложенные (...)-группы, содержащие кириллицу (русские переводы)."""
    changed = True
    while changed:
        changed = False
        m = _RUSSIAN_PAREN_RE.search(t)
        if m:
            t = (t[: m.start()] + t[m.end() :]).strip()
            changed = True
    return t


def clean_token(token: str) -> str | None:
    """Чистит один INCI-токен. Возвращает чистый токен или None (если это мусор)."""
    t = (token or "").strip()
    if not t:
        return None
    # Органические маркеры * не являются частью INCI-имени.
    t = t.replace("*", "").strip()
    t = _strip_russian_parens(t)
    # После удаления русских скобок осталась кириллица → русский текст/описание.
    if _CYR_RE.search(t):
        return None
    # Стрипаем только граничные пунктуационные символы, НЕ скобки:
    # () — легитимная часть INCI (напр. "Water (Eau)").
    t = t.strip(" ,;.")
    if not t:
        return None
    return t


def clean_ingredients(raw) -> Tuple[str, int]:
    """Чистит INCI-строку продукта. Возвращает (cleaned_string, removed_junk_count)."""
    if not raw or not str(raw).strip():
        return "", 0

    s = str(raw)
    s = _cut_html_comment(s)
    s = _HTML_ENTITY_RE.sub(" ", s)
    s = _HTML_TAG_RE.sub(" ", s)
    s = _URL_RE.sub(" ", s)
    s = _EMAIL_RE.sub(" ", s)
    s = _PHONE_RE.sub(" ", s)

    # Разделяем по запятой/;/\n, НО не по запятой между цифрами
    # (напр. "1,2-Hexanediol" — позиционная запятая в химическом имени).
    tokens = [p for p in re.split(r"(?<!\d),(?!\d)|[;\n]+", s)]
    seen: Set[str] = set()
    kept: List[str] = []
    removed = 0

    for tok in tokens:
        raw_tok = tok.strip()
        if not raw_tok:
            continue
        cleaned = clean_token(tok)
        if not cleaned:
            removed += 1
            continue
        key = _WS_RE.sub(" ", cleaned).strip(" ,;").lower()
        if key in seen:
            removed += 1  # дубликат
            continue
        seen.add(key)
        kept.append(cleaned)

    return ", ".join(kept), removed


def load_known_names() -> Set[str]:
    """normalized_name + synonyms ингредиентов из ingredient DB (для отчёта «missing»)."""
    known: Set[str] = set()
    try:
        conn = get_connection(AIDERMY_DB)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT normalized_name, synonyms FROM ingredients_catalog"
            ).fetchall()
            for r in rows:
                name = (r["normalized_name"] or "").strip().lower()
                if name:
                    known.add(name)
                for syn in (r["synonyms"] or "").split(","):
                    syn = syn.strip().lower()
                    if syn:
                        known.add(syn)
        finally:
            conn.close()
    except Exception:
        pass
    return known


def _still_suspicious(cleaned: str) -> List[str]:
    """Признаки мусора, оставшиеся после очистки (для отчёта «подозрительных»)."""
    flags: List[str] = []
    if not cleaned:
        return flags
    if _URL_RE.search(cleaned):
        flags.append("url")
    if _HTML_TAG_RE.search(cleaned):
        flags.append("html")
    if _CYR_RE.search(cleaned):
        flags.append("cyrillic")
    if _EMAIL_RE.search(cleaned):
        flags.append("email")
    return flags


def run(apply: bool, limit: int | None) -> int:
    conn = get_connection(PRODUCTS_DB)
    conn.row_factory = sqlite3.Row
    try:
        query = "SELECT id, name, ingredients FROM products WHERE is_canonical = 1"
        if limit:
            query += f" LIMIT {int(limit)}"
        rows = [dict(r) for r in conn.execute(query).fetchall()]
    finally:
        conn.close()

    known = load_known_names()

    total = len(rows)
    processed = 0
    changed = 0
    junk_removed = 0
    suspicious = 0
    missing_ingredients = 0
    missing_products = 0
    examples: List[Tuple[str, str, str]] = []
    updates: List[Tuple[str, int]] = []

    for r in rows:
        raw = r["ingredients"] or ""
        cleaned, removed = clean_ingredients(raw)
        processed += 1
        junk_removed += removed

        if cleaned != raw:
            changed += 1
            updates.append((cleaned, r["id"]))

        if _still_suspicious(cleaned):
            suspicious += 1

        cleaned_tokens = [t.strip() for t in re.split(r"(?<!\d),(?!\d)|[;]+", cleaned) if t.strip()]
        for tok in cleaned_tokens:
            key = normalize_ingredient_name(tok)
            if key and key not in known and key not in {"water", "aqua"}:
                missing_ingredients += 1
        if cleaned_tokens and any(
            normalize_ingredient_name(t) not in known for t in cleaned_tokens
        ):
            missing_products += 1

        if changed and len(examples) < 10:
            examples.append((r["name"], raw[:120], cleaned[:120]))

    if apply:
        conn = get_connection(PRODUCTS_DB)
        try:
            conn.execute("BEGIN")
            for cleaned, pid in updates:
                conn.execute(
                    "UPDATE products SET ingredients = ? WHERE id = ?", (cleaned, pid)
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    print("=== INCI CLEANUP REPORT ===")
    print(f"mode: {'APPLY (written)' if apply else 'DRY-RUN (nothing written)'}")
    print(f"total products: {total}")
    print(f"processed: {processed}")
    print(f"changed: {changed}")
    print(f"junk elements removed: {junk_removed}")
    print(f"suspicious remaining: {suspicious}")
    print(f"products with missing ingredients: {missing_products}")
    print(f"missing ingredient occurrences: {missing_ingredients}")
    print()
    print("10 BEFORE -> AFTER examples:")
    for name, before, after in examples:
        print(f"  [{name[:45]!r}]")
        print(f"    BEFORE: {before!r}")
        print(f"    AFTER : {after!r}")
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Clean web junk from INCI in production products DB")
    p.add_argument("--apply", action="store_true", help="Actually write changes (default dry-run)")
    p.add_argument("--limit", type=int, default=None, help="Limit number of products (for testing)")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    return run(apply=args.apply, limit=args.limit)


if __name__ == "__main__":
    raise SystemExit(main())

