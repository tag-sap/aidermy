# AI_HANDOFF — двухфазная оценка совместимости

Обновлено: 2026-10-13

## Контракт двух фаз

### Phase 1 — допуск (обязательная, до Phase 2)
- Детерминированная проверка ограничений (`backend/app/phase1.py`).
- Блокирующие ветви: `irritation`, `sensitization` (пороги ПРЕДВАРИТЕЛЬНЫЕ: 0.7 / 0.5).
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
- `backend/app/models.py` — `CheckResponse` с phase1-полями.

## Команды запуска тестов
```bash
cd /var/www/aidermy/backend
ANALYSIS_USE_POSTGRES=false CATALOG_READ_FROM_POSTGRES=false ./venv/bin/python3 -m pytest
```

## Известные ограничения
- Пороги Phase 1 (0.7 / 0.5) и λ=1.0 — ПРЕДВАРИТЕЛЬНЫЕ, не откалиброваны по независимым меткам.
- Заблокированные/недостаточно определённые результаты НЕ сохраняются в таблицу `analysis` (пересчитываются при каждом запросе); статус не теряется в API, но не персистируется в history.
- 9 предсуществующих падающих тестов (PostgreSQL-подключение и LLM-отчёт) не связаны с Phase 1.
