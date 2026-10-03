"""
upload_processed_images.py — публикует уже обработанные PNG (remove_background)
в Yandex Object Storage и опционально подменяет image_url в products.db.

Запуск (из корня репозитория):
  python backend/upload_processed_images.py [--dir DIR] [--update-db]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.image_storage import upload_image, processed_key  # noqa: E402
from app.database import get_connection, PRODUCTS_DB  # noqa: E402

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "processed_images"


def safe_slug(slug: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in (slug or ""))


def main() -> int:
    parser = argparse.ArgumentParser(description="Публикация обработанных PNG в S3")
    parser.add_argument("--dir", type=str, default=str(DEFAULT_DIR), help="Каталог с обработанными PNG")
    parser.add_argument("--update-db", action="store_true", help="Обновить image_url в products.db")
    args = parser.parse_args()

    in_dir = Path(args.dir)
    state_path = in_dir / ".uploaded.json"
    uploaded_state = set()
    if state_path.exists():
        try:
            uploaded_state = set(json.loads(state_path.read_text(encoding="utf-8")))
        except Exception:
            uploaded_state = set()

    conn = get_connection(PRODUCTS_DB)
    rows = conn.execute("SELECT id, slug, image_url FROM products WHERE image_url IS NOT NULL AND trim(image_url) != ''").fetchall()

    total = len(rows)
    ok = 0
    skipped = 0
    errors = 0

    for pid, slug, _image_url in rows:
        key_id = str(pid)
        if key_id in uploaded_state:
            skipped += 1
            continue
        local_file = in_dir / f"{safe_slug(slug)}.png"
        if not local_file.exists():
            # ещё не обработан (batch не дошёл) — пропускаем без ошибки.
            skipped += 1
            continue
        try:
            url = upload_image(processed_key(slug), local_file.read_bytes())
            if args.update_db:
                conn.execute("UPDATE products SET image_url = ? WHERE id = ?", (url, pid))
                conn.commit()
            uploaded_state.add(key_id)
            ok += 1
            if ok % 50 == 0:
                state_path.write_text(json.dumps(sorted(uploaded_state)), encoding="utf-8")
                print(f"  ... загружено {ok}", flush=True)
        except Exception as exc:
            errors += 1
            print(f"  upload {pid} {slug}: {exc}", flush=True)

    conn.close()
    state_path.write_text(json.dumps(sorted(uploaded_state)), encoding="utf-8")

    print("\n=== ПУБЛИКАЦИЯ ===")
    print(f"всего:      {total}")
    print(f"загружено:  {ok}")
    print(f"пропущено:  {skipped}")
    print(f"ошибок:     {errors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
