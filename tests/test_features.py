import unittest

import pandas as pd

from scripts.features import create_time_features


class TestTimeFeatures(unittest.TestCase):

    def setUp(self):
        self.df = pd.DataFrame({
            "timestamp": pd.date_range(
                start="2024-01-01",
                periods=30,
                freq="h",
            ),
            "pm25": range(1, 31),
        })

    def test_one_hour_lag(self):
        result = create_time_features(self.df)

        self.assertTrue(pd.isna(result.loc[0, "pm25_lag_1h"]))
        self.assertEqual(result.loc[5, "pm25_lag_1h"], 5)

    def test_24_hour_lag(self):
        result = create_time_features(self.df)

        self.assertTrue(pd.isna(result.loc[23, "pm25_lag_24h"]))
        self.assertEqual(result.loc[24, "pm25_lag_24h"], 1)

    def test_seven_hour_moving_average(self):
        result = create_time_features(self.df)

        self.assertTrue(pd.isna(result.loc[6, "pm25_ma_7h"]))
        self.assertAlmostEqual(result.loc[7, "pm25_ma_7h"], 4)

    def test_24_hour_moving_average(self):
        result = create_time_features(self.df)

        self.assertTrue(pd.isna(result.loc[23, "pm25_ma_24h"]))
        self.assertAlmostEqual(result.loc[24, "pm25_ma_24h"], 12.5)

    def test_original_dataframe_is_not_modified(self):
        original = self.df.copy()

        create_time_features(self.df)

        pd.testing.assert_frame_equal(self.df, original)
    
    def test_missing_hour_raises_error(self):
        df = self.df.drop(index=10)

        with self.assertRaisesRegex(ValueError, "one hour apart"):
            create_time_features(df)

    def test_unsorted_timestamps_are_sorted(self):
        df = self.df.iloc[::-1].reset_index(drop=True)

        result = create_time_features(df)

        self.assertTrue(result["timestamp"].is_monotonic_increasing)
        self.assertEqual(result.loc[5, "pm25"], 6)

    def test_missing_pm25_value_affects_later_features(self):
        df = self.df.copy()
        df.loc[10, "pm25"] = float("nan")

        result = create_time_features(df)

        # The one-hour lag is missing only for the row immediately after the gap.
        self.assertTrue(pd.isna(result.loc[11, "pm25_lag_1h"]))
        self.assertFalse(pd.isna(result.loc[12, "pm25_lag_1h"]))

        # The seven-hour moving average needs seven consecutive observed values.
        for row in range(11, 18):
            self.assertTrue(pd.isna(result.loc[row, "pm25_ma_7h"]))

        self.assertFalse(pd.isna(result.loc[18, "pm25_ma_7h"]))


if __name__ == "__main__":
    unittest.main()