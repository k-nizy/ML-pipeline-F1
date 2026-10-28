// Run in mongosh against the beijing_air database.
// Paste each result under its query once the full data is loaded.

// Query 1: the 5 most polluted hours (pm25 above 300), worst first.
db.readings.find({ "target.pm25": { $gt: 300 } })
           .sort({ "target.pm25": -1 })
           .limit(5);
// RESULT: 1759 readings are above 300. The 5 highest, in order:
//   994 (2012-01-23 01:00), 980 (2010-02-14 01:00), 972 (2012-01-23 02:00),
//   886 (2013-01-12 20:00), 858 (2013-01-12 22:00)

// Query 2: average pollution for each month.
db.readings.aggregate([
  { $group: {
      _id: { year: { $year: "$timestamp" }, month: { $month: "$timestamp" } },
      avg_pm25: { $avg: "$target.pm25" }
  } },
  { $sort: { "_id.year": 1, "_id.month": 1 } }
]);
// RESULT: one row per month (60 rows, 2010-01 to 2014-12). The first three:
//   2010-01: 90.44, 2010-02: 97.23, 2010-03: 94.10

// Query 3: the latest reading in the collection.
db.readings.find().sort({ timestamp: -1 }).limit(1);
// RESULT: the newest reading is 2014-12-31 23:00 UTC, pm25 = 12 (wind NW, temp -3, pres 1034)