"""Fetch recent readings from the SQL API and forecast PM2.5 24 hours ahead."""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import lightgbm as lgb
import pandas as pd
import requests

if __package__:
    from scripts.features import HISTORY_HOURS, add_timestamp, build_features
else:
    from features import HISTORY_HOURS, add_timestamp, build_features

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METADATA = PROJECT_ROOT / "outputs" / "models" / "e4_regularized_pm25_24h.json"
DEFAULT_API_URL = "http://127.0.0.1:8000"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Base URL of the running API")
    parser.add_argument("--station-id", type=int, default=1, help="Station identifier")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds")
    parser.add_argument(
        "--metadata",
        type=Path,
        default=DEFAULT_METADATA,
        help="Path to the exported model metadata JSON",
    )
    return parser.parse_args()


def fetch_history(
    api_url: str,
    station_id: int,
    timeout: float,
) -> list[dict[str, Any]]:
    """Fetch the latest timestamp, then request the 25 hourly rows ending there."""
    base_url = api_url.rstrip("/")
    latest_response = requests.get(
        f"{base_url}/api/sql/readings/latest",
        params={"station_id": station_id},
        timeout=timeout,
    )
    latest_response.raise_for_status()
    latest = latest_response.json()
    if not isinstance(latest, dict) or "observed_at" not in latest:
        raise ValueError("Latest-reading API response must contain an observed_at field.")

    latest_timestamp = pd.Timestamp(latest["observed_at"])
    if latest_timestamp.tz is not None:
        raise ValueError(
            "The model expects timezone-naive dataset timestamps; "
            "the API returned a timezone-aware timestamp."
        )
    start = latest_timestamp - pd.Timedelta(hours=HISTORY_HOURS - 1)
    history_response = requests.get(
        f"{base_url}/api/sql/readings/range",
        params={
            "start": start.isoformat(),
            "end": latest_timestamp.isoformat(),
            "station_id": station_id,
            "limit": HISTORY_HOURS,
        },
        timeout=timeout,
    )
    history_response.raise_for_status()
    records = history_response.json()
    if not isinstance(records, list):
        raise ValueError("Date-range API response must be a JSON list of readings.")
    if not records or pd.Timestamp(records[-1]["observed_at"]) != latest_timestamp:
        raise ValueError(
            "Date-range results must end at the timestamp returned by the latest endpoint."
        )
    return records


def records_to_features(records: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Map API field names into the shared training feature builder."""
    if len(records) != HISTORY_HOURS:
        raise ValueError(
            f"Expected {HISTORY_HOURS} hourly records, received {len(records)}. "
            "The API must return the full feature history, including rows with null PM2.5."
        )

    api = pd.DataFrame.from_records(records)
    required = {
        "observed_at", "pm25", "dewp", "temp", "pres", "wind_dir",
        "wind_speed", "snow_hours", "rain_hours",
    }
    missing = required.difference(api.columns)
    if missing:
        raise ValueError(f"Date-range records are missing required fields: {sorted(missing)}")

    timestamps = pd.to_datetime(api["observed_at"], errors="raise")
    if timestamps.dt.tz is not None:
        raise ValueError(
            "The model expects timezone-naive dataset timestamps; "
            "date-range records contain timezone-aware timestamps."
        )
    api = api.assign(timestamp=timestamps).sort_values("timestamp")
    differences = api["timestamp"].diff().dropna()
    if not differences.eq(pd.Timedelta(hours=1)).all():
        raise ValueError("The API history must contain unique consecutive hourly records.")

    latest_timestamp = api["timestamp"].iloc[-1]
    hourly = pd.DataFrame(
        {
            "year": api["timestamp"].dt.year,
            "month": api["timestamp"].dt.month,
            "day": api["timestamp"].dt.day,
            "hour": api["timestamp"].dt.hour,
            "pm2.5": pd.to_numeric(api["pm25"], errors="raise"),
            "DEWP": pd.to_numeric(api["dewp"], errors="raise"),
            "TEMP": pd.to_numeric(api["temp"], errors="raise"),
            "PRES": pd.to_numeric(api["pres"], errors="raise"),
            "cbwd": api["wind_dir"].str.strip().str.lower(),
            "Iws": pd.to_numeric(api["wind_speed"], errors="raise"),
            "Is": pd.to_numeric(api["snow_hours"], errors="raise"),
            "Ir": pd.to_numeric(api["rain_hours"], errors="raise"),
        }
    )
    hourly = add_timestamp(hourly)
    features = build_features(hourly)
    return features.iloc[[-1]], latest_timestamp


def predict(
    api_url: str,
    station_id: int,
    timeout: float,
    metadata_path: Path,
) -> dict[str, Any]:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("horizon_hours") != 24:
        raise ValueError("This script currently supports the exported 24-hour forecast model only.")
    if metadata.get("feature_notes", {}).get("history_hours_required") != HISTORY_HOURS:
        raise ValueError("Model metadata history requirement does not match the shared feature pipeline.")

    model_path = metadata_path.parent / metadata["model_file"]
    if not model_path.is_file():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    records = fetch_history(api_url, station_id, timeout)
    features, latest_timestamp = records_to_features(records)
    feature_columns = metadata["feature_columns"]
    missing_features = set(feature_columns).difference(features.columns)
    if missing_features:
        raise ValueError(f"Feature builder is missing model inputs: {sorted(missing_features)}")
    model = lgb.Booster(model_file=str(model_path))
    if model.feature_name() != feature_columns:
        raise ValueError("Model feature names do not match the metadata feature_columns.")
    prediction = max(0.0, float(model.predict(features.loc[:, feature_columns])[0]))
    forecast_timestamp = latest_timestamp + timedelta(hours=metadata["horizon_hours"])
    return {
        "model": metadata["experiment"],
        "station_id": station_id,
        "latest_observation_at": latest_timestamp.isoformat(),
        "forecast_for": forecast_timestamp.isoformat(),
        "horizon_hours": metadata["horizon_hours"],
        "predicted_pm25": prediction,
        "unit": "µg/m³",
    }


def main() -> None:
    args = parse_args()
    try:
        result = predict(args.api_url, args.station_id, args.timeout, args.metadata)
    except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError, FileNotFoundError) as exc:
        raise SystemExit(f"Prediction failed: {exc}") from exc
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
