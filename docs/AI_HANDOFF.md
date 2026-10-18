# AI_HANDOFF — двухфазная оценка совместимости

Обновлено: 2026-10-13 (Phase 1 v2.0.0; merge 8d19c04; регрессия 132 passed)

## Контракт двух фаз

### Phase 1 — допуск (обязательная, до Phase 2)
- Детерминированная проверка ограничений (`backend/app/phase1.py`).
- `PHASE1_VERSION = "2.0.0"`. Все оси `AXES` отслеживаются; ось блокирует только при профильном multiplier > 1.0. Порог вычисляется как `2.0 - multiplier` (multiplier ограничивается диапазоном [1, 2]); при multiplier <= 1.0 порог отсутствует и ось не блокирует. Нагрузка сравнивается с порогом без повторного масштабирования профилем.
- Статусы: `passed`, `blocked`, `insufficient_data`.
- `blocked` → обычная Phase 2 НЕ выполняется; `score=None`; `recommendation_status="Не рекомендовано"`.
- `insufficient_data` → `score=None`; `recommendation_status="Недостаточно данных"`.
- `passed` → выполняется Phase 2.
- Отсутствие статуса НЕ означает `passed`. Запрещён fallback `phase1_status or "passed"`.

### Phase 2 — обычная персональная совместимость
- Запускается только при `passed`.
- Детерминированный Score Engine (`scoring_engine.py`), формула/веса/шкала не меняются.
- AI не определяет score/вердикт.

### Пользовательский score vs технический retrieval-вектор
- Пользовательский score — итоговая Phase 2 совместимость (0–100), только при `passed`.
- PPM / Product Vector / retrieval-векторы — внутреннее представление для подбора, НЕ финальный пользовательский score.

## Правила null и negative-only score
- `null` остаётся `null`, не превращается в `0`.
- `negative_only_score` — негативный балл только по факторам ограничений (без компенсации позитивом), при `blocked`.
- При `insufficient_data` негативный балл не выдумывается (`negative_only_score=None`).
- `UNKNOWN_SCORE_FLOOR=40` — не обходит контракт двух фаз.

## Фактические точки входа
- `backend/app/phase1.py` — evaluate_phase1, compute_negative_loads, compute_negative_only_score, recommendation_status.
- `backend/app/scoring_engine.py` — `pre_score_check` gate внутри `score_product_against_profile_canonical`.
- `backend/app/analysis_service.py` — интеграция gate, негативный балл, recommendation_status.
- `backend/app/decision_engine.py` — обработка `score=None` (verdict/summary для blocked/insufficient).
- `backend/app/services.py` — `check_product_with_ingredients` передаёт phase1-поля и сохраняет None.
- `backend/app/main.py` — `/api/check`, `/api/check-with-ingredients` возвращают phase1-поля; `score=None` при не-passed.
- `backend/app/shelf_service.py` — `score_product` возвращает blocked-анализ (не legacy-фолбэк `check_history`); `build_cabinet_payload` пробрасывает `phase1_status`/`recommendation_status`/`verdict` и не помечает blocked как «нужен речеек».
- `backend/app/models.py` — `CheckResponse` с phase1-полями.

## Команды запуска тестов
```bash
cd /var/www/aidermy/backend
ANALYSIS_USE_POSTGRES=false CATALOG_READ_FROM_POSTGRES=false ./venv/bin/python3 -m pytest
```

## Известные ограничения
- Динамическая схема порогов Phase 1 версии 2.0.0 реализована и покрыта тестами, но НЕ откалибрована по независимым меткам. Параметр `PHASE1_LAMBDA = 1.0` не является подтверждением калибровки.
- Реализовано сохранение blocked/insufficient результатов с nullable score (main.py/database.py) и чтение через полку (`shelf_service.score_product`). Тесты `tests/test_analysis_blocked_persistence.py` и `tests/test_blocked_persistence.py` проверяют сохранение и чтение. Production-деплой выполнен (commit `3391f90`, `b680abb`): smoke-тесты подтвердили blocked→score=NULL+статус, insufficient→score=NULL, passed→обычный score.
- 9 предсуществующих падающих тестов (PostgreSQL-подключение и LLM-отчёт) не связаны с Phase 1.

## 2026-10-13 — blocked report context
- `backend/app/services.py`: blocked phase now excludes positive factors from LLM report context and adds explicit grounding restrictions.
- Verification: py_compile passed; 12 focused report tests passed; git diff --check passed.
- Production success for ARAVIA analysis 1735 is not yet confirmed. Next: reload worker, check health, retry report, preserve strict grounding validation.

