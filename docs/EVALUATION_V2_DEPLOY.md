# Evaluation V2 — развёртывание и эксплуатация

Документ описывает, как включить новую механику анализа на сервере **без** изменения
production-данных в рамках этой работы. Ни одна миграция здесь не применена к
production/staging, деплой не выполнялся.

## 1. Что переиспользуется из Aidermy

| Возможность | Существующий компонент | Как используется в V2 |
|---|---|---|
| DeepSeek | env `DEEPSEEK_API_KEY` / `DEEPSEEK_API_URL`, модели `deepseek-chat`, `deepseek-v4-flash`, `deepseek-flash` | `evaluation/llm_research.py` (свой минимальный клиент, тот же endpoint/ключ; модель-фолбэк как в проекте) |
| Поиск источников | `app/product_identification.search_web_urls` (DuckDuckGo HTML, UA, retry, фильтр рекламы) | `evaluation/websearch.py` — тонкий адаптер, без второго поискового клиента |
| Загрузка страниц | `httpx` (уже в requirements), SSRF-подход как в `scraper.service.validate_public_url` | `evaluation/documents.py::HttpDocumentFetcher` (проверка каждого редиректа, лимит размера) |
| Каталог продуктов и INCI | `app.database.get_product_by_id` (в PG-режиме идёт в Supabase `public.products`) | `evaluation/knowledge.py` |
| Supabase | `app/postgres_connection.get_postgres_connection` (`SUPABASE_DATABASE_URL`) | `evaluation/postgres_store.py` |
| Аутентификация | `app.auth.get_current_user` (JWT) | все пользовательские эндпоинты V2 |
| Админ-доступ | `app.admin_routes.verify_admin` (HTTP Basic) | `/analyze/research`, `/products/{id}/research`, `/research-jobs` |
| Логи | стандартный `logging` приложения | `[EVALUATION]` строки: статус, пробелы, число источников, ошибки |

## 2. Переменные окружения

| Переменная | Обязательна | По умолчанию | Назначение |
|---|---|---|---|
| `SUPABASE_DATABASE_URL` | да (для хранения) | — | PostgreSQL/Supabase; без неё V2 отвечает 503, приложение работает |
| `DEEPSEEK_API_KEY` | да (для исследования) | — | без неё `/analyze` работает, `/analyze/research` → 503 |
| `DEEPSEEK_API_URL` | нет | `https://api.deepseek.com/v1/chat/completions` | endpoint |
| `AIDERMY_EVALUATION_ENABLED` | нет | `1` | `0` — полностью отключить регистрацию роутов V2 |
| `AIDERMY_FETCH_ENABLED` | нет | `1` | `0` — не скачивать страницы (только известные документы) |
| `AIDERMY_SEARCH_ENABLED` | нет | `1` | `0` — не искать новые URL |
| `AIDERMY_FETCH_TIMEOUT` | нет | `15` | таймаут загрузки страницы, сек |
| `AIDERMY_MAX_DOCUMENTS` | нет | `8` | документов на одну сессию |
| `AIDERMY_MAX_COST_PER_JOB` | нет | `0.50` | лимит стоимости одной задачи, USD |
| `AIDERMY_MAX_COST_PER_RUN` | нет | `5.00` | лимит стоимости прогона, USD |
| `AIDERMY_MAX_ATTEMPTS` | нет | `3` | попыток на параметр |
| `AIDERMY_LLM_MODELS` | нет | три модели DeepSeek | список моделей через запятую |
| `AIDERMY_LLM_PRICE_PER_1K` | нет | `0` | цена за 1k токенов для бюджета (задайте реальную) |

## 3. Миграции

Файлы (применять по порядку, идемпотентны):

1. `migrations/20261023_evaluation_v2.sql`
2. `migrations/20261024_evaluation_v2_statuses.sql`
3. `migrations/20261025_evaluation_v2_provenance.sql`
4. `migrations/20261026_evaluation_v2_documents.sql`

Скрипт с защитой от production:

```bash
cd backend
# локальная изолированная БД (по умолчанию только localhost + aidermy_eval_test*)
EVALUATION_TEST_DSN=postgresql://... python scripts/apply_evaluation_migrations.py --dry-run
EVALUATION_TEST_DSN=postgresql://... python scripts/apply_evaluation_migrations.py

# staging: только осознанно, с двумя подтверждениями
AIDERMY_ALLOW_REMOTE_MIGRATIONS=1 \
  python scripts/apply_evaluation_migrations.py --dsn "$STAGING_DSN" --allow-remote --yes
```

