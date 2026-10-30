# Task 2: Database design and queries

Member 3, SQL lead: Kevinn

## 1. What the database needed to do

The dataset is one time series. It has 43,824 hourly rows from 1 January 2010 to 31 December 2014, one monitoring station in Beijing, PM2.5 as the value to predict and five weather columns as the other variables. Two database systems were built on this data. I did the MySQL side and Selena did the MongoDB side.

Three things the rest of the project needed from MySQL decided the design.

- The API has to return the latest record and any date range quickly, so the timestamp needs an index of its own.
- The loader may be run more than once, so the database has to make it impossible to store the same station and hour twice.
- Task 1 needs lags and 7 and 30 day moving averages, so these are calculated once in the database instead of again in every notebook.

## 2. The six tables

`sql/schema.sql` creates six tables in three groups. The brief asks for at least three. Six are used because hourly measurements, daily features and model results are different kinds of data, and squeezing them into fewer tables would mean repeating the 43,824 hourly rows once for each day they belong to, or once for each model run.

Table 1. The tables created by `sql/schema.sql`.

| Table | One row per | Rows in my copy | What it holds |
|---|---|---|---|
| `stations` | monitoring site | 1 | station name, city and coordinates |
| `readings` | station and hour | 43,824 | the hourly measurements |
| `daily_aggregates` | station and day | 1,826 | daily mean, maximum, minimum and count |
| `models` | model setup | 0 | name and type of each model |
| `forecast_runs` | training run | 0 | one experiment with its RMSE, MAE and R2 |
| `forecast_predictions` | forecasted hour | 0 | predicted value next to the actual value |

The last three tables had no rows when I checked. They are designed to hold model results, but nothing writes to them yet. Task 1 saved its experiment results to `outputs/figures/experiment_table.csv` and `outputs/models/` instead of the database, and the prediction script prints its forecast instead of storing it, so query 7 returns nothing.

## 3. Keys and rules

- Each table has its own auto increment number as the primary key. The station name or the timestamp would not be a stable key, and they are wide to copy into every child row.
- `UNIQUE(station_id, observed_at)` on `readings` is the important rule. One sensor cannot report two values for the same hour, so the database refuses the second one. This is also what makes `scripts/load_mysql.py` safe to run twice. It updates the row that is already there instead of adding another, and the count stays at 43,824.
- Deleting a station or a training run deletes its children, using `ON DELETE CASCADE`, so no reading or prediction is left behind without a parent.
- `CHECK` constraints stop negative concentrations, negative wind speed and impossible coordinates. Sensors fail by reporting nonsense, so the database rejects it before the model ever sees it.
- `pm25` is allowed to be empty. 2,067 hours, which is 4.7 per cent of the table, have no reading because the instrument was down. Storing 0 would look like clean air and would pull every average down, so the gap stays empty, and `is_imputed` marks the rows that preprocessing filled.

## 4. Indexes

Table 2. The three indexes on `readings`.

| Index | Columns | Used for |
|---|---|---|
| `uq_readings_station_hour` | `station_id`, `observed_at` | stopping duplicates, and finding the newest hour of a station without sorting |
| `idx_readings_observed_at` | `observed_at` | the date range queries |
| `idx_readings_pm25` | `pm25` | threshold queries, for example the hours above 300 |

The date index is not a copy of the unique key. In `UNIQUE(station_id, observed_at)` the timestamp is the second column, so a query that filters on a date alone cannot use that key and would read the whole table. With the separate index, one month of readings is found in about 721 rows out of 43,824 and comes back in about 0.08 seconds.

Query 6 filters on the date and on PM2.5 together. For that query MySQL is free to use either index, and on this data it picks `idx_readings_pm25` (Figure 7). Both plans are range scans, so neither reads all 43,824 rows.

## 5. The daily table and the moving average view

`daily_aggregates` is redundant in strict normalisation, because every column in it can be recalculated from `readings`. I kept it for three reasons.

1. A 7 day average over 1,826 daily rows is cheap. The same average over 43,824 hourly rows, repeated for each analytical question, is not.
2. Hourly PM2.5 follows a day and night cycle that hides the trend. An average of daily means answers "is the air getting worse" directly.
3. `pm25_count` records how many hours of that day actually had a value, so a day with gaps can be left out of a calculation. 37 days had no readings at all, and those days store NULL instead of a mean of nothing.

The view `v_daily_pm25_moving_avg` adds `pm25_lag1`, `pm25_lag7`, `pm25_ma7`, `pm25_ma30` and `ma7_window_days`. The last column is the number of days the 7 day average really used, because the first six days of the series do not have a full week behind them. The procedure `sp_refresh_daily_aggregates` rebuilds the table from `readings`, so the daily numbers cannot drift away from the hourly ones.

## 6. ERD

Figure 1 is the diagram. `stations` is the only dimension table and it has two children, `readings` and `daily_aggregates`. The three model tables form a chain from `models` to `forecast_runs` to `forecast_predictions`. The source is kept in `sql/erd.dbml`, so the picture can be redrawn after a schema change instead of going out of date.

