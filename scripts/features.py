import pandas as pd


WEATHER_COLS = ["DEWP", "TEMP", "PRES", "Iws", "Is", "Ir"]
WIND_CATS = ["NE", "NW", "SE", "cv"]
LAGS = [1, 2, 3, 24]
MA_WINDOWS = [7, 24]
HISTORY_HOURS = max(max(LAGS) + 1, max(MA_WINDOWS))


def add_timestamp(df):
    """Build the timestamp, sort the rows, and enforce a complete hourly grid."""
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df[["year", "month", "day", "hour"]])
    return df.sort_values("timestamp").set_index("timestamp").asfreq("h")


def build_features(df):
    """Create the shared model features using observations through the current hour."""
    features = df[WEATHER_COLS].copy()
    for category in WIND_CATS:
        features[f"wind_{category}"] = (df["cbwd"] == category).astype(int)
    features["hour"] = df.index.hour
    features["month"] = df.index.month
    features["pm25"] = df["pm2.5"]
    for lag in LAGS:
        features[f"pm25_lag_{lag}h"] = df["pm2.5"].shift(lag)
    for window in MA_WINDOWS:
        features[f"pm25_ma_{window}h"] = (
            df["pm2.5"].rolling(window, min_periods=window).mean()
        )
    return features


def make_target(df, horizon):
    """Return PM2.5 values `horizon` hours after each feature row."""
    return df["pm2.5"].shift(-horizon)


def create_time_features(df):
    """
    Create lag and moving-average features from hourly PM2.5 data.

    The input must contain a timestamp column with unique, consecutive
    hourly timestamps and a pm25 column.

    Features created:
    - pm25_lag_1h: PM2.5 value from the previous hour.
    - pm25_lag_24h: PM2.5 value from 24 hours earlier.
    - pm25_ma_7h: Mean PM2.5 over the previous 7 hours.
    - pm25_ma_24h: Mean PM2.5 over the previous 24 hours.

    All features use past observations only, excluding the current hour.
    Moving averages require every observation in their respective windows
    to be available. Missing values can therefore cause additional NaNs.
    """
    if "timestamp" not in df.columns:
        raise ValueError("The dataframe must contain a 'timestamp' column.")

    if "pm25" not in df.columns:
        raise ValueError("The dataframe must contain a 'pm25' column.")

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    time_differences = df["timestamp"].diff().dropna()

    if not (time_differences == pd.Timedelta(hours=1)).all():
        raise ValueError(
            "Timestamps must be unique and consecutive, exactly one hour apart."
        )

    df["pm25_lag_1h"] = df["pm25"].shift(1)
    df["pm25_lag_24h"] = df["pm25"].shift(24)

    df["pm25_ma_7h"] = (
        df["pm25"]
        .shift(1)
        .rolling(window=7, min_periods=7)
        .mean()
    )

    df["pm25_ma_24h"] = (
        df["pm25"]
        .shift(1)
        .rolling(window=24, min_periods=24)
        .mean()
    )

    return df