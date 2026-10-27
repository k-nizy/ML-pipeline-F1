from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = (
    PROJECT_ROOT / "data" / "raw" / "PRSA_data_2010.1.1-2014.12.31.csv"
)
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PROCESSED_FILE = PROCESSED_DIR / "beijing_clean.csv"

REQUIRED_COLUMNS = [
    "year",
    "month",
    "day",
    "hour",
    "pm2.5",
    "DEWP",
    "TEMP",
    "PRES",
    "cbwd",
    "Iws",
    "Is",
    "Ir",
]


def preprocess_data(input_file=RAW_FILE):
    """Load, validate, and chronologically organize hourly PM2.5 data."""
    df = pd.read_csv(input_file)

    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in df.columns
    ]
    if missing_columns:
        raise ValueError(
            f"Input dataset is missing required columns: {missing_columns}"
        )

    df["timestamp"] = pd.to_datetime(
        df[["year", "month", "day", "hour"]]
    )

    df = df.sort_values("timestamp").reset_index(drop=True)

    if df["timestamp"].isna().any():
        raise ValueError("Timestamps cannot contain missing values.")

    if df["timestamp"].duplicated().any():
        raise ValueError("Duplicate timestamps were found.")

    time_differences = df["timestamp"].diff().dropna()

    if not (time_differences == pd.Timedelta(hours=1)).all():
        raise ValueError(
            "Timestamps must be consecutive, exactly one hour apart."
        )

    df = df.rename(columns={"pm2.5": "pm25"})

    return df


def prepare_training_data(df):
    """Return rows with observed PM2.5 targets for supervised training."""
    return df.dropna(subset=["pm25"]).copy()


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    df = preprocess_data()
    df.to_csv(PROCESSED_FILE, index=False, date_format="%Y-%m-%d %H:%M:%S")

    print(f"Processed dataset saved to: {PROCESSED_FILE}")
    print(f"Dataset shape: {df.shape}")
    print(f"Missing PM2.5 values: {df['pm25'].isna().sum()}")
    print(f"Duplicate timestamps: {df['timestamp'].duplicated().sum()}")
    print(f"Missing hourly timestamps: {df['timestamp'].diff().gt(pd.Timedelta(hours=1)).sum()}")
    print(f"First timestamp: {df['timestamp'].min()}")
    print(f"Last timestamp: {df['timestamp'].max()}")


if __name__ == "__main__":
    main()