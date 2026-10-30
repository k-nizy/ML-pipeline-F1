# 3. Task 3 — CRUD and time-series endpoints

> Draft report section, written from live responses captured against the running
> service (MySQL 8.0.40, `beijing_air`, 43,824 rows). Paste into the group report
> and re-date the screenshots if the API is restarted.
>
> Work split: the `/api/sql/*` surface (this section) was implemented by Member 3,
> the SQL lead. The `/api/mongo/*` mirror is the MongoDB lead's implementation and
> is described in §3.9.

## 3.1 Architecture

One **FastAPI** application exposes two parallel backends behind a single service,
so the two database implementations can be compared side by side and the Task 4
prediction script can switch between them without changing its code:

```
client (curl / Swagger UI / predict.py)
        │
        ▼
   FastAPI app  ─ src/api/main.py            (routers, CORS, /health)
        │
        ├── /api/sql/...    → src/api/routers/sql.py   → db_sql.py   → MySQL   (Member 3)
        └── /api/mongo/...  → src/api/routers/mongo.py → db_mongo.py → MongoDB (MongoDB lead)
                                     │
                                     └── src/api/schemas.py  (shared Pydantic models)
```

Design decisions worth stating:

- **One shared schema layer.** `schemas.py` defines `ReadingCreate`, `ReadingUpdate`
  and `ReadingOut` once, and both backends use them — so a JSON payload means the
  same thing whether it becomes a MySQL row or a MongoDB document.
- **Short-lived connection per request** (`db_sql.py`). The dataset is static and
  requests are small, so this avoids a silently stale pooled connection after a
  laptop sleeps; the cost is a sub-millisecond local handshake.
- **Bound parameters everywhere.** SQL strings are built from *column names and
  placeholders only*; every value travels through PyMySQL's parameter binding, so
  the two filter endpoints cannot be injection vectors.
- **`DECIMAL` → `float` on the way out.** PyMySQL returns `decimal.Decimal`, which
  JSON-encodes to a string (`"12.00"`). `db_sql._normalise` converts it, so clients
  never have to cast.

Start the service with:

```bash
uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Interactive documentation (auto-generated from the route signatures) is then at
`http://127.0.0.1:8000/docs`.

## 3.2 Endpoint inventory

Table 3.1 — every endpoint exposed by the service. The four CRUD verbs plus the two
required time-series queries are present on **both** backends.

| # | Method | Path | Purpose | Success | Errors |
|---|---|---|---|---|---|
| 1 | GET | `/health` | liveness, touches no database | 200 | — |
| 2 | GET | `/api/sql/health` | MySQL connectivity + version | 200 | 503 |
| 3 | GET | `/api/sql/stations` | monitoring sites | 200 | 503 |
| 4 | **POST** | `/api/sql/readings` | create one hourly reading | 201 | 409, 422, 503 |
| 5 | **GET** | `/api/sql/readings` | list + filters | 200 | 400, 503 |
| 6 | **GET** | `/api/sql/readings/{id}` | read one | 200 | 404, 503 |
| 7 | **PUT** | `/api/sql/readings/{id}` | partial update | 200 | 400, 404, 409, 422 |
| 8 | **DELETE** | `/api/sql/readings/{id}` | delete one | 204 | 404, 503 |
| 9 | **GET** | **`/api/sql/readings/latest`** | **latest record (required)** | 200 | 404, 503 |
| 10 | **GET** | **`/api/sql/readings/range`** | **records by date range (required)** | 200 | 400, 422, 503 |
| 11 | GET | `/api/sql/aggregates/daily` | daily rollup + lags and moving averages | 200 | 400, 503 |
| 12 | GET | `/api/sql/stats` | dataset summary statistics | 200 | 503 |
| 13 | GET | `/api/mongo/health` | MongoDB connectivity | 200 | 503 |
| 14–19 | POST/GET/PUT/DELETE | `/api/mongo/readings…` | the same six operations on MongoDB | 201/200/204 | 409, 422, 503 |
| 20 | GET | `/api/mongo/readings/latest` | latest document (required) | 200 | 404, 503 |
| 21 | GET | `/api/mongo/readings/range` | documents by date range (required) | 200 | 400, 422, 503 |

