"""A recommended trip built from a ready-made route of app/guide/trips.json (see
tools/guide/build_recommended.py, which writes them all to recommended.json) and, at request time,
the same for any number of days (Manu, 2026-11-16: "anche volendo 10 giorni, 17 giorni"): the
route of the nearest length in that season, its nights cut or stretched within what each zone's
guide says a stay takes (app.guide.todo nights), then filled day by day from the zone guides.
"""
from __future__ import annotations

from app import globe
from app.guide import ready
from app.guide.todo import area_for
from app.services import explore

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# Where you sleep, in metres: the stops the globe's routes don't give a height for, and a few
# where the globe has the park's height and not the village's. Written here so the build never
# depends on the network (globe.elevation geocodes otherwise).
ELEVATION = {
    "ar-bariloche": 890, "ar-mendoza": 750, "ar-puerto-iguazu": 170, "ar-puerto-madryn": 10,
    "ar-purmamarca": 2320, "ar-salta": 1150, "at-durnstein": 210, "at-innsbruck": 575, "at-kitzbuhel": 760,
    "at-salzburg": 425, "at-st-wolfgang": 540, "at-vienna": 190, "bo-copacabana": 3840, "bo-la-paz": 3640,
    "bo-laguna-colorada": 4300, "bo-uyuni": 3670, "ch-aletsch-glacier": 1925, "ch-bern": 540,
    "ch-geneva": 375, "ch-lausanne": 495, "ch-lauterbrunnen": 800, "ch-lucerne": 435, "ch-zurich": 410,
    "cl-castro": 40, "cl-hanga-roa": 40, "cl-puerto-varas": 60, "cl-punta-arenas": 20,
    "cl-torres-del-paine-national-park": 150, "is-hofn": 5, "is-husavik": 15, "is-isafjordur": 5,
    "is-lake-myvatn": 280, "is-skaftafell": 100, "is-snaefellsnes": 20, "jp-hakone": 700, "jp-himeji": 20,
    "jp-kanazawa": 40, "jp-koguchi": 110, "jp-nara": 60, "jp-nikko": 600, "ma-asilah": 10,
    "ma-dades-gorges": 1600, "ma-imlil": 1740, "ma-meknes": 550, "ma-ouzoud-falls": 1000, "ma-rabat": 50,
    "ma-taghazout": 10, "na-bagani": 1010, "na-epupa-falls": 750, "na-opuwo": 1150, "na-twyfelfontein": 600,
    "no-alesund": 10, "no-alta": 20, "no-andalsnes": 10, "no-flam": 10, "no-geiranger": 10,
    "no-hardangerfjord": 20, "no-loen": 10, "no-senja": 20, "no-stavanger": 10, "no-trondheim": 20,
    "np-bamboo": 2310, "np-bandipur": 1030, "np-chhomrong": 2170, "np-deurali": 3230, "np-dhulikhel": 1550,
    "np-dingboche": 4410, "np-ghandruk": 1940, "np-ghorepani": 2860, "np-gorak-shep": 5164,
    "np-jhinu-danda": 1780, "np-jomsom": 2720, "np-kagbeni": 2810, "np-khumjung": 3790,
    "np-lo-manthang": 3840, "np-marpha": 2670, "np-nagarkot": 2100, "np-namche-bazaar": 3440,
    "np-pangboche": 3985, "np-pheriche": 4370, "np-sauraha": 180, "np-tadapani": 2630, "np-ulleri": 2070,
    "nz-abel-tasman-national-park": 10, "nz-aoraki-mount-cook-national-park": 760,
    "nz-coromandel-peninsula": 10, "nz-lake-tekapo": 710, "nz-paihia": 10, "nz-punakaiki": 10,
    "nz-te-anau": 210, "nz-tongariro-national-park": 1100, "nz-waitomo": 120, "nz-wanaka": 300,
    "pe-chivay": 3630, "pe-huaraz": 3050, "pe-paracas": 5, "pe-puerto-maldonado": 180, "tz-lake-natron": 610,
    "tz-lushoto": 1400, "tz-mount-kilimanjaro": 3900, "tz-nungwi": 5, "vn-can-tho": 5, "vn-ha-giang": 110,
    "vn-mai-chau": 175, "vn-ninh-binh": 5, "vn-phong-nha": 30, "x-at-hallstatt": 510,
    "x-at-zell-am-see": 760, "x-ch-appenzell": 780, "x-ch-grindelwald": 1035, "x-ch-lugano": 275,
    "x-ch-st-moritz": 1820, "x-ch-zermatt": 1610,
    # Italy (2026-11-16): the towns you sleep in; the Cinque Terre's globe point is up on the
    # ridge (331 m), the villages are on the sea
    "it-alberobello": 428, "it-amalfi": 10, "it-bologna": 54, "it-bolzano": 262, "it-cefalu": 16,
    "it-cinque-terre": 20, "it-cortina-dampezzo": 1224, "it-lipari": 10, "it-milan": 120,
    "it-ortisei": 1236, "it-ragusa": 450, "it-sirmione": 70, "it-sorrento": 50, "it-syracuse": 17,
    "it-trapani": 3, "it-varenna": 220, "it-verona": 59,
}

