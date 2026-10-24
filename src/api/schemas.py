"""Request/response models shared by both database backends.

The same payload shape describes a MongoDB document and a MySQL row, so the
prediction script can switch backends without changing its code.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

WIND_DIRECTIONS = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW", "CV",
)


class _ReadingFields(BaseModel):
    """Validation rules for the measurement columns."""

    pm25: float | None = Field(
        default=None, ge=0, le=2000,
        description="PM2.5 in ug/m3. null means the sensor had a gap, not zero.",
    )
    dewp: float | None = Field(default=None, ge=-60, le=60, description="Dew point, degC")
    temp: float | None = Field(default=None, ge=-60, le=60, description="Temperature, degC")
    pres: float | None = Field(default=None, ge=800, le=1100, description="Pressure, hPa")
    wind_dir: str | None = Field(default=None, description="16-point compass direction or CV")
    wind_speed: float | None = Field(default=None, ge=0, description="Cumulated wind speed, m/s")
    snow_hours: int = Field(default=0, ge=0, le=24)
    rain_hours: int = Field(default=0, ge=0, le=24)
    is_imputed: bool = Field(default=False, description="True if the target was filled by preprocessing")

    model_config = ConfigDict(extra="forbid")

    @field_validator("wind_dir")
    @classmethod
    def _normalise_wind_dir(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalised = value.strip().upper()
        if normalised not in WIND_DIRECTIONS:
            raise ValueError(
                f"wind_dir must be one of {', '.join(WIND_DIRECTIONS)}"
            )
        return normalised


class ReadingCreate(_ReadingFields):
    """POST body for a single hourly observation."""

    station_id: int = Field(default=1, ge=1)
    observed_at: datetime = Field(description="Hourly timestamp, e.g. 2014-12-31 23:00:00")

    @field_validator("observed_at")
    @classmethod
    def _to_hour_grain(cls, value: datetime) -> datetime:
        """The dataset is hourly, so drop minutes/seconds instead of storing them."""
        return value.replace(minute=0, second=0, microsecond=0)


class ReadingUpdate(BaseModel):
    """PUT body. Every field is optional: only what you send is updated."""

    station_id: int | None = Field(default=None, ge=1)
    observed_at: datetime | None = None
    pm25: float | None = Field(default=None, ge=0, le=2000)
    dewp: float | None = Field(default=None, ge=-60, le=60)
    temp: float | None = Field(default=None, ge=-60, le=60)
    pres: float | None = Field(default=None, ge=800, le=1100)
    wind_dir: str | None = None
    wind_speed: float | None = Field(default=None, ge=0)
    snow_hours: int | None = Field(default=None, ge=0, le=24)
    rain_hours: int | None = Field(default=None, ge=0, le=24)
    is_imputed: bool | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("wind_dir")
    @classmethod
    def _normalise_wind_dir(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalised = value.strip().upper()
        if normalised not in WIND_DIRECTIONS:
            raise ValueError(f"wind_dir must be one of {', '.join(WIND_DIRECTIONS)}")
        return normalised


class ReadingOut(BaseModel):
    """A stored observation as returned by the API."""

    reading_id: int | None = None
    station_id: int
    observed_at: datetime
    pm25: float | None = None
    dewp: float | None = None
    temp: float | None = None
    pres: float | None = None
    wind_dir: str | None = None
    wind_speed: float | None = None
    snow_hours: int = 0
    rain_hours: int = 0
    is_imputed: bool = False
    ingested_at: datetime | None = None
    updated_at: datetime | None = None
