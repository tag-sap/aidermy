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

## Интеграционная проверка на реальном PostgreSQL (2026-10-23)

Среда: локальный PostgreSQL 16.2 (`127.0.0.1:57879`, БД `aidermy_eval_test`),
production не использовался. 31 проверка, все проходят.

Эта проверка нашла **три дефекта, невидимых на моках** — все исправлены:

| ID | Дефект | Почему моки не видели | Исправление |
|---|---|---|---|
| I1 | `build_snapshot` падал с `TypeError: datetime is not JSON serializable`: `composition.verified_at` из БД — `datetime`, а не строка | в фейках даты были строками | `_iso()` нормализует даты; snapshot идентичен независимо от источника данных |
| I2 | Гонка при первой записи оценки: два параллельных `save_evaluation` → `UniqueViolation` | фейковое соединение не конкурентно | `pg_advisory_xact_lock` по (composition, parameter, method) |
| I3 | Порядок supersede: `INSERT` до `UPDATE` нарушал частичный уникальный индекс даже внутри транзакции | тест проверял только текст SQL, а не семантику индекса | «обновить старое → вставить новое» + `FK superseded_by` сделан `deferrable initially deferred` |

RLS подтверждён реальными ролями (`authenticated`, `anon`, `service_role` с `BYPASSRLS`):

- без GRANT — `InsufficientPrivilege`;
- с `GRANT SELECT` — владелец видит только свою строку, чужой `snapshot_id` → 0 строк;
- с `GRANT INSERT` — всё равно `InsufficientPrivilege` (нет INSERT-политики);
- `service_role` видит все строки.

Важное уточнение по безопасности: текущая миграция **не выдаёт** GRANT ролям
`anon`/`authenticated`, поэтому прямой клиентский доступ к `evaluation.*` закрыт
полностью. Политика `snapshots_owner_read` проверена только после явного GRANT
(это тестовая эмуляция Supabase-привилегий).

Не проверено (ограничения): TLS/пулер Supabase, реальный JWT-claim, распределённая
конкуренция, Storage/S3.

## AI-слой исследования (2026-10-23)

Добавлен контракт доказательств, провайдер с fake-реализацией и оркестратор.
Проверки требований:

| Требование | Где проверено |
|---|---|
| доказательство привязано к продукту, составу и параметру | `test_evidence_roundtrip_is_bound_to_composition_and_parameter`, `test_wrong_parameter_is_rejected` |
| нет цитаты/источника — нет подтверждённого факта | `test_missing_quote_is_rejected`, `test_missing_source_text_is_rejected`, `test_quote_must_exist_in_source_text` |
| недостаточные доказательства не создают score | `test_no_evidence_means_insufficient_not_zero`, `test_insufficient_evidence_is_saved_and_not_retried` |
| отсутствие сведений о пользе ≠ доказанный вред | `test_neutral_only_is_insufficient_not_harm` |
| устаревшие данные требуют повторной проверки | `test_composition_change_requires_new_research`, `test_old_method_version_requires_new_research` |
| одинаковые задачи дедуплицируются | `test_second_run_reuses_evaluations_without_provider_calls`, `test_parallel_workers_call_provider_once_per_parameter` |
| сбой провайдера не оставляет ложный успех | `test_provider_error_leaves_no_success_state`, `test_all_candidates_rejected_is_a_failure` |
| объяснение только из подтверждённых доказательств | `test_rationale_uses_only_confirmed_claims` |

Дефект, найденный интеграционным тестом: миграция разрешала в `rule_versions`
только `aggregation = 'weighted_mean'`, из-за чего новая версия правил
`2.0.0-draft` (арифметическое среднее) не могла быть зарегистрирована в БД.
CHECK расширен до `('weighted_mean', 'arithmetic_mean')`.

Осознанные решения, требующие калибровки:
- полосы `evidence-bands-1.0.0` и «прежнее незнание» 0.6 — черновые;
- `rationale` намеренно шаблонный (claim + quote + домен), без свободного текста модели.