## 2026-10-13 — Phase 1 gate при чтении сохранённого анализа
- `backend/app/shelf_service.py`: нормализатор истории сохраняет Phase 1 metadata и скрывает обычный score при `blocked`/`insufficient_data`.
- `score_product()` теперь возвращает `None` вместо обычного score и не переходит к legacy fallback для этих статусов.
- `backend/tests/test_analysis_state.py`: добавлены два regression tests на блокировку возврата score/fallback.
- Verification: targeted pytest — 11 passed; `git diff --check` passed. Четыре предупреждения `datetime.utcnow()` в `app/database.py`.
- Production health до применения патча: HTTP 200. Production rollout и smoke test ещё не подтверждены.
- Следующий шаг: установить активный Gunicorn listener, применить патч безопасным reload и проверить Phase 1 в production.

## 2026-10-13 — Phase 1 gate при чтении сохранённого анализа
- `backend/app/shelf_service.py`: блокируется возврат обычного score для `blocked` и `insufficient_data`, включая legacy fallback.
- `backend/tests/test_analysis_state.py`: два регрессионных теста; targeted pytest — 11 passed, `git diff --check` passed.
- Production health до rollout: HTTP 200; production smoke test после патча ещё не выполнен.
- Следующий шаг: graceful reload Gunicorn и проверка production.

- 2026-10-13: `review_shelf_product()` защищён от утечки сохранённого обычного score при `blocked`/`insufficient_data`; версия отчёта — `1.0.1`. Три целевые группы тестов: 29 passed. Production reload и реальное повторное открытие отчёта ещё не подтверждены.


## 2026-10-14 — Supabase Analysis persistence patch

- Commit `3050f3e8b71f17a62f9bf458241cae169045e522` adds the explicit `ANALYSIS_STORAGE=postgres` adapter in `backend/app/database.py`; SQLite remains the default until the production flag is changed. Profile timestamps still come from SQLite `users`.
- `clear_analysis_history()` deletes canonical Analysis in Supabase and legacy user-linked history in SQLite when PostgreSQL mode is enabled; these operations are not cross-database atomic.
- Production server pulled the code commit. Backup created at `backend/backups/aidermy_pre_supabase_20261014_133209.db`.
- Supabase schema inspection returned `is_identity='YES'`, `identity_generation='BY DEFAULT'`, and `pg_get_serial_sequence('public.analysis','id')='public.analysis_id_seq'`. Therefore ID generation is already configured and the original migration's `ALTER SEQUENCE ... OWNED BY` is incompatible with the existing identity sequence.
- The first migration attempt failed at that `OWNED BY` statement. Do not rerun the original SQL. The migration file was patched on branch `fix/identity-safe-analysis-migration-20261014` to no-op for identity-backed columns and to configure a sequence only for a legacy integer column without a default.
- Not yet verified: persistence tests, production `ANALYSIS_STORAGE` flag, service restart, and a Supabase write/read/delete smoke test. The flag remains disabled pending those steps.
- Next: merge the identity-safe migration/doc correction, pull it on production, inspect existing configuration without exposing secrets, then enable `ANALYSIS_STORAGE=postgres`, restart the service, and run a disposable exact-row persistence smoke test.

## 2026-10-15 — Stale Match Phase 1 persistence

- `backend/app/shelf_service.py`: stale recalculation now persists `blocked`/`insufficient_data` even when ordinary score is `None`.
- Regression test in `backend/tests/test_score_engine_versioning.py`: targeted test passed (1 passed); `py_compile` and `git diff --check` passed.
- Full test file still has a separate PostgreSQL `expires_at` type mismatch; not attributed to this patch.
- This does not yet prove every API/PPM path respects phase order.
- Next: trace API entry points and PPM/Product Vector flow, then plan a narrow production rollout.


## 2026-10-15 — Сохранение решений Phase 1 при пересчёте Match

- `backend/app/main.py`: при результате без обычного score статусы `blocked` и `insufficient_data` сохраняются через `_save_system_analysis`; API возвращает идентификатор анализа, если сохранение удалось.
- `backend/app/shelf_service.py`: stale-пересчёт не отбрасывает детерминированное решение Phase 1 со статусом `blocked` или `insufficient_data` только из-за отсутствия обычного score.
- `backend/tests/test_score_engine_versioning.py`: целевой регрессионный тест прошёл — 1 passed. `py_compile` и `git diff --check` прошли.
- Коммит: `9984fdf` (`fix: persist phase-one blocked shelf analyses`), отправлен в `origin/main`.
- Production: Gunicorn перезапущен; новый master PID `198128`, worker PID `198130`; `/openapi.json` вернул HTTP 200 после перезапуска.
- Ограничение проверки: доступность OpenAPI не подтверждает сквозное поведение всех сценариев Phase 1 → Phase 2. Полный порядок фаз и остальные API-пути ещё требуют адресной проверки.
- Следующий шаг: проверить оставшиеся пути повторной проверки и обработки результата, затем провести один сквозной сценарий заблокированной Phase 1 без запуска полного аудита.


## 2026-10-15 — Текущее состояние: единый score / порядок двух фаз

Эта запись актуализирует контракт реализации; более ранние упоминания `negative_only_score` ниже по истории являются устаревшим описанием предыдущего варианта.

