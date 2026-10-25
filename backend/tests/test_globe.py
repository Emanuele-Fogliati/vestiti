"""Globe places: one compact response, every place inside its own country, pictures only for named places."""
import gzip
import json

from app import globe


def test_places_endpoint_is_compact_and_gzipped(client):
    r = client.get("/api/globe/places", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert "max-age" in r.headers["cache-control"]
    d = r.json()  # the test client decompresses
    assert d["fields"][:7] == ["id", "name", "country", "kind", "lat", "lon", "trips"]
    assert len(d["places"]) > 1000
    assert d["inventory_trips"] > 4000
    raw, gz = globe.payload_bytes()
    assert json.loads(gzip.decompress(gz)) == json.loads(raw)
    assert len(gz) < 250_000  # stays light enough for a phone


def test_places_have_valid_rows():
    d = globe.payload()
    kinds = {"city", "town", "landmark", "nature", "island", "region"}
    ids = set()
    for pid, name, cc, kind, lat, lon, trips, art, art_label, its in d["places"]:
        assert pid not in ids
        ids.add(pid)
        assert name and len(cc) == 2 and cc.isupper() and kind in kinds
        assert -90 <= lat <= 90 and -180 <= lon <= 180
        assert trips >= 3
        assert (art is None) == (art_label is None)
        assert all(0 <= i < len(d["itineraries"]) for i in its)
    # most visited first
    trips = [p[6] for p in d["places"]]
    assert trips == sorted(trips, reverse=True)


def test_cusco_gets_its_picture_and_itinerary_but_not_its_neighbours():
    d = globe.payload()
    by_id = {p[0]: p for p in d["places"]}
    cusco = by_id["pe-cusco"]
    assert cusco[2] == "PE" and abs(cusco[4] + 13.53) < 0.1 and abs(cusco[5] + 71.97) < 0.1
    assert cusco[7] is not None and "cusco" in cusco[7]
    assert any(d["itineraries"][i]["slug"].startswith("peru") for i in cusco[9])
    # a place near Cusco with no scene of its own gets no picture (no borrowed landmark)
    assert by_id["pe-sacsayhuaman"][7] is None
