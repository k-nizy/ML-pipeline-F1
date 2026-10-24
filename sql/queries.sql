-- =============================================================================
--  sql/queries.sql - the analytical queries behind Task 2
--  Run after loading:  mysql -u root -p beijing_air < sql/queries.sql
--  Results captured in outputs/query_results.md
-- =============================================================================
USE beijing_air;

-- -----------------------------------------------------------------------------
-- Q1. Latest record per station (the "latest record" time-series endpoint in SQL)
--     Technique: ROW_NUMBER() window function, so it still works with many sites.
-- -----------------------------------------------------------------------------
SELECT station_id, reading_id, observed_at, pm25, dewp, temp, pres, wind_dir, wind_speed
FROM (
    SELECT r.*,
           ROW_NUMBER() OVER (PARTITION BY r.station_id
                              ORDER BY r.observed_at DESC) AS rn
    FROM readings r
) ranked
WHERE rn = 1;

-- -----------------------------------------------------------------------------
-- Q2. Lagged + moving-average features over the daily rollup
--     Technique: the v_daily_pm25_moving_avg view (LAG + windowed AVG).
--     Shows today vs yesterday vs the same day last week vs 7/30-day averages.
-- -----------------------------------------------------------------------------
SELECT agg_date,
       pm25_avg,
       pm25_lag1        AS yesterday,
       pm25_lag7        AS same_day_last_week,
       pm25_ma7         AS moving_avg_7d,
       ma7_window_days,
       pm25_ma30        AS moving_avg_30d
FROM v_daily_pm25_moving_avg
WHERE station_id = 1
ORDER BY agg_date DESC
LIMIT 14;

-- -----------------------------------------------------------------------------
-- Q3. Monthly seasonality: which months are worst, and how many bad days each
--     Technique: GROUP BY on a derived date part over the rollup table.
-- -----------------------------------------------------------------------------
SELECT YEAR(agg_date)  AS yr,
       MONTH(agg_date) AS mth,
       COUNT(*)                    AS days,
       ROUND(AVG(pm25_avg), 1)     AS avg_pm25,
       ROUND(MAX(pm25_max), 1)     AS peak_hourly,
       SUM(pm25_max > 150)         AS days_above_150
FROM daily_aggregates
GROUP BY yr, mth
ORDER BY avg_pm25 DESC;

-- -----------------------------------------------------------------------------
-- Q4. Lag-1 dependency: does yesterday's daily mean predict today's?
--     Technique: self-join on date + 1 day, then Pearson r computed inline
--     (MySQL has no CORR() aggregate).
-- -----------------------------------------------------------------------------
SELECT COUNT(*) AS paired_days,
       ROUND(
         (COUNT(*) * SUM(t.pm25_avg * y.pm25_avg) - SUM(t.pm25_avg) * SUM(y.pm25_avg))
         / SQRT(
             (COUNT(*) * SUM(t.pm25_avg * t.pm25_avg) - POW(SUM(t.pm25_avg), 2))
           * (COUNT(*) * SUM(y.pm25_avg * y.pm25_avg) - POW(SUM(y.pm25_avg), 2))
           ), 4) AS lag1_pearson_r
FROM daily_aggregates y
JOIN daily_aggregates t
  ON t.station_id = y.station_id
 AND t.agg_date    = y.agg_date + INTERVAL 1 DAY
WHERE y.pm25_avg IS NOT NULL
  AND t.pm25_avg IS NOT NULL;

-- -----------------------------------------------------------------------------
-- Q5. External variable: how strongly does wind direction move the target?
--     Technique: categorical GROUP BY with an aggregate on the target.
-- -----------------------------------------------------------------------------
SELECT wind_dir,
       COUNT(*)                  AS hours,
       ROUND(AVG(pm25), 1)       AS avg_pm25,
       ROUND(MAX(pm25), 1)       AS max_pm25,
       ROUND(STDDEV_SAMP(pm25), 1) AS sd_pm25
FROM readings
WHERE pm25 IS NOT NULL
GROUP BY wind_dir
ORDER BY avg_pm25 DESC;

-- -----------------------------------------------------------------------------
-- Q6. Date-range + threshold: the 20 worst hours of January 2014.
--     Technique: indexed range scan on observed_at, then a join to stations.
--     Run EXPLAIN to show idx_readings_observed_at is used.
-- -----------------------------------------------------------------------------
EXPLAIN
SELECT r.observed_at, s.station_name, r.pm25, r.wind_dir, r.wind_speed, r.temp
FROM readings r
JOIN stations s ON s.station_id = r.station_id
WHERE r.observed_at BETWEEN '2014-01-01 00:00:00' AND '2014-01-31 23:59:59'
  AND r.pm25 >= 300
ORDER BY r.pm25 DESC
LIMIT 20;

SELECT r.observed_at, s.station_name, r.pm25, r.wind_dir, r.wind_speed, r.temp
FROM readings r
JOIN stations s ON s.station_id = r.station_id
WHERE r.observed_at BETWEEN '2014-01-01 00:00:00' AND '2014-01-31 23:59:59'
  AND r.pm25 >= 300
ORDER BY r.pm25 DESC
LIMIT 20;

-- -----------------------------------------------------------------------------
-- Q7. Experiment comparison table straight out of the database (Task 1 data).
-- -----------------------------------------------------------------------------
SELECT m.model_name,
       m.model_type,
       fr.experiment_label,
       fr.rmse,
       fr.mae,
       fr.r2,
       fr.test_start,
       fr.test_end
FROM forecast_runs fr
JOIN models m ON m.model_id = fr.model_id
ORDER BY fr.rmse ASC;
