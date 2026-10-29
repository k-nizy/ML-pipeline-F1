# MongoDB API endpoint tests

Tested locally on 2026-10-29 against the Atlas collection `beijing_air.readings`
(43,824 documents), using the browser and the FastAPI test page at /docs.

| # | Endpoint | Test | Result |
|---|---|---|---|
| 1 | GET /api/mongo/health | Ping Atlas | 200, {"status":"ok"} |
| 2 | GET /api/mongo/readings/latest | Newest document | 200, 2014-12-31 23:00, pm25 = 12 |
| 3 | GET /api/mongo/readings/range | start=2010-01-01T00:00:00 to end=2010-01-01T03:00:00 | 200, 4 documents (00:00 to 03:00), pm25 null |
| 4 | GET /api/mongo/readings | limit=2, offset=10 | 200, 2 documents (2010-01-01 10:00 and 11:00) |
| 5 | GET /api/mongo/readings/{id} | Id of the newest document | 200, same document as test 2 |
| 6 | POST /api/mongo/readings | New document for 2015-01-01 00:00 | 201, document created with an _id |
| 7 | POST /api/mongo/readings | Same document again | 409, "A reading for this station and hour already exists." (unique index on station.id + timestamp) |
| 8 | PUT /api/mongo/readings/{id} | {"target.pm25": 99} on the test document | 200, pm25 changed from 25 to 99, other fields unchanged |
| 9 | DELETE /api/mongo/readings/{id} | Delete the test document | 204, document removed |
| 10 | GET /api/mongo/readings/{id} | Invalid id: abc | 400, "Invalid reading id." |
| 11 | GET /api/mongo/readings/{id} | Well-formed id that matches no document (000000000000000000000000) | 404, "Reading not found." |

The test document was deleted afterwards, so the collection is back to its original 43,824 documents.

Missing PM2.5 readings are stored as null (not imputed), following the data lead's decision, so the first hours of 2010 show pm25 null.