# Where you sleep, when the globe's point is the middle of a park: Torres del Paine's sits on the
# ice field to the west (1-9 °C in January, a warm down jacket in summer); the refugios and hotels
# are on the east side (Opus check of the day-by-day clothes, 2026-11-16).
COORDS = {"cl-torres-del-paine-national-park": (-50.96, -72.87),
          # Riederalp, the village above the Aletsch glacier; the Machame camps on Kilimanjaro's south-west side
          "ch-aletsch-glacier": (46.381, 8.026), "tz-mount-kilimanjaro": (-3.09, 37.30)}


def _from_trip_files() -> None:
    """Heights and sleeping spots written next to the routes in guide/trips/*.json ("elevation":
    {place id: metres}, "coords": {place id: [lat, lon]}), so each region's thread keeps its own
    (2026-11-17, USA and Canada)."""
    from app.guide import ready
    for doc in ready._docs():
        ELEVATION.update(doc.get("elevation", {}))
        COORDS.update({k: tuple(v) for k, v in doc.get("coords", {}).items()})


_from_trip_files()


def height(p: dict, strict: bool = True) -> int:
    """strict (the built library): every stop's height written down; a stop the traveller added
    takes the place search's (globe.elevation)."""
    if p["id"] in ELEVATION:
        return ELEVATION[p["id"]]
    known = globe._route_elevations().get(p["id"])
    if known is None:
        if not strict:
            return round(globe.elevation(p))
        raise ValueError(f"no height for {p['id']}: add it to ELEVATION")
    return round(known)


def month_range(ms: list[int]) -> str:
    """[9, 10, 11, 12, 1, 2, 3] -> "Sep-Mar"; a gap -> "Jun, Aug"."""
    s = set(ms)
    if len(s) == 12:
        return "all year"
    start = next(m for m in range(1, 13) if m in s and ((m - 2) % 12) + 1 not in s)
    runs, cur = [], None
    for k in range(12):
        m = ((start - 1 + k) % 12) + 1
        if m in s:
            cur = [cur[0], m] if cur else [m, m]
        elif cur:
            runs.append(cur)
            cur = None
    if cur:
        runs.append(cur)
    return ", ".join(MONTHS[a - 1] if a == b else f"{MONTHS[a - 1]}–{MONTHS[b - 1]}" for a, b in runs)




def acts_of(things: list) -> list[dict]:
    """The activities of a stop: one of each kind, the highest of the hikes."""
    out: dict[tuple, dict] = {}
    for it in things:
        a = dict(it.act or {"type": "city"})
        k = (a.get("type"), a.get("difficulty"), bool(a.get("glacier")))
        if k not in out or (a.get("max_altitude_m") or 0) > (out[k].get("max_altitude_m") or 0):
            out[k] = a
    acts = list(out.values()) or [{"type": "city"}]
    return [{k: v for k, v in a.items() if v not in (None, False)} for a in acts]


def line(day: dict, items: dict, band: list[int], first: bool, also: list[str]) -> str:
    names = []
    for t in day.get("items", []):
        it = items.get(t["id"])
        n = t["name"]
        if it is not None and it.months and not set(band) <= set(it.months):
            n += f" ({month_range(it.months)})"
        names.append(n)
    if day["kind"] == "free":
        return "A spare day for the weather" + (f", or: {also[0]}." if also else ".")
    if day["kind"] == "arrive":
        head = "Arrive and settle in." if first else "Arrive."
        return f"{head} {names[0]}." if names else (head + " An easy evening.")
    if not names:
        return "A free day."
    return ". ".join(names) + "."


