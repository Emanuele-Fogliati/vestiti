One JSON file per travel area ({"trips": [...], "journeys": [...]}, same fields as ../trips.json),
read after trips.json by app.guide.ready. Separate files so parallel threads never edit the same
one (2026-11-17: us-west.json, us-east.json, us-pacific.json, ca.json).
