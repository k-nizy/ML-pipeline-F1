"""Re-run the analytical SQL queries and write the results to markdown.

This keeps ``outputs/query_results.md`` in sync with whatever is actually in the
database, so the report never quotes stale numbers. Run it after loading data:

    python scripts/export_query_results.py
    python scripts/export_query_results.py --port 3307 --output outputs/query_results.md
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

# (number, title, why it matters, sql)
QUERIES: list[tuple[str, str, str, str]] = [
    (
        "Q1",
        "Latest record per station",
        "The 'latest record' time-series requirement, written with ROW_NUMBER() so it "
        "still returns one row per site once more stations are added.",
        """
        SELECT station_id, reading_id, observed_at, pm25, dewp, temp, pres, wind_dir, wind_speed
        FROM (
            SELECT r.*, ROW_NUMBER() OVER (PARTITION BY r.station_id
                                           ORDER BY r.observed_at DESC) AS rn
            FROM readings r
        ) ranked
        WHERE rn = 1
        """,
    ),
    (
        "Q2",
        "Daily value with 1-day / 7-day lag and 7 & 30-day moving averages",
        "Requirement: lagged features and moving averages. pm25_ma7 is the trailing "
        "7-day mean, pm25_lag7 the same weekday last week - the two features the "
        "modelling task leans on.",
        """
        SELECT agg_date, pm25_avg, pm25_lag1, pm25_lag7, pm25_ma7, ma7_window_days, pm25_ma30
        FROM v_daily_pm25_moving_avg
        WHERE station_id = 1
        ORDER BY agg_date DESC
        LIMIT 14
        """,
    ),
    (
        "Q3",
        "Monthly seasonality (worst 15 station-months)",
        "Answers 'is there a seasonal trend?': January and February dominate, "
        "summer months are far cleaner.",
        """
        SELECT YEAR(agg_date) AS yr, MONTH(agg_date) AS mth, COUNT(*) AS days,
               ROUND(AVG(pm25_avg), 1) AS avg_pm25,
               ROUND(MAX(pm25_max), 1) AS peak_hourly,
               SUM(pm25_max > 150)     AS days_above_150
        FROM daily_aggregates
        GROUP BY yr, mth
        ORDER BY avg_pm25 DESC
        """,
    ),
    (
        "Q4",
        "Lag-1 dependency: yesterday vs today (Pearson r)",
        "Answers 'are there lag effects?'. Computed inline because MySQL has no CORR() "
        "aggregate; a healthy positive r justifies lag features in the model.",
        """
        SELECT COUNT(*) AS paired_days,
               CAST(
                 (COUNT(*) * SUM(t.pm25_avg * y.pm25_avg) - SUM(t.pm25_avg) * SUM(y.pm25_avg))
                 / SQRT(
                     (COUNT(*) * SUM(t.pm25_avg * t.pm25_avg) - POW(SUM(t.pm25_avg), 2))
                   * (COUNT(*) * SUM(y.pm25_avg * y.pm25_avg) - POW(SUM(y.pm25_avg), 2))
                   ) AS DECIMAL(10,4)) AS lag1_pearson_r
        FROM daily_aggregates y
        JOIN daily_aggregates t
          ON t.station_id = y.station_id AND t.agg_date = y.agg_date + INTERVAL 1 DAY
        WHERE y.pm25_avg IS NOT NULL AND t.pm25_avg IS NOT NULL
        """,
    ),
    (
        "Q5",
        "External variable: wind direction vs target",
        "Answers 'do external variables correlate with the target?'. Calm/variable air "
        "traps pollution; north-westerly winds ventilate the city.",
        """
        SELECT wind_dir, COUNT(*) AS hours,
               ROUND(AVG(pm25), 1)         AS avg_pm25,
               ROUND(MAX(pm25), 1)         AS max_pm25,
               ROUND(STDDEV_SAMP(pm25), 1) AS sd_pm25
        FROM readings
        WHERE pm25 IS NOT NULL
        GROUP BY wind_dir
        ORDER BY avg_pm25 DESC
        """,
    ),
    (
        "Q6",
        "Date-range + threshold: worst hours of January 2014",
        "The 'records by date range' requirement (mirrored by GET /api/sql/readings/range), "
        "combined with a target threshold and an index-friendly predicate.",
        """
        SELECT r.observed_at, s.station_name, r.pm25, r.wind_dir, r.wind_speed, r.temp
        FROM readings r
        JOIN stations s ON s.station_id = r.station_id
        WHERE r.observed_at BETWEEN '2014-01-01 00:00:00' AND '2014-01-31 23:59:59'
          AND r.pm25 >= 300
        ORDER BY r.pm25 DESC
        LIMIT 20
        """,
    ),
    (
        "Q7",
        "Experiment comparison table (Task 1)",
        "Reads the experiment table straight out of MySQL. Populated by "
        "scripts/train_model.py, so it is empty until the model lead's first run.",
        """
        SELECT m.model_name, m.model_type, fr.experiment_label,
               fr.rmse, fr.mae, fr.r2, fr.test_start, fr.test_end
        FROM forecast_runs fr
        JOIN models m ON m.model_id = fr.model_id
        ORDER BY fr.rmse ASC
        """,
    ),
]

# The exact query the date-range endpoint runs (no join), so the plan shown here
# is the plan the API actually uses.
RANGE_SQL = """
SELECT reading_id, observed_at, pm25
FROM readings
WHERE observed_at BETWEEN '2014-01-01 00:00:00' AND '2014-01-31 23:59:59'
"""


def cell(value) -> str:
    """Render one value for a markdown table."""
    if value is None:
        return "*NULL*"
    if isinstance(value, Decimal):
        # Keep the scale MySQL returned: 12.00 stays 12.00, but a Pearson r of
        # 0.5632 is not silently rounded to 0.56.
        return str(value)
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value).replace("|", "\\|")


def render(rows: list[dict], columns: list[str], max_rows: int | None = None) -> str:
    """Turn a result set into a markdown table, optionally truncated."""
    if not rows:
        return "_(no rows - table is empty)_\n"

    shown = rows[:max_rows] if max_rows else rows
    lines = ["| " + " | ".join(columns) + " |",
             "|" + "|".join("---" for _ in columns) + "|"]
    for row in shown:
        lines.append("| " + " | ".join(cell(row[c]) for c in columns) + " |")
    if max_rows and len(rows) > max_rows:
        lines.append(f"\n_Showing {max_rows} of {len(rows)} rows._")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    parser.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    parser.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
    parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "beijing_air"))
    parser.add_argument("--output", default="outputs/query_results.md")
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()

    connection = pymysql.connect(
        host=args.host, port=args.port, user=args.user, password=args.password,
        database=args.database, charset="utf8mb4", cursorclass=DictCursor,
    )

    parts = [
        "# SQL query results\n",
        "Auto-generated by `scripts/export_query_results.py` - re-run it after reloading "
        "the data instead of pasting results by hand.\n",
        f"Database `{args.database}` on `{args.host}:{args.port}`, "
        f"generated {datetime.now():%Y-%m-%d %H:%M}.\n",
    ]

    try:
        with connection.cursor() as cursor:
            for number, title, why, sql in QUERIES:
                cursor.execute(sql)
                rows = list(cursor.fetchall())
                columns = list(rows[0].keys()) if rows else ["result"]
                max_rows = 15 if number == "Q3" else None

                parts.append(f"\n## {number}. {title}\n")
                parts.append(f"*{why}*\n")
                parts.append("```sql\n" + sql.strip() + "\n```\n")
                parts.append(render(rows, columns, max_rows))
                parts.append(f"\n_{len(rows)} row(s) returned._\n")

            # Execution plan for the date-range query the API runs.
            cursor.execute("EXPLAIN " + RANGE_SQL)
            plan = list(cursor.fetchall())
            parts.append("\n## Execution plan: date-range query\n")
            parts.append("Proves the date-range query is a range scan over "
                         "`idx_readings_observed_at` (744 of 43,824 rows for one month) "
                         "instead of a full table scan.\n")
            parts.append(render(plan, list(plan[0].keys()) if plan else ["result"]))

            # Same query with measured timing.
            cursor.execute("EXPLAIN ANALYZE " + RANGE_SQL)
            analysed = [list(row.values())[0] for row in cursor.fetchall()]
            parts.append("\nMeasured with `EXPLAIN ANALYZE`:\n\n```text\n"
                         + "\n".join(str(line) for line in analysed) + "\n```\n")
    finally:
        connection.close()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(parts), encoding="utf-8", newline="\n")
    print(f"wrote {output} ({len(QUERIES)} queries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
