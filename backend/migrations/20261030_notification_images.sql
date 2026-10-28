-- Превью проверенного средства/набора в уведомлениях.
-- Аддитивная и идемпотентная миграция: приложение также добавляет колонку
-- при старте (compat_store.ensure_schema), здесь — для ручного применения.
ALTER TABLE IF EXISTS public.user_notifications
    ADD COLUMN IF NOT EXISTS image_urls TEXT DEFAULT '';