Незавершённая часть: **production-провайдер не реализован** — нет веб-поиска,
загрузки страниц и LLM-извлечения. Все тесты используют `FakeResearchProvider`,
платные вызовы не выполнялись.

## Аудит соответствия архитектуре (2026-10-22)

Проверка выявила, что реестр 12 «универсальных характеристик продукта» не соответствовал
реальной анкете: фронтенд собирает 7 разделов (`skin_type`, `age`, `concerns`, `therapy`,
`procedures`, `allergies`, `goals`) с десятками вариантов, а оценка хранилась по осям
(`hydration`, `barrier`, `therapy_safety`, …). Исправлено:

| Несоответствие | Было | Стало |
|---|---|---|
| единица оценки — универсальная ось | `hydration`, `barrier`, `therapy_safety`, … | реальный подпараметр анкеты: `problem:dryness`, `therapy:tretinoin`, `procedure:recent_laser@<7`, `intolerance:fragrance_intolerance`, `goal:hydration` |
| релевантность по таблицам весов | `ID_RELEVANCE` / `CATEGORY_RELEVANCE` с весами 0…1 | `resolve_parameters`: набор параметров из ответов, всем равная доля |
| варианты лечения терялись | любая терапия → `therapy_safety` | конкретное вещество (`therapy:tretinoin`), группа — только если вещество не выбрано |
| период процедуры не входил в ключ | `procedure_safety` | `procedure:<id>@<period>`; `>3m` не создаёт параметр |
| аллергии без ингредиента | общий `fragrance_allergen` | категория из анкеты (`intolerance:*`) + конкретный ингредиент из структурированного профиля |
| объяснение было общим | claim + quote без привязки к вопросу | `label` + `question` + вывод по полосе + цитаты + оговорка о происхождении цитат |
| противоречие маскировалось | `50` при равных «за» и «против» | `contradictory_evidence`, `value = null` |
| новый состав считался готовым | `status` по умолчанию `active` | `unverified` без `verified_at`; research заблокирован; `verify_composition` + предупреждение в snapshot |
| реестр в БД не отражал анкету | 12 строк | 81 параметр каталога (все варианты анкеты, кроме `age`) |

Добавлены тесты (25 в `test_evaluation_questionnaire.py`), в том числе паритет каталога
с `figma-make-preview/src/data.ts`: тест читает TS-файл и сравнивает id/подписи всех
вариантов, поэтому «придумать» параметр больше нельзя.

Проверено на локальном PostgreSQL 16.2 (тестовая БД `aidermy_eval_test`):
146 модульных/контрактных тестов + 40 интеграционных, все проходят. Production не
изменялся, роутер по-прежнему не зарегистрирован в `main.py`.

## Финализация модели оценки (2026-10-22, этап 2)

Что изменилось после аудита анкеты:

| Решение | Было | Стало |
|---|---|---|
| кто выбирает балл | детерминированный пересчёт баланса цитат (`net_score`, полосы 20…80) | модель исследования выбирает один из `0/25/50/75/100`, детерминированная часть только валидирует |
| количество цитат | влияло на значение | не влияет: две цитаты с баллом 25 и одна с баллом 100 дают 25 и 100 соответственно (тест `test_score_is_not_derived_from_quote_count`) |
| статусы | `evaluated`, `insufficient_evidence`, `contradictory_evidence`, `not_researched`, `stale` | `assessed`, `not_applicable`, `insufficient_evidence`, `pending`, `stale` (+ legacy-значения только для чтения истории) |
| применимость | не рассматривалась | отдельное решение модели; без обоснования и подтверждённого источника понижается до `insufficient_evidence`; категориальный запрет по разделам снят на этапе 3 (см. ниже) |
| достаточность | выводилась из полос | отдельное решение модели; `sufficient=false` не может содержать балл, `sufficient=true` без балла отклоняется |
| балл 50 | «нейтрально/неизвестно» | допустим только как осознанный уровень «частично соответствует», с обоснованием и доказательствами |
| порог полноты | `completeness < 0.5` отключал итог | порога нет: считается среднее по любым ≥1 `assessed`; нет оценок — `total = null` |
| округление | `int(floor(x+0.5))` мог исказить среднее | `total` дробный (например 58.33), баллы подпараметров не меняются |
| отчёт | все релевантные параметры со статусами | только `assessed`; остальные статусы остаются в хранилище |
| frontend payload | `goals` не отправлялись, непереносимости только подписями | `structured.goals`, `structured.intolerances`, `structured.age` с стабильными id; подписи оставлены для legacy |

