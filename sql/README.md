# SQL design notes (Task 2)

How the relational schema was designed, and why. Everything below is measured
against the loaded dataset, not estimated.

| | |
|---|---|
| Fact rows | 43,824 hourly readings |
| Calendar span | 2010-01-01 → 2014-12-31 (1,826 days, no missing days) |
| Missing target | 2,067 hours (4.7 %) have no `pm25`; **37 whole days** have none |
| Target statistics | mean 98.61, sd 92.05, min 0, max 994 µg/m³; 8,991 hours above 150 |

---

## 1. Why six tables

The brief asks for at least three. Six are used because the pipeline has three
genuinely different kinds of data, and mixing them would either duplicate rows or
make a query impossible to index.

| Layer | Table | Grain | Purpose |
|---|---|---|---|
| Dimension | `stations` | one row per site | Coordinates and metadata. Kept separate so a second city only adds a row, never a migration of 43k readings. |
| Fact | `readings` | one row per **station-hour** | The raw observation. Everything analytical is derived from this. |
| Derived | `daily_aggregates` | one row per **station-day** | Materialised rollup for lags and moving averages. |
| Model | `models` | one row per model config | Name, features, hyperparameters, artefact path. |
| Model | `forecast_runs` | one row per **experiment** | RMSE / MAE / R² for Experiment A, B, … → the experiment table becomes queryable. |
| Model | `forecast_predictions` | one row per forecasted hour | Predicted vs actual, plus a generated absolute-error column. |

The last three are what make Task 4's prediction script write *back* into the
database instead of printing to stdout: a forecast is only reproducible if the
model version and its metrics are stored next to the numbers it produced.

## 2. Keys and constraints

- **Surrogate primary keys** (`AUTO_INCREMENT`) on every table: natural keys in
  time-series data change (a station can be renamed) and are wide to carry
  through foreign keys.
- **`UNIQUE(station_id, observed_at)`** on `readings` encodes the real business
  rule — a sensor cannot report two values for the same hour. It is also the
  upsert key, so `load_mysql.py` can be re-run without creating duplicates.
- **`ON DELETE CASCADE`** from `stations` and from `forecast_runs`: deleting a
  site or an experiment must not leave orphaned measurements behind.
- **`CHECK` constraints** on `pm25 >= 0` and `wind_speed >= 0`, plus latitude /
  longitude bounds: sensors fail by reporting nonsense, and the database is the
  last line of defence before that nonsense reaches the model.
- `pm25` is **nullable on purpose**. A missing reading means the instrument was
  down; storing `0` would look like perfectly clean air and bias every average
  and the model itself. `is_imputed` records the cases where a gap was later
  filled by the preprocessing pipeline, so analyses can include or exclude them.

## 3. Index design (with evidence)

| Index | Column(s) | Why |
|---|---|---|
| `uq_readings_station_hour` | `(station_id, observed_at)` | Duplicate prevention + upsert target + per-site time ordering. |
| `idx_readings_observed_at` | `observed_at` | The date-range endpoint filters on time only. The composite key above **cannot** serve that predicate because `station_id` is not supplied, which is exactly why a separate index exists. |
| `idx_readings_pm25` | `pm25` | Threshold queries ("hours worse than 300 µg/m³"). |

Measured with `EXPLAIN` on one month of data:

```
type=range  key=idx_readings_observed_at  rows=744  Extra=Using index condition
EXPLAIN ANALYZE: Index range scan ... (cost=335 rows=744) (actual time=0.64..2.87 rows=744)
```

744 of 43,824 rows (1.7 %) are read instead of a full table scan. Full plans are
in [`../outputs/query_results.md`](../outputs/query_results.md).

## 4. Why `daily_aggregates` is deliberately denormalised

In strict 3NF this table is redundant — every value can be recomputed from
`readings`. It is kept anyway:

1. **The analytical questions need lags and moving averages.** `AVG(...) OVER
   (ORDER BY agg_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)` over 1,826 daily
   rows is cheap; the same over 43,824 hourly rows, repeated for every question,
   is not.
2. **Hourly PM2.5 is too noisy for a daily trend.** A 7-day mean of hourly
   values is dominated by the daily cycle; a mean of daily means answers "is the
   air getting worse?" directly.
3. **Data quality travels with the aggregate.** `pm25_count` (hours with a real
   value) lets any query exclude incomplete days — 37 days have `pm25_count = 0`
   and `pm25_avg` `NULL` rather than being silently averaged from nothing.

It is refreshed from the fact table by `sp_refresh_daily_aggregates` (called by
the loader), so it can never drift from `readings` for long.

The moving averages live in the view `v_daily_pm25_moving_avg`, which exposes
`pm25_lag1`, `pm25_lag7`, `pm25_ma7`, `pm25_ma30` and `ma7_window_days`. The last
column matters: the first six days of the series have partial 7-day windows, and
`ma7_window_days` makes that visible instead of hiding it.

## 5. MongoDB mapping (for the MongoDB lead)

`readings` → one document per station-hour, with the flat row split into
meaningful sub-documents:

```javascript
{
  station:   { id: 1, name: "Beijing US Embassy", city: "Beijing" },
  timestamp: ISODate("2014-12-31T23:00:00Z"),
  target:    { pm25: 12.0, imputed: false },
  weather:   { dewp: -21, temp: -3, pres: 1034,
               wind_dir: "NW", wind_speed: 249.85,
               snow_hours: 0, rain_hours: 0 },
  ingested_at: ISODate("...")
}
```

Indexes: `{ timestamp: 1 }` and unique `{ "station.id": 1, "timestamp": -1 }`,
matching the two relational indexes above. A native time-series collection
(`timeseries: { timeField: "timestamp", metaField: "station", granularity: "hours" }`)
is the natural fit if Atlas supports it on the chosen tier.

## 6. Regenerating the ERD

1. Open <https://dbdiagram.io/d>.
2. Paste [`erd.dbml`](erd.dbml).
3. Export → PNG → save as `sql/erd.png`.

The `.dbml` source is committed so the diagram can be regenerated after any
schema change rather than becoming a stale screenshot.

## 7. Caveats worth stating in the report

- **Timezone**: timestamps are stored as given by the source (Asia/Shanghai)
  without an offset. `TIME_ZONE` is therefore a deployment concern; mixing in UTC
  data would shift every lag by 8 hours.
- **One station**: the dataset is a single site, so `stations` has one row. The
  schema is multi-site ready, but no cross-station query will return more than
  one group today.
- **Spatial mismatch**: PM2.5 comes from the US Embassy monitor, weather from
  Beijing Capital Airport ~20 km away. This is inherent to the source data.
