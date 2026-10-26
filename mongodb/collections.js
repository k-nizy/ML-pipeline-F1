// Run in mongosh against the beijing_air database.

// 1. Create the collection that holds one card per hour.
db.createCollection("readings");

// 2. Index on time: makes "latest record" and "date range" searches fast.
db.readings.createIndex({ timestamp: 1 });

// 3. Index on station + time: fast per-station searches, and the
//    unique option stops the same station-hour being stored twice.
db.readings.createIndex({ "station.id": 1, timestamp: -1 }, { unique: true });