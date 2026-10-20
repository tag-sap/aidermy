-- 2026-10-19: семантика взаимодействий для слоя замещения.
--
-- effect_kind:
--   'delta'    — величина изменения относительно индивидуальных эффектов (legacy).
--                НЕ допускается к замещению: полный совместный эффект восстановить нельзя.
--   'absolute' — полный совместный эффект пары на указанной оси (допускается к замещению
--                при подтверждённом источнике и confidence >= DEFAULT_CONFIDENCE_THRESHOLD).
--
-- Значение по умолчанию 'delta' сохраняет прежнее поведение для существующих записей.

ALTER TABLE public.ingredient_interactions
    ADD COLUMN IF NOT EXISTS effect_kind TEXT NOT NULL DEFAULT 'delta';

-- Диагностика: сколько записей допускается к замещению по семантике.
-- (Фактический допуск дополнительно проверяет confidence/source_type/evidence в коде.)
SELECT effect_kind, COUNT(*) FROM public.ingredient_interactions GROUP BY effect_kind;
