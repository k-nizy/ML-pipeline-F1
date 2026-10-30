# Task 3: API endpoints for MySQL

Member 3, SQL lead: Kevinn

## 1. What the API does

One FastAPI application serves both databases. I wrote the SQL side under `/api/sql` and Selena wrote the MongoDB side under `/api/mongo`, and both use the same request and response shapes, so a client does not need to know which database is behind it.

The SQL side has twelve endpoints. Four of them are the CRUD operations, two are the required time-series queries, and the rest check the connection or return summary numbers. The two required ones are `GET /api/sql/readings/latest` and `GET /api/sql/readings/range`.

A few things in the code are worth explaining.

- The routers are in `src/api/routers/` and they share `src/api/schemas.py`, so the create, update and read shapes are defined once and reused by both databases.
- `sql.py` never puts a value into the SQL string. Column names are chosen from an allow list and every value goes through a bound parameter, so the filter endpoints cannot be used for injection.
- Two routes have to be declared before `/readings/{reading_id}`. If `latest` and `range` came after it, FastAPI would try to read the word `latest` as a number and answer 422.
- MySQL returns `Decimal` for `DECIMAL` columns, which does not serialise to a JSON number. `db_sql._normalise` converts those values to floats so the client never sees a string where a number belongs.

## 2. Endpoints

Table 1. The SQL endpoints.

| Method | Path | Purpose | Success | Errors |
|---|---|---|---|---|
| GET | `/health` | checks the service is up, does not touch the database | 200 | |
| GET | `/api/sql/health` | checks the MySQL connection | 200 | 503 |
| GET | `/api/sql/stations` | the monitoring sites | 200 | 503 |
| POST | `/api/sql/readings` | creates one hourly reading | 201 | 409, 422, 503 |
| GET | `/api/sql/readings` | lists readings with filters | 200 | 400, 503 |
| GET | `/api/sql/readings/{id}` | reads one reading | 200 | 404, 503 |
| PUT | `/api/sql/readings/{id}` | updates part of one reading | 200 | 400, 404, 409, 422 |
| DELETE | `/api/sql/readings/{id}` | deletes one reading | 204 | 404, 503 |
| GET | `/api/sql/readings/latest` | latest record, required | 200 | 404, 503 |
| GET | `/api/sql/readings/range` | records by date range, required | 200 | 400, 422, 503 |
| GET | `/api/sql/aggregates/daily` | the daily table with lags and moving averages | 200 | 400, 503 |
| GET | `/api/sql/stats` | summary numbers for the dataset | 200 | 503 |

## 3. The latest record

`GET /api/sql/readings/latest` returns the newest observation in the table.

```bash
curl http://127.0.0.1:8000/api/sql/readings/latest
```

The reply is 200 with one object. The PM2.5 value is 12 at 2014-12-31 23:00, which is the last hour of the dataset, and the same row that query 1 in Task 2 returns.

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

There is an optional `station_id` parameter, so the endpoint still makes sense when a second station is added.

## 4. Records by date range

`GET /api/sql/readings/range` needs a `start` and an `end`, and both ends are included. This is the endpoint the Task 4 prediction script uses to fetch its input window.

```bash
curl "http://127.0.0.1:8000/api/sql/readings/range?start=2014-12-31T21:00:00&end=2014-12-31T23:00:00"
```

The reply is 200 with three objects in date order and a header that gives the total.

```text
x-total-count: 3
```

```json
[
  { "reading_id": 43822, "observed_at": "2014-12-31T21:00:00", "pm25": 10.0, "wind_dir": "NW", "wind_speed": 242.70, "temp": -3.0, "pres": 1034.0 },
  { "reading_id": 43823, "observed_at": "2014-12-31T22:00:00", "pm25": 8.0,  "wind_dir": "NW", "wind_speed": 246.72, "temp": -4.0, "pres": 1034.0 },
  { "reading_id": 43824, "observed_at": "2014-12-31T23:00:00", "pm25": 12.0, "wind_dir": "NW", "wind_speed": 249.85, "temp": -3.0, "pres": 1034.0 }
]
```

The other columns are cut here to keep the sample short. A reversed range, where the start is later than the end, returns 400 rather than an empty list, because an empty list would look like a valid answer to a question that was asked wrongly.

## 5. Create, read, update and delete

I ran the four operations in order against the running service. The test row uses 2015-06-01 00:00, which is outside the dataset window, so it cannot clash with real data, and it is removed at the end.

### Create

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
  "pm25": 87.5,
  "dewp": 3.0,
  "temp": 22.0,
  "pres": 1009.0,
  "wind_dir": "SE",
  "wind_speed": 2.5,
  "snow_hours": 0,
  "rain_hours": 0,
  "is_imputed": false,
  "ingested_at": "2026-10-28T12:02:43",
  "updated_at": "2026-10-28T12:02:43"
}
```

The reply is 201. Two things happen on the way in. The wind direction was sent in lower case and comes back as `SE`, and the server gave the row its own `reading_id`.

### Read

```bash
curl http://127.0.0.1:8000/api/sql/readings/83835
```

The reply is 200 and the object is the same as the one just created.

### Update

```bash
curl -X PUT http://127.0.0.1:8000/api/sql/readings/83835 \
  -H "Content-Type: application/json" -d '{"pm25":120.0}'
