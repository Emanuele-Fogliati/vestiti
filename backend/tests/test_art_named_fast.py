"""Matching place names to landmark scenes must stay fast: the home globe matches ~6,900 places
on the first request after every start, and scanning every landmark for each place took 20 s."""
import time

from app import art, globe


def _scan(text, lat=None, lon=None):
    """The plain scan of every landmark that the index replaced: both must agree."""
    t = f" {art._norm(text)} "
    n = art._norm(text)
    hits = []
    for lm in art.landmarks():
        found = [(t.find(f" {a} "), -len(a)) for a in lm.aliases if f" {a} " in t]
        found += [(0, -len(a)) for a in lm.names if a == n]
        if found:
            hits.append((*min(found), lm))
    near = (lambda lm: art._km(lat, lon, lm.lat, lm.lon)) if lat is not None else (lambda lm: 0)
    return [lm.id for _, _, lm in sorted(hits, key=lambda h: (h[0], near(h[2]), h[1]))]


def test_index_matches_the_plain_scan():
    texts = [lm.label for lm in art.landmarks()[::25]]
    texts += [f"Day trip to {lm.label} and {o.label}" for lm, o in zip(art.landmarks()[::97], art.landmarks()[50::97])]
    texts += ["", "Red Fort of Agra", "Golden temple of Dambulla", "Cusco, Sacred Valley and Machu Picchu"]
    for x in texts:
        assert [lm.id for lm in art._named(x, -13.5, -72.0)] == _scan(x, -13.5, -72.0), x


def test_globe_places_match_fast():
    t = time.perf_counter()
    for p in globe.payload()["places"]:
        art._named(p[1])
    assert time.perf_counter() - t < 5
