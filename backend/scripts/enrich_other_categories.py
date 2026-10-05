from __future__ import annotations

import argparse
import csv
from datetime import datetime
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import PRODUCTS_DB
from app.catalog_taxonomy import TAXONOMY
from app.services import DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_MODEL_FALLBACKS


def allowed_categories():
    result = []
    for area in TAXONOMY:
        for cat in area["categories"]:
            if cat["key"] != "all":
                result.append({
                    "body_area": area["title"],
                    "key": cat["key"],
                    "title": cat["title"],
                })
    return result


CATEGORIES = allowed_categories()
CATEGORY_TITLES = {x["title"] for x in CATEGORIES}


def load_products(limit: int, offset: int):
    con = sqlite3.connect(PRODUCTS_DB)
    con.row_factory = sqlite3.Row

    rows = con.execute(
        """
        SELECT
            id,
            name,
            brand,
            manufacturer,
            description,
            ingredients,
            category,
            subcategory,
            taxonomy_category,
            url
        FROM products
        WHERE
            COALESCE(TRIM(subcategory), '') IN (
                'Другое',
                'Все товары категории'
            )
            OR (
                COALESCE(TRIM(subcategory), '') = ''
                AND COALESCE(TRIM(category), '') = 'Другое'
            )
        ORDER BY id
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()

    con.close()
    return [dict(r) for r in rows]

def build_prompt(products):
    categories_text = "\n".join(
        f"- {x['title']} [{x['body_area']}]"
        for x in CATEGORIES
    )

    products_text = []

    for p in products:
        products_text.append(
            json.dumps(
                {
                    "id": p["id"],
                    "name": p["name"],
                    "brand": p["brand"],
                    "manufacturer": p["manufacturer"],
                    "description": p["description"],
                    "ingredients": p["ingredients"],
                    "url": p["url"],
                },
                ensure_ascii=False,
            )
        )

    return f"""
Ты классифицируешь товары косметического каталога Aidermy.

Твоя задача — определить ФАКТИЧЕСКОЕ НАЗНАЧЕНИЕ каждого товара.

Разрешены ТОЛЬКО следующие категории:

{categories_text}

КРИТИЧЕСКИЕ ПРАВИЛА:

1. Выбирай категорию по назначению продукта, а не по отдельным ингредиентам.
2. Название и описание имеют приоритет над INCI.
3. Brand/manufacturer используй как дополнительный контекст.
4. INCI используй только как вспомогательный сигнал.
5. Не классифицируй продукт по одному ингредиенту.
6. Если продукт относится к волосам, телу, макияжу или парфюмерии — не помещай его в категорию ухода за лицом.
7. Если продукт явно относится к типу товара, которого нет в разрешённом списке, выбирай "Другое".
8. Если информации недостаточно или есть серьёзная неоднозначность — выбирай "Другое".
9. Не придумывай новые категории.
10. Не используй "Все товары категории".
11. Верни ровно ОДНУ категорию на товар.

Особенно внимательно отличай:
- hair serum / hair oil / leave-in от сывороток для лица;
- hair mask от масок для лица;
- body cream / body lotion от кремов для лица;
- makeup от skincare;
- perfume/fragrance от ухода;
- шампуни и кондиционеры от средств для кожи головы/лица.

Верни ТОЛЬКО JSON-массив без markdown и без пояснений.

Формат:

[
  {{
    "id": 123,
    "category": "Сыворотки",
    "confidence": 0.95,
    "reason": "Название явно указывает на сыворотку для лица."
  }}
]

confidence — число от 0 до 1.

Товары:

{chr(10).join(products_text)}
"""


async def call_deepseek(prompt: str):
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY отсутствует")

    import httpx

    async with httpx.AsyncClient(timeout=60) as client:
        for model in DEEPSEEK_MODEL_FALLBACKS:
            try:
                response = await client.post(
                    DEEPSEEK_API_URL,
                    headers={
                        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "Отвечай строго валидным JSON без markdown.",
                            },
                            {
                                "role": "user",
                                "content": prompt,
                            },
                        ],
                        "temperature": 0.1,
                        "max_tokens": 5000,
                    },
                )

                if response.status_code != 200:
                    print(
                        f"[WARN] {model}: HTTP {response.status_code}",
                        file=sys.stderr,
                    )
                    continue

                data = response.json()
                content = data["choices"][0]["message"]["content"]

                if content and content.strip():
                    return content

            except Exception as exc:
                print(f"[WARN] {model}: {exc}", file=sys.stderr)

    raise RuntimeError("DeepSeek не вернул результат")


def parse_result(raw: str, products):
    raw = raw.strip()

    if raw.startswith("```"):
        lines = raw.splitlines()
        lines = [
            x for x in lines
            if not x.strip().startswith("```")
        ]
        raw = "\n".join(lines).strip()

    result = json.loads(raw)

    if not isinstance(result, list):
        raise ValueError("Ответ DeepSeek не является массивом")

    source_ids = {p["id"] for p in products}
    seen = set()
    validated = []

    for item in result:
        if not isinstance(item, dict):
            continue

        pid = item.get("id")

        if pid not in source_ids:
            continue

        if pid in seen:
            continue

        seen.add(pid)

        category = str(item.get("category") or "").strip()
        confidence = float(item.get("confidence", 0))
        reason = str(item.get("reason") or "").strip()

        # DeepSeek иногда возвращает категорию вместе с родительским разделом:
        # "Сыворотки [Уход для лица]" -> "Сыворотки"
        # Нормализуем только если базовая категория существует в TAXONOMY.
        if category not in CATEGORY_TITLES and "[" in category:
            base_category = category.split("[", 1)[0].strip()
            if base_category in CATEGORY_TITLES:
                category = base_category

        if category not in CATEGORY_TITLES:
            category = "Другое"
            confidence = 0.0
            reason = "AI вернул категорию вне разрешённой таксономии."

        confidence = max(0.0, min(1.0, confidence))

        validated.append(
            {
                "id": pid,
                "category": category,
                "confidence": round(confidence, 3),
                "reason": reason,
            }
        )

    missing = source_ids - seen

    for pid in sorted(missing):
        validated.append(
            {
                "id": pid,
                "category": "Другое",
                "confidence": 0.0,
                "reason": "AI не вернул результат для товара.",
            }
        )

    return sorted(validated, key=lambda x: x["id"])


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    products = load_products(args.limit, args.offset)

    if not products:
        print("Товаров «Другое» не найдено.")
        return

    print(f"Загружено товаров: {len(products)}")
    print(f"Диапазон: offset={args.offset}, limit={args.limit}")
    print("РЕЖИМ: APPLY — БД БУДЕТ ИЗМЕНЕНА") if args.apply else print("РЕЖИМ: PREVIEW — БД НЕ ИЗМЕНЯЕТСЯ")
    print()

    result = []

    for start in range(0, len(products), 10):
        chunk = products[start:start + 10]

        print(
            f"AI batch {start + 1}-{start + len(chunk)} из {len(products)}...",
            flush=True,
        )

        prompt = build_prompt(chunk)
        raw = await call_deepseek(prompt)

        # RAW AI RESPONSE отключён — оставляем только нормализованный результат.

        chunk_result = parse_result(raw, chunk)
        result.extend(chunk_result)


    by_id = {p["id"]: p for p in products}

    # Первая безопасная волна:
    # применяем только уверенные классификации.
    # Спорные товары явно исключены из автоматического применения.
    BLOCKED_IDS = {
        66, 86, 141, 166, 181, 305, 308, 309, 361, 371, 376,
    }

    safe_result = [
        item
        for item in result
        if item["category"] != "Другое"
        and item["confidence"] >= 0.85
        and item["id"] not in BLOCKED_IDS
    ]

    changed = 0
    stayed = 0

    for item in result:
        old = by_id[item["id"]].get("subcategory") or "Другое"

        if item["category"] == "Другое":
            stayed += 1
        else:
            changed += 1

        print(
            f"[{item['id']}] "
            f"{by_id[item['id']]['name']} | "
            f"{item['category']} | "
            f"{item['confidence']:.2f}"
        )

    print("=" * 80)
    print(f"Всего:              {len(result)}")
    print(f"AI предложил смену: {changed}")
    print(f"Безопасно к применению: {len(safe_result)}")
    print(f"Оставить Другое:    {stayed}")

    if args.apply and safe_result:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = Path(f"category_enrichment_backup_{stamp}.csv")

        with backup_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "id",
                "name",
                "old_subcategory",
                "new_subcategory",
                "confidence",
                "reason",
            ])

            for item in safe_result:
                product = by_id[item["id"]]
                writer.writerow([
                    item["id"],
                    product["name"],
                    product.get("subcategory") or "",
                    item["category"],
                    item["confidence"],
                    item["reason"],
                ])

        con = sqlite3.connect(PRODUCTS_DB)

        for item in safe_result:
            con.execute(
                """
                UPDATE products
                SET subcategory = ?
                WHERE id = ?
                  AND (
                      COALESCE(TRIM(subcategory), '') IN (
                          'Другое',
                          'Все товары категории'
                      )
                      OR (
                          COALESCE(TRIM(subcategory), '') = ''
                          AND COALESCE(TRIM(category), '') = 'Другое'
                      )
                  )
                """,
                (item["category"], item["id"]),
            )

        con.commit()
        con.close()

        print()
        print(f"ПРИМЕНЕНО:          {len(safe_result)}")
        print(f"CSV-БЭКАП:          {backup_path}")


if __name__ == "__main__":
    asyncio.run(main())
