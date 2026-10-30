# Team contributions

Counts are from `git log` on `main` on 30 October 2026, and the repository had 38 commits in total at that point. Only GitHub handles are recorded in the repository, so the names column needs filling in before this goes into the PDF.

```bash
git shortlog -sn --all      # the commit counts below
git log --author="<handle>" --oneline | wc -l
```

## 1. Commits and what each member delivered

| Member | Handle | Role | Commits | Main work |
|---|---|---|---|---|
| Member 1 | ambabazi | Data lead | 13 | Cleaning and validation (`scripts/preprocess.py`), lag and moving average features (`scripts/features.py`), the EDA notebook, the cleaned CSV and the unit tests |
| Member 2 | AHIRWE1 | Modelling lead | 1 | Model training with six experiments (`outputs/figures/experiment_table.csv`, `outputs/models/`), the prediction script (`scripts/predict.py`) and its test |
| Member 3 | k-nizy | SQL lead | 13 | Repository setup and the shared API application, MySQL schema and ERD, analytical queries, CSV loader, the SQL endpoints, the Workbench screenshots and this section |
| Member 4 | selenai9 | MongoDB lead | 11 | Collection design and indexes, sample documents, three queries, the loader into Atlas, the MongoDB endpoints with their test log |

## 2. Task coverage

| Task | Where it is in the repository | Owner | Status |
|---|---|---|---|
| Task 1, preprocessing and EDA | `notebooks/pm25_EDA.ipynb`, `scripts/preprocess.py`, `scripts/features.py`, `data/processed/beijing_clean.csv` | Member 1 | done |
| Task 1, model and experiments | `outputs/figures/experiment_table.csv`, `outputs/models/`, `notebooks/pm25_EDA.ipynb` | Member 2 | done, but the training script itself is not in the repository |
| Task 2, relational design | `sql/schema.sql`, `sql/erd.png`, `sql/README.md`, `outputs/query_results.md`, `outputs/screenshots/` | Member 3 | done |
| Task 2, document design | `mongodb/collections.js`, `mongodb/sample_documents.json`, `mongodb/queries.js` | Member 4 | done |
| Task 3, endpoints for MySQL | `src/api/routers/sql.py`, twelve endpoints | Member 3 | done |
| Task 3, endpoints for MongoDB | `src/api/routers/mongo.py`, eight endpoints, log in `mongodb/api_tests.md` | Member 4 | done |
| Task 4, prediction script | `scripts/predict.py`, `tests/test_predict.py` | Member 2 | done |

## 3. What each member did, in their own words

These are short statements to go under the table. Each person should edit their own.

**Member 1, data lead.** I cleaned the raw file and combined the year, month, day and hour columns into one timestamp. I kept the 2,067 hours with no PM2.5 reading as empty values instead of filling them, because a zero would look like clean air and would bias the target. I wrote the lag and moving average features and the tests that check them, and the notebook that answers the EDA questions.

**Member 2, modelling lead.** I trained the model and tuned it, and the experiment table compares six settings against a baseline that repeats the previous day. The best result was RMSE 87.75 against 110.26 for the baseline. I also wrote the prediction script that reads a window from the API, prepares it the same way as the training data and prints a forecast.

**Member 3, SQL lead.** I set up the repository and the API application that everyone else added to. I designed the MySQL schema with six tables, its indexes, constraints and a daily table for the moving averages, drew the ERD, wrote the loader that reads the cleaned CSV into MySQL, wrote the seven analytical queries and recorded their results, and built the twelve SQL endpoints. I also took the Workbench screenshots and wrote the Task 2 and Task 3 sections of this report.

**Member 4, MongoDB lead.** I designed the collection so that one card holds one hour, with the station, the PM2.5 value and the weather inside it. I added the indexes, wrote the sample cards and the three queries, loaded all 43,824 rows into Atlas, and built and tested the eight MongoDB endpoints.