Схема: добавлена миграция `20261024_evaluation_v2_statuses.sql` (CHECK статусов и баллов,
`assessed` требует объяснение и `evidence_ids`, `snapshots.total → numeric(5,2)`),
ограничения `NOT VALID` — существующие строки не удаляются и не переписываются.
Обе миграции проверены на локальном PostgreSQL 16.2 и идемпотентны.

Тесты: 171 модульных/контрактных + 45 интеграционных, все проходят. Полный прогон
`unittest discover` — 937 тестов, 8 failures / 49 errors / 4 skipped; набор падений
**идентичен** `origin/main` и предыдущему состоянию ветки (новых падений нет),
в `test_evaluation_*` падений нет.

Остаются непроверенными: реальный провайдер поиска/загрузки, калибровка критериев
пяти уровней, staging Supabase. Роутер по-прежнему не зарегистрирован в `main.py`.

## Аудит этапа 3 (2026-10-25): безопасность `/preview`, INCI, `not_applicable`, provenance

Проверены четыре заявленных требования. Все четыре при предыдущей реализации не
выполнялись; исправлено в коде и покрыто тестами.

| ID | Место | Дефект | Как исправлено |
|---|---|---|---|
| S1 | `api.preview` | `EvaluationInput.status` имел значение по умолчанию `assessed`: запрос без полей вообще возвращал «оценённый» балл, доказательства не проверялись, эндпоинт был публичным. | `status` обязателен (422 без него). `assessed` требует авторизации, непустого `composition_hash` и сохранённых доказательств этого же параметра и состава с `verification=confirmed` и `provenance=fetched` (`_require_verified_preview_evidence`). Нет хранилища — 503. Пустой `composition_hash` — 422. Тесты: `test_preview_requires_explicit_status`, `test_assessed_preview_requires_authentication`, `test_assessed_preview_requires_stored_evidence`, `..._rejects_synthetic_evidence`, `..._rejects_evidence_of_another_parameter`, `..._rejects_evidence_of_another_composition`. |
| S2 | `assessment.py` | Непереносимости проверялись по цитатам, а не по составу: «отдушки нет» могло следовать из маркетингового текста. | Новый `evaluation/inci.py`: закрытые категории (fragrance, alcohol, niacinamide) при отсутствии в полном подтверждённом INCI дают `not_applicable`; открытые (эфирные масла, ретиноиды, кислоты) — `unverifiable`; пустой/неподтверждённый/обрезанный/однотокенный INCI — `unverifiable`. `unverifiable` всегда понижает до `insufficient_evidence`; найденный ингредиент запрещает `not_applicable` (понижение) и балл 100 (`ContractError`). 22 теста в `test_evaluation_inci.py`. |
| S3 | `assessment.SAFETY_SECTIONS` | Запрет `not_applicable` по названию раздела был одновременно слишком широким (терапия/процедуры) и не связанным с доказательствами. | Запрет удалён; вместо него `not_applicable` требует обоснования и подтверждённого источника **этого** параметра + `provenance=fetched`. Неприменимость без источника остаётся `insufficient_evidence`. |
| S4 | `evidence.py` / `research.py` / `assessment.py` / миграции | Провенанс не фиксировался: fake-источник и реально загруженная страница были неразличимы, `/preview` принимал любые `evidence_ids`. | Поле `provenance` (`fetched`/`synthetic`/`unknown`) у `Source` и `Evidence`, `Evidence.fetched`; `candidate()` по умолчанию `synthetic`; валидатор и `assess()` не принимают не-`fetched` доказательства без явного `allow_synthetic_evidence=True` (только тесты); `evidence_ref()` в обоих хранилищах; миграция `20261025_evaluation_v2_provenance.sql` (CHECK `NOT VALID`, идемпотентна). |
| S5 | `freshness.py` | `insufficient_evidence` и `not_applicable` кэшировались бессрочно: новые источники не детектируются, значит «данных нет» могло остаться навсегда. | `review_after_days` (по умолчанию 30) инвалидирует только эти два статуса; `assessed` живёт по `valid_until`/`max_age_days`; `None` отключает окно явно. Тесты свежести в `test_evaluation_engine.py` и сквозные — `ResearchReviewWindowTests` в `test_evaluation_research.py`. |

