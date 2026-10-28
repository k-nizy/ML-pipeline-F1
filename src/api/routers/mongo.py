"""MongoDB routes - owned by the MongoDB lead.

The shape of every endpoint deliberately mirrors ``routers/sql.py`` so both
backends can be compared side by side in the report. The connection helper
(``src.api.db_mongo.get_collection``) is already wired; each handler only needs
its body filled in.

Document shape agreed with the SQL schema (one document per station-hour):

    {
      "_id": ObjectId("..."),
      "station": {"id": 1, "name": "Beijing US Embassy", "city": "Beijing"},
      "timestamp": ISODate("2014-12-31T23:00:00Z"),
      "target": {"pm25": 41.0, "imputed": false},
      "weather": {"dewp": -14.0, "temp": -3.0, "pres": 1026.0,
                  "wind_dir": "NW", "wind_speed": 1.79,
                  "snow_hours": 0, "rain_hours": 0},
      "ingested_at": ISODate("...")
    }

Indexes the collection needs:

    db.readings.createIndex({ "timestamp": 1 })
    db.readings.createIndex({ "station.id": 1, "timestamp": -1 }, { unique: true })

TODO (MongoDB lead): implement each handler below and add the pass-through
tests to outputs/query_results.md.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from src.api.db_mongo import get_collection

router = APIRouter(prefix="/api/mongo", tags=["MongoDB"])

_NOT_IMPLEMENTED = (
    "Not implemented yet - the MongoDB lead owns /api/mongo. "
    "See the module docstring for the agreed document shape."
)

def _clean(doc: dict) -> dict:
    """Turn the ObjectId into plain text so it can be sent as JSON."""
    doc["_id"] = str(doc["_id"])
    return doc

@router.get("/health")
def mongo_health() -> dict:
    """Ping the Atlas cluster."""
    get_collection().database.command("ping")
    return {"status": "ok"}


@router.post("/readings", status_code=201)
def create_reading(payload: dict) -> dict:
    """Insert one hourly document. Reject duplicates on (station.id, timestamp)."""
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.get("/readings")
def list_readings(
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list:
    """Filtered, paginated read - the MongoDB twin of the SQL listing endpoint."""
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.get("/readings/latest")
def latest_reading() -> dict:
    """Most recent document by ``timestamp``."""
    doc = get_collection().find_one(sort=[("timestamp", -1)])
    if doc is None:
        raise HTTPException(status_code=404, detail="No readings found.")
    return _clean(doc)


@router.get("/readings/range")
def readings_by_range(start: datetime, end: datetime) -> list:
    """Required time-series endpoint: records between two timestamps."""
    query = {"timestamp": {"$gte": start, "$lte": end}}
    cursor = get_collection().find(query).sort("timestamp", 1).limit(1000)
    return [_clean(doc) for doc in cursor]


@router.get("/readings/{reading_id}")
def get_reading(reading_id: str) -> dict:
    """Fetch one document by its ObjectId string."""
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.put("/readings/{reading_id}")
def update_reading(reading_id: str, payload: dict) -> dict:
    """Partial update (``$set``) of one document."""
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.delete("/readings/{reading_id}", status_code=204)
def delete_reading(reading_id: str) -> None:
    """Delete one document by ObjectId."""
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)