Route order matters: `/readings/latest` and `/readings/range` are declared **before**
`/readings/{reading_id}` in the router, otherwise FastAPI would try to parse `latest`
as an integer id and answer 422.

## 3.3 Required endpoint 1 — latest record

`GET /api/sql/readings/latest` returns the single most recent observation. The SQL is
`SELECT … FROM readings ORDER BY observed_at DESC LIMIT 1`, which the index
`idx_station_time (station_id, observed_at)` serves directly; the optional
`station_id` filter keeps it correct once more stations are added.

Request:

```bash
curl http://127.0.0.1:8000/api/sql/readings/latest
```

Response — `HTTP 200`:

```json
{
  "reading_id": 43824,
  "station_id": 1,
  "observed_at": "2014-12-31T23:00:00",
  "pm25": 12.0,
  "dewp": -21.0,
  "temp": -3.0,
  "pres": 1034.0,
  "wind_dir": "NW",
  "wind_speed": 249.85,
  "snow_hours": 0,
  "rain_hours": 0,
  "is_imputed": 0,
  "ingested_at": "2026-10-25T00:29:58",
  "updated_at": "2026-10-25T00:29:58"
}
```

## 3.4 Required endpoint 2 — records by date range

`GET /api/sql/readings/range` requires `start` and `end` (inclusive) and is the
endpoint the Task 4 prediction script calls to fetch its input window. Both bounds
are bound parameters, so the index range scan is used rather than a full scan
(same plan shown in the Task 2 `EXPLAIN` evidence).

Request:

```bash
curl "http://127.0.0.1:8000/api/sql/readings/range?start=2014-12-31T21:00:00&end=2014-12-31T23:00:00"
```

Response — `HTTP 200`, three rows, plus a total-count header:

```
x-total-count: 3
```

```json
[
  { "reading_id": 43822, "observed_at": "2014-12-31T21:00:00", "pm25": 10.0, "wind_dir": "NW", "wind_speed": 242.70, "temp": -3.0, "pres": 1034.0, "…": "…" },
  { "reading_id": 43823, "observed_at": "2014-12-31T22:00:00", "pm25": 8.0,  "wind_dir": "NW", "wind_speed": 246.72, "temp": -4.0, "pres": 1034.0, "…": "…" },
  { "reading_id": 43824, "observed_at": "2014-12-31T23:00:00", "pm25": 12.0, "wind_dir": "NW", "wind_speed": 249.85, "temp": -3.0, "pres": 1034.0, "…": "…" }
]
```

(`"…"` elides the unchanged columns `station_id`, `dewp`, `snow_hours`,
`rain_hours`, `is_imputed`, `ingested_at`, `updated_at`.)

The calendar ordering is visible in the response: three consecutive hours, ascending,
ending at the last hour of the dataset.

## 3.5 CRUD walkthrough (MySQL)

A complete create → read → update → delete cycle, executed against the live service.
The test row uses a timestamp outside the dataset window (`2015-06-01 00:00`) so it
cannot collide with real data, and it is deleted at the end.

**POST — create (`HTTP 201`)**

```bash
curl -X POST http://127.0.0.1:8000/api/sql/readings \
  -H "Content-Type: application/json" \
  -d '{"station_id":1,"observed_at":"2015-06-01T00:00:00","pm25":87.5,
       "dewp":3.0,"temp":22.0,"pres":1009.0,"wind_dir":"se","wind_speed":2.5}'
```

```json
{
  "reading_id": 83835,
  "station_id": 1,
  "observed_at": "2015-06-01T00:00:00",
  "pm25": 87.5, "dewp": 3.0, "temp": 22.0, "pres": 1009.0,
  "wind_dir": "SE", "wind_speed": 2.5,
  "snow_hours": 0, "rain_hours": 0, "is_imputed": false,
  "ingested_at": "2026-10-28T12:02:43",
  "updated_at": "2026-10-28T12:02:43"
}
```

