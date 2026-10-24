"""Load the Beijing PM2.5 time series into MySQL.

Reads either the cleaned CSV (``data/processed/beijing_clean.csv``) or the raw
UCI CSV (``data/raw/PRSA_data_2010.1.1-2014.12.31.csv``), normalises the columns
to the agreed contract, upserts the rows into ``readings`` and rebuilds
``daily_aggregates``.

The upsert key is ``UNIQUE(station_id, observed_at)``, so running this script
twice does not duplicate anything - it refreshes the values instead.

Usage
-----
    python scripts/load_mysql.py --csv data/processed/beijing_clean.csv
    python scripts/load_mysql.py --csv data/raw/PRSA_data_2010.1.1-2014.12.31.csv --truncate

Connection settings come from the environment (see .env.example), and every
one can be overridden with a CLI flag.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

import pymysql
from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
# Column contract
# --------------------------------------------------------------------------- #
# Keys are lower-cased, punctuation-stripped header names; values are the
# column names used inside MySQL.
COLUMN_ALIASES = {
    "timestamp": "timestamp",
    "datetime": "timestamp",
    "date_time": "timestamp",
    "pm25": "pm25",
    "pm2_5": "pm25",
    "dewp": "dewp",
    "temp": "temp",
    "temperature": "temp",
    "pres": "pres",
    "pressure": "pres",
    "cbwd": "wind_dir",
    "wind_dir": "wind_dir",
    "wind_direction": "wind_dir",
    "iws": "wind_speed",
    "wind_speed": "wind_speed",
    "is": "snow_hours",
    "snow_hours": "snow_hours",
    "ir": "rain_hours",
    "rain_hours": "rain_hours",
}

# The raw data only ever contains NW / NE / SE / cv, but the enum allows the
# full 16-point compass so richer datasets can reuse the schema unchanged.
VALID_WIND_DIRS = {
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW", "CV",
}

INSERT_SQL = """
INSERT INTO readings
    (station_id, observed_at, pm25, dewp, temp, pres,
     wind_dir, wind_speed, snow_hours, rain_hours, is_imputed)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    pm25       = VALUES(pm25),
    dewp       = VALUES(dewp),
    temp       = VALUES(temp),
    pres       = VALUES(pres),
    wind_dir   = VALUES(wind_dir),
    wind_speed = VALUES(wind_speed),
    snow_hours = VALUES(snow_hours),
    rain_hours = VALUES(rain_hours),
    is_imputed = VALUES(is_imputed)
"""

# Same rollup as sp_refresh_daily_aggregates, kept inline so the loader works
# even if the procedure was not created.
ROLLUP_SQL = """
INSERT INTO daily_aggregates (
    station_id, agg_date, pm25_avg, pm25_max, pm25_min, pm25_std,
    pm25_count, readings_count, temp_avg, pres_avg
)
SELECT station_id,
       DATE(observed_at),
       ROUND(AVG(pm25), 2), MAX(pm25), MIN(pm25), ROUND(STDDEV_SAMP(pm25), 2),
       SUM(pm25 IS NOT NULL), COUNT(*),
       ROUND(AVG(temp), 2), ROUND(AVG(pres), 2)
FROM readings
GROUP BY station_id, DATE(observed_at)
ON DUPLICATE KEY UPDATE
    pm25_avg       = VALUES(pm25_avg),
    pm25_max       = VALUES(pm25_max),
    pm25_min       = VALUES(pm25_min),
    pm25_std       = VALUES(pm25_std),
    pm25_count     = VALUES(pm25_count),
    readings_count = VALUES(readings_count),
    temp_avg       = VALUES(temp_avg),
    pres_avg       = VALUES(pres_avg)
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", default="data/processed/beijing_clean.csv",
                        help="cleaned CSV (preferred) or the raw UCI CSV")
    parser.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    parser.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    parser.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
    parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "beijing_air"))
    parser.add_argument("--station-id", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--truncate", action="store_true",
                        help="delete existing readings first (full rebuild)")
    return parser.parse_args()


def normalise_header(name: str) -> str:
    """'PM2.5' -> 'pm25', 'wind_dir' -> 'wind_dir'."""
    cleaned = name.strip().lower().replace(".", "").replace("-", "_").replace(" ", "_")
    return COLUMN_ALIASES.get(cleaned, cleaned)


def to_float(value):
    """Return a float or None for 'NA', '', 'NaN'."""
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.upper() in {"NA", "NAN", "NULL", "N/A"}:
        return None
    return float(text)


def to_int(value, default=0) -> int:
    number = to_float(value)
    return default if number is None else int(round(number))


def normalise_wind_dir(value):
    if value is None:
        return None
    text = str(value).strip().upper()
    if text == "" or text in {"NA", "NAN"}:
        return None
    return text if text in VALID_WIND_DIRS else "CV"


