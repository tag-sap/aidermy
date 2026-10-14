-- Safe for both identity-backed and legacy integer-backed schemas.
-- Current Supabase schema may already define analysis.id as IDENTITY.
DO $$
DECLARE
    id_is_identity text;
    id_default text;
BEGIN
    SELECT is_identity, column_default
      INTO id_is_identity, id_default
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = 'analysis'
       AND column_name = 'id';

    IF id_is_identity = 'YES' THEN
        RAISE NOTICE 'public.analysis.id is already an identity column; no migration needed';
    ELSIF id_default IS NULL THEN
        CREATE SEQUENCE IF NOT EXISTS public.analysis_id_seq;

        ALTER TABLE public.analysis
            ALTER COLUMN id SET DEFAULT nextval('public.analysis_id_seq'::regclass);

        ALTER SEQUENCE public.analysis_id_seq
            OWNED BY public.analysis.id;

        PERFORM setval(
            'public.analysis_id_seq'::regclass,
            GREATEST(COALESCE(MAX(id), 1), 1),
            COALESCE(MAX(id), 0) > 0
        )
        FROM public.analysis;
    ELSE
        RAISE NOTICE 'public.analysis.id already has a default; no migration needed';
    END IF;
END
$$;