- `passed`: используется обычный канонический Score Engine с положительными и отрицательными факторами.
- `blocked`: положительные эффекты не должны компенсировать блокировку Phase 1; для заблокированного результата используется согласованный канонический score, а статус рекомендации имеет приоритет в пользовательском представлении.
- `insufficient_data`: score остаётся `None`; пригодность продукта не выдумывается.
- `negative_only_score` и `compute_negative_only_score` не являются частью целевого контракта единого score. Перед публикацией нужно подтвердить, что связанные API, persistence, report и shelf-пути согласованы.
- Покрытие знаний определяется данными по ингредиентам, а не простым отсутствием `positive_factors`. Добавлен тест `test_positive_factor_cannot_resolve_fully_unknown_ingredient_coverage`.
- Проверка: целевые тесты `test_phase1.py`, `test_api_phase1.py`, `test_report_flow.py`, `test_report_phase_status.py`, `test_blocked_persistence.py` — **53 passed, 22 warnings**; `git diff --check` прошёл.
- Коммит, push, production deploy и smoke test для этого набора изменений пока не подтверждены.
- Следующий шаг: проверить точный diff и выбрать только относящиеся к патчу файлы для staging; сохранить остальные изменения и артефакты без удаления.

## 2026-10-16 — Phase 1 / единый score: регрессия перед reload

- Целевой набор: 68 passed, 12 warnings за 2.19s; `git diff --check` прошёл.
- Предупреждения: `datetime.utcnow()` в `backend/app/database.py:1199` и `:1203`.
- Удалён неиспользуемый импорт `HARD_FLAG_SCORE_CAP` из `backend/app/scoring_engine.py`; формула, веса и пороги этим изменением не менялись.
- Резервная копия: `/var/backups/aidermy-phase-order-20261016-012950`.
- До reload API `/openapi.json` отвечал HTTP 200; master PID `198128`, текущий worker PID `198546`.
- Следующий шаг: подтвердить reload сменой worker и повторным HTTP smoke check. До этой проверки production-загрузка текущего кода не считается подтверждённой.

- Reload 2026-10-16 подтверждён: master PID 198128, worker сменился с 198546 на 212835, `/openapi.json` вернул HTTP 200. Сквозной сценарий Phase 1 → Phase 2 на production отдельно не проверен.

## 2026-10-16 — Результат регрессионной проверки двух фаз

- После production reload повторно выполнено: `venv/bin/python -m pytest -q tests/test_decision_engine.py tests/test_score_neutral.py tests/test_phase1.py` из `backend/`.
- Результат: **40 passed in 0.14s**.
- Расширенный релевантный набор, выполненный ранее в этой сессии: **68 passed, 12 warnings**.
- Gunicorn master `198128` поднял worker `212835`; локальный запрос к `/openapi.json` вернул HTTP 200.
- Не утверждать, что сквозной пользовательский production-сценарий подтверждён: реальная оценка продукта через API после reload ещё не проверена.
- Следующий шаг: проверить `git diff --check`, `git status --short` и diff только относящихся к задаче файлов; затем выбрать безопасный непишущий smoke test API.


## 2026-10-16 — порядок двух фаз скоринга

- Изменён `backend/app/scoring_engine.py`: агрегация осевых вкладов отложена до успешного результата Phase 1; при `blocked` используется отдельный набор отрицательных нагрузок; при `insufficient_data` числовая оценка не рассчитывается.
- Добавлен регрессионный тест `test_phase1_runs_before_axis_aggregation` в `backend/tests/test_phase1.py`: проверяет, что callback Phase 1 получает ещё не агрегированные оси, а после `passed` итоговые оси рассчитываются.
- Проверки: `venv/bin/python -m pytest -q tests/test_phase1.py tests/test_decision_engine.py tests/test_scoring_engine.py`; `git diff --check`. Результат фиксируется по фактическому выводу команды выше.
- Production не перезапускался; деплой не подтверждён.
- Следующий шаг: изучить итоговый diff только этих изменений, затем выполнить согласованный production rollout и health check. Существующие изменения и резервные файлы не удалять.

## 2026-10-16 — production rollout порядка двух фаз

- Регрессионный тест `test_phase1_runs_before_axis_aggregation` добавлен в `backend/tests/test_phase1.py`.
- Проверки перед rollout: `venv/bin/python -m pytest -q tests/test_phase1.py tests/test_decision_engine.py tests/test_scoring_engine.py` — 37 passed; `git diff --check` прошёл.
- Production: Gunicorn master PID 198128 получил HUP; новый worker PID 214149 запустился, прежний worker штатно завершился.
- Health check после reload: `/api/health` вернул HTTP 200, `{"status":"ok","deepseek":"connected"}`.
- Ограничение: health check подтверждает доступность API, но не заменяет сквозную проверку пользовательского анализа.
- Следующий шаг: проверить реальный анализ продукта и подтвердить, что при блокировке Phase 1 положительные эффекты Phase 2 не компенсируют отрицательные факторы.
