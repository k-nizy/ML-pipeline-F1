import os
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
client = MongoClient(os.getenv("MONGO_URI"))
readings = client[os.getenv("MONGO_DATABASE")][os.getenv("MONGO_COLLECTION")]

df = pd.read_csv("data/processed/beijing_clean.csv", parse_dates=["timestamp"])
now = datetime.now(timezone.utc)

docs = []
for row in df.itertuples():
    pm25 = None if pd.isna(row.pm25) else int(row.pm25)
    docs.append({
        "station": {"id": 1, "name": "Beijing US Embassy", "city": "Beijing"},
        "timestamp": row.timestamp.to_pydatetime(),
        "target": {"pm25": pm25, "imputed": False},
        "weather": {
            "dewp": float(row.DEWP),
            "temp": float(row.TEMP),
            "pres": float(row.PRES),
            "wind_dir": row.cbwd,
            "wind_speed": float(row.Iws),
            "snow_hours": int(row.Is),
            "rain_hours": int(row.Ir),
        },
        "ingested_at": now,
    })

readings.delete_many({})
readings.create_index([("timestamp", 1)])
readings.create_index([("station.id", 1), ("timestamp", -1)], unique=True)
for i in range(0, len(docs), 5000):
    readings.insert_many(docs[i:i + 5000])
print("loaded", readings.count_documents({}))