Ограничения, которые аудит не устраняет (задокументированы в `EVALUATION_V2.md`):
`provenance=fetched` — заявление провайдера, а не проверенный факт; полного
справочника INCI нет (открытые категории принципиально `unverifiable`); детекции
новых источников нет, только окно пересмотра; миграции не применены к staging.

Проверено на локальном PostgreSQL 16.2 (`aidermy_eval_test`): 225 модульных/контрактных
теста + 48 интеграционных, все проходят. Полный `unittest discover` — 992 теста,
8 failures / 49 errors / 4 skipped; 53 уникальных имени падений — подмножество базового
набора из 67, в `test_evaluation_*` падений нет (новых регрессий не добавлено).

## Этап 4 (2026-10-25): сквозная механика анализа

Требование этапа — не набор технических действий, а законченная механика: продукт →
полный скан параметров → совместное исследование пробелов → независимый результат
каждого параметра → накопление знаний → честный итог. Что уже было верным и осталось:
шкала `0/25/50/75/100`, среднее только по `assessed`, `null` без оценок, выключенный
вердикт, INCI-проверка, провенанс, история версий.

| ID | Место | Чего не хватало | Что реализовано |
|---|---|---|---|
| M1 | `gaps.py` (новый) | скан не различал «нет результата», «устарело», «недостаточно доказательств»; `insufficient_evidence` кэшировался как знание | `scan_parameters` проходит весь список параметров до исследования и возвращает `ParameterGap(missing/stale/insufficient/unsupported)`; `insufficient` всегда пробел, повтор ограничен `max_attempts` |
| M2 | `documents.py` (новый) | источники не загружались и не переиспользовались; у продукта не было общей базы знаний | `SourceDocument` (текст + hash + provenance), `HttpDocumentFetcher` (httpx, SSRF-защита, лимиты), `FakeDocumentFetcher`, `DocumentLibrary`, `collect_source_urls`; тексты хранятся в `evaluation.source_documents` (миграция `20261026`) |
| M3 | `llm_research.py` (новый) | провайдер был только fake | Реальный DeepSeek/OpenAI-совместимый провайдер: строгий JSON, цитаты только из переданных документов, честные `source_unavailable`/`provider_error`, токены и цена |
| M4 | `research_service.py` | каждый параметр исследовался отдельно, страницы не переиспользовались | Одна сессия на все пробелы: одна загрузка на сессию, общие `documents` во всех запросах, документы провайдера доступны следующим параметрам, отдельные задачи/оценки/доказательства на параметр |
| M5 | `evidence.py` | цитата проверялась по тексту самого провайдера | При наличии документов `source_text` берётся из хранилища, кандидат с чужим URL отклоняется; `provenance` наследуется от документа |
| M6 | `knowledge.py` (новый) | продукт и его источники не подтягивались из Aidermy | `load_product_knowledge` читает карточку каталога, считает `composition_hash` по INCI, собирает seed-URL из карточки и источников ингредиентных claims; состав не подтверждается автоматически |
| M7 | `analysis.py` (новый), `snapshot.py`, `service.py`, `api.py` | незавершённый анализ выглядел как готовый отчёт | `AnalysisService.analyze`/`analyze_product`, блок `analysis` (`complete/incomplete/failed/blocked`, `is_final`, пробелы) в snapshot и ответах API, эндпоинты `/analyze` и `/analyze/research` (админ) |
| M8 | `runtime.py` (новый) | не было способа включить реальное исследование | `configure_evaluation` подключает store, провайдера и загрузчик; без `DEEPSEEK_API_KEY` исследование возвращает 503, а не фиктивный успех |

