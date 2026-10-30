# Team contribution table (for the report PDF)

> Drafted from the actual git history on `main` on 28 Oct 2026.
> Regenerate the counts any time with:
>
> ```bash
> git shortlog -sne --all
> git log --author="<handle>" --oneline | wc -l
> ```
>
> **Fill in the real names** — only GitHub handles are recorded in the repository.

## 1. Contributions

| Member | Name | Role | Commits | Major components delivered |
|---|---|---|---|---|
| Member 1 | *ambabazi* | **Data lead** | **13** | Dataset cleaning and validation (`scripts/preprocess.py`), feature engineering (`scripts/features.py`, lags + moving averages), the EDA notebook `notebooks/pm25_EDA.ipynb` covering temporal patterns, monthly trends, correlation, lag and wind-direction analysis, the cleaned dataset `data/processed/beijing_clean.csv`, and 17 unit tests |
| Member 2 | *name* | **Modelling lead** | **0 ⚠** | Task 1 model + hyperparameter tuning + experiment table (`scripts/train_model.py`), Task 4 prediction script (`scripts/predict.py`), final PDF assembly — **nothing pushed yet** |
| Member 3 | *k-nizy* | **SQL lead** | **10** | Repository scaffolding and shared FastAPI app (`src/api/*`, `requirements.txt`, `README.md`), MySQL schema with 6 tables (`sql/schema.sql`), ERD (`sql/erd.dbml`, `sql/erd.png`), analytical queries (`sql/queries.sql`), CSV→MySQL loader with daily rollup (`scripts/load_mysql.py`), query-result exporter, all 14 `/api/sql/*` endpoints |
| Member 4 | *selenai9* | **MongoDB lead** | **4** | MongoDB collection design and indexes (`mongodb/collections.js`), sample documents (`mongodb/sample_documents.json`), three queries (`mongodb/queries.js`), design notes and index/sample screenshots |

Commit counts are per author on `main`; total **27** commits at the time of writing.

## 2. Task coverage

| Task | Evidence in repo | Owner(s) | Status |
|---|---|---|---|
| **Task 1 — preprocessing & EDA** | `notebooks/pm25_EDA.ipynb`, `scripts/preprocess.py`, `scripts/features.py`, `data/processed/beijing_clean.csv` | Member 1 | ✅ delivered |
| **Task 1 — model & experiments** | `scripts/train_model.py`, rows in the `forecast_runs` table | Member 2 | ❌ missing |
| **Task 2 — relational design** | `sql/schema.sql`, `sql/erd.png`, `sql/README.md`, `outputs/query_results.md` (Q1–Q6) | Member 3 | ✅ delivered |
| **Task 2 — document design** | `mongodb/collections.js`, `mongodb/sample_documents.json`, `mongodb/queries.js` | Member 4 | ✅ delivered |
| **Task 3 — CRUD + time-series API (SQL)** | `src/api/routers/sql.py` — 14 endpoints, verified live | Member 3 | ✅ delivered |
| **Task 3 — CRUD + time-series API (MongoDB)** | `src/api/routers/mongo.py` — **7 handlers still raise 501** | Member 4 | ❌ incomplete |
| **Task 4 — prediction script** | `scripts/predict.py` | Member 2 | ❌ missing |

## 3. Individual contribution statements

Short prose to paste under the table — adjust the wording to your own voice.

**Member 1 (Data lead).** Designed and implemented the preprocessing pipeline,
including the missing-value strategy: the 2,067 hours without a PM2.5 reading are
kept as `NULL` rather than zero-filled, because zero would read as clean air and
bias the target. Built the lag and moving-average feature functions with unit tests,
and produced the EDA notebook that answers the temporal, seasonal, correlation and
wind-direction questions in Task 1.

**Member 2 (Modelling lead).** Selected the model architecture, ran the
hyperparameter search, and produced the experiment table comparing at least two
configurations; wrote the end-to-end prediction script that fetches a window from
the API, applies the same preprocessing as Task 1, loads the trained model and
emits a forecast; assembled the final report PDF.

**Member 3 (SQL lead).** Set up the GitHub repository and the shared FastAPI
application every member pushed into. Designed the relational schema (six tables
across dimension, fact and model layers) with its indexes, constraints and a
daily-rollup view; produced the ERD; wrote and executed the analytical queries with
results captured in `outputs/query_results.md`; built the CSV→MySQL loader; and
implemented all fourteen SQL endpoints, including the two required time-series
queries.

**Member 4 (MongoDB lead).** Designed the document model (one document per
station-hour with embedded `target` and `weather` sub-documents), created the
collection and its indexes, authored the sample documents and the three MongoDB
queries, and documented the mapping between the relational and document designs.

## 4. Before submitting — two things this table exposes

1. **One member has no commits.** The rubric scores *Individual Technical
   Contribution* separately (5 points, 4+ commits each). Work that is only in
   someone's local folder cannot be marked, and a contribution table that credits
   un-pushed work is easy for a marker to check against `git log`.
2. **The MongoDB API half is unwired.** Task 3 is graded as one criterion covering
   *both* databases; the seven `501` responses in `src/api/routers/mongo.py` cap it
   regardless of how complete the SQL surface is.
