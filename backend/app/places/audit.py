"""Audit every place the app knows against public sources, and report what does not add up.

    python -m app.places.audit                  # registry (seed/places.json) + landmark art catalog
    python -m app.places.audit --fill           # also look up missing coordinates/elevation and
                                                # write the result (and the "verified" field)
    python -m app.places.audit --stops          # also the stops of the trips saved in the database
    python -m app.places.audit --report r.md    # write the report to a file too

What is checked, for each place:
- country: the coordinates fall inside the declared country (OpenStreetMap reverse geocoding);
- name: GeoNames or OpenStreetMap knows a place of that name, in that country, near those
  coordinates (so "Aguas Calientes, PE" is not a Mexican Aguas Calientes);
- elevation: the declared elevation matches the SRTM ground height there (+-300 m);
- a sight's base town is in the same country and close by.
A place is verified when nothing failed and at least two independent sources agree.
Needs network. Answers are cached in .cache/place-audit.json, so re-runs are fast.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from app.places import countries
from app.places.sources import Sources, km

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "seed" / "places.json"
ART = ROOT / "app" / "art"
CACHE = ROOT / ".cache" / "place-audit.json"
NEAR_KM = {"town": 15, "site": 25, "lake": 60, "region": 60}
ELEV_TOL = 300


def _names(p: dict) -> list[str]:
    out = [p["name"]]
    out += [a for a in p.get("aliases", []) if a.lower() != p["name"].lower()][:2]
    return out


def check_place(p: dict, src: Sources, by_id: dict[str, dict] | None = None) -> dict:
    """One registry place against the sources. Returns {ok, problems, sources, notes, ...}."""
    cc = (p.get("country_code") or "").upper()
    res = {"id": p["id"], "name": p["name"], "country_code": cc, "problems": [], "notes": [],
           "sources": []}
    if not countries.is_code(cc):
        res["problems"].append(f"'{cc}' is not an ISO country code")
        res["ok"] = False
        return res
    lat, lon = p.get("latitude"), p.get("longitude")
    if lat is None or lon is None:
        res["problems"].append("no coordinates")
        res["ok"] = False
        return res
    kind = p.get("kind", "town")
    radius = p.get("radius_km") or NEAR_KM.get(kind, 25)

    osm_cc = src.osm_country(lat, lon)
    if osm_cc == cc:
        res["sources"].append("openstreetmap (country of the coordinates)")
    elif osm_cc:
        res["problems"].append(f"the coordinates are in {countries.name(osm_cc)} ({osm_cc}), "
                               f"not in {countries.name(cc)}")
    else:
        res["notes"].append("OpenStreetMap has no country at the coordinates (water?)")

    best = None  # nearest confirming hit, from either source
    for n in _names(p):
        for h in src.geonames(n, cc):
            d = km(lat, lon, h["latitude"], h["longitude"])
            if best is None or d < best[0]:
                best = (d, f"geonames:{h['id']}", h)
        for h in src.osm_search(n, cc, kind=kind):
            d = km(lat, lon, h["latitude"], h["longitude"])
            if best is None or d < best[0]:
                best = (d, f"openstreetmap:{h['osm']}", h)
        if best and best[0] <= radius:
            break
    if best and best[0] <= radius:
        res["sources"].append(best[1])
    elif best:
        res["problems"].append(f"the nearest '{p['name']}' in {cc} that the sources know is "
                               f"{best[0]:.0f} km away (limit {radius} km)")
        res["suggest"] = {"latitude": round(best[2]["latitude"], 4),
                          "longitude": round(best[2]["longitude"], 4), "from": best[1]}
    else:
        res["problems"].append(f"no source knows a '{p['name']}' in {countries.name(cc)}")

    # several places of that name in the same country (Peru has five Aguas Calientes): the
    # entry must say which one with "near", a registry place it is close to
    spots: list[dict] = []
    for h in src.geonames(p["name"], cc):
        if not (h.get("feature") or "").startswith("PPL"):
            continue  # Vancouver Island is not another Vancouver
        if all(km(h["latitude"], h["longitude"], o["latitude"], o["longitude"]) > 50 for o in spots):
            spots.append(h)
    main = max(spots, key=lambda h: h.get("population") or 0) if spots else None
    is_main = bool(main and (main.get("population") or 0) > 0
                   and km(lat, lon, main["latitude"], main["longitude"]) <= radius)
    if p.get("near") and by_id is not None:
        n = by_id.get(p["near"])
        if n is None or n.get("latitude") is None:
            res["problems"].append(f"near '{p['near']}' is not in the registry")
        elif km(lat, lon, n["latitude"], n["longitude"]) > 300:
            res["problems"].append(f"it should be near {n['name']} but is "
                                   f"{km(lat, lon, n['latitude'], n['longitude']):.0f} km away")
    elif len(spots) > 1 and kind == "town" and not is_main:
        # "Santiago, Chile" is the capital without saying so; "Aguas Calientes, Peru" is not
        res["problems"].append(f"{len(spots)} places called '{p['name']}' in {countries.name(cc)}: "
                               "say which with \"near\"")

    # the homonyms abroad that made the old geocoder wrong ("Aguas Calientes" -> Mexico)
    abroad = sorted({h["country_code"] for h in src.geonames(p["name"])[:5]
                     if h.get("country_code") and h["country_code"] != cc})
    if abroad:
        res["notes"].append("same name also in " + ", ".join(abroad))

    if kind != "region" and p.get("elevation_m") is not None:
        ground = src.srtm([(lat, lon)])[0]
        if ground is not None:
            if abs(ground - p["elevation_m"]) > ELEV_TOL:
                res["problems"].append(f"elevation {p['elevation_m']:.0f} m, but the ground there is "
                                       f"{ground:.0f} m (SRTM)")
                res["suggest_elevation"] = ground
            else:
                res["sources"].append("srtm (elevation)")
    if p.get("base") and by_id is not None:
        b = by_id.get(p["base"])
        if b is None:
            res["problems"].append(f"base '{p['base']}' is not in the registry")
        elif b["country_code"].upper() != cc:
            res["problems"].append(f"base {b['name']} is in another country ({b['country_code']})")
        elif b.get("latitude") is not None and km(lat, lon, b["latitude"], b["longitude"]) > 150:
            res["problems"].append(f"base {b['name']} is "
                                   f"{km(lat, lon, b['latitude'], b['longitude']):.0f} km away")
    res["ok"] = not res["problems"] and len(res["sources"]) >= 2
    if not res["problems"] and not res["ok"]:
        res["problems"].append("only one source confirms it")
    return res


def fill(p: dict, src: Sources, by_id: dict[str, dict] | None = None) -> list[str]:
    """Look up what a registry entry lacks. Returns what changed."""
    cc = p["country_code"].upper()
    changed = []
    if p.get("latitude") is None:
        hit = None
        near = by_id.get(p["near"]) if by_id and p.get("near") else None
        if p.get("kind", "town") == "town":
            hits = src.geonames(p["name"], cc)
            if near:  # the one close to the place it is said to be near
                hits.sort(key=lambda h: km(h["latitude"], h["longitude"], near["latitude"], near["longitude"]))
            else:
                hits.sort(key=lambda h: (-(h.get("population") or 0)))
            hit = hits[0] if hits else None
            if hit:
                p.setdefault("admin", hit.get("admin"))
                if hit.get("elevation_m") is not None and p.get("elevation_m") is None:
                    p["elevation_m"] = hit["elevation_m"]
        if hit is None:
            for n in _names(p):
                hits = src.osm_search(n, cc, kind=p.get("kind", "town"))
                if near:
                    hits.sort(key=lambda h: km(h["latitude"], h["longitude"], near["latitude"], near["longitude"]))
                if hits:
                    hit = hits[0]
                    break
        if hit:
            p["latitude"], p["longitude"] = round(hit["latitude"], 4), round(hit["longitude"], 4)
            changed.append("coordinates")
    if p.get("latitude") is not None and p.get("elevation_m") is None and p.get("kind") != "region":
        ground = src.srtm([(p["latitude"], p["longitude"])])[0]
        if ground is not None:
            p["elevation_m"] = round(ground)
            changed.append("elevation")
    return changed


# ---------------------------------------------------------------- landmark art catalog
def art_places() -> list[dict]:
    """The landmark catalog in either layout: art/catalog.json (old) or art/catalog/<cc>.json."""
    out = []
    old = ART / "catalog.json"
    if old.is_file():
        for d in json.loads(old.read_text(encoding="utf-8"))["landmarks"]:
            cc = d["country"].upper()
            out.append({**d, "id": f"{cc.lower()}-{d['id']}", "country_code": cc,
                        "name": d["label"], "_file": str(old.relative_to(ROOT))})
    for f in sorted((ART / "catalog").glob("*.json")) if (ART / "catalog").is_dir() else []:
        data = json.loads(f.read_text(encoding="utf-8"))
        cc = data["country"].upper()
        if f.stem.upper() != cc:
            out.append({"id": f.name, "name": f.name, "country_code": cc, "_file": str(f.relative_to(ROOT)),
                        "_problem": f"file {f.name} declares country {cc}"})
        for d in data["places"]:
            out.append({**d, "id": f"{cc.lower()}-{d['slug']}", "country_code": cc, "name": d["label"],
                        "_file": str(f.relative_to(ROOT))})
    return out


def check_art(a: dict, src: Sources, reg: dict[str, dict]) -> dict:
    if a.get("_problem"):
        return {"id": a["id"], "name": a["name"], "country_code": a["country_code"], "ok": False,
                "problems": [a["_problem"]], "notes": [], "sources": []}
    cc = a["country_code"]
    p = {"id": a["id"], "name": a["aliases"][0] if a.get("aliases") else a["name"], "kind": "site",
         "country_code": cc, "latitude": a["lat"], "longitude": a["lon"],
         "elevation_m": a.get("elevation_m"), "aliases": a.get("aliases", [])[1:3],
         "radius_km": max(a.get("radius_km") or 25, 10)}
    res = check_place(p, src)
    res["name"] = a["name"]
    same = reg.get(a["id"])
    if same and km(a["lat"], a["lon"], same["latitude"], same["longitude"]) > (a.get("radius_km") or 25):
        res["problems"].append(f"the registry puts {same['name']} "
                               f"{km(a['lat'], a['lon'], same['latitude'], same['longitude']):.0f} km away")
    # an alias that names a registry place of another country would put the art in the wrong country
    from app.places.countries import norm
    for al in a.get("aliases", []):
        other = [r for r in reg.values()
                 if norm(al) in {norm(r["name"]), *(norm(x) for x in r.get("aliases", []))}
                 and r["country_code"].upper() != cc]
        if other and not any(r["country_code"].upper() == cc for r in reg.values()
                             if norm(al) in {norm(r["name"]), *(norm(x) for x in r.get("aliases", []))}):
            res["problems"].append(f"alias '{al}' is {other[0]['name']} in {other[0]['country_code']}")
    res["ok"] = res["ok"] and not res["problems"]
    return res


# ---------------------------------------------------------------- saved trips
def check_stops(src: Sources) -> list[dict]:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Trip
    from app.places.verify import check_stops as trip_checks
    out = []
    with SessionLocal() as db:
        for t in db.scalars(select(Trip)).all():
            stops = sorted(t.stops, key=lambda s: (s.position, s.start_date))
            checks = trip_checks(stops, t.countries or [])
            for s, c in zip(stops, checks):
                problems = list(c.issues)
                osm_cc = src.osm_country(s.latitude, s.longitude)
                if osm_cc and s.country_code and osm_cc != s.country_code.upper():
                    problems.append(f"saved as {s.country_code} but the coordinates are in {osm_cc}")
                if problems:
                    out.append({"id": f"trip {t.id[:8]} / {s.name}", "name": s.name,
                                "country_code": s.country_code, "ok": False, "problems": problems,
                                "notes": [], "sources": []})
    return out


# ---------------------------------------------------------------- report
def report(sections: list[tuple[str, list[dict]]]) -> str:
    lines = [f"# Place audit, {date.today().isoformat()}", ""]
    for title, rows in sections:
        bad = [r for r in rows if not r["ok"]]
        lines += [f"## {title}: {len(rows) - len(bad)} of {len(rows)} verified", ""]
        if bad:
            lines += ["| place | country | problem |", "|---|---|---|"]
            for r in bad:
                fix = ""
                if r.get("suggest"):
                    s = r["suggest"]
                    fix = f" (sources say {s['latitude']}, {s['longitude']})"
                lines.append(f"| {r['name']} (`{r['id']}`) | {r['country_code']} | "
                             f"{'; '.join(r['problems'])}{fix} |")
            lines.append("")
        risky = [r for r in rows if any(n.startswith("same name also in") for n in r["notes"])]
        if risky:
            lines.append("Names that also exist abroad (the registry pins the right one): " + ", ".join(
                f"{r['name']} ({next(n for n in r['notes'] if n.startswith('same name'))[18:]})"
                for r in risky))
            lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="app.places.audit")
    ap.add_argument("--fill", action="store_true", help="look up missing data and write the registry")
    ap.add_argument("--stops", action="store_true", help="also check the trips saved in the database")
    ap.add_argument("--report", help="write the markdown report here too")
    ap.add_argument("--no-art", action="store_true", help="skip the landmark art catalog")
    args = ap.parse_args(argv)

    src = Sources(cache=CACHE)
    doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
    rows = doc["places"]
    by_id = {p["id"]: p for p in rows}
    sections = []
    try:
        if args.fill:
            for p in rows:
                ch = fill(p, src, by_id)
                if ch:
                    print(f"filled {p['id']}: {', '.join(ch)}", file=sys.stderr)
        results = []
        for p in rows:
            r = check_place(p, src, by_id)
            results.append(r)
            if args.fill:
                p["verified"] = {"ok": r["ok"], "on": date.today().isoformat(), "sources": r["sources"]}
                if r["problems"]:
                    p["verified"]["problems"] = r["problems"]
            print(f"{'ok ' if r['ok'] else 'BAD'} {p['id']}: {'; '.join(r['problems'])}", file=sys.stderr)
        sections.append(("Place registry (seed/places.json)", results))
        if args.fill:
            REGISTRY.write_text(dump(doc), encoding="utf-8")
        if not args.no_art:
            sections.append(("Landmark art catalog",
                             [check_art(a, src, by_id) for a in art_places()]))
        if args.stops:
            sections.append(("Saved trips", check_stops(src)))
    finally:
        src.save()
    text = report(sections)
    print(text)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
    return 0 if all(r["ok"] for _, rs in sections for r in rs) else 1


def dump(doc: dict) -> str:
    """One place per line: easy to review in a diff."""
    head = {k: v for k, v in doc.items() if k != "places"}
    body = ",\n".join(" " + json.dumps(p, ensure_ascii=False) for p in doc["places"])
    return json.dumps(head, ensure_ascii=False)[:-1] + ',\n "places": [\n' + body + "\n ]\n}\n"


if __name__ == "__main__":
    sys.exit(main())