Figure 1. ERD for the MySQL schema (`sql/erd.png`).

## 7. Queries and results

Seven queries are in `sql/queries.sql`; the brief asks for three. Their full output is in `outputs/query_results.md`, which `scripts/export_query_results.py` writes from the database, so the numbers in this section were not typed by hand. Each figure is a MySQL Workbench screenshot of the statement above it.

### 7.1 The latest record

```sql
SELECT station_id, reading_id, observed_at, pm25, dewp, temp, pres, wind_dir, wind_speed
FROM (
    SELECT r.*,
           ROW_NUMBER() OVER (PARTITION BY r.station_id
                              ORDER BY r.observed_at DESC) AS rn
    FROM readings r
) ranked
WHERE rn = 1;
```

Figure 2. Q1 result in MySQL Workbench: one row, 2014-12-31 23:00.

One row comes back because the data has one station. `ROW_NUMBER()` splits the table by station before numbering, so the same query returns one row per station once more sensors are added. That is why the API endpoint for this is not written with a plain `ORDER BY ... LIMIT 1`.

### 7.2 Yesterday, last week and the moving averages

```sql
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
```

Figure 3. Q2 result: 14 daily rows with lag and moving average columns.

On 31 December 2014 the daily mean was 10.04, the day before was 46.08, the same day last week was 14.13 and the 7 day average was 121.20. Across those two weeks the daily value moved between 10 and 239, but the 30 day average stayed close to 84. So the swings are short lived and sit on a steadier level for the season. That is the reason Task 1 uses lag and rolling features instead of the raw hourly value alone.

### 7.3 Monthly averages

```sql
SELECT YEAR(agg_date)  AS yr,
       MONTH(agg_date) AS mth,
       COUNT(*)                    AS days,
       ROUND(AVG(pm25_avg), 1)     AS avg_pm25,
       ROUND(MAX(pm25_max), 1)     AS peak_hourly,
       SUM(pm25_max > 150)         AS days_above_150
FROM daily_aggregates
GROUP BY yr, mth
ORDER BY avg_pm25 DESC;
```

Figure 4. Q3 result: 60 monthly rows ordered by average PM2.5.

The query returns 60 rows, one for each month from January 2010 to December 2014; the worst are shown first. January 2013 is the worst month at 194.2 µg/m³, with 27 days above 150. Six of the ten worst months are in November, December, January or February, which fits the heating season. The exceptions are October 2011 and October 2014 at about 140, and July 2010 at 123.6.

### 7.4 Is there a one day lag effect?

```sql
SELECT COUNT(*) AS paired_days,
       CAST(
         (COUNT(*) * SUM(t.pm25_avg * y.pm25_avg) - SUM(t.pm25_avg) * SUM(y.pm25_avg))
         / SQRT(
             (COUNT(*) * SUM(t.pm25_avg * t.pm25_avg) - POW(SUM(t.pm25_avg), 2))
           * (COUNT(*) * SUM(y.pm25_avg * y.pm25_avg) - POW(SUM(y.pm25_avg), 2))
           ) AS DECIMAL(10,4)) AS lag1_pearson_r
FROM daily_aggregates y
JOIN daily_aggregates t
  ON t.station_id = y.station_id
 AND t.agg_date    = y.agg_date + INTERVAL 1 DAY
WHERE y.pm25_avg IS NOT NULL
  AND t.pm25_avg IS NOT NULL;
```

Figure 5. Q4 result: 1,770 pairs of days and a correlation of 0.5632.

MySQL has no `CORR()` function, so the Pearson correlation is written out in the query. It uses 1,770 pairs of consecutive days and gives r = 0.5632, which is a moderate positive correlation. Yesterday's daily mean explains part of today's, so a lag feature carries real information, but most of the variation is still unexplained and a forecast that simply repeats yesterday would be wrong often. The experiment table in Task 1 shows the same thing, with the persistence baseline at RMSE 110.26 against 87.75 for the best model.

### 7.5 Wind direction and PM2.5

```sql
SELECT wind_dir,
       COUNT(*)                  AS hours,
       ROUND(AVG(pm25), 1)       AS avg_pm25,
       ROUND(MAX(pm25), 1)       AS max_pm25,
       ROUND(STDDEV_SAMP(pm25), 1) AS sd_pm25
FROM readings
WHERE pm25 IS NOT NULL
GROUP BY wind_dir
ORDER BY avg_pm25 DESC;
```

Figure 6. Q5 result: four wind directions with their averages.

| Wind direction | Hours | Average PM2.5 | Highest |
|---|---|---|---|
| Calm or variable | 8,944 | 126.2 | 980.0 |
| South east | 14,573 | 110.8 | 845.0 |
| North east | 4,756 | 90.2 | 852.0 |
| North west | 13,484 | 70.1 | 994.0 |

Calm or variable wind averages 126.2 µg/m³ and north westerly wind averages 70.1, a gap of 56. This matches the physical explanation of the city: still air holds the pollution in the basin and north westerly wind clears it out. Only four of the seventeen values the `ENUM` allows appear in this data, but a new value from a future feed would load without a schema change.

