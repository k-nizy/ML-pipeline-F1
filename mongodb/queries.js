// Run in mongosh against the beijing_air database.
// Paste each result under its query once the full data is loaded.

// Query 1: the 5 most polluted hours (pm25 above 300), worst first.
db.readings.find({ "target.pm25": { $gt: 300 } })
           .sort({ "target.pm25": -1 })
           .limit(5);
// RESULT: (paste here)

// Query 2: average pollution for each month.
db.readings.aggregate([
  { $group: {
      _id: { year: { $year: "$timestamp" }, month: { $month: "$timestamp" } },
      avg_pm25: { $avg: "$target.pm25" }
  } },
  { $sort: { "_id.year": 1, "_id.month": 1 } }
]);
// RESULT: (paste here)

// Query 3: the latest reading in the collection.
db.readings.find().sort({ timestamp: -1 }).limit(1);
// RESULT: (paste here)