import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.preprocess import (
    preprocess_data,
    prepare_training_data,
)


class TestPreprocessData(unittest.TestCase):

    def test_dataset_shape(self):
        df = preprocess_data()
        self.assertEqual(df.shape, (43824, 13))

    def test_timestamps_are_sorted(self):
        df = preprocess_data()
        self.assertTrue(df["timestamp"].is_monotonic_increasing)

    def test_timestamps_are_unique(self):
        df = preprocess_data()
        self.assertEqual(df["timestamp"].duplicated().sum(), 0)

    def test_missing_pm25_values_are_preserved(self):
        df = preprocess_data()
        self.assertEqual(df["pm25"].isna().sum(), 2067)

    def test_timestamp_range(self):
        df = preprocess_data()
        self.assertEqual(
            df["timestamp"].min(),
            pd.Timestamp("2010-01-01 00:00:00"),
        )
        self.assertEqual(
            df["timestamp"].max(),
            pd.Timestamp("2014-12-31 23:00:00"),
        )

    def test_training_data_has_no_missing_targets(self):
        df = preprocess_data()
        training_df = prepare_training_data(df)

        self.assertEqual(training_df["pm25"].isna().sum(), 0)

    def test_training_data_has_expected_row_count(self):
        df = preprocess_data()
        training_df = prepare_training_data(df)

        self.assertEqual(len(training_df), 41757)

    def test_missing_required_column_raises_error(self):
        raw_df = pd.DataFrame({
            "year": [2010, 2010],
            "month": [1, 1],
            "day": [1, 1],
            "hour": [0, 1],
            "pm2.5": [10, 20],
            "DEWP": [-10, -9],
            "TEMP": [-5, -4],
            "PRES": [1020, 1021],
            "cbwd": ["NW", "NW"],
            "Iws": [1.0, 2.0],
            "Is": [0, 0],
            # The required "Ir" column is intentionally missing.
        })

        with tempfile.TemporaryDirectory() as temp_dir:
            input_file = Path(temp_dir) / "incomplete.csv"
            raw_df.to_csv(input_file, index=False)

            with self.assertRaisesRegex(ValueError, "missing required columns"):
                preprocess_data(input_file)

    def test_missing_hour_raises_error(self):
        raw_df = pd.DataFrame({
            "year": [2010, 2010, 2010],
            "month": [1, 1, 1],
            "day": [1, 1, 1],
            "hour": [0, 1, 3],
            "pm2.5": [10, 20, 30],
            "DEWP": [-10, -9, -8],
            "TEMP": [-5, -4, -3],
            "PRES": [1020, 1021, 1022],
            "cbwd": ["NW", "NW", "NW"],
            "Iws": [1.0, 2.0, 3.0],
            "Is": [0, 0, 0],
            "Ir": [0, 0, 0],
        })

        with tempfile.TemporaryDirectory() as temp_dir:
            input_file = Path(temp_dir) / "missing_hour.csv"
            raw_df.to_csv(input_file, index=False)

            with self.assertRaisesRegex(ValueError, "one hour apart"):
                preprocess_data(input_file)


if __name__ == "__main__":
    unittest.main()