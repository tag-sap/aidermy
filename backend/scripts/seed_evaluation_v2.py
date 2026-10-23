"""Register the Evaluation V2 rule version and parameter registry (idempotent).

The `evaluation` schema must already exist (see apply_evaluation_migrations.py).
Without the rule row every snapshot insert fails with "rule version ... is not
registered". This script uses upserts, so it is safe to run on every deploy.

Usage:
    cd backend
    python scripts/seed_evaluation_v2.py --yes
    ... --dsn "$SUPABASE_DATABASE_URL" --yes   # explicit target
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

from app.evaluation.postgres_store import PostgresStore  # noqa: E402
from app.evaluation.rules import get_rules  # noqa: E402
from app.evaluation.service import DEFAULT_METHOD_VERSION  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default="")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    if not args.yes:
        print("refusing to write without --yes")
        return 2

    load_dotenv(BACKEND / ".env")
    if args.dsn:
        os.environ["SUPABASE_DATABASE_URL"] = args.dsn
    if not os.getenv("SUPABASE_DATABASE_URL"):
        print("SUPABASE_DATABASE_URL is not set")
        return 2

    rules = get_rules()
    store = PostgresStore()
    version = store.seed_rule(rules)
    count = store.seed_registry(DEFAULT_METHOD_VERSION)
    print(f"rule_version={version} calibrated={rules.calibrated}")
    print(f"method_version={DEFAULT_METHOD_VERSION} parameters={count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
