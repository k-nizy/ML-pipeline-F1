import unittest

import pandas as pd

from scripts.preprocess import (
    preprocess_data,
    prepare_training_data,
)

class TestPreprocessData(unittest.TestCase):

    def test_dataset_shape(self):
        df = preprocess_data()
        self.assertEqual(df.shape, (43824, 14))

    def test_timestamps_are_sorted(self):
        df = preprocess_data()
        self.assertTrue(df["timestamp"].is_monotonic_increasing)

    def test_timestamps_are_unique(self):
        df = preprocess_data()
        self.assertEqual(df["timestamp"].duplicated().sum(), 0)

    def test_missing_pm25_values_are_preserved(self):
        df = preprocess_data()
        self.assertEqual(df["pm2.5"].isna().sum(), 2067)

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

        self.assertEqual(training_df["pm2.5"].isna().sum(), 0)

    def test_training_data_has_expected_row_count(self):
        df = preprocess_data()
        training_df = prepare_training_data(df)

        self.assertEqual(len(training_df), 41757)    


if __name__ == "__main__":
    unittest.main()