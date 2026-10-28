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

from datetime import datetime, timezone

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

def _to_object_id(reading_id: str) -> ObjectId:
    """Check the id from the web address and turn it into an ObjectId."""
    try:
        return ObjectId(reading_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid reading id.")

@router.get("/health")
def mongo_health() -> dict:
    """Ping the Atlas cluster."""
    get_collection().database.command("ping")
    return {"status": "ok"}


@router.post("/readings", status_code=201)
def create_reading(payload: dict) -> dict:
    """Insert one hourly document. Reject duplicates on (station.id, timestamp)."""
    try:
        payload["station"]["id"]
        payload["timestamp"] = datetime.fromisoformat(str(payload["timestamp"]))
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Payload needs station.id and a valid ISO timestamp.",
        )
    payload["ingested_at"] = datetime.now(timezone.utc)
    try:
        get_collection().insert_one(payload)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="A reading for this station and hour already exists.",
        )
    return _clean(payload)


@router.get("/readings")
def list_readings(
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list:
    """Filtered, paginated read - the MongoDB twin of the SQL listing endpoint."""
    query = {}
    if start is not None or end is not None:
        query["timestamp"] = {}
        if start is not None:
            query["timestamp"]["$gte"] = start
        if end is not None:
            query["timestamp"]["$lte"] = end
    cursor = get_collection().find(query).sort("timestamp", 1).skip(offset).limit(limit)
    return [_clean(doc) for doc in cursor]


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
    doc = get_collection().find_one({"_id": _to_object_id(reading_id)})
    if doc is None:
        raise HTTPException(status_code=404, detail="Reading not found.")
    return _clean(doc)


@router.put("/readings/{reading_id}")
def update_reading(reading_id: str, payload: dict) -> dict:
    """Partial update (``$set``) of one document."""
    oid = _to_object_id(reading_id)
    payload.pop("_id", None)
    if not payload:
        raise HTTPException(status_code=400, detail="Nothing to update.")
    collection = get_collection()
    result = collection.update_one({"_id": oid}, {"$set": payload})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reading not found.")
    return _clean(collection.find_one({"_id": oid}))


@router.delete("/readings/{reading_id}", status_code=204)
def delete_reading(reading_id: str) -> None:
    """Delete one document by ObjectId."""
    result = get_collection().delete_one({"_id": _to_object_id(reading_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Reading not found.")