### 7.6 The worst hours inside a date range

```sql
SELECT r.observed_at, s.station_name, r.pm25, r.wind_dir, r.wind_speed, r.temp
FROM readings r
JOIN stations s ON s.station_id = r.station_id
WHERE r.observed_at BETWEEN '2014-01-01 00:00:00' AND '2014-01-31 23:59:59'
  AND r.pm25 >= 300
ORDER BY r.pm25 DESC
LIMIT 20;
```

Figure 7. Q6 query plan from `EXPLAIN`: a range scan, key `idx_readings_pm25`.

Table 3. Q6 result: the 20 worst hours of January 2014.

| Observed at | PM2.5 | Wind | Speed | Temp |
|---|---|---|---|---|
| 2014-01-16 04:00 | 671.00 | NE | 1.79 | -3.00 |
| 2014-01-16 01:00 | 659.00 | CV | 0.89 | -3.00 |
| 2014-01-16 03:00 | 651.00 | CV | 2.67 | -3.00 |
| 2014-01-16 02:00 | 648.00 | CV | 1.78 | -3.00 |
| 2014-01-16 05:00 | 623.00 | SE | 1.79 | -3.00 |
| 2014-01-16 06:00 | 618.00 | NW | 0.89 | -4.00 |
| 2014-01-16 00:00 | 569.00 | SE | 1.79 | -3.00 |
| 2014-01-15 23:00 | 567.00 | CV | 0.89 | -2.00 |
| 2014-01-15 22:00 | 539.00 | SE | 1.79 | -2.00 |
| 2014-01-16 07:00 | 532.00 | NW | 1.78 | -4.00 |
| 2014-01-15 21:00 | 513.00 | CV | 1.78 | -2.00 |
| 2014-01-16 10:00 | 490.00 | CV | 0.89 | -2.00 |
| 2014-01-15 20:00 | 489.00 | CV | 0.89 | -2.00 |
| 2014-01-16 09:00 | 479.00 | NW | 5.36 | -5.00 |
| 2014-01-16 08:00 | 477.00 | NW | 3.57 | -5.00 |
| 2014-01-16 11:00 | 476.00 | NE | 1.79 | 1.00 |
| 2014-01-31 01:00 | 469.00 | SE | 41.58 | -1.00 |
| 2014-01-16 12:00 | 457.00 | NE | 5.81 | 2.00 |
| 2014-01-16 20:00 | 437.00 | SE | 13.87 | -1.00 |
| 2014-01-15 19:00 | 435.00 | SE | 8.94 | 0.00 |

Every row is from the same station, so `station_name` is left out of the table. Sixteen of the twenty hours fall on 15 and 16 January, which means the pollution did not build up slowly through the month. It arrived as one episode and then cleared.

### 7.7 The experiment table

```sql
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
```

This query returns no rows at the moment. Task 1 saved its results as a CSV instead of writing them to `forecast_runs`, so the join has nothing to match. The same numbers are in `outputs/figures/experiment_table.csv`: baseline 110.26, E1 88.34, E2 88.40, E3 88.09, E4 87.75, E5 96.88 and E6 87.75.

## 8. Limitations

- Times are stored exactly as they appear in the source, which is Beijing time, with no offset. If UTC data were added, every lag would shift by eight hours.
- There is one station, so `stations` holds one row. The queries are written to survive several stations, but this dataset cannot compare two parts of the city.
- PM2.5 is measured at the US Embassy while the weather columns come from Beijing Capital Airport about 20 km away. The mismatch comes from the dataset itself and is written in `data/README.md` rather than hidden.
- The three model tables are created and query 7 is written against them, but they hold no rows. Training saved its metrics as a CSV and the prediction script prints its output, so no step writes to these tables yet.

## 9. How to reproduce

```bash
mysql -u root -p < sql/schema.sql
python scripts/load_mysql.py --csv data/raw/PRSA_data_2010.1.1-2014.12.31.csv
python scripts/export_query_results.py
```

The loader prints 43,824 hourly rows, 1,826 days, 2,067 rows without a PM2.5 value and 1,826 daily aggregates. Running it a second time prints the same numbers, because the rows are updated instead of copied.

## 10. My contribution

I designed the schema and wrote `sql/schema.sql`, which includes the indexes, the moving average view, the refresh procedure and the seed row for the station. I drew the ERD and wrote its source file, the loader that reads the cleaned CSV into MySQL and rebuilds the daily table, the seven analytical queries and their results file, and the SQL side of the API. I also ran the queries in MySQL Workbench and took the screenshots used as the figures above.

Table 4. My files.

| Component | Where in the repository |
|---|---|
| Schema, indexes, view, procedure | `sql/schema.sql` |
| ERD | `sql/erd.png`, `sql/erd.dbml` |
| Analytical queries and results | `sql/queries.sql`, `outputs/query_results.md` |
| CSV loader | `scripts/load_mysql.py` |
| SQL API endpoints | `src/api/routers/sql.py`, `src/api/db_sql.py` |
| Workbench screenshots | `outputs/screenshots/` |
