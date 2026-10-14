-- Run once against the configured Supabase PostgreSQL database before
-- setting ANALYSIS_STORAGE=postgres in the production .env.
CREATE SEQUENCE IF NOT EXISTS public.analysis_id_seq;

ALTER SEQUENCE public.analysis_id_seq
    OWNED BY public.analysis.id;

ALTER TABLE public.analysis
    ALTER COLUMN id SET DEFAULT nextval('public.analysis_id_seq'::regclass);

SELECT setval(
    'public.analysis_id_seq'::regclass,
    GREATEST(COALESCE((SELECT MAX(id) FROM public.analysis), 0) + 1, 1),
    false
);
