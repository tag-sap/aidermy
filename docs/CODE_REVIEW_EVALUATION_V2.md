# Code review: `feat/evaluation-v2`

Дата: 2026-10-23. Объём: 10 модулей `backend/app/evaluation/`, миграция, 4 файла тестов
(~1 900 строк кода и тестов). Ревью выполнено чтением кода + прогоном тестов;
дефекты, помеченные **fixed**, исправлены и покрыты тестами.

```
75 passed  (engine 34, service 10, postgres store 18, api 13)
```

## Критичные (fixed)

| ID | Место | Дефект | Как исправлено |
|---|---|---|---|
| C1 | `postgres_store.py` | `INSERT ... RETURNING` в `upsert_composition` и `enqueue_research` шёл через `_fetchone`, который закрывает соединение **без commit** → запись откатывалась. Тесты на fake-соединении этого не видели. | Добавлен `_fetchone_write` (обёртка `with conn:`), оба вызова переведены на него; добавлены тесты `test_upsert_is_committed`, `test_enqueue_returns_true_when_row_is_created` (проверяют `commits`). |
| C2 | `postgres_store.get_snapshot` / `snapshot.py` | Snapshot хэшируется по строковым полям, а из БД `created_at`/`verified_at` возвращались в другом формате, `completeness` — с другой точностью. Итог: `verify_snapshot()` падал бы на **каждом** чтении из Postgres. | В таблицу добавлена колонка `document jsonb`, хранящая канонический snapshot целиком; `get_snapshot` возвращает документ как есть (fallback на реконструкцию для пустого `{}`). Тесты: `test_document_is_returned_verbatim`, `test_existing_snapshot_is_returned_without_insert`. |

## Высокие (fixed)

| ID | Место | Дефект | Исправление |
|---|---|---|---|
| H1 | `api.create_research_jobs` | Любой авторизованный пользователь мог ставить AI-задачи → прямой расход денег. | Эндпоинт требует `require_admin` (переиспользует `verify_admin`), тест `test_research_requires_admin` (401/403). |
| H2 | `api.read_snapshot` | Snapshot с `user_id = NULL` (внутренний) читался любым авторизованным пользователем. | `owner is None` теперь тоже 403; тест `test_snapshot_of_another_user_is_forbidden` покрывает оба случая. |
| H3 | `snapshot.py` | Вес параметра округлялся до 6 знаков и попадал в snapshot: сторонний пересчёт из snapshot мог дать другой `total` (±1). | Вес пишется без округления; `total` и `weight` теперь согласованы в документе. |
| H4 | `freshness.py` | Невалидный `valid_until` молча считался «срока нет» → устаревшая оценка признавалась актуальной. | Возвращается причина «некорректный формат valid_until»; аналогично для `evaluated_at`. Тест `test_invalid_valid_until_is_treated_as_stale`. |

## Средние (fixed)

| ID | Место | Дефект | Исправление |
|---|---|---|---|
| M1 | `parameters.collect_signals` | Если `therapy`/`procedures` приходят словарём (`{"tretinoin": true}`), итерация по ключам давала мусорные ID и теряла флаг. | `_as_items()` нормализует list/dict/str; тест `test_dict_shaped_therapy_is_understood`. |
| M2 | `engine.py` | При `min_confidence > 0` оценка с `confidence=None` проходила как достоверная. | `None` трактуется как ниже порога; тест `test_min_confidence_excludes_unknown_confidence`. |
| M3 | `contracts.py` | Не валидировались: немонотонные/дублирующиеся `verdict_bands`, пустые бэнды при `calibrated=True`, нечисловые якоря. | Добавлены проверки + 3 теста. |
| M4 | `store.InMemoryStore` | `upsert_composition` не обновлял `source`/`verified_at`, в отличие от Postgres → тесты могли проходить по-разному. | Реализации выровнены. |
| M5 | `postgres_store.py` | Мёртвая функция `evaluation_to_params`. | Удалена. |

## Низкие (accepted / documented)

| ID | Замечание | Решение |
|---|---|---|
| L1 | Причины в `ParameterResult.reason` — русские пользовательские строки внутри технического API. | Принято: продукт русскоязычный; отчёт будет использовать их как есть. |
| L2 | Тесты обращаются к приватному `store._snapshots` для имитации подмены. | Принято: только в тестах, без влияния на прод-код. |
| L3 | Нет ограничения размера `profile` в теле запроса. | Открыто: включить лимит при регистрации роутера (uvicorn/nginx). |
| L4 | `/preview` использует `DEFAULT_METHOD_VERSION`, а не `app.state`. | Принято: движок не зависит от method_version (это поле freshness, а не расчёта). |
| L5 | Нет rate limiting на `/snapshots`. | Открыто: добавить на уровне nginx/бэкенда до включения роутера. |
| L6 | `require_admin` импортирует legacy `admin_routes` лениво внутри функции. | Принято: избегает тяжёлого импорта при загрузке пакета. |
| L7 | `snapshots.document` дублирует колонки (в 2 раза больше места на snapshot). | Принято сознательно: это цена гарантии целостности при чтении. Снимков мало (по одному на пользователя×продукт×версию). |

## Открытые вопросы, требующие решения (не дефекты кода)

1. **Миграция не применена** → поведение `PostgresStore` на живой схеме не проверено.
   Нужен staging-прогон: `seed_rule` → `ensure_composition` → `save_evaluation` →
   `build` → `verify_snapshot` после чтения из БД.
2. **RLS**: политика есть только для `snapshots`; остальные таблицы —
   service-role-only (документировано). Если когда-нибудь появится прямой клиент
   Supabase, политики придётся добавить.
3. **Нет AI-слоя** → `pending_parameters` пока только возвращается наружу, исследование
   не запускается.
4. **Калибровка не проведена** → `calibrated=false`, вердикт не выводится. Это
   намеренное состояние, а не баг.
5. **Стоимость**: research-эндпоинт закрыт админом и дедуплицирован, но лимитов
   на количество задач на продукт нет — задать перед включением.

## Вывод

Ветка пригодна к слиянию **только после** staging-проверки миграции и `PostgresStore`.
До этого она безопасна: роутер не зарегистрирован, миграция не применена, production
не изменён. Критичных дефектов в текущем состоянии не осталось; открытые пункты —
эксплуатационные (лимиты, RLS-политики, калибровка), а не логические.
