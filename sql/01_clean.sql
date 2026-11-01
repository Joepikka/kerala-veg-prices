-- Clean tomato/onion/potato records and build the daily series every analysis uses.
-- Rules (also in README):
--  1. Only Rs/quintal prices and tonne arrivals; anything else is excluded and counted.
--  2. Impossible prices are dropped: modal <= 0, modal > 30,000 Rs/q (Rs 300/kg), or modal outside
--     [0.5 x min, 2 x max] when min/max exist (typing errors such as an extra zero).
--  3. The two sources overlap on 27-31 Oct 2025; there the new source wins.
--  4. Exact duplicates (same market, date, crop, variety, grade, prices, arrivals) are removed.

CREATE OR REPLACE VIEW staged AS SELECT * FROM read_parquet('data/staging/mandi.parquet');

CREATE OR REPLACE TABLE dq_units AS
SELECT commodity, arrival_unit, price_unit, count(*) AS n
FROM staged WHERE commodity IN ('Tomato', 'Onion', 'Potato')
GROUP BY ALL ORDER BY commodity, n DESC;

CREATE OR REPLACE TABLE top_raw AS
SELECT * FROM staged
WHERE commodity IN ('Tomato', 'Onion', 'Potato')
  AND date BETWEEN DATE '2021-01-01' AND DATE '2026-05-31'
  AND NOT (source = 'old' AND date >= DATE '2025-10-27');

-- One market, one identity. The sources use different market codes (and the old source itself carries
-- two code systems that overlap from Jan 2021 to Mar 2023, so the same market-day appears twice).
-- A market is identified by state + its name without the "Apmc"/"Market" suffix and spaces.
-- Per market, day, crop, variety and grade one record is kept: new source first, then the newer
-- short code system, then the record with the larger arrivals.
CREATE OR REPLACE TABLE top_clean AS
WITH valid AS (
    SELECT
        date, state, district, lat, lon, commodity, variety, grade, market_code, source,
        regexp_replace(trim(market), '(\s+(Apmc|APMC|Market|market))+$', '')                                AS market,
        state || '|' || regexp_replace(regexp_replace(lower(trim(market)), '(\s+(apmc|market))+$', ''), '\s+', '', 'g') AS market_key,
        arrival_qty AS arrival_t, min_price, max_price, modal_price
    FROM top_raw
    WHERE replace(price_unit, '.', '') ILIKE 'Rs/Quintal'
      AND arrival_unit ILIKE '%tonnes'
      AND modal_price > 0 AND modal_price <= 30000
      AND (min_price IS NULL OR max_price IS NULL OR min_price <= 0
           OR modal_price BETWEEN 0.5 * min_price AND 2 * max_price)
)
SELECT * EXCLUDE (rn) FROM (
    SELECT *, row_number() OVER (
        PARTITION BY market_key, date, commodity, variety, coalesce(grade, '')
        ORDER BY (source = 'new') DESC, (market_code < 10000) DESC, arrival_t DESC NULLS LAST) AS rn
    FROM valid
) WHERE rn = 1;

CREATE OR REPLACE TABLE dq_clean AS
SELECT
    (SELECT count(*) FROM top_raw)                                   AS raw_rows,
    (SELECT count(*) FROM top_clean)                                 AS clean_rows,
    (SELECT count(*) FROM top_raw WHERE NOT (replace(price_unit, '.', '') ILIKE 'Rs/Quintal'
                                         AND arrival_unit ILIKE '%tonnes')) AS dropped_units,
    (SELECT count(*) FROM top_raw WHERE modal_price IS NULL OR modal_price <= 0 OR modal_price > 30000) AS dropped_price_range,
    (SELECT min(date) FROM top_clean)                                AS first_date,
    (SELECT max(date) FROM top_clean)                                AS last_date;

-- One row per market, day and crop: arrival-weighted modal across varieties/grades.
CREATE OR REPLACE TABLE market_day_all AS
SELECT
    date, commodity, state, market_key,
    arg_max(market, date) AS market, arg_max(district, date) AS district,
    any_value(lat) AS lat, any_value(lon) AS lon,
    sum(arrival_t)                                                    AS arrival_t,
    CASE WHEN sum(arrival_t) > 0 THEN sum(modal_price * arrival_t) / sum(arrival_t)
         ELSE avg(modal_price) END                                    AS price,  -- Rs/quintal
    count(*)                                                          AS n_records
FROM top_clean
GROUP BY date, commodity, state, market_key;

-- Outlier reports: a market-day more than 3x above or below the same state's median price for that
-- crop on that day (e.g. Kollengode reporting a flat Rs 27,000/q for weeks in early 2023 while Kerala's
-- median was about Rs 3,000/q). Applied only when at least 5 markets in the state reported that day.
CREATE OR REPLACE TABLE market_day AS
WITH ref AS (
    SELECT date, commodity, state, median(price) AS state_median, count(*) AS n
    FROM market_day_all GROUP BY ALL
)
SELECT m.* FROM market_day_all m JOIN ref USING (date, commodity, state)
WHERE ref.n < 5 OR m.price BETWEEN ref.state_median / 3 AND ref.state_median * 3;

CREATE OR REPLACE TABLE dq_outliers AS
SELECT a.state = 'Kerala' AS kerala, a.commodity, count(*) AS market_days,
       count(*) - count(m.date) AS dropped
FROM market_day_all a LEFT JOIN market_day m USING (date, commodity, market_key)
GROUP BY 1, 2 ORDER BY 1, 2;

CREATE OR REPLACE TABLE dq_dedup AS
SELECT (SELECT count(*) FROM top_raw) AS raw_rows, (SELECT count(*) FROM top_clean) AS kept_rows,
       (SELECT count(DISTINCT market_code) FROM top_clean) AS source_codes,
       (SELECT count(DISTINCT market_key) FROM top_clean) AS markets;

-- Kerala (destination) and all-India daily series per crop.
CREATE OR REPLACE TABLE series AS
SELECT date, commodity, 'Kerala' AS region,
       sum(price * greatest(arrival_t, 0.01)) / sum(greatest(arrival_t, 0.01)) AS price,
       sum(arrival_t) AS arrival_t, count(*) AS n_markets
FROM market_day WHERE state = 'Kerala' GROUP BY ALL
UNION ALL
SELECT date, commodity, 'India' AS region,
       sum(price * greatest(arrival_t, 0.01)) / sum(greatest(arrival_t, 0.01)),
       sum(arrival_t), count(*)
FROM market_day GROUP BY ALL;
