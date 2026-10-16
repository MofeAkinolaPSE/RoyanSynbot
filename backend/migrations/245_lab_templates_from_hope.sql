-- 245: a result template for every lab test Royan has run, built from Hope's history, so the lab only types values.
-- Hope recorded each result as one row per parameter ({"parameter", "result", "uom", "range"}). For each test this
-- takes the parameters that appear on at least a fifth of its orders (and at least twice), in the order the lab
-- entered them, with the most recent unit and normal range. The Record Result panel pre-fills these lines
-- (GET /lab/parameters); the report prints them. Tests that already have an active template are left alone.
-- Additive only.
BEGIN;
WITH r AS (
    SELECT o.id AS oid, o.test_name AS test, o.test_code, o.ordered_at,
           trim(x.result_data->>'parameter') AS p,
           NULLIF(trim(x.result_data->>'uom'), '') AS u,
           NULLIF(trim(x.result_data->>'range'), '') AS rg,
           row_number() OVER (PARTITION BY o.id ORDER BY x.id) AS pos
    FROM royan_lab_results x
    JOIN royan_lab_orders o ON o.id = x.lab_order_id
    WHERE x.external_source IS NOT NULL AND x.result_data ? 'parameter' AND o.test_name IS NOT NULL
), n AS (
    SELECT test, COUNT(DISTINCT oid) AS orders, max(test_code) AS test_code FROM r GROUP BY test
), p AS (
    SELECT test, p, COUNT(DISTINCT oid) AS k, avg(pos) AS apos,
           (array_agg(u ORDER BY ordered_at DESC) FILTER (WHERE u IS NOT NULL))[1] AS unit,
           (array_agg(rg ORDER BY ordered_at DESC) FILTER (WHERE rg IS NOT NULL))[1] AS rng
    FROM r WHERE p IS NOT NULL AND p NOT IN ('', '.', '-') GROUP BY test, p
), kept AS (
    SELECT p.*, n.test_code FROM p JOIN n USING (test)
    WHERE p.k >= GREATEST(2, 0.2 * n.orders)
), t AS (
    SELECT test, max(test_code) AS test_code,
           jsonb_agg(jsonb_build_object(
               'name', p, 'unit', unit, 'reference_range', rng,
               'normal_low', CASE WHEN rng ~ '^\s*[0-9]+(\.[0-9]+)?\s*-\s*[0-9]+(\.[0-9]+)?\s*$'
                                  THEN split_part(regexp_replace(rng, '\s', '', 'g'), '-', 1)::numeric END,
               'normal_high', CASE WHEN rng ~ '^\s*[0-9]+(\.[0-9]+)?\s*-\s*[0-9]+(\.[0-9]+)?\s*$'
                                   THEN split_part(regexp_replace(rng, '\s', '', 'g'), '-', 2)::numeric END
           ) ORDER BY apos) AS analytes
    FROM kept GROUP BY test
)
INSERT INTO royan_lab_test_templates (test_name, catalog_id, version, analytes, is_active, created_by)
SELECT t.test,
       (SELECT c.id FROM royan_lab_catalog c WHERE c.code = 'HOPE' || t.test_code OR upper(c.name) = upper(t.test)
        ORDER BY (c.code = 'HOPE' || t.test_code) DESC LIMIT 1),
       COALESCE((SELECT max(version) + 1 FROM royan_lab_test_templates x WHERE x.test_name = t.test), 1),
       t.analytes, true, 'hope_history'
FROM t
WHERE NOT EXISTS (SELECT 1 FROM royan_lab_test_templates x WHERE upper(x.test_name) = upper(t.test) AND x.is_active);
COMMIT;