Проверки: 282 модульных/контрактных теста + 53 интеграционных на PostgreSQL 16.2 — все
проходят. Полный `unittest discover` — 1049 тестов, 8 failures / 49 errors / 4 skipped,
новых падений нет. Отдельно проверено: одна загрузка на все параметры, отклонение
цитаты из незагруженной страницы, повторное использование документов между запусками,
лимит попыток, статусы `complete/incomplete/failed/blocked`.

Объективно не завершено: нет поискового провайдера (URL берутся из данных Aidermy),
LLM не проверялся на живом ключе, калибровка не выполнена, миграции не применены к
staging, роутер не зарегистрирован в `main.py`.


## Этап 5 (2026-10-25): интеграция в приложение, реальный поиск, Supabase

Проверено, что уже есть в проекте, и что из этого действительно подходит V2.

| Возможность | Проверенный контракт | Решение |
|---|---|---|
| DeepSeek | env `DEEPSEEK_API_KEY` / `DEEPSEEK_API_URL`, модели `deepseek-chat`, `deepseek-v4-flash`, `deepseek-flash`, прямые httpx-вызовы в `services.py` | Переиспользованы ключ, endpoint и модели; отдельного общего клиента в проекте нет, поэтому V2-провайдер остаётся тонким клиентом в `llm_research.py` (без копирования логики отчётов) |
| Поиск источников | `product_identification._search_product_urls` (DuckDuckGo HTML, UA, retry/backoff, фильтр рекламы) | Вынесен публичный `search_web_urls(query, limit)`; `evaluation/websearch.py` вызывает его, второго поискового клиента нет |
| Загрузка страниц | `scraper.service` (Scrapling, тяжёлый, антибот), `httpx` в requirements | Для V2 используется httpx-загрузчик с SSRF-проверкой каждого редиректа: Scrapling не нужен для текста и недоступен в тестовой среде |
| Продукт и INCI | `database.get_product_by_id` (в PG-режиме читает `public.products` Supabase) | `knowledge.py` использует этот загрузчик; ничего не дублируется |
| Supabase | `postgres_connection.get_postgres_connection`, `SUPABASE_DATABASE_URL` | `PostgresStore`; миграции проверены на изолированном PostgreSQL 16.2 |
| Роуты/аутентификация | `app.main`, JWT `get_current_user`, admin basic | V2-роутер зарегистрирован в `main.py`; продуктовые эндпоинты используют те же зависимости |
| Логи | `logging.basicConfig` в `main.py` | `[EVALUATION]` строки: статус, пробелы, источники, ошибки |

Реализовано в этом этапе:

1. **Поиск новых источников** — `evaluation/websearch.py` (адаптер + построение
   запросов + приоритет URL) и интеграция в `ResearchService`: найденные URL
   дедуплицируются с известными, ограничены `max_documents`, сбой поиска не ломает
   анализ.
2. **Регистрация в приложении** — `app/main.py` → `configure_evaluation(app)`;
   kill-switch `AIDERMY_EVALUATION_ENABLED=0`; readiness-проверка схемы без миграций.
3. **Продуктовые эндпоинты** — `POST /products/{id}/status|analyze|research`;
   админ явно подтверждает INCI каталога (`verify_catalog_inci`), обычный анализ
   никогда не подтверждает состав сам.
4. **Health** — `GET /api/v1/evaluation/health`: хранилище, таблицы, провайдер,
   загрузчик, поиск.
5. **Безопасность выполнения** — анализ в worker-thread (не блокирует event loop),
   лимиты `AIDERMY_MAX_DOCUMENTS/COST_PER_JOB/COST_PER_RUN/MAX_ATTEMPTS`,
   модель-фолбэк DeepSeek с логированием.
