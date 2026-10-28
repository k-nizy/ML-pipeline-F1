"""MySQL endpoints: CRUD plus the two required time-series queries.

Route order matters in FastAPI: the literal paths (``/readings/latest``,
``/readings/range``) are declared before ``/readings/{reading_id}``, otherwise
``latest`` would be parsed as an integer id and rejected with a 422.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pymysql
from fastapi import APIRouter, HTTPException, Query, Response

from src.api.config import settings
from src.api.db_sql import cursor, fetch_all, fetch_one
from src.api.schemas import ReadingCreate, ReadingOut, ReadingUpdate

router = APIRouter(prefix="/api/sql", tags=["SQL / MySQL"])

READING_COLUMNS = (
    "reading_id, station_id, observed_at, pm25, dewp, temp, pres, wind_dir, "
    "wind_speed, snow_hours, rain_hours, is_imputed, ingested_at, updated_at"
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _db_error(exc: pymysql.err.MySQLError) -> HTTPException:
    """Map driver errors to honest status codes.

    Only a connection-level failure (OperationalError) is a 503; a bad column or
    syntax error is a server bug (500), and mislabelling it as 'unreachable'
    sends whoever debugs it in the wrong direction.
    """
    if isinstance(exc, pymysql.err.OperationalError):
        return HTTPException(
            status_code=503,
            detail=(
                f"MySQL is unreachable ({exc}). Start the server, run "
                "sql/schema.sql, and check MYSQL_* in .env."
            ),
        )
    return HTTPException(status_code=500, detail=f"database error: {exc}")


def _check_range(start: datetime | None, end: datetime | None) -> None:
    if start and end and start > end:
        raise HTTPException(status_code=400, detail="start must be earlier than end")


def _where_clause(
    start: datetime | None = None,
    end: datetime | None = None,
    station_id: int | None = None,
    min_pm25: float | None = None,
    max_pm25: float | None = None,
) -> tuple[str, list[Any]]:
    """Build a safe WHERE clause; values always travel as bound parameters."""
    clauses: list[str] = []
    params: list[Any] = []

    if station_id is not None:
        clauses.append("station_id = %s")
        params.append(station_id)
    if start is not None:
        clauses.append("observed_at >= %s")
        params.append(start)
    if end is not None:
        clauses.append("observed_at <= %s")
        params.append(end)
    if min_pm25 is not None:
        clauses.append("pm25 >= %s")
        params.append(min_pm25)
    if max_pm25 is not None:
        clauses.append("pm25 <= %s")
        params.append(max_pm25)

    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _get_reading_or_404(reading_id: int) -> dict[str, Any]:
    row = fetch_one(
        f"SELECT {READING_COLUMNS} FROM readings WHERE reading_id = %s", (reading_id,)
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"reading {reading_id} not found")
    return row


def _count(where: str, params: list[Any]) -> int:
    row = fetch_one(f"SELECT COUNT(*) AS n FROM readings{where}", tuple(params))
    return int(row["n"]) if row else 0


# --------------------------------------------------------------------------- #
# meta
# --------------------------------------------------------------------------- #
@router.get("/health", summary="Check the MySQL connection")
def sql_health() -> dict[str, Any]:
    try:
        row = fetch_one("SELECT VERSION() AS version, DATABASE() AS db")
    except pymysql.err.MySQLError as exc:
        raise _db_error(exc) from exc
    return {"status": "ok", **(row or {})}


@router.get("/stations", summary="List monitoring stations")
def list_stations() -> list[dict[str, Any]]:
    try:
        return fetch_all(f"SELECT * FROM stations WHERE station_id IS NOT NULL ORDER BY station_id")
    except pymysql.err.MySQLError as exc:
        raise _db_error(exc) from exc


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
@router.post("/readings", response_model=ReadingOut, status_code=201,
             summary="Create one hourly reading")
def create_reading(payload: ReadingCreate) -> dict[str, Any]:
    sql = """
        INSERT INTO readings
            (station_id, observed_at, pm25, dewp, temp, pres, wind_dir,
             wind_speed, snow_hours, rain_hours, is_imputed)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        payload.station_id, payload.observed_at, payload.pm25, payload.dewp,
        payload.temp, payload.pres, payload.wind_dir, payload.wind_speed,
        payload.snow_hours, payload.rain_hours, int(payload.is_imputed),
    )
    try:
        with cursor(commit=True) as cur:
            cur.execute(sql, params)
            new_id = cur.lastrowid
    except pymysql.err.IntegrityError as exc:
        if exc.args and exc.args[0] == 1062:
            raise HTTPException(
                status_code=409,
                detail=(f"a reading for station {payload.station_id} at "
                        f"{payload.observed_at} already exists"),
            ) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except pymysql.err.MySQLError as exc:
        raise _db_error(exc) from exc
    return _get_reading_or_404(int(new_id))


