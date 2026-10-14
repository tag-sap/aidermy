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
- Реализовано сохранение blocked/insufficient результатов с nullable score (main.py/database.py) и чтение через полку (`shelf_service.score_product`, commit `b78e91b`). Тесты `tests/test_analysis_blocked_persistence.py` и `tests/test_blocked_persistence.py` проверяют сохранение и чтение. Сквозное production-поведение истории требует отдельного smoke-теста.
- 9 предсуществующих падающих тестов (PostgreSQL-подключение и LLM-отчёт) не связаны с Phase 1.
