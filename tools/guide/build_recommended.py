"""Build the recommended trips (Manu, 2026-11-16: "per ogni posto un viaggio raccomandato da 1, 2,
3, 4 settimane, per ogni mese"; then "viaggi che possono andare su più nazioni") from the
ready-made routes of app/guide/trips.json that belong to a journey: a travel region as tour
operators cut it (Patagonia on both sides of the border, Atacama with Uyuni, Peru with Bolivia).

Each route (zones to sleep in, nights, in order, one per season band) becomes an itinerary of
app.inspire: the days filled from the hand-written guide of each zone (app.guide.todo: the things
in the order not to miss, several a day when their hours fit, a spare day for the weather where
the zone keeps one), only the things in season in that band; the activities of each stop come
from the things planned there, so the clothes (app.inspire.wear) follow what you actually do.
Nothing is copied from the operators' trips: their merged patterns only say what to see on the
way. Deterministic: same data in, same file out.

    cd backend && PYTHONPATH=. python ../tools/guide/build_recommended.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import globe  # noqa: E402
from app.guide import ready  # noqa: E402
from app.guide.todo import area_for  # noqa: E402
from app.services import explore  # noqa: E402

OUT = ROOT / "backend" / "app" / "inspire" / "recommended.json"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# Where you sleep, in metres: the stops the globe's routes don't give a height for, and a few
# where the globe has the park's height and not the village's. Written here so the build never
# depends on the network (globe.elevation geocodes otherwise).
ELEVATION = {
    "ar-bariloche": 890, "ar-mendoza": 750, "ar-puerto-iguazu": 170, "ar-puerto-madryn": 10, "ar-purmamarca": 2320,
    "ar-salta": 1150, "bo-copacabana": 3840, "bo-la-paz": 3640, "bo-laguna-colorada": 4300, "bo-uyuni": 3670, "cl-castro": 40, "cl-hanga-roa": 40, "cl-puerto-varas": 60, "cl-punta-arenas": 20,
    "cl-torres-del-paine-national-park": 150, "is-hofn": 5, "is-husavik": 15, "is-isafjordur": 5,
    "is-lake-myvatn": 280, "is-skaftafell": 100, "is-snaefellsnes": 20, "jp-hakone": 700, "jp-himeji": 20,
    "jp-kanazawa": 40, "jp-koguchi": 110, "jp-nara": 60, "jp-nikko": 600, "na-bagani": 1010,
    "na-epupa-falls": 750, "na-opuwo": 1150, "na-twyfelfontein": 600, "nz-abel-tasman-national-park": 10,
    "nz-aoraki-mount-cook-national-park": 760, "nz-coromandel-peninsula": 10, "nz-lake-tekapo": 710,
    "nz-paihia": 10, "nz-punakaiki": 10, "nz-te-anau": 210, "nz-tongariro-national-park": 1100,
    "nz-waitomo": 120, "nz-wanaka": 300, "pe-chivay": 3630, "pe-huaraz": 3050, "pe-paracas": 5,
    "pe-puerto-maldonado": 180, "vn-can-tho": 5, "vn-ha-giang": 110, "vn-mai-chau": 175, "vn-ninh-binh": 5,
    "vn-phong-nha": 30,
}

# Where you sleep, when the globe's point is the middle of a park: Torres del Paine's sits on the
# ice field to the west (1-9 °C in January, a warm down jacket in summer); the refugios and hotels
# are on the east side (Opus check of the day-by-day clothes, 2026-11-16).
COORDS = {"cl-torres-del-paine-national-park": (-50.96, -72.87)}


def height(p: dict) -> int:
    if p["id"] in ELEVATION:
        return ELEVATION[p["id"]]
    known = globe._route_elevations().get(p["id"])
    if known is None:
        raise SystemExit(f"no height for {p['id']}: add it to ELEVATION")
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


JOURNEYS = {j.id: j for j in ready.journeys()}


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


def build(t: ready.ReadyTrip) -> dict:
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
            "name": p["name"], "country_code": p["country"],
            "lat": round(COORDS.get(p["id"], (p["lat"], p["lon"]))[0], 4),
            "lon": round(COORDS.get(p["id"], (p["lat"], p["lon"]))[1], 4),
            "elevation_m": height(p), "days": s["days"],
            "activities": acts_of(planned),
            "visits": visits,
            "plan": [line(d, items, t.months, i == 0, s.get("also") or []) for d in s["plan"]],
            "do": do, "skip": [], "excursions": exc,
            "area": a.id if a else None,
            "day_plans": [day_plan(d, items, s.get("also") or []) for d in s["plan"]],
        })
    countries = sorted({x["country_code"] for x in out})
    dest = JOURNEYS[t.journey].name
    return {
        "slug": t.id, "title": t.title, "countries": countries, "summary": t.why,
        "destination": dest, "region": t.journey, "weeks": round(t.days / 7),
        "months": t.months, "best_months": t.best, "season_note": t.note,
        "pace": t.pace, "level": t.level, "stops": out, "group_trips": [],
    }


def main() -> None:
    its = [build(t) for t in ready.trips() if t.journey]
    its.sort(key=lambda x: (x["destination"], x["weeks"], -len(x["best_months"]), x["slug"]))
    doc = {"_doc": ("Recommended trips built by tools/guide/build_recommended.py from app/guide/trips.json and the "
                    "hand-written zone guides. Do not edit by hand: change the routes or the guides and run the tool."),
           "itineraries": its}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(its)} recommended trips -> {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