@router.get("/readings", summary="List readings (filter by station, date, target)")
def list_readings(
    response: Response,
    start: datetime | None = Query(default=None, description="inclusive, e.g. 2014-01-01"),
    end: datetime | None = Query(default=None, description="inclusive, e.g. 2014-01-31"),
    station_id: int | None = Query(default=None, ge=1),
    min_pm25: float | None = Query(default=None, ge=0),
    max_pm25: float | None = Query(default=None, ge=0),
    limit: int = Query(default=settings.default_page_size, ge=1, le=settings.max_page_size),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    _check_range(start, end)
    where, params = _where_clause(start, end, station_id, min_pm25, max_pm25)
    sql = (f"SELECT {READING_COLUMNS} FROM readings{where} "
           f"ORDER BY observed_at ASC, reading_id ASC LIMIT %s OFFSET %s")
    try:
        rows = fetch_all(sql, tuple(params + [limit, offset]))
        response.headers["X-Total-Count"] = str(_count(where, params))
    except pymysql.err.MySQLError as exc:
        raise _db_error(exc) from exc
    return rows


@router.get("/readings/latest", summary="Latest record (required time-series query)")
def latest_reading(
    station_id: int | None = Query(default=None, ge=1),
) -> dict[str, Any]:
    where, params = _where_clause(station_id=station_id)
    sql = f"SELECT {READING_COLUMNS} FROM readings{where} ORDER BY observed_at DESC LIMIT 1"
    try:
        row = fetch_one(sql, tuple(params))
    except pymysql.err.MySQLError as exc:
        raise _db_error(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="no readings stored yet")
    return row


@router.get("/readings/range", summary="Records by date range (required time-series query)")
def readings_by_range(
    response: Response,
    start: datetime = Query(description="inclusive start, e.g. 2014-12-30T00:00:00"),
    end: datetime = Query(description="inclusive end, e.g. 2014-12-31T23:00:00"),
    station_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=settings.max_page_size, ge=1, le=10000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Same filter as the listing endpoint but with a mandatory window - this is
    the endpoint the Task 4 prediction script calls."""
    _check_range(start, end)
    where, params = _where_clause(start, end, station_id)
    sql = (f"SELECT {READING_COLUMNS} FROM readings{where} "
           f"ORDER BY observed_at ASC LIMIT %s OFFSET %s")
    try:
        rows = fetch_all(sql, tuple(params + [limit, offset]))
        response.headers["X-Total-Count"] = str(_count(where, params))
    except pymysql.err.MySQLError as exc:
        raise _db_error(exc) from exc
    return rows


@router.get("/readings/{reading_id}", response_model=ReadingOut, summary="Get one reading")
def get_reading(reading_id: int) -> dict[str, Any]:
    try:
        return _get_reading_or_404(reading_id)
    except pymysql.err.MySQLError as exc:
        raise _db_error(exc) from exc


@router.put("/readings/{reading_id}", response_model=ReadingOut, summary="Update a reading")
def update_reading(reading_id: int, payload: ReadingUpdate) -> dict[str, Any]:
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="no fields supplied")

    if "observed_at" in updates and updates["observed_at"] is not None:
        updates["observed_at"] = updates["observed_at"].replace(minute=0, second=0, microsecond=0)
    if "is_imputed" in updates and updates["is_imputed"] is not None:
        updates["is_imputed"] = int(updates["is_imputed"])

    assignments = ", ".join(f"{column} = %s" for column in updates)
    params = list(updates.values()) + [reading_id]
    try:
        with cursor(commit=True) as cur:
            cur.execute(f"UPDATE readings SET {assignments} WHERE reading_id = %s", params)
    except pymysql.err.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="update violates a unique constraint") from exc
    except pymysql.err.MySQLError as exc:
        raise _db_error(exc) from exc

    # MySQL counts *changed* rows, not matched ones, so rowcount is also 0 when the
    # PUT body repeats the stored values. Only a genuinely missing row is a 404, so
    # the existence check below decides, not rowcount.
    return _get_reading_or_404(reading_id)


@router.delete("/readings/{reading_id}", status_code=204, summary="Delete a reading")
def delete_reading(reading_id: int) -> Response:
    try:
        with cursor(commit=True) as cur:
            cur.execute("DELETE FROM readings WHERE reading_id = %s", (reading_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"reading {reading_id} not found")
    except pymysql.err.MySQLError as exc:
        raise _db_error(exc) from exc
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# analysis helpers used by the notebook / prediction script
# --------------------------------------------------------------------------- #
@router.get("/aggregates/daily", summary="Daily rollup with 7/30-day moving averages")
def daily_aggregates(
    start: datetime | None = None,
    end: datetime | None = None,
    station_id: int = Query(default=settings.default_station_id, ge=1),
    limit: int = Query(default=365, ge=1, le=5000),
) -> list[dict[str, Any]]:
    _check_range(start, end)
    sql = """
        SELECT agg_date, pm25_avg, pm25_max, pm25_min, pm25_std,
               pm25_count, readings_count, temp_avg, pres_avg,
               pm25_lag1, pm25_lag7, pm25_ma7, pm25_ma30, ma7_window_days
        FROM v_daily_pm25_moving_avg
        WHERE station_id = %s
          AND (%s IS NULL OR agg_date >= DATE(%s))
          AND (%s IS NULL OR agg_date <= DATE(%s))
        ORDER BY agg_date ASC
        LIMIT %s
    """
    params = (station_id, start, start, end, end, limit)
    try:
        return fetch_all(sql, params)
    except pymysql.err.MySQLError as exc:
        raise _db_error(exc) from exc


@router.get("/stats", summary="Dataset summary statistics")
def dataset_stats() -> dict[str, Any]:
    sql = """
        SELECT COUNT(*)                AS hourly_rows,
               MIN(observed_at)        AS first_timestamp,
               MAX(observed_at)        AS last_timestamp,
               COUNT(DISTINCT DATE(observed_at)) AS days_covered,
               SUM(pm25 IS NULL)       AS null_target_rows,
               ROUND(AVG(pm25), 2)     AS pm25_mean,
               ROUND(MIN(pm25), 2)     AS pm25_min,
               ROUND(MAX(pm25), 2)     AS pm25_max,
               ROUND(STDDEV_SAMP(pm25), 2) AS pm25_std
        FROM readings
    """
    try:
        return fetch_one(sql) or {}
    except pymysql.err.MySQLError as exc:
        raise _db_error(exc) from exc
