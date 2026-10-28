-- Кэш минимальной достоверной цены продукта (источник + дата проверки).
-- Аддитивная идемпотентная миграция; локальный SQLite-вариант создаёт
-- price_service.ensure_price_table().
CREATE TABLE IF NOT EXISTS public.product_prices (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL UNIQUE,
    price NUMERIC,
    currency TEXT DEFAULT '',
    volume TEXT DEFAULT '',
    volume_ml NUMERIC,
    source_url TEXT DEFAULT '',
    source_title TEXT DEFAULT '',
    checked_at TIMESTAMPTZ DEFAULT now()
);

-- Совместимость с таблицей, созданной до появления суррогатного ключа:
-- pg_adapter дописывает "RETURNING id" к INSERT, поэтому колонка нужна.
ALTER TABLE public.product_prices
    ADD COLUMN IF NOT EXISTS id BIGSERIAL;
