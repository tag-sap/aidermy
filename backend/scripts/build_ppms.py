# scripts/build_ppms.py
# CLI: batch-построение PPM + единого Product Vector index для каталога.
#
# Без LLM: используется только существующая knowledge map. Idempotent.
#
# Запуск:  cd backend && python scripts/build_ppms.py
#
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ppm_service import build_all_ppms


def main() -> int:
    def progress(done: int, total: int, stats) -> None:
        print(
            f"  [{done}/{total}] pm={stats['pm']} ppm={stats['ppm']} "
            f"skipped_current={stats['skipped_current']} failed={stats['failed']}"
        )

    print("Building PPMs + product vectors ...")
    stats = build_all_ppms(progress_cb=progress)

    print("=== Build complete ===")
    for k in ("total", "pm", "ppm", "skipped_current", "skipped_no_ingredients", "failed"):
        print(f"  {k}: {stats.get(k, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