def build_timestamp(row: dict) -> datetime | None:
    """Prefer a ready-made timestamp column, otherwise combine year/month/day/hour."""
    if row.get("timestamp"):
        text = str(row["timestamp"]).strip().replace("T", " ")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        raise ValueError(f"unparseable timestamp: {row['timestamp']!r}")

    try:
        return datetime(
            int(row["year"]), int(row["month"]), int(row["day"]), int(row["hour"])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("row has neither a timestamp column nor year/month/day/hour") from exc


def read_rows(csv_path: Path):
    """Yield (timestamp, values-tuple) for each usable CSV row."""
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SystemExit(f"{csv_path} is empty")

        renamed = {name: normalise_header(name) for name in reader.fieldnames}
        stats = {"read": 0, "bad_timestamp": 0, "null_target": 0, "null_wind": 0}
        rows = []

        for raw in reader:
            stats["read"] += 1
            row = {renamed[key]: value for key, value in raw.items() if key is not None}
            try:
                observed_at = build_timestamp(row)
            except (ValueError, KeyError, TypeError):
                stats["bad_timestamp"] += 1
                continue

            pm25 = to_float(row.get("pm25"))
            if pm25 is None:
                stats["null_target"] += 1
            wind_dir = normalise_wind_dir(row.get("wind_dir"))
            if wind_dir is None:
                stats["null_wind"] += 1

            # is_imputed mirrors the preprocessing flag if the cleaned CSV has one,
            # otherwise a NULL target is an observed gap, not an imputed value.
            is_imputed = to_int(row.get("is_imputed", 0))

            rows.append((
                observed_at,
                pm25,
                to_float(row.get("dewp")),
                to_float(row.get("temp")),
                to_float(row.get("pres")),
                wind_dir,
                to_float(row.get("wind_speed")),
                to_int(row.get("snow_hours")),
                to_int(row.get("rain_hours")),
                is_imputed,
            ))

    return rows, stats


def connect(args: argparse.Namespace):
    return pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        charset="utf8mb4",
        autocommit=False,
    )


def main() -> int:
    load_dotenv()
    args = parse_args()
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"[error] CSV not found: {csv_path}\n"
              f"        see data/README.md for the download instructions", file=sys.stderr)
        return 2

    print(f"[1/4] reading {csv_path} ...")
    rows, stats = read_rows(csv_path)
    print(f"      parsed {len(rows):,} rows "
          f"(skipped {stats['bad_timestamp']} without a timestamp, "
          f"{stats['null_target']} with a missing target)")

    connection = connect(args)
    try:
        with connection.cursor() as cursor:
            if args.truncate:
                print("[2/4] truncating readings and daily_aggregates ...")
                cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                cursor.execute("TRUNCATE TABLE forecast_predictions")
                cursor.execute("TRUNCATE TABLE forecast_runs")
                cursor.execute("TRUNCATE TABLE daily_aggregates")
                cursor.execute("TRUNCATE TABLE readings")
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

            # --- station must exist before the FK insert ---------------------
            cursor.execute("SELECT station_id FROM stations WHERE station_id = %s",
                           (args.station_id,))
            if cursor.fetchone() is None:
                print(f"[error] station_id={args.station_id} not found. "
                      f"Run sql/schema.sql first.", file=sys.stderr)
                return 3

            print(f"[3/4] upserting {len(rows):,} hourly rows in batches of "
                  f"{args.batch_size:,} ...")
            payload = [
                (args.station_id, *values) for values in rows
            ]
            for start in range(0, len(payload), args.batch_size):
                cursor.executemany(INSERT_SQL, payload[start:start + args.batch_size])
                connection.commit()
                done = min(start + args.batch_size, len(payload))
                print(f"      {done:,}/{len(payload):,}", end="\r")
            print()

            print("[4/4] rebuilding daily_aggregates ...")
            cursor.execute(ROLLUP_SQL)
            connection.commit()

            # --- report ------------------------------------------------------
            cursor.execute("""
                SELECT COUNT(*), MIN(observed_at), MAX(observed_at),
                       SUM(pm25 IS NULL), COUNT(DISTINCT DATE(observed_at))
                FROM readings WHERE station_id = %s
            """, (args.station_id,))
            total, first_ts, last_ts, null_target, days = cursor.fetchone()

            cursor.execute("SELECT COUNT(*) FROM daily_aggregates WHERE station_id = %s",
                           (args.station_id,))
            daily_rows = cursor.fetchone()[0]

        print("\nload summary")
        print(f"  hourly rows        : {total:,}")
        print(f"  time range         : {first_ts}  ->  {last_ts}")
        print(f"  days covered       : {days:,}")
        print(f"  null pm25 rows     : {null_target:,}")
        print(f"  daily_aggregates   : {daily_rows:,} rows")
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
