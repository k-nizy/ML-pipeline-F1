# Data

## Raw data (not committed)

We use the **Beijing PM2.5 Data Set** (hourly, 2010-01-01 → 2014-12-31, 43,824 rows).

- Kaggle: <https://www.kaggle.com/datasets/uciml/beijing-multisite-airquality-data-set> (search "Beijing PM2.5")
- UCI mirror (used here): <https://archive.ics.uci.edu/static/public/381/beijing+pm2+5+data.zip>
- Direct file: `PRSA_data_2010.1.1-2014.12.31.csv`

Download it and place it at:

```
data/raw/PRSA_data_2010.1.1-2014.12.31.csv
```

Raw columns: `No, year, month, day, hour, pm2.5, DEWP, TEMP, PRES, cbwd, Iws, Is, Ir`

| Column | Meaning |
|---|---|
| `pm2.5` | PM2.5 concentration, µg/m³ — **the prediction target** (has gaps) |
| `DEWP` | dew point, °C |
| `TEMP` | temperature, °C |
| `PRES` | pressure, hPa |
| `cbwd` | combined wind direction |
| `Iws` | cumulated wind speed, m/s |
| `Is` | cumulated hours of snow |
| `Ir` | cumulated hours of rain |

## Cleaned data (committed)

`data/processed/beijing_clean.csv` — produced by `scripts/preprocess.py` (data lead).

**Column contract** that the loader, API and model all depend on:

```
timestamp,pm25,dewp,temp,pres,wind_dir,wind_speed,snow_hours,rain_hours
```

- `timestamp` — ISO-8601 hourly, `YYYY-MM-DD HH:MM:SS` (no timezone offset, Asia/Shanghai)
- `pm25` — nullable float (raw `NaN`s stay `NaN`; the preprocessing script documents its imputation rule)
- `wind_dir` — one of the 16 compass points or `CV` (calm/variable)

Rebuild the database with:

```bash
python scripts/load_mysql.py --csv data/processed/beijing_clean.csv
```