def day_plan(day: dict, items: dict, also: list[str]) -> dict:
    """The day by its things (ids of the zone guide); a spare day names what to do if it is clear."""
    out = {"kind": day["kind"] if day["kind"] in ("arrive", "free") else "day",
           "things": [t["id"] for t in day.get("items", []) if t["id"] in items]}
    if day["kind"] == "free" and also:
        out["spare"] = next((k for k, it in items.items() if it.name == also[0]), None)
    return out


def build(t: ready.ReadyTrip, strict: bool = True) -> dict:
    P = globe.by_id()
    stops = [{**explore._stop_of_base({**P[s.place], "sights": []}, s.nights),
              "key": s.place if all(x.place != s.place for x in t.stops[:i]) else f"{s.place}~back"}
             for i, s in enumerate(t.stops)]
    explore._days_of(stops)
    explore._guide_days(stops, None, None, spare=True, months=t.months)
    out = []
    for i, s in enumerate(stops):
        p = P[s["place_id"]]
        a = area_for(p["name"], p["country"], p["lat"], p["lon"])
        items = {it.id: it for it in (a.items if a else [])}
        planned = [items[x["id"]] for d in s["plan"] for x in d.get("items", []) if x["id"] in items]
        visits = []
        for d in s["plan"]:
            for n in d.get("sights", [])[:4]:
                if n not in [v["name"] for v in visits]:
                    visits.append({"name": n[:120], "day": d["day"]})
        do = []
        if a and a.sleep and not s["key"].endswith("~back"):
            do.append(f"Sleep: {a.sleep}")
        for it in planned:
            for x in it.extras:
                if len(do) < 4 and x not in do:
                    do.append(x)
        if not do:
            do = [planned[0].why] if planned and planned[0].why else ["The last night before the flight home: keep it easy."]
        exc = []
        for it in planned:
            if it.book and len(exc) < 2:
                q = (it.sights[0] if it.sights else it.name)[:110]
                exc.append({"title": it.name, "query": q})
        out.append({
            "place": p["id"], "name": p["name"], "country_code": p["country"],
            "lat": round(COORDS.get(p["id"], (p["lat"], p["lon"]))[0], 4),
            "lon": round(COORDS.get(p["id"], (p["lat"], p["lon"]))[1], 4),
            "elevation_m": height(p, strict), "days": s["days"],
            "activities": acts_of(planned),
            "visits": visits,
            "plan": [line(d, items, t.months, i == 0, s.get("also") or []) for d in s["plan"]],
            "do": do, "skip": [], "excursions": exc,
            "area": a.id if a else None,
            "day_plans": [day_plan(d, items, s.get("also") or []) for d in s["plan"]],
        })
    countries = sorted({x["country_code"] for x in out})
    dest = _journey_name(t.journey)
    return {
        "slug": t.id, "title": t.title, "countries": countries, "summary": t.why,
        "destination": dest, "region": t.journey, "weeks": min(4, max(1, round(t.days / 7))),
        "months": t.months, "best_months": t.best, "season_note": t.note,
        "pace": t.pace, "level": t.level, "stops": out, "group_trips": [],
    }




def _journey_name(jid: str) -> str:
    return next(j.name for j in ready.journeys() if j.id == jid)


# ------------------------------------------------------------- any number of days

MIN_DAYS, MAX_DAYS = 3, 35


def _range(place: str, nights: int) -> tuple[int, int, int]:
    """Least, ideal and most nights at a place, from its zone guide (the route's own nights stay
    possible); a place without a guide keeps its own, give or take one."""
    p = globe.by_id()[place]
    a = area_for(p["name"], p["country"], p["lat"], p["lon"])
    if a and a.nights:
        return min(a.nights[0], nights), a.nights[1], max(a.nights[2], nights)
    return min(1, nights), nights, nights + 1


def _stops(t: ready.ReadyTrip) -> list[list]:
    return [[s.place, s.nights, *_range(s.place, s.nights)] for s in t.stops]


