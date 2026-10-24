# Beijing PM2.5 — Time-Series Pipeline

End-to-end pipeline for forecasting hourly **PM2.5 concentration in Beijing**: preprocessing and EDA, a tuned model, a relational **and** a document database behind one **FastAPI** service, and a prediction script that consumes the API end to end.

> Formative 1 — *Building a Pipeline for Time Series Data* (45 marks, group of 4).
> Report: [`docs/report.pdf`](docs/) · Query evidence: [`outputs/query_results.md`](outputs/query_results.md)

---

## 1. Problem

Beijing's winter air quality is a public-health problem with a strong hourly rhythm: pollution builds up under calm winds and is flushed out when north-westerly winds arrive. We treat it as a **supervised time-series regression** task.

| | |
|---|---|
| **Target** | `pm25` — PM2.5 concentration (µg/m³), hourly |
| **Horizon** | next hour (1-step ahead), with lag/rolling features |
| **Predictors** | dew point, temperature, pressure, wind direction, wind speed, snow/rain hours, plus lagged and rolling PM2.5 |
| **Why this dataset** | one clean timestamp column, a continuous measurable target with real sensor gaps, several meteorological covariates sampled at the same frequency, and 5 full years (2010–2014) — enough to hold out a whole year for testing |

## 2. Dataset

**Beijing PM2.5 Data Set** (UCI / Kaggle) — 43,824 hourly rows, 2010-01-01 00:00 → 2014-12-31 23:00.

- Time range: **5 years**, 1,826 distinct days, no gaps in the calendar (only missing *values*).
- Granularity: **hourly**; 2,067 rows (4.7 %) have no `pm2.5` reading — a sensor outage, not a zero.
- Full column dictionary and download instructions: [`data/README.md`](data/README.md).

## 3. Repository layout

```
ML-pipeline-F1/
├── data/
│   ├── raw/          # downloaded CSV (gitignored)
│   └── processed/    # cleaned CSV produced by the data lead
├── notebooks/        # EDA notebook
├── scripts/
│   ├── preprocess.py           # cleaning pipeline (data lead)
│   ├── load_mysql.py           # CSV -> MySQL + daily rollup (SQL lead)
│   ├── load_mongo.py           # CSV -> Atlas (MongoDB lead)
│   ├── train_model.py          # training + experiments (model lead)
│   ├── export_query_results.py # regenerates outputs/query_results.md
│   └── predict.py              # Task 4 end-to-end prediction
├── sql/
│   ├── schema.sql    # DDL: 6 tables, indexes, view, stored procedure, seed
│   ├── queries.sql   # analytical queries
│   ├── erd.dbml      # ERD source (render at dbdiagram.io)
│   └── erd.png       # exported diagram
├── mongodb/          # collection design, sample documents, queries
├── src/api/          # FastAPI service: /api/sql and /api/mongo
├── outputs/          # figures, model artefacts, query results
└── docs/             # report draft, contribution table
```

## 4. Quick start

### 4.1 Python environment

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in your MySQL password
```

### 4.2 MySQL

Install MySQL 8 (or use XAMPP/MariaDB — the schema is compatible), then:

```bash
mysql -u root -p < sql/schema.sql
python scripts/load_mysql.py --csv data/raw/PRSA_data_2010.1.1-2014.12.31.csv
```

Expected output:

```
hourly rows        : 43,824
time range         : 2010-01-01 00:00:00  ->  2014-12-31 23:00:00
days covered       : 1,826
null pm25 rows     : 2,067
daily_aggregates   : 1,826 rows
```

The loader is **idempotent** (upsert on `UNIQUE(station_id, observed_at)`), so re-running it refreshes values instead of duplicating rows.

### 4.3 API

```bash
uvicorn src.api.main:app --reload --port 8000
```

Open <http://127.0.0.1:8000/docs> for the interactive reference.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/api/sql/health` | MySQL connectivity |
| GET | `/api/sql/stations` | monitoring sites |
| POST | `/api/sql/readings` | create one hourly reading |
| GET | `/api/sql/readings` | list + filters (`start`, `end`, `station_id`, `min_pm25`, `max_pm25`, `limit`, `offset`) |
| GET | `/api/sql/readings/{id}` | read one |
| PUT | `/api/sql/readings/{id}` | partial update |
| DELETE | `/api/sql/readings/{id}` | delete |
| **GET** | **`/api/sql/readings/latest`** | **latest record** (required) |
| **GET** | **`/api/sql/readings/range?start=&end=`** | **records by date range** (required) |
| GET | `/api/sql/aggregates/daily` | daily rollup + 7/30-day moving averages |
| GET | `/api/sql/stats` | dataset summary statistics |
| * | `/api/mongo/...` | same surface on MongoDB (MongoDB lead) |

List responses carry an `X-Total-Count` header; pages are capped by `MAX_PAGE_SIZE`.

### 4.4 Queries and the prediction script

```bash
python scripts/export_query_results.py --output outputs/query_results.md
python scripts/predict.py            # Task 4
```

## 5. Database design (Task 2)

Six tables in three layers — full rationale in [`sql/README.md`](sql/README.md), diagram in [`sql/erd.png`](sql/).

| Layer | Tables | Purpose |
|---|---|---|
| Dimension | `stations` | monitoring site metadata |
| Fact / derived | `readings`, `daily_aggregates` | hourly grain (43,824) and the daily rollup (1,826) that lags and moving averages are computed from |
| Model / forecast | `models`, `forecast_runs`, `forecast_predictions` | model registry, per-experiment metrics, predicted vs actual |

MongoDB mirrors `readings` as one document per hour with embedded `target` and `weather` sub-documents — see [`mongodb/`](mongodb/).

## 6. Reproducing the results

1. `pip install -r requirements.txt`
2. Download the raw CSV (§2) into `data/raw/`
3. Run the preprocessing notebook/script → `data/processed/beijing_clean.csv`
4. Create and load MySQL (§4.2)
5. `python scripts/train_model.py` → writes metrics to `forecast_runs` and the model to `outputs/models/`
6. `uvicorn src.api.main:app` in one terminal, `python scripts/predict.py` in another
7. `python scripts/export_query_results.py` to regenerate the evidence file

## 7. Notes / limitations

- `pm2.5` gaps are kept as `NULL` in the database and flagged (`is_imputed`) rather than silently zero-filled; zero would look like clean air and bias the model.
- Weather variables come from Beijing Capital Airport while PM2.5 comes from the US Embassy monitor ~20 km away — a documented spatial mismatch inherent to this dataset.
- The dataset is a single site, so `stations` currently holds one row; the schema is already multi-site ready.
