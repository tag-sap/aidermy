-- Add persistent product identifiers without rewriting the products table.
-- barcode stays TEXT to preserve leading zeroes; variant is a separate display value
-- when the package explicitly contains a line/variant name.
ALTER TABLE public.products
    ADD COLUMN IF NOT EXISTS barcode TEXT;

ALTER TABLE public.products
    ADD COLUMN IF NOT EXISTS variant TEXT;

CREATE INDEX IF NOT EXISTS idx_products_barcode
    ON public.products (barcode);

-- One canonical card per barcode. Partial index keeps legacy rows without barcode valid.
CREATE UNIQUE INDEX IF NOT EXISTS uq_products_barcode_canonical
    ON public.products (barcode)
    WHERE barcode IS NOT NULL AND btrim(barcode) <> '' AND is_canonical = 1;
