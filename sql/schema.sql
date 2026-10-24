-- =============================================================================
--  Beijing PM2.5 hourly time series - relational schema (MySQL 8.0 / MariaDB 10.4+)
--  Formative 1: Building a Pipeline for Time Series Data
--  Owner: SQL lead
--
--  Run:      mysql -u root -p < sql/schema.sql
--  Re-runs:  safe. It recreates only the tables/views it owns (never the
--            database), dropping children before parents so FKs never block.
--
--  Design at a glance
--    stations            dimension - one row per monitoring site
--    readings            fact      - one row per station per HOUR (43,824 rows)
--    daily_aggregates    derived   - one row per station per DAY (1,826 rows)
--    models              registry  - one row per trained model configuration
--    forecast_runs       one row per training/evaluation run + its metrics
--    forecast_predictions one row per forecasted timestamp (predicted vs actual)
--
--  Why daily_aggregates exists:
--    The analytical questions use lagged features and 7/30-day moving averages.
--    Recomputing those over 43k hourly rows on every query is wasteful, so the
--    hourly fact table is rolled up once per day and the moving averages are
--    computed over 1,826 daily rows instead.  It also stores data completeness
--    (pm25_count) so imputed days can be excluded from analysis.
-- =============================================================================

CREATE DATABASE IF NOT EXISTS beijing_air
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

USE beijing_air;

-- ---------------------------------------------------------------------------
-- Rebuild (children first)
-- ---------------------------------------------------------------------------
DROP VIEW  IF EXISTS v_daily_pm25_moving_avg;
DROP TABLE IF EXISTS forecast_predictions;
DROP TABLE IF EXISTS forecast_runs;
DROP TABLE IF EXISTS models;
DROP TABLE IF EXISTS daily_aggregates;
DROP TABLE IF EXISTS readings;
DROP TABLE IF EXISTS stations;

