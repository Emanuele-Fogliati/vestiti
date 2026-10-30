"""Is every stop of a trip where the traveller means? Checks that never let a wrong country
through silently:

- country: the stop is in one of the trip's countries (named in the text, "Perù e Bolivia",
  or shared by at least two stops). A stop alone in a country nobody named is asked about.
- distance: a stop more than FAR_KM from every other stop of the trip is a homonym abroad far
  more often than a real trip (Aguas Calientes, Mexico, between Cusco and Puno). Measured to
  the nearest stop, not just the next one, so one wrong stop does not make Puno look far.
- elevation: the program says "quota 3827" and the map match is at 234 m: another place.

A stop that fails is not dropped or moved silently: it is marked "check" with the reason, and
the app asks the traveller "Is this the place? Aguas Calientes, Mexico".
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from app.places import countries
from app.places.sources import km

FAR_KM = 2500       # no overland day goes further; a homonym abroad usually does
ELEV_GAP_M = 1000   # the text's altitude vs the map match's
ELEV_RANGE = (-450, 6000)  # where people sleep


@dataclass
class Check:
    status: str = "ok"                 # ok | check
    codes: list[str] = field(default_factory=list)   # country | far | elevation
    issues: list[str] = field(default_factory=list)  # one sentence each, for the traveller

    def add(self, code: str, text: str):
        self.status = "check"
        if code not in self.codes:
            self.codes.append(code)
            self.issues.append(text)

    def json(self) -> dict:
        return {"status": self.status, "codes": self.codes, "issues": self.issues}

    @property
    def note(self) -> str | None:
        return " ".join(self.issues) or None


def _get(s, k):
    return s.get(k) if isinstance(s, dict) else getattr(s, k, None)


def stop_countries(ccs: list[str | None]) -> set[str]:
    """Countries at least two stops share (a one-stop trip: its own)."""
    c = Counter(cc for cc in ccs if cc)
    if len([cc for cc in ccs if cc]) == 1:
        return set(c)
    return {cc for cc, n in c.items() if n >= 2}


def expected_countries(text: str | None, ccs: list[str | None],
                       candidates: list[set[str]] | None = None) -> set[str]:
    """The trip's countries: named in its text (when some stop could be there: "partenza
    dall'Italia" does not make Italy one of them) plus those two or more stops share."""
    named = set(countries.mentioned(text))
    if candidates is not None:
        possible = set().union(*candidates) if candidates else set()
        named &= possible | {cc for cc in ccs if cc}
    return named | stop_countries(ccs)


def check_stops(stops: list, expected: set[str] | list[str] | None = None,
                altitudes: list[float | None] | None = None) -> list[Check]:
    """One Check per stop, in trip order. stops: dicts or objects with name, country_code,
    latitude, longitude, elevation_m. expected: the trip's countries if known."""
    ccs = [(_get(s, "country_code") or "").upper() or None for s in stops]
    exp = set(expected or ()) | stop_countries(ccs)
    out = []
    for i, s in enumerate(stops):
        c = Check()
        cc = ccs[i]
        if len(stops) > 1 and cc and exp and cc not in exp:
            where = " and ".join(countries.name(x) for x in sorted(exp)) or "the other stops"
            c.add("country", f"It is in {countries.name(cc)}, but the rest of the trip is in {where}.")
        near = [n for j, n in enumerate(stops) if j != i]
        if near and _get(s, "latitude") is not None:
            ds = [(km(_get(s, "latitude"), _get(s, "longitude"), _get(n, "latitude"), _get(n, "longitude")),
                   _get(n, "name")) for n in near if _get(n, "latitude") is not None]
            if ds and min(d for d, _ in ds) > FAR_KM:
                d, other = min(ds)
                c.add("far", f"It is {d:,.0f} km from {other}.")
        alt = altitudes[i] if altitudes and i < len(altitudes) else None
        el = _get(s, "elevation_m")
        if alt and el and abs(alt - el) > ELEV_GAP_M:
            c.add("elevation", f"This place is at {el:,.0f} m, but your program says {alt:,.0f} m.")
        elif el is not None and not (ELEV_RANGE[0] <= el <= ELEV_RANGE[1]):
            c.add("elevation", f"This place is at {el:,.0f} m.")
        out.append(c)
    return out


def mark_ready_made(trip) -> None:
    """A trip copied from one of our own routes or itineraries: its places are curated, so the
    trip's countries are all of its stops' and no stop is asked about (a route with one night
    across a border is not a homonym). Later edits by the traveller are checked as usual."""
    trip.countries = sorted({s.country_code.upper() for s in trip.stops if s.country_code})
    for s in trip.stops:
        s.place_status, s.place_note = "ok", None
