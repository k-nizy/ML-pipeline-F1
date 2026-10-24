# MongoDB (Task 2, non-relational side)

Owned by the **MongoDB lead**. Expected contents of this folder:

| File | What it should contain |
|---|---|
| `collections.js` | `db.createCollection(...)` + `createIndex(...)` calls that build the collection from scratch |
| `sample_documents.json` | two or three real documents copied out of Atlas |
| `queries.js` | at least three `find`/`aggregate` queries with their output captured |

## Agreed document shape

One document per **station-hour**, mirroring the `readings` table so both
backends answer the same questions:

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

Indexes:

```javascript
db.readings.createIndex({ timestamp: 1 });
db.readings.createIndex({ "station.id": 1, timestamp: -1 }, { unique: true });
```

## API surface

Implemented in [`../src/api/routers/mongo.py`](../src/api/routers/mongo.py) — the
routes and the connection helper (`src/api/db_mongo.py`) are already wired; each
handler raises `501` until it is filled in. The endpoint list is identical to
`/api/sql`, so the report can compare the two implementations side by side.

Set `MONGO_URI` in `.env` with the Atlas connection string.