-- ---------------------------------------------------------------------------
-- 1. stations - the monitoring site (dimension)
-- ---------------------------------------------------------------------------
CREATE TABLE stations (
    station_id   INT UNSIGNED NOT NULL AUTO_INCREMENT,
    station_name VARCHAR(100) NOT NULL,
    city         VARCHAR(100) NOT NULL,
    country      VARCHAR(60)  NOT NULL DEFAULT 'China',
    latitude     DECIMAL(9,6) NOT NULL,
    longitude    DECIMAL(9,6) NOT NULL,
    timezone     VARCHAR(40)  NOT NULL DEFAULT 'Asia/Shanghai',
    description  VARCHAR(255) NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (station_id),
    UNIQUE KEY uq_stations_name (station_name),
    CONSTRAINT chk_stations_lat CHECK (latitude  BETWEEN -90  AND 90),
    CONSTRAINT chk_stations_lon CHECK (longitude BETWEEN -180 AND 180)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- 2. readings - hourly observation (the fact table, grain = station + hour)
-- ---------------------------------------------------------------------------
CREATE TABLE readings (
    reading_id  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    station_id  INT UNSIGNED NOT NULL,
    observed_at DATETIME NOT NULL
        COMMENT 'hourly timestamp (Asia/Shanghai), minute and second always 00',
    pm25        DECIMAL(7,2) NULL
        COMMENT 'TARGET: PM2.5 concentration in ug/m3. NULL = sensor gap (not zero)',
    dewp        DECIMAL(5,2) NULL COMMENT 'dew point, degC',
    temp        DECIMAL(5,2) NULL COMMENT 'temperature, degC',
    pres        DECIMAL(7,2) NULL COMMENT 'pressure, hPa',
    wind_dir    ENUM('N','NNE','NE','ENE','E','ESE','SE','SSE',
                     'S','SSW','SW','WSW','W','WNW','NW','NNW','CV') NULL
        COMMENT 'combined wind direction, CV = calm/variable',
    wind_speed  DECIMAL(5,2) NULL COMMENT 'cumulated wind speed, m/s',
    snow_hours  SMALLINT UNSIGNED NOT NULL DEFAULT 0
        COMMENT 'cumulated hours of snow',
    rain_hours  SMALLINT UNSIGNED NOT NULL DEFAULT 0
        COMMENT 'cumulated hours of rain',
    is_imputed  TINYINT(1) NOT NULL DEFAULT 0
        COMMENT '1 = pm25 was filled in by the preprocessing pipeline, 0 = observed',
    ingested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (reading_id),

    -- One physical sensor cannot report the same hour twice. This is also the
    -- key the loader upserts on, which makes re-running the import idempotent.
    UNIQUE KEY uq_readings_station_hour (station_id, observed_at),

    -- Required time-series endpoint: "records by date range". A range predicate
    -- on observed_at alone cannot use the composite unique key above (station_id
    -- is its leading column), so observed_at gets its own index -> range scan
    -- instead of a 43k-row full scan.
    KEY idx_readings_observed_at (observed_at),

    -- Supports threshold/anomaly lookups (e.g. hours above 300 ug/m3).
    KEY idx_readings_pm25 (pm25),

    CONSTRAINT fk_readings_station FOREIGN KEY (station_id)
        REFERENCES stations (station_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_readings_pm25  CHECK (pm25 IS NULL OR pm25 >= 0),
    CONSTRAINT chk_readings_wind  CHECK (wind_speed IS NULL OR wind_speed >= 0)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- 3. daily_aggregates - daily rollup used for lags and moving averages
-- ---------------------------------------------------------------------------
CREATE TABLE daily_aggregates (
    agg_id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    station_id     INT UNSIGNED NOT NULL,
    agg_date       DATE NOT NULL,
    pm25_avg       DECIMAL(7,2) NULL,
    pm25_max       DECIMAL(7,2) NULL,
    pm25_min       DECIMAL(7,2) NULL,
    pm25_std       DECIMAL(7,2) NULL COMMENT 'sample standard deviation within the day',
    pm25_count     SMALLINT UNSIGNED NOT NULL DEFAULT 0
        COMMENT 'hours with a real pm25 value (24 = complete day)',
    readings_count SMALLINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'hours present in the table',
    temp_avg       DECIMAL(5,2) NULL,
    pres_avg       DECIMAL(7,2) NULL,
    refreshed_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (agg_id),
    UNIQUE KEY uq_daily_station_date (station_id, agg_date),
    KEY idx_daily_date (agg_date),
    CONSTRAINT fk_daily_station FOREIGN KEY (station_id)
        REFERENCES stations (station_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- 4. models - registry of trained model configurations (Task 1)
-- ---------------------------------------------------------------------------
CREATE TABLE models (
    model_id      INT UNSIGNED NOT NULL AUTO_INCREMENT,
    model_name    VARCHAR(100) NOT NULL COMMENT 'e.g. ridge_baseline, lstm_v1',
    model_type    VARCHAR(50)  NOT NULL COMMENT 'linear_regression | random_forest | lstm ...',
    feature_set   JSON NULL COMMENT 'list of feature names used for training',
    hyperparams   JSON NULL COMMENT 'hyperparameters after tuning',
    artifact_path VARCHAR(255) NOT NULL COMMENT 'path to the persisted model file',
    trained_at    DATETIME NOT NULL,
    notes         TEXT NULL,
    PRIMARY KEY (model_id),
    UNIQUE KEY uq_models_name (model_name)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- 5. forecast_runs - one row per experiment, carrying its test metrics
--    This is what turns Task 1's experiment table into queryable data.
-- ---------------------------------------------------------------------------
CREATE TABLE forecast_runs (
    run_id           INT UNSIGNED NOT NULL AUTO_INCREMENT,
    model_id         INT UNSIGNED NOT NULL,
    experiment_label VARCHAR(60) NOT NULL COMMENT 'Experiment A / Experiment B ...',
    run_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    horizon_hours    SMALLINT UNSIGNED NOT NULL DEFAULT 1 COMMENT 'forecast horizon',
    train_start      DATE NULL,
    train_end        DATE NULL,
    test_start       DATE NULL,
    test_end         DATE NULL,
    rmse             DECIMAL(8,3) NULL,
    mae              DECIMAL(8,3) NULL,
    r2               DECIMAL(7,4) NULL,
    notes            VARCHAR(255) NULL,
    PRIMARY KEY (run_id),
    UNIQUE KEY uq_runs_model_label (model_id, experiment_label),
    CONSTRAINT fk_runs_model FOREIGN KEY (model_id)
        REFERENCES models (model_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- 6. forecast_predictions - predicted vs actual per forecasted hour
-- ---------------------------------------------------------------------------
CREATE TABLE forecast_predictions (
    prediction_id  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    run_id         INT UNSIGNED NOT NULL,
    target_time    DATETIME NOT NULL,
    predicted_pm25 DECIMAL(7,2) NOT NULL,
    actual_pm25    DECIMAL(7,2) NULL COMMENT 'NULL for future hours (no observation yet)',
    abs_error      DECIMAL(8,2) GENERATED ALWAYS AS (ABS(predicted_pm25 - actual_pm25)) STORED,
    PRIMARY KEY (prediction_id),
    UNIQUE KEY uq_predictions_run_target (run_id, target_time),
    KEY idx_predictions_target_time (target_time),
    CONSTRAINT fk_predictions_run FOREIGN KEY (run_id)
        REFERENCES forecast_runs (run_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- Analytical view: daily moving averages and lags over the rollup table.
-- window_days tells you how many days actually went into the average, because
-- the first 6 (MA7) / 29 (MA30) rows of the series are partial windows.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_daily_pm25_moving_avg AS
SELECT
    d.station_id,
    d.agg_date,
    d.pm25_avg,
    d.pm25_max,
    d.pm25_min,
    d.pm25_std,
    d.pm25_count,
    d.readings_count,
    d.temp_avg,
    d.pres_avg,
    ROUND(AVG(d.pm25_avg) OVER (
        PARTITION BY d.station_id ORDER BY d.agg_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2)  AS pm25_ma7,
    COUNT(*) OVER (
        PARTITION BY d.station_id ORDER BY d.agg_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)      AS ma7_window_days,
    ROUND(AVG(d.pm25_avg) OVER (
        PARTITION BY d.station_id ORDER BY d.agg_date
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW), 2) AS pm25_ma30,
    LAG(d.pm25_avg, 1) OVER (
        PARTITION BY d.station_id ORDER BY d.agg_date)  AS pm25_lag1,
    LAG(d.pm25_avg, 7) OVER (
        PARTITION BY d.station_id ORDER BY d.agg_date)  AS pm25_lag7
FROM daily_aggregates d;

-- ---------------------------------------------------------------------------
-- Stored procedure: rebuild the daily rollup from the hourly fact table.
-- Called by scripts/load_mysql.py, but runnable on its own:
--     CALL sp_refresh_daily_aggregates(NULL);   -- all stations
-- ---------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_refresh_daily_aggregates;

DELIMITER $$
CREATE PROCEDURE sp_refresh_daily_aggregates(IN p_station_id INT UNSIGNED)
BEGIN
    INSERT INTO daily_aggregates (
        station_id, agg_date, pm25_avg, pm25_max, pm25_min, pm25_std,
        pm25_count, readings_count, temp_avg, pres_avg
    )
    SELECT
        r.station_id,
        DATE(r.observed_at),
        ROUND(AVG(r.pm25), 2),
        MAX(r.pm25),
        MIN(r.pm25),
        ROUND(STDDEV_SAMP(r.pm25), 2),
        SUM(r.pm25 IS NOT NULL),
        COUNT(*),
        ROUND(AVG(r.temp), 2),
        ROUND(AVG(r.pres), 2)
    FROM readings r
    WHERE p_station_id IS NULL OR r.station_id = p_station_id
    GROUP BY r.station_id, DATE(r.observed_at)
    ON DUPLICATE KEY UPDATE
        pm25_avg       = VALUES(pm25_avg),
        pm25_max       = VALUES(pm25_max),
        pm25_min       = VALUES(pm25_min),
        pm25_std       = VALUES(pm25_std),
        pm25_count     = VALUES(pm25_count),
        readings_count = VALUES(readings_count),
        temp_avg       = VALUES(temp_avg),
        pres_avg       = VALUES(pres_avg);
END$$
DELIMITER ;

-- ---------------------------------------------------------------------------
-- Seed: the monitoring site behind the dataset.
-- PM2.5 comes from the US Embassy rooftop monitor in Beijing; the weather
-- columns (DEWP/TEMP/PRES/wind/rain/snow) come from Beijing Capital
-- International Airport, ~20 km north-east. Both are recorded in one hourly
-- row by UCI, so the design keeps one station row and documents the caveat.
-- ---------------------------------------------------------------------------
INSERT INTO stations
    (station_name, city, country, latitude, longitude, timezone, description)
VALUES
    ('Beijing US Embassy', 'Beijing', 'China', 39.954600, 116.472500, 'Asia/Shanghai',
     'PM2.5 from the US Embassy rooftop monitor (39.9546N, 116.4725E); meteorology from Beijing Capital Airport (40.0801N, 116.5846E), ~20 km NE.')
ON DUPLICATE KEY UPDATE
    latitude = VALUES(latitude),
    longitude = VALUES(longitude);

-- Sanity check after a fresh rebuild: expect 1 station, 0 readings.
SELECT 'stations' AS table_name, COUNT(*) AS rows_loaded FROM stations
UNION ALL SELECT 'readings', COUNT(*) FROM readings
UNION ALL SELECT 'daily_aggregates', COUNT(*) FROM daily_aggregates;