def _trim(t: ready.ReadyTrip, days: int, core: set[str]) -> list[list] | None:
    """The longer route cut to `days`, as a tour operator would: first the nights beyond what each
    zone needs, then the stops the shorter route does without (Ushuaia before Fitz Roy), then the
    weather days, never the first or the last stop."""
    stops = _stops(t)
    total = lambda: sum(s[1] for s in stops)  # noqa: E731

    def cut(floor: int) -> None:
        while total() > days:
            spare = [s for s in stops if s[1] > s[floor]]
            if not spare:
                return
            max(spare, key=lambda s: s[1] - s[floor])[1] -= 1

    ring = len(stops) > 1 and stops[-1][0] == stops[0][0]

    def drop(only_extra: bool) -> None:
        while total() > days:
            # a line ends sooner (Patagonia stops before Punta Arenas and Ushuaia); a ring keeps
            # its way home and loses the stop that best matches what is too much
            cand = stops[1:-1] if ring else stops[1:]
            cand = [s for s in cand if not only_extra or s[0] not in core]
            if not cand:
                return
            over = total() - days
            stops.remove(min(cand, key=lambda s: (abs(s[1] - over), -s[1])) if ring else cand[-1])

    cut(3)  # down to the ideal stay
    drop(True)
    cut(2)  # down to the least
    drop(False)
    if total() > days:
        return None
    if ring and len(stops) == 2:  # Reykjavik and back to Reykjavik: one stay
        stops[0][1] += stops.pop()[1]
    while total() < days:  # a stop dropped took more than needed: give it back where it fits
        room = [s for s in stops if s[1] < s[4]]
        if not room:
            return None
        min(room, key=lambda s: s[1] - s[3])[1] += 1
    return stops


def _stretch(t: ready.ReadyTrip, days: int) -> list[list]:
    """The shorter route made longer: first up to each zone's ideal stay, then to its most. Never
    beyond: when the zones have nothing more to give, the trip stays shorter than asked."""
    stops = _stops(t)
    for top in (3, 4):
        while sum(s[1] for s in stops) < days:
            room = [s for s in stops if s[1] < s[top]]
            if not room:
                break
            min(room, key=lambda s: (s[1] - s[top], -s[top]))[1] += 1
    return stops


def fitted(journey: str, days: int, month: int) -> ready.ReadyTrip | None:
    """The route of `journey` for `days` days in `month`: a ready route of that length, else the
    next longer one cut down, else the next shorter one stretched."""
    routes = [t for t in ready.trips() if t.journey == journey and month in t.months]
    if not routes or not MIN_DAYS <= days <= MAX_DAYS:
        return None
    same = [t for t in routes if t.days == days]
    if same:
        return max(same, key=lambda t: len(t.best))
    longer = sorted((t for t in routes if t.days > days), key=lambda t: (t.days, -len(t.best)))
    shorter = sorted((t for t in routes if t.days < days), key=lambda t: (-t.days, -len(t.best)))
    stops, base = None, None
    if longer:
        base = longer[0]
        stops = _trim(base, days, {s.place for s in shorter[0].stops} if shorter else set())
    if stops is None and shorter:
        base = shorter[0]
        stops = _stretch(base, days)
    if stops is None:
        return None
    name = _journey_name(journey)
    got = sum(s[1] for s in stops)
    return base.model_copy(update={
        "id": base.id, "title": f"{name} in {got} days",
        "stops": [ready.ReadyStop(place=s[0], nights=s[1]) for s in stops]})


# ------------------------------------------------------------- the traveller's own changes

MAX_STOPS = 15


def edited(base: ready.ReadyTrip, stops: list[tuple[str, int]]) -> ready.ReadyTrip | None:
    """The route with the traveller's stops and nights (Manu, 2026-11-16: "da qui stesso posso
    direttamente editare il viaggio"): any place of the globe, 1 to 10 nights each, 3 to 35 days
    in all. None when a place is unknown or the numbers are out of range."""
    P = globe.by_id()
    if not 1 <= len(stops) <= MAX_STOPS or any(p not in P or not 1 <= n <= 10 for p, n in stops):
        return None
    total = sum(n for _, n in stops)
    if not MIN_DAYS <= total <= MAX_DAYS:
        return None
    return base.model_copy(update={"title": f"{_journey_name(base.journey)} in {total} days" if base.journey else base.title,
                                   "stops": [ready.ReadyStop(place=p, nights=n) for p, n in stops]})