Two validations are visible in that response: `wind_dir` was sent lowercase (`se`)
and was normalised to `SE`, and the server assigned `reading_id` itself.

**GET — read one (`HTTP 200`)**

```bash
curl http://127.0.0.1:8000/api/sql/readings/83835
```

Returns the same object as above.

**PUT — partial update (`HTTP 200`)**

```bash
curl -X PUT http://127.0.0.1:8000/api/sql/readings/83835 \
  -H "Content-Type: application/json" -d '{"pm25":120.0}'
```

```json
{ "reading_id": 83835, "pm25": 120.0, "temp": 22.0, "…": "…", "updated_at": "2026-10-28T12:04:24" }
```

Only the supplied field changed — `temp`, `pres` and the rest are untouched because
the handler builds its `SET` list from `payload.model_dump(exclude_unset=True)`.

**DELETE — remove (`HTTP 204`)**

```bash
curl -X DELETE http://127.0.0.1:8000/api/sql/readings/83835
```

Then `GET` on the same id returns `HTTP 404 {"detail": "reading 83835 not found"}`,
and `hourly_rows` in `/api/sql/stats` is back to **43,824** — proving the cycle left
the dataset unchanged.

## 3.6 Validation and error handling

Table 3.2 — error behaviour, each line verified against the running service.

| Situation | Request | Response |
|---|---|---|
| Duplicate station + timestamp | POST of an existing `(station_id, observed_at)` | **409** `{"detail": "a reading for station 1 at 2015-06-01 00:00:00 already exists"}` |
| Invalid wind direction | POST with `"wind_dir": "SIDEWAYS"` | **422** `{"detail": [{"loc": ["body","wind_dir"], "msg": "Value error, wind_dir must be one of N, NNE, …, CV"}]}` |
| Inverted date range | `range?start=2014-12-31T23:00:00&end=2014-12-30T00:00:00` | **400** `{"detail": "start must be earlier than end"}` |
| Unknown id | `GET /readings/99999999` | **404** `{"detail": "reading 99999999 not found"}` |
| Empty update body | `PUT` with `{}` | **400** `{"detail": "no fields supplied"}` |
| MySQL not running | any endpoint | **503** `{"detail": "MySQL is unreachable (…). Start the server, run sql/schema.sql, and check MYSQL_* in .env."}` |

Numeric fields are range-checked by Pydantic before they reach SQL (`pm25` 0–2000,
`pres` 800–1100, `temp`/`dewp` −60–60, hours 0–24), so a physically impossible
observation is rejected at the edge with 422 rather than stored.

**One defect found and fixed during this testing.** The first version of `PUT`
returned **404** when the body repeated the values already stored. MySQL reports the
number of *changed* rows, not *matched* rows, so an identical update yields
`rowcount = 0` — which the handler had interpreted as "row does not exist". The fix
is to decide existence with a follow-up `SELECT` instead of trusting `rowcount`;
re-testing now gives `200` for a repeated identical update and still `404` for a
genuinely missing id. Worth a sentence in the report: it is the kind of bug only a
second identical request exposes.

## 3.7 Filtering and pagination

`GET /api/sql/readings` accepts `start`, `end`, `station_id`, `min_pm25`, `max_pm25`,
`limit` and `offset`; `limit` defaults to 100 and is capped at 1000
(`MAX_PAGE_SIZE`), so a single request cannot pull all 43,824 rows by accident.
The total number of matches travels in a response header rather than being repeated
in every page:

```bash
curl -D - "http://127.0.0.1:8000/api/sql/readings?min_pm25=600&limit=2"
```

```
x-total-count: 32
```

```json
[
  { "reading_id": 1058, "observed_at": "2010-02-14T01:00:00", "pm25": 980.0, "wind_dir": "CV", "wind_speed": 0.89 },
  { "reading_id": 1877, "observed_at": "2010-03-20T04:00:00", "pm25": 700.0, "wind_dir": "NW", "wind_speed": 4.92 }
]
```

