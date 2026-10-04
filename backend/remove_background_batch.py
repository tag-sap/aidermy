"""
remove_background_batch.py — безопасный batch-скрипт обработки существующих
изображений товаров модулем remove_background.

Что делает:
  * обходит все товары products.db с image_url;
  * скачивает изображение, удаляет белый фон, сохраняет PNG с прозрачностью;
  * оригиналы сохраняет в originals/ (для отката);
  * не трогает Score Engine / Match / рекомендации / структуру products.db;
  * пропускает уже обработанные (state-файл), ошибочные и «пустые» товары;
  * в конце печатает статистику: всего / обработано / пропущено / ошибок.

Запуск (из корня репозитория):
  python backend/remove_background_batch.py [--limit N] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

# Позволяет запускать и как `python backend/remove_background_batch.py`, и из
# самой директории backend.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.remove_background import remove_background  # noqa: E402
from app.database import get_connection, PRODUCTS_DB  # noqa: E402
from app.image_storage import upload_image, processed_key  # noqa: E402


DEFAULT_OUT = Path(__file__).resolve().parent.parent / "processed_images"


def load_state(state_path: Path) -> set:
    if state_path.exists():
        try:
            return set(json.loads(state_path.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_state(state_path: Path, processed: set) -> None:
    state_path.write_text(json.dumps(sorted(processed), ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch удаление белого фона у товаров")
    parser.add_argument("--limit", type=int, default=0, help="Обработать не более N товаров (0 — все)")
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT), help="Каталог для результата")
    parser.add_argument("--timeout", type=float, default=20.0, help="Таймаут загрузки изображения, сек")
    parser.add_argument("--upload", action="store_true", help="Загрузить обработанные PNG в Yandex Object Storage")
    parser.add_argument("--update-db", action="store_true", help="Обновить image_url в products.db на обработанный (только с --upload)")
    args = parser.parse_args()

    out_dir = Path(args.out)
    originals_dir = out_dir / "originals"
    out_dir.mkdir(parents=True, exist_ok=True)
    originals_dir.mkdir(parents=True, exist_ok=True)

    state_path = out_dir / ".processed.json"
    processed = load_state(state_path)

    conn = get_connection(PRODUCTS_DB)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, slug, name, image_url FROM products "
        "WHERE image_url IS NOT NULL AND trim(image_url) != '' "
        "ORDER BY id"
    )
    rows = cursor.fetchall()
    conn.close()

    total = len(rows)
    ok = 0
    skipped = 0
    errors = 0
    uploaded = 0
    errors_log: list[str] = []

    db_conn = None
    db_cursor = None
    if args.update_db:
        db_conn = get_connection(PRODUCTS_DB)
        db_cursor = db_conn.cursor()

    client = httpx.Client(timeout=args.timeout, follow_redirects=True, headers={
        "User-Agent": "aidermy-image-pipeline/1.0"
    })

    for i, (pid, slug, name, image_url) in enumerate(rows):
        if args.limit and i >= args.limit:
            break
        key = str(pid)
        if key in processed:
            skipped += 1
            continue

        safe_slug = (slug or f"product-{pid}").strip() or f"product-{pid}"
        safe_slug = "".join(c if (c.isalnum() or c in "-_") else "_" for c in safe_slug)
        out_path = out_dir / f"{safe_slug}.png"

        try:
            resp = client.get(image_url)
            resp.raise_for_status()
            original = resp.content
        except Exception as exc:
            errors += 1
            errors_log.append(f"download {pid} {safe_slug}: {exc}")
            continue

        # Сохраняем оригинал для отката (один раз, не перезаписываем).
        orig_path = originals_dir / f"{safe_slug}.orig"
        if not orig_path.exists():
            try:
                orig_path.write_bytes(original)
            except Exception:
                pass

        result = remove_background(original, output_format="PNG")
        if result is None:
            errors += 1
            errors_log.append(f"process {pid} {safe_slug}: failed (kept original)")
            continue

        out_path.write_bytes(result)

        # Опционально: публикуем обработанный PNG в Object Storage и подменяем URL.
        if args.upload:
            try:
                key_processed = processed_key(slug or f"product-{pid}")
                url = upload_image(key_processed, result)
                uploaded += 1
                if args.update_db:
                    db_cursor.execute(
                        "UPDATE products SET image_url = ? WHERE id = ?",
                        (url, pid),
                    )
                    db_conn.commit()
            except Exception as exc:
                errors_log.append(f"upload {pid} {safe_slug}: {exc}")

        processed.add(key)
        ok += 1

        if ok % 10 == 0:
            save_state(state_path, processed)
            print(f"  ... обработано {ok}", flush=True)

    client.close()
    if db_conn is not None:
        db_conn.close()
    save_state(state_path, processed)

    print("\n=== СТАТИСТИКА ===")
    print(f"всего:      {total}")
    print(f"обработано: {ok}")
    print(f"пропущено:  {skipped}")
    print(f"ошибок:     {errors}")
    if args.upload:
        print(f"загружено:  {uploaded}")
    print(f"\nРезультат:   {out_dir}")
    print(f"Оригиналы:   {originals_dir}")
    if errors_log:
        log_path = out_dir / ".errors.log"
        log_path.write_text("\n".join(errors_log), encoding="utf-8")
        print(f"Лог ошибок:  {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
