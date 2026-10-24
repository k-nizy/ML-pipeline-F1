"""Lazy MongoDB client.

The client is created on first use so the app still starts (and the SQL routes
still work) when no Atlas URI is configured. The Mongo lead owns this file and
the router in ``routers/mongo.py``.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from src.api.config import settings

_client: Any | None = None


def get_collection():
    """Return the ``readings`` collection, or raise 503 if Mongo is unavailable."""
    global _client

    if not settings.mongo_uri:
        raise HTTPException(
            status_code=503,
            detail=(
                "MongoDB is not configured. Set MONGO_URI in .env "
                "(see .env.example) - the MongoDB lead supplies the Atlas URI."
            ),
        )

    if _client is None:
        try:
            from pymongo import MongoClient
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise HTTPException(
                status_code=503,
                detail="pymongo is not installed. Run: pip install -r requirements.txt",
            ) from exc

        _client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)

    return _client[settings.mongo_database][settings.mongo_collection]