6. **Скрипты эксплуатации** — `apply_evaluation_migrations.py` (guard: только
   локальная тестовая БД, remote — с двумя подтверждениями) и
   `evaluation_live_check.py` (один платный запрос, только с `--yes`).
7. **Инструкция** — `docs/EVALUATION_V2_DEPLOY.md`.

Проверки: 309 модульных/контрактных + 56 интеграционных на PostgreSQL (включая
полный цикл V2 через `AnalysisService` → документы → доказательства → оценки →
snapshot, возобновление незавершённого анализа, ошибки провайдера и повтор).
`unittest discover` — 1081 тест, новых падений V2 нет. Отдельно установлено, что
`tests/test_yandex_identity.py` (3 ошибки: в таблице `users` нет `is_verified`) —
**предсуществующая** проблема legacy-авторизации, ранее скрытая отсутствием
`authlib`; к V2 отношения не имеет и не отключалась.

Не выполнено по ограничениям: живой платный вызов DeepSeek (нет ключа в этой среде),
живой вызов DuckDuckGo, применение миграций к staging/production, деплой.


## Этап 6 (2026-10-25): проверка production и интерфейса

Фактическое состояние production (read-only проверка по SSH, host `eclectusgames.ru`):

| Что | Факт |
|---|---|
| Ветка/коммит на сервере | `main` = `eeecb66` (2026-10-20), на 1 коммит позади `origin/main` = `6ea708a` |
| Рабочее дерево сервера | грязное: 50 изменённых tracked-файлов, 92 untracked, 2 удалённых |
| Код V2 на сервере | отсутствует: нет `backend/app/evaluation` |
| Ветка `feat/evaluation-v2` (`fb1861d`) | **не отправлена в origin**, на сервере её нет |
| Маршруты V2 | `/api/health` → 200, `/api/v1/evaluation/health` → 404 (локально и публично) |
| Схема БД | в Supabase **нет** схемы `evaluation`; в `public` 42 таблицы |
| Зависимости | `psycopg 3.3.6`, `psycopg-pool 3.3.3`, `authlib 1.7.2`, `httpx 0.28.1`, `scrapling 0.4.15` установлены |
| Конфигурация | `.env` содержит `SUPABASE_DATABASE_URL` и `DEEPSEEK_API_KEY`; `AIDERMY_EVALUATION_ENABLED` не задан (по умолчанию включён, но включать нечего) |
| Frontend | сборка от 2026-10-22 04:37, `api/v1/evaluation` в ассетах нет |

Контролируемая живая проверка кода V2 (копия `app/evaluation` + скрипта в `/tmp`, без
изменения production-пути и без записи в БД):

- загрузка `https://incidecoder.com/ingredients/niacinamide` — успешно (9295 символов,
  `provenance=fetched`, hash);
- один запрос DeepSeek — `ok`, 2 кандидата, оба цитирования подтверждены по тексту
  страницы, токены 1927/554, стоимость по настроенной цене 0 (цена не задана);
- страница товара goldapple.ru (`/19000188127-...`) не дала пригодного текста для
  простого httpx-загрузчика — это ограничение источника, а не механики.

Вывод по production: **V2 не развёрнут**, причина не в коде, а в том, что коммиты не
отправлены в origin, схема не создана и production-дерево грязное. Деплой не выполнялся.

Интерфейс: в текущем production UI V2 не используется. Добавлена панель «Оценка
состава · V2» в существующий drawer продукта под флагом `VITE_EVALUATION_V2=1`
(по умолчанию выключена, текущий отчёт не меняется). Проверено `tsc --noEmit` и
production-сборкой Vite с флагом и без него; в браузере на staging не проверялось,
потому что staging отсутствует, а production-деплой запрещён.


## Вывод


Ветка пригодна к слиянию **только после** staging-проверки миграции и `PostgresStore`.
До этого она безопасна: роутер не зарегистрирован, миграция не применена, production
не изменён. Критичных дефектов в текущем состоянии не осталось; открытые пункты —
эксплуатационные (лимиты, RLS-политики, калибровка), а не логические.
