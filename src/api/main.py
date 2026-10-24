"""FastAPI service for the Beijing PM2.5 time-series pipeline.

Two backends sit behind one app so every member can push to the same service:

    /api/sql/...     MySQL implementation (SQL lead)
    /api/mongo/...   MongoDB implementation (MongoDB lead)

Start it with:

    uvicorn src.api.main:app --reload --port 8000

Interactive docs: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.config import settings
from src.api.routers import mongo, sql

app = FastAPI(
    title="Beijing PM2.5 Time-Series API",
    version="1.0.0",
    description=(
        "CRUD plus time-series queries (latest record, date range) over the "
        "Beijing PM2.5 hourly dataset, implemented twice: once on MySQL and "
        "once on MongoDB."
    ),
)

# Local development only: the prediction script and notebooks call this app
# from another origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sql.router)
app.include_router(mongo.router)


@app.get("/", tags=["meta"])
def root() -> dict:
    """Cheap landing endpoint listing the available route groups."""
    return {
        "service": "Beijing PM2.5 Time-Series API",
        "docs": "/docs",
        "sql": "/api/sql",
        "mongo": "/api/mongo",
        "health": "/health",
    }


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness check that does not touch either database."""
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
