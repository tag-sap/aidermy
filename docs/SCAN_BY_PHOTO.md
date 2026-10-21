# Скан по фото: единый сценарий

## Пользовательский интерфейс

Production-фронтенд — Vite-приложение `figma-make-preview`. В нём остались три режима:
`Скан по фото`, `Ссылка`, `Ручной ввод`. Отдельные кнопки «По фото упаковки» и
«По фото состава» из меню добавления удалены.

«Скан по фото» (`figma-make-preview/src/photo-scan.tsx`) требует два изображения
одного продукта:

1. лицевая сторона — бренд, название, вариант, объём, штрихкод;
2. задняя сторона — INCI, маркировка.

Пока оба фото не загружены, кнопка распознавания disabled. Каждое фото можно заменить
или удалить. После ошибки доступны «Повторить» (фото сохраняются) и «Заменить фото».

## Backend

`POST /api/product/scan`

```json
{
  "front_image": "data:image/jpeg;base64,...",
  "back_image": "data:image/jpeg;base64,..."
}
```

Сервис `backend/app/product_scan.py`:

1. `identify_product([front, back])` — существующий DeepSeek Vision; бренд, название,
   вариант, тип, объём, штрихкод;
2. `recognize_composition([back])` — существующий OCR INCI;
3. `find_product_candidates` — существующий matcher `product_dedup.match_score`,
   возвращает несколько кандидатов вместо случайного выбора;
4. `web_search_product` — существующий Web Search + scraper; официальный сайт бренда
   ранжируется выше каталога/продавца;
5. возвращает `ready` / `ambiguous` / `needs_confirmation` / `not_found` и черновик.

Сервис не пишет в БД и не запускает Score Engine.

## Сохранение карточки

Черновик подтверждает пользователь. `POST /api/products/create` расширен полями:

- `image_data_url` — лицевое фото; загружается в S3 через существующий `image_storage`;
- `source_url`, `volume`, `variant`, `barcode`, `category`, `source_type`.

Штрихкод и вариант хранятся в `products.barcode` / `products.variant` (обе колонки TEXT,
штрихкод не приводится к числу и сохраняет ведущие нули). Миграция:
`backend/sql/20261022_products_barcode_variant.sql`; для SQLite `init_db()` добавляет
колонки и partial unique index идемпотентно.

Если штрихкод уже принадлежит другой canonical-карточке, `POST /api/products/create`
возвращает `409 conflict` с существующим продуктом. Карточки не объединяются вслепую.

Сохранение идемпотентно: используется существующий
`product_dedup.find_or_create_canonical_product`. Повторный вызов не создаёт дубликат.
Подтверждённый состав из `official/verified` не перезаписывается более длинным INCI
из сканера/OCR.

После сохранения/выбора существующего продукта UI вызывает существующий `/api/check`
(Score Engine), а не считает score/вердикт на фронтенде.

## Ограничения

- DeepSeek Vision и S3 не проверялись live в локальной среде без ключей; pipeline
  проверен unit-тестами с моками Vision/S3 и реальным локальным matcher/DB.
- Web Search + scraper проверены live на `cosrx.com`: выбрана официальная карточка,
  извлечено 24 ингредиента (без мусорных блоков страницы).
- Штрихкод и вариант отображаются в карточке; штрихкод участвует в поиске/дедупликации
  как строгий идентификатор.
- `figma-make-preview` содержит старые API `/api/composition/recognize` и
  `/api/product/identify` для обратной совместимости других экранов; единый сценарий
  использует только `/api/product/scan`.