```

The reply is 200 and only PM2.5 changed. The other columns are untouched because the handler builds its `SET` list from the fields that were actually sent, not from the whole object.

### Delete

```bash
curl -X DELETE http://127.0.0.1:8000/api/sql/readings/83835
```

The reply is 204 with no body. A read of the same id afterwards returns 404, and `/api/sql/stats` shows 43,824 hourly rows again, so the test left the dataset as it found it.

## 6. Testing and error handling

I tested the endpoints in the browser through the `/docs` page and with curl. Table 2 lists the cases I checked and what came back.

Table 2. Endpoint tests.

| # | Test | Result |
|---|---|---|
| 1 | GET `/health` | 200, status ok |
| 2 | GET `/api/sql/health` | 200, connected to MySQL 8.0.40 |
| 3 | GET `/api/sql/stations` | 200, one station, Beijing US Embassy |
| 4 | GET `/readings/latest` | 200, 2014-12-31 23:00, PM2.5 = 12 |
| 5 | GET `/readings/range` for three hours | 200, three rows, `x-total-count: 3` |
| 6 | GET `/readings/range` with start after end | 400, start must be earlier than end |
| 7 | DELETE the test row | 204, row removed |
| 8 | GET `/readings/latest` in January 2014 range from Task 2 | 20 rows, peak 671 |

The full set of tests, including the error cases below, is in Table 3.

Table 3. Error cases.

| Situation | What was sent | What came back |
|---|---|---|
| The station and hour already exist | POST of an existing station and timestamp | 409, a reading for station 1 at that hour already exists |
| Wind direction is not a real value | POST with `"wind_dir": "SIDEWAYS"` | 422, wind_dir must be one of N, NNE and the rest |
| The date range is backwards | `range` with start later than end | 400, start must be earlier than end |
| The id does not exist | GET `/readings/99999999` | 404, reading not found |
| The update body is empty | PUT with `{}` | 400, no fields supplied |
| MySQL is not running | any endpoint | 503, MySQL is unreachable, with a note to start the server |

Numbers are checked before they reach SQL as well. PM2.5 must be between 0 and 2000, pressure between 800 and 1100, temperature and dew point between -60 and 60, and the rain and snow hours between 0 and 24, so an impossible value is refused with 422 instead of being stored.

## 7. A bug I found while testing

The first version of the update endpoint returned 404 when the same values were sent twice. The cause was that MySQL reports the number of rows it changed, not the number it matched, so an update that changes nothing reports zero. The handler was reading that zero as "this row does not exist".

I fixed it by checking whether the row exists with a separate `SELECT` before deciding what to answer. Testing it again, a repeated update returns 200 and an id that really is missing still returns 404. It is the kind of fault that only shows up when a request is sent twice, which is why I sent each one twice.

## 8. Filtering and paging

`GET /api/sql/readings` takes `start`, `end`, `station_id`, `min_pm25`, `max_pm25`, `limit` and `offset`. The limit is 100 by default and cannot go above 1000, so one request cannot pull all 43,824 rows by accident. The number of matches is put in a response header instead of being repeated on every page.

```bash
curl -D - "http://127.0.0.1:8000/api/sql/readings?min_pm25=600&limit=2"
```

```text
x-total-count: 32
```

```json
[
  { "reading_id": 1058, "observed_at": "2010-02-14T01:00:00", "pm25": 980.0, "wind_dir": "CV", "wind_speed": 0.89 },
  { "reading_id": 1877, "observed_at": "2010-03-20T04:00:00", "pm25": 700.0, "wind_dir": "NW", "wind_speed": 4.92 }
]
```

Only 32 hours in five years are above 600 µg/m³. The series is mostly between 0 and 200 with a long thin tail, which is why one error number is not enough to judge the model.

## 9. Two endpoints used by the other tasks

`GET /api/sql/stats` returns the summary row that Task 1 quotes.

```json
{"hourly_rows": 43824, "first_timestamp": "2010-01-01T00:00:00",
 "last_timestamp": "2014-12-31T23:00:00", "days_covered": 1826,
 "null_target_rows": 2067.0, "pm25_mean": 98.61, "pm25_min": 0.0,
 "pm25_max": 994.0, "pm25_std": 92.05}
```

`GET /api/sql/aggregates/daily` returns the rows of the moving average view, so the lag and rolling features can be read from the database instead of rebuilt in the notebook.

```json
{"agg_date": "2010-01-02", "pm25_avg": 145.96, "pm25_max": 181.0,
 "pm25_lag1": null, "pm25_lag7": null, "pm25_ma7": 145.96,
 "pm25_ma30": 145.96, "ma7_window_days": 2}
```

The two empty values are correct. The second day of the series has a day before it but the preprocessing left that day without a mean, and a 7 day lag needs a week of history that does not exist yet.

## 10. How to run it

```bash
# 1. database
mysql -u root -p < sql/schema.sql
python scripts/load_mysql.py --csv data/raw/PRSA_data_2010.1.1-2014.12.31.csv

# 2. service
uvicorn src.api.main:app --host 127.0.0.1 --port 8000

# 3. quick check
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/sql/readings/latest
curl "http://127.0.0.1:8000/api/sql/readings/range?start=2014-12-31T21:00:00&end=2014-12-31T23:00:00"
```

The interactive page at `http://127.0.0.1:8000/docs` lists every route and can be used to send the four CRUD requests without curl.

## 11. My contribution

I wrote the SQL router and the MySQL connection layer, the shared request and response models, and the validation rules for wind direction, the date range and the numeric columns. I tested all twelve endpoints, wrote down the error cases, found and fixed the update bug, and wrote this section from the responses the service actually returned. Selena wrote the MongoDB side of the same API and describes it in her section.

Table 4. My files.

| Component | Where in the repository |
|---|---|
| Application and routers | `src/api/main.py`, `src/api/routers/sql.py` |
| MySQL connection and row cleaning | `src/api/db_sql.py` |
| Request and response models | `src/api/schemas.py` |
| Settings | `src/api/config.py`, `.env.example` |
| Unit tests | `tests/` |
