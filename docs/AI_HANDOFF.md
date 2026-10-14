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


## 2026-10-14 — Supabase Analysis persistence patch (not yet deployed)

- Branch: `fix/supabase-analysis-persistence-20261014`.
- `backend/app/database.py`: Analysis CRUD now routes through `get_analysis_connection()`; the explicit `ANALYSIS_STORAGE=postgres` flag selects Supabase while SQLite remains the default for safe rollout and tests. Profile timestamps continue to come from the existing SQLite `users` table.
- `backend/sql/20261014_analysis_id_sequence.sql`: creates a sequence/default for `public.analysis.id`, which had no default and would reject new inserts.
- `clear_analysis_history()`: retains the single SQLite transaction in SQLite mode; in PostgreSQL mode it deletes canonical Analysis in Supabase and legacy user-linked history in SQLite (cross-database atomicity is not possible).
- Verified facts before patch: Supabase `public.analysis` had 0 rows, primary key on `id`, and no ID default. Existing Analysis functions used SQLite.
- Not yet verified: Python tests, execution of the SQL sequence migration, production environment flag, deployment, and production write/read smoke test.
- Next: inspect the branch diff, run focused persistence tests, apply the SQL file to Supabase, deploy code, set `ANALYSIS_STORAGE=postgres` in production `.env`, restart service, then create/read/delete one test Analysis and confirm it exists in Supabase.