Only **32 hours in five years** exceed 600 µg/m³, which matches the tail of the
distribution described in Task 1 and is why the model must not be judged on RMSE
alone.

## 3.8 Analysis endpoints used by the later tasks

- `GET /api/sql/stats` — the summary table quoted in Task 1:

  ```json
  {"hourly_rows": 43824, "first_timestamp": "2010-01-01T00:00:00",
   "last_timestamp": "2014-12-31T23:00:00", "days_covered": 1826,
   "null_target_rows": 2067.0, "pm25_mean": 98.61, "pm25_min": 0.0,
   "pm25_max": 994.0, "pm25_std": 92.05}
  ```

- `GET /api/sql/aggregates/daily` — serves the `v_daily_pm25_moving_avg` view, i.e.
  the lag and moving-average features straight from the database instead of
  recomputing them in the notebook. Example row:

  ```json
  {"agg_date": "2010-01-02", "pm25_avg": 145.96, "pm25_max": 181.0,
   "pm25_lag1": null, "pm25_lag7": null, "pm25_ma7": 145.96,
   "pm25_ma30": 145.96, "ma7_window_days": 2}
  ```

  The `null`s on 2010-01-02 are correct: the first day of the series has no
  yesterday, and a 7-day lag needs a week of history. That is exactly the boundary
  effect the report's missing-value discussion refers to.

## 3.9 The MongoDB mirror

`/api/mongo/*` exposes the same six operations plus the two required time-series
queries, returning the document shape agreed in
[`mongodb/README.md`](../mongodb/README.md): one document per station-hour with
embedded `target` (`pm25`, `imputed`) and `weather` sub-documents, a `timestamp`
`ISODate`, and a unique index on `{"station.id": 1, "timestamp": -1}`.

The mapping between the two designs is one-to-one:

| SQL | MongoDB |
|---|---|
| `readings` row | one document in `readings` |
| `reading_id` (`BIGINT` PK) | `_id` (`ObjectId`) |
| `observed_at` (`DATETIME`) | `timestamp` (`ISODate`) |
| `pm25`, `is_imputed` | `target.pm25`, `target.imputed` |
| `dewp`, `temp`, `pres`, `wind_dir`, `wind_speed`, `snow_hours`, `rain_hours` | `weather.*` |
| `stations` join | embedded `station` sub-document |

> **Placeholder — MongoDB lead:** replace this paragraph with your implementation
> and the query results from `mongodb/queries.js`, then delete the note below.
>
> As of this draft the `/api/mongo/*` handlers still raise `501 Not Implemented`
> (`src/api/routers/mongo.py`), and `scripts/load_mongo.py` does not exist yet, so
> the mirror cannot be demonstrated end to end. `MONGO_URI` must also be set in
> `.env` before those endpoints can return anything other than `503`.

## 3.10 Reproducing this section

```bash
# 1. database
mysql -u root -p < sql/schema.sql
python scripts/load_mysql.py --csv data/raw/PRSA_data_2010.1.1-2014.12.31.csv

# 2. service
uvicorn src.api.main:app --host 127.0.0.1 --port 8000

# 3. manual check of every endpoint, in order
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/sql/health
curl http://127.0.0.1:8000/api/sql/stations
curl http://127.0.0.1:8000/api/sql/readings/latest
curl "http://127.0.0.1:8000/api/sql/readings/range?start=2014-12-31T21:00:00&end=2014-12-31T23:00:00"
curl -D - "http://127.0.0.1:8000/api/sql/readings?min_pm25=600&limit=2"
curl http://127.0.0.1:8000/api/sql/stats
curl "http://127.0.0.1:8000/api/sql/aggregates/daily?limit=2"

# 4. the Swagger UI is the fastest way to demo CRUD live
open http://127.0.0.1:8000/docs
```

Figures to add for this section: one `GET /docs` screenshot showing both route
groups (`SQL / MySQL` and `MongoDB`), and one screenshot of the
`/api/sql/readings/range` response in Swagger (or the curl output above).
