from pathlib import Path

import pandas as pd


# Locate the project root and dataset files.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "PRSA_data_2010.1.1-2014.12.31.csv"
)
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PROCESSED_FILE = PROCESSED_DIR / "pm25_processed.csv"


def preprocess_data(input_file=RAW_FILE):
    """Load, validate, and chronologically organize the PM2.5 dataset."""
    df = pd.read_csv(input_file)

    # Create a timestamp from the original date and time columns.
    df["timestamp"] = pd.to_datetime(
        df[["year", "month", "day", "hour"]]
    )

    # Sort observations by timestamp.
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Check that timestamps are unique and chronologically ordered.
    if df["timestamp"].duplicated().any():
        raise ValueError("Duplicate timestamps were found.")

    if not df["timestamp"].is_monotonic_increasing:
        raise ValueError("Timestamps are not sorted chronologically.")

    return df

def prepare_training_data(df):
    """Return rows with observed PM2.5 targets for supervised training."""
    training_df = df.dropna(subset=["pm2.5"]).copy()
    return training_df

def main():
    """Run preprocessing and save the processed dataset."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    df = preprocess_data()
    df.to_csv(PROCESSED_FILE, index=False)

    print(f"Processed dataset saved to: {PROCESSED_FILE}")
    print(f"Dataset shape: {df.shape}")
    print(f"Missing PM2.5 values: {df['pm2.5'].isna().sum()}")
    print(f"Duplicate timestamps: {df['timestamp'].duplicated().sum()}")
    print(f"First timestamp: {df['timestamp'].min()}")
    print(f"Last timestamp: {df['timestamp'].max()}")


if __name__ == "__main__":
    main()