Проверка схемы после применения:

```bash
EVALUATION_TEST_DSN=... python scripts/evaluation_test_env.py
```

Ожидается 9 таблиц в схеме `evaluation`, включая `source_documents`.

После миграций обязательно зарегистрировать версию правил и реестр параметров
(идемпотентно). Без этого research падает на вставке снапшота с
`rule version ... is not registered`:

```bash
cd backend
python scripts/seed_evaluation_v2.py --yes
# rule_version=3.0.0-draft calibrated=False
# method_version=research-1.0.0-draft parameters=...
```

В production-рабочей копии SQL лежит в `backend/sql/`; скрипт миграций ищет
`*evaluation_v2*.sql` и в `backend/migrations/`, и в `backend/sql/`.

## 4. Проверка после деплоя

```bash
curl -s https://<host>/api/v1/evaluation/health | jq
# storage.configured=true, schema.ready=true,
# research.provider="llm", fetcher="http", search="duckduckgo"
```

Пользовательский путь (JWT):

```bash
curl -s -X POST https://<host>/api/v1/evaluation/products/123/status \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"profile": {"skin_type": "dry", "concerns": ["dryness"]}}' | jq '.analysis'
```

Админский путь. Эндпоинт требует одновременно JWT пользователя и admin Basic,
поэтому Basic передаётся отдельным заголовком `X-Admin-Authorization` (обычный
`Authorization: Basic` тоже поддерживается, но он затирает Bearer):

```bash
curl -s -X POST https://<host>/api/v1/evaluation/products/123/research \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Admin-Authorization: Basic $(printf 'admin:%s' "$ADMIN_PASSWORD" | base64 -w0)" \
  -H 'Content-Type: application/json' \
  -d '{"profile": {"skin_type": "dry", "concerns": ["dryness"]}, "verify_catalog_inci": true}' | jq '.analysis'
```

`analysis.status=complete` и `is_final=true` означают готовый отчёт; `incomplete`
означает, что часть параметров осталась без подтверждённых данных (это видно в
`analysis.gaps`), `failed` — техническая ошибка провайдера, `blocked` — состав не
подтверждён.

## 4.1. Интерфейс

В `figma-make-preview` добавлена панель «Оценка состава · V2» в существующем drawer
продукта (для авторизованных пользователей). Она не заменяет текущий отчёт:

- показывает `analysis.status`, итог (или «нет подтверждённых оценок»), оценки по
  параметрам с обоснованием, непроверенные пункты и число источников;
- кнопка «Обновить» вызывает `/products/{id}/analyze` (без расходов на исследование);
- админское исследование остаётся HTTP-операцией (`/products/{id}/research`).

Включается только при сборке фронтенда:

```bash
cd figma-make-preview
VITE_EVALUATION_V2=1 npm run build
```

Без переменной (`VITE_EVALUATION_V2` не задана) панель не рендерится и поведение
сайта не меняется. Перед включением убедитесь, что backend V2 развёрнут и
`/api/v1/evaluation/health` отвечает 200.

## 5. Контролируемая проверка DeepSeek (одна платная операция)

Выполняется только вручную, один запрос:

```bash
cd backend
DEEPSEEK_API_KEY=... python scripts/evaluation_live_check.py \
  --url https://<brand-page> --parameter problem:dryness --yes
```

Скрипт: скачивает одну страницу, отправляет один запрос, проверяет цитаты по
сохранённому тексту, печатает статус/токены/стоимость. Без `--yes` и без ключа
он отказывается работать.

## 6. Ограничения и откат

- Миграции аддитивные, `NOT VALID`; откат — отключить `AIDERMY_EVALUATION_ENABLED=0`
  (роуты исчезнут, таблицы останутся и не влияют на legacy).
- Источники находятся только по известным URL и через DuckDuckGo-поиск; отдельного
  платного поискового API нет.
- Вердикт выключен (`calibrated=false`), баллы не откалиброваны.
- Полный отчёт возможен только при подтверждённом составе; для продуктов каталога
  подтверждение делает админ явно (`verify_catalog_inci=true`).
