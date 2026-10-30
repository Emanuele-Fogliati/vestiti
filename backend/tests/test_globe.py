"""Globe places: one compact response, every place inside its own country, pictures only for named places."""
import gzip
import json

from app import globe


def test_places_endpoint_is_compact_and_gzipped(client):
    r = client.get("/api/globe/places", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    # revalidated every time, so new landmark scenes reach the globe at once; 304 when unchanged
    assert r.headers["cache-control"] == "no-cache" and r.headers["etag"]
    again = client.get("/api/globe/places", headers={"Accept-Encoding": "gzip", "If-None-Match": r.headers["etag"]})
    assert again.status_code == 304
    d = r.json()  # the test client decompresses
    assert d["fields"][:7] == ["id", "name", "country", "kind", "lat", "lon", "level"]
    assert len(d["places"]) > 1000
    # never how many organised trips include a place, nor how many we read (Manu, 2026-10-26)
    assert "inventory_trips" not in d and "trips" not in d["fields"]
    raw, gz = globe.payload_bytes()
    assert json.loads(gzip.decompress(gz)) == json.loads(raw)
    assert len(gz) < 250_000  # stays light enough for a phone


def test_places_have_valid_rows():
    d = globe.payload()
    kinds = {"city", "town", "landmark", "nature", "island", "region"}
    ids = set()
    for pid, name, cc, kind, lat, lon, lvl, art, art_label, its in d["places"]:
        assert pid not in ids
        ids.add(pid)
        assert name and len(cc) == 2 and cc.isupper() and kind in kinds
        assert -90 <= lat <= 90 and -180 <= lon <= 180
        assert lvl in range(1, 7)
        assert (art is None) == (art_label is None)
        assert all(0 <= i < len(d["itineraries"]) for i in its)
    # most visited first
    levels = [p[6] for p in d["places"]]
    assert levels == sorted(levels, reverse=True)
    assert levels[0] == 6 and levels[-1] == 1


def test_popularity_levels():
    assert [globe.level(t) for t in (109, 60, 59, 30, 15, 8, 5, 4, 3)] == [6, 6, 5, 5, 4, 3, 2, 1, 1]


def test_cusco_gets_its_picture_and_itinerary_but_not_its_neighbours():
    d = globe.payload()
    by_id = {p[0]: p for p in d["places"]}
    cusco = by_id["pe-cusco"]
    assert cusco[2] == "PE" and abs(cusco[4] + 13.53) < 0.1 and abs(cusco[5] + 71.97) < 0.1
    assert cusco[7] is not None and "cusco" in cusco[7]
    assert any(d["itineraries"][i]["slug"].startswith("peru") for i in cusco[9])
    # a place near Cusco with no scene of its own gets no picture (no borrowed landmark)
    assert by_id["pe-sacsayhuaman"][7] is None
