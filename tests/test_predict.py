import unittest

import pandas as pd

from scripts.features import HISTORY_HOURS
from scripts.predict import records_to_features


class TestPredictionInput(unittest.TestCase):

    def setUp(self):
        timestamps = pd.date_range("2014-12-30 23:00", periods=HISTORY_HOURS, freq="h")
        self.records = [
            {
                "observed_at": timestamp.isoformat(),
                "pm25": None if index == 0 else float(index + 1),
                "dewp": -5.0,
                "temp": 2.0,
                "pres": 1010.0,
                "wind_dir": "CV" if index == HISTORY_HOURS - 1 else "NW",
                "wind_speed": 1.5,
                "snow_hours": 0,
                "rain_hours": 0,
            }
            for index, timestamp in enumerate(timestamps)
        ]

    def test_api_fields_build_last_model_row_and_keep_null_pm25(self):
        features, latest = records_to_features(self.records)

        self.assertEqual(len(features), 1)
        self.assertEqual(latest, pd.Timestamp(self.records[-1]["observed_at"]))
        self.assertEqual(features.iloc[0]["pm25"], self.records[-1]["pm25"])
        self.assertTrue(pd.isna(features.iloc[0]["pm25_lag_24h"]))
        self.assertEqual(features.iloc[0]["wind_cv"], 1)
        self.assertEqual(features.iloc[0]["wind_NW"], 0)

    def test_rejects_missing_history_rows(self):
        with self.assertRaisesRegex(ValueError, "Expected 25 hourly records"):
            records_to_features(self.records[:-1])

    def test_rejects_nonconsecutive_timestamps(self):
        records = self.records.copy()
        for record in records[10:]:
            record["observed_at"] = (
                pd.Timestamp(record["observed_at"]) + pd.Timedelta(hours=1)
            ).isoformat()

        with self.assertRaisesRegex(ValueError, "consecutive hourly"):
            records_to_features(records)


if __name__ == "__main__":
    unittest.main()
