-- Backfill products.model using regex on item_name.
-- Only updates rows where model IS NULL.
-- Safe to re-run: existing non-null values are never touched.

UPDATE products
SET model = CASE

  -- 1. ThinkPad X1 two-word series (must come before generic ThinkPad)
  WHEN item_name ~* 'ThinkPad\s+X1\s+(Carbon|Yoga|Nano|Extreme)'
    THEN 'ThinkPad ' || initcap(
      (regexp_match(item_name, '(?i)ThinkPad\s+(X1\s+(?:Carbon|Yoga|Nano|Extreme))'))[1]
    )

  -- 2. ThinkPad generic: L580, T14s, E14, X280, etc.
  WHEN item_name ~* 'ThinkPad\s+[A-Z][0-9]{2,3}[a-zA-Z0-9]*'
    THEN 'ThinkPad ' || initcap(
      (regexp_match(item_name, '(?i)ThinkPad\s+([A-Z][0-9]{2,3}[a-zA-Z0-9]*)'))[1]
    )

  -- 3. IdeaPad: Slim3, Slim 5, L3, C34, etc.
  WHEN item_name ~* 'IdeaPad\s+(Slim\s*[0-9]+|[A-Z][0-9]{1,2})'
    THEN 'IdeaPad ' || initcap(
      (regexp_match(item_name, '(?i)IdeaPad\s+(Slim\s*[0-9]+|[A-Z][0-9]{1,2})'))[1]
    )

  -- 4. Latitude legacy e-series: E5400, E5550, etc. (before 4-digit rule)
  WHEN item_name ~* 'Latitude\s+[Ee][0-9]{4}'
    THEN 'Latitude ' || upper(substring(
      (regexp_match(item_name, '(?i)Latitude\s+([Ee][0-9]{4})'))[1], 1, 1
    )) || substring(
      (regexp_match(item_name, '(?i)Latitude\s+([Ee][0-9]{4})'))[1], 2
    )

  -- 5. Latitude modern 4-digit: 5300, 5320, 5590, etc.
  WHEN item_name ~* 'Latitude\s+[0-9]{4}'
    THEN 'Latitude ' || (regexp_match(item_name, '(?i)Latitude\s+([0-9]{4})'))[1]

  -- 6. Inspiron: word-boundary aware
  WHEN item_name ~* '\mInspiron\s+[0-9]{2,5}\M'
    THEN 'Inspiron ' || (regexp_match(item_name, '(?i)\mInspiron\s+([0-9]{2,5})\M'))[1]

  -- 7. Dell XPS
  WHEN item_name ~* '\mXPS\s+[0-9]{2}\M'
    THEN 'Dell XPS ' || (regexp_match(item_name, '(?i)\mXPS\s+([0-9]{2})\M'))[1]

  -- 8. Lenovo Legion
  WHEN item_name ~* '\mLegion\s+[A-Z0-9][A-Za-z0-9]*[0-9]'
    THEN 'Legion ' || initcap(
      (regexp_match(item_name, '(?i)\mLegion\s+([A-Z0-9][A-Za-z0-9]*[0-9][A-Za-z0-9]*)'))[1]
    )

  ELSE model  -- keep existing value unchanged
END
WHERE model IS NULL
  AND item_name IS NOT NULL;
