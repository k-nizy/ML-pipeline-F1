"""Configuration loaded from the environment (or a local .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Repository root: this file lives at <root>/src/api/config.py
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    """Every setting has a safe local default, except the two secrets."""

    # MySQL
    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "root")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "")
    mysql_database: str = os.getenv("MYSQL_DATABASE", "beijing_air")

    # MongoDB
    mongo_uri: str = os.getenv("MONGO_URI", "")
    mongo_database: str = os.getenv("MONGO_DATABASE", "beijing_air")
    mongo_collection: str = os.getenv("MONGO_COLLECTION", "readings")

    # API
    api_host: str = os.getenv("API_HOST", "127.0.0.1")
    api_port: int = int(os.getenv("API_PORT", "8000"))

    default_station_id: int = int(os.getenv("DEFAULT_STATION_ID", "1"))

    # Guardrails so one request cannot pull the whole 43k-row table by accident.
    max_page_size: int = int(os.getenv("MAX_PAGE_SIZE", "1000"))
    default_page_size: int = int(os.getenv("DEFAULT_PAGE_SIZE", "100"))


settings = Settings()
