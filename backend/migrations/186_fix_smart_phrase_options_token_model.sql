-- Migration 186: fix royan_smart_phrase_options linkage
--
-- Migration 185 modeled this as a per-phrase FK (smart_phrase_id), but
-- direct content inspection of Hope's smart_phrase_multiple showed
-- phrase_id actually references the {token:id::default} placeholder id
-- embedded inside a phrase_text, not a smart_phrases row -- and a single
-- option list can be reused across many different phrases. Table was still
-- empty (no data loaded under the old shape), so dropped and recreated
-- rather than migrated in place.

BEGIN;

DROP TABLE IF EXISTS public.royan_smart_phrase_options;

CREATE TABLE public.royan_smart_phrase_options (
    id              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    token_id        text        NOT NULL,
    list_name       text        NOT NULL,
    option_text     text        NOT NULL,
    sort_order      int         NOT NULL DEFAULT 0,
    external_source text,
    external_id     text
);

ALTER TABLE public.royan_smart_phrase_options
    ADD CONSTRAINT royan_smart_phrase_options_external_source_external_id_key
    UNIQUE (external_source, external_id);

CREATE INDEX idx_royan_smart_phrase_options_token
    ON public.royan_smart_phrase_options (token_id, list_name);

COMMIT;
