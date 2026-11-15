"""The official trails of the United States and Canada (Manu, 2026-11-15): OpenStreetMap is thin there
(few hiking relations), but the park agencies publish their own trail lines as open data:

- NPS Public Trails (US National Park Service, public domain):
  mapservices.nps.gov/arcgis/rest/services/NationalDatasets/NPS_Public_Trails/MapServer/0
- National Forest System Trails (USDA Forest Service, public domain):
  apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSPublish_01/MapServer/0
- Trails APCA (Parks Canada, Open Government Licence - Canada):
  services2.arcgis.com/wCOMu5IS7YdSyPNx/arcgis/rest/services/vw_Trails_Sentiers_APCA_V2_FGP/FeatureServer/0

Each agency gives one line per segment: the segments of one trail (same park and name, or the same
Forest Service trail number) are joined, the longest joined piece is the trail. Kept: named, for
walkers (no motor trails, no ski, snowmobile, horse-only or water trails), 1 to 250 km, not
already in the app as an OpenStreetMap route of the same name. Numbers, months, base and scores
as every world trek (world_tail.py); dots only, no drawings.

  python3 tools/trails/parks_na.py <nps.json> <usfs.json> <pc.json>    # ArcGIS features, EPSG:4326
     -> backend/app/trails/world/us.json, ca.json (added to the OSM treks), then world_tail.py dots
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "backend"))
sys.path.insert(0, str(HERE))

import build_trails as bt  # noqa: E402
import osm_tail as ot  # noqa: E402
import world_tail as wt  # noqa: E402

MIN_KM, MAX_KM = 0.5, 250.0
NOT_FOR_WALKERS = re.compile(
    r"\b(ski|snowmobile|snowmachine|nordic|winter|atv|ohv|ohrv|4x4|jeep|motorcycle|motorized|mtb|bike|bicycle|"
    r"horse|equestrian|stock|bridle|canoe|kayak|paddl|water trail|road|rd|sidewalk|parking|connector|"
    r"spur|access|cutoff|cut-off|tie|bypass|service|utility|fire ?line|powerline|unnamed|unknown|social|"
    r"campground|campsite|camp \d|picnic|amphitheat\w*|parking|lot|housing|residence|maintenance|employee|admin\w*)\b", re.I)
DROPS: Counter = Counter()


def _title(s: str) -> str:
    """'BIG SPRINGS' -> 'Big Springs Trail' (the Forest Service writes names in capitals)."""
    s = re.sub(r"\s+", " ", s).strip()
    if s.isupper():
        s = " ".join(w if re.fullmatch(r"[IVX]+|[A-Z]{1,2}\d*|\d+\w*", w) else w.capitalize() for w in s.split())
        s = re.sub(r"\bMc(\w)", lambda m: "Mc" + m.group(1).upper(), s)
    if not re.search(r"\b(trail|trl|path|loop|walk|way|route|track|nature trail|boardwalk|tour)\b", s, re.I):
        s += " Trail"
    return s.replace(" Trl", " Trail")


def groups(nps: list, usfs: list, pc: list) -> list[dict]:
    """[{key, cc, agency, name, unit, paths: [[[lon, lat], ...]], url}] one per trail."""
    g: dict[tuple, dict] = {}

    def add(key, cc, agency, name, unit, f, url):
        paths = (f.get("geometry") or {}).get("paths") or []
        if not paths:
            return
        r = g.setdefault(key, {"key": key, "cc": cc, "agency": agency, "name": name, "unit": unit, "paths": [], "url": url})
        r["paths"] += paths
    for f in nps:
        a = f["attributes"]
        name = (a.get("TRLNAME") or a.get("MAPLABEL") or "").strip()
        if (not name or a.get("TRLSTATUS") not in ("Existing", None, " ", "Unknown")
                or a.get("TRLFEATTYPE") in ("Unofficial Trail", "Non-NPS Trail", "Unmaintained Trail")
                or a.get("TRLTYPE") in ("Water Trail", "Snow Trail", "Sidewalk")):
            continue
        use = a.get("TRLUSE") or ""
        if use and not re.search(r"hike|hiker|pedestrian|unknown|foot|walk", use, re.I):
            continue
        add(("nps", a.get("UNITCODE"), name.lower()), "US", "nps", name, (a.get("UNITNAME") or "").strip(), f,
            f"https://www.nps.gov/{(a.get('UNITCODE') or '').lower()}/")
    for f in usfs:
        a = f["attributes"]
        name = (a.get("trail_name") or "").strip()
        if not name or a.get("trail_type") not in ("TERRA", None):
            continue
        hikers = any(a.get(k) for k in ("hiker_pedestrian_managed", "hiker_pedestrian_accpt", "hiker_pedestrian_accpt_disc"))
        motors = any(a.get(k) for k in ("motorcycle_managed", "atv_managed", "fourwd_managed", "motorcycle_accpt", "atv_accpt"))
        if not hikers or motors:
            continue
        add(("usfs", a.get("trail_cn") or name.lower()), "US", "usfs", _title(name), "", f,
            "https://www.fs.usda.gov/")
    for f in pc:
        a = f["attributes"]
        name = (a.get("Name_Official_e") or a.get("Label_e_5k_less") or "").strip()
        if not name or a.get("Official_Officiel") == 0:
            continue
        url = a.get("URL_e") or "https://parks.canada.ca/"
        unit = re.sub(r".*/(pn-np|lhn-nhs|amnc-nmca)/\w+/([^/]+).*", r"\2", url) if "pc.gc.ca" in url else ""
        add(("pc", unit, name.lower()), "CA", "pc", name, unit.replace("-", " ").title(), f, url)
    return list(g.values())


def joined(paths: list, gap_km: float = 0.15) -> list[tuple[float, float]]:
    """The segments joined end to end (the agencies' segment ends do not always meet exactly: a gap
    up to 150 m is closed); the longest chain, as [(lat, lon)]."""
    from shapely.geometry import MultiLineString
    from shapely.ops import linemerge
    lines = [[(round(x, 5), round(y, 5)) for x, y in p] for p in paths if len(p) >= 2]
    if not lines:
        return []
    m = linemerge(MultiLineString(lines))
    parts = [[(y, x) for x, y in p.coords] for p in (list(m.geoms) if hasattr(m, "geoms") else [m]) if not p.is_empty]
    if not parts:
        return []

    def length(p):
        return sum(bt.km(a, b) for a, b in zip(p, p[1:]))
    parts.sort(key=length, reverse=True)
    chains = []
    while parts:
        out = parts.pop(0)
        while True:
            best = None
            for i, p in enumerate(parts):
                for d, at_end, flip in ((bt.km(out[-1], p[0]), True, False), (bt.km(out[-1], p[-1]), True, True),
                                        (bt.km(out[0], p[-1]), False, False), (bt.km(out[0], p[0]), False, True)):
                    if d <= gap_km and (best is None or d < best[0]):
                        best = (d, i, at_end, flip)
            if not best:
                break
            _, i, at_end, flip = best
            p = parts.pop(i)
            p = p[::-1] if flip else p
            out = out + p if at_end else p + out
        chains.append(out)
    return max(chains, key=length)


def _osm_names(cc: str) -> dict[str, list[tuple[float, float]]]:
    """The OSM treks the app already has in the country, by name: (lat, lon) of their points."""
    out: dict[str, list] = defaultdict(list)
    f = wt.WORLD / f"{cc.lower()}.json"
    if f.exists():
        for t in json.loads(f.read_text(encoding="utf-8"))["trails"]:
            if "-osm-" in t["id"] or "-goal-" in t["id"]:
                out[ot._norm(t["name"].split(" near ")[0])] += [(p["lat"], p["lon"]) for p in t["points"]]
    return out


def build(tr: dict, line: list) -> tuple[dict, dict] | None:
    """One trail (osm_tail.build_one's rules on the agency's line)."""
    cc = tr["cc"]
    d = {"id": 1, "name": tr["name"], "line": [list(p) for p in line], "length": tr["km"] * 1000,
         "sac": 1, "tags": {"operator": tr["unit"]}}
    r = ot.build_one(d, cc, [], [])
    if not r:
        DROPS[next(iter(ot.DROPS), "dropped")] += 1
        ot.DROPS.clear()
        return None
    t, g = r
    if t["shape"] == "one_way" and g["one_way_km"] < 8:
        _there_and_back(t, g)
    slug = ot._slug(tr["name"])[:40]
    k = tr["key"]
    tid = (f"us-nps-{(k[1] or 'x').lower()}-{slug}" if tr["agency"] == "nps" else
           f"us-usfs-{ot._slug(str(k[1]))}" if tr["agency"] == "usfs" else f"ca-pc-{ot._slug(k[1] or 'x')[:20]}-{slug}")
    t["id"] = g["id"] = tid
    t.pop("osm", None)
    t["region"] = tr["unit"][:100]
    who = {"nps": "the National Park Service", "usfs": "the Forest Service", "pc": "Parks Canada"}[tr["agency"]]
    what = "loop" if t["shape"] == "loop" else "trail, there and back," if t["shape"] == "out_and_back" else "trail"
    where = f" in {tr['unit']}" if tr["unit"] and tr["agency"] != "usfs" else ""
    t["why"] = (f"An official {what} of {who}{where}: {g['km']:.1f} km, +{g['gain_m']:,} m, up to {g['max_m']:,} m, "
                f"from near {t['base']}.")[:300]
    t["sources"] = [tr["url"], {"nps": "https://public-nps.opendata.arcgis.com/",
                                "usfs": "https://data.fs.usda.gov/geodata/edw/datasets.php",
                                "pc": "https://open.canada.ca/data/en/dataset/64a90e8d-5bc0-4027-8645-b5881b4068d4"}[tr["agency"]]]
    return t, wt.compact(g)


def _there_and_back(t: dict, g: dict) -> None:
    """A short trail that does not come back (2 km to a lake) is walked there and back, not with a
    car at each end: the numbers double (build_trails.build's out_and_back rule)."""
    up, down = g["gain_m"], g["loss_m"]
    g["km"] = round(g["one_way_km"] * 2, 1)
    g["gain_m"] = g["loss_m"] = round(up + down)
    g["walk_hours"] = round(bt.walk_hours(g["km"], g["gain_m"], g["loss_m"]), 1)
    t["shape"] = "out_and_back"
    if t["points"][-1]["name"] == "End":
        t["points"][-1]["name"] = "Turnaround"
    h = g["walk_hours"]
    t["hours"] = [max(0.5, round(h * 0.85 * 2) / 2), max(0.5, round(h * 1.15 * 2) / 2)]
    t["difficulty"] = ot._difficulty(1, h, g["gain_m"], g["max_m"])
    pic = any(p.get("scene") for p in t["points"])
    t["scores"] = ot.scores(t["name"], g, t["days"], h, pic, t["scores"]["culture"] == 1)


def rank(t: dict, g: dict, unit: str) -> int:
    """The globe ladder of the world treks by length; a trail of a National Park is seen from one step further."""
    km = g["km"]
    r = 4 if km >= 100 else 3 if km >= 30 else 2 if km >= 12 else 1
    return min(4, r + 1) if re.search(r"National Park|Parc national", unit) or t["id"].startswith("ca-pc-") else r


def main(nps_f: str, usfs_f: str, pc_f: str) -> None:
    from multiprocessing import Pool
    trs = groups(*(json.loads(Path(f).read_text()) for f in (nps_f, usfs_f, pc_f)))
    print(f"{len(trs)} named trails", flush=True)
    keep = []
    names = {cc: _osm_names(cc) for cc in ("US", "CA")}
    for tr in trs:
        if NOT_FOR_WALKERS.search(tr["name"]) or not re.search(r"[A-Za-z]{3,}", re.sub(r"\b(Trail|Loop)\b", "", tr["name"])):
            DROPS["not for walkers"] += 1
            continue
        line = joined(tr["paths"])
        km = sum(bt.km(a, b) for a, b in zip(line, line[1:]))
        if not MIN_KM <= km <= MAX_KM:
            DROPS["shorter than 0.5 km" if km < MIN_KM else "longer than 250 km"] += 1
            continue
        same = names[tr["cc"]].get(ot._norm(tr["name"])) or names[tr["cc"]].get(ot._norm(tr["name"].replace(" Trail", "")))
        if same and min(bt.km(line[0], p) for p in same) < 15:
            DROPS["already an OSM trek"] += 1
            continue
        tr["km"] = km
        tr["line"] = line
        keep.append(tr)
    print(f"{len(keep)} to build; {dict(DROPS)}", flush=True)
    regions = {"hawaii": (-161.0, 18.0, -154.0, 23.0), "alaska": (-180.0, 51.0, -129.0, 72.0),
               "us": (-125.5, 24.0, -66.0, 49.5), "canada": (-141.0, 41.5, -52.0, 70.0),
               "islands": (-171.0, -15.0, 146.0, 19.0)}  # Puerto Rico, Virgin Islands, Guam, Samoa: below
    out: dict[str, list] = defaultdict(list)
    for name, box in regions.items():
        lon0, lat0, lon1, lat1 = box
        if name == "islands":
            todo = [tr for tr in keep if not tr.get("done")]
        else:
            todo = [tr for tr in keep if not tr.get("done") and lat0 <= tr["line"][0][0] <= lat1
                    and lon0 <= tr["line"][0][1] <= lon1 and (name != "canada" or tr["cc"] == "CA")]
        for tr in todo:
            tr["done"] = True
        if not todo:
            continue
        if name == "islands":  # few and scattered: one small box each
            groups_: dict = defaultdict(list)
            for tr in todo:
                groups_[(int(tr["line"][0][0] // 5), int(tr["line"][0][1] // 5))].append(tr)
            jobs = [((k[1] * 5 - 1, k[0] * 5 - 1, k[1] * 5 + 6, k[0] * 5 + 6), v) for k, v in groups_.items()]
        else:
            jobs = [(box, todo)]
        for bx, trs_ in jobs:
            print(f"{name} {bx}: {len(trs_)} trails", flush=True)
            wt.Climate(bx)
            wt.Towns()
            wt.prefetch(tr["line"] for tr in trs_)
            with Pool(4, wt._init, (bx,)) as pool:
                for n, (tr, r) in enumerate(zip(trs_, pool.imap(_job, trs_, chunksize=16))):
                    if r:
                        r[0]["rank"] = rank(r[0], r[1], tr["unit"])
                        out[tr["cc"]].append(r)
                    if n % 1000 == 999:
                        print(f"  {n + 1}/{len(trs_)}: {sum(map(len, out.values()))} kept", flush=True)
    for cc, rows in out.items():
        seen = Counter()
        uniq = []
        for t, g in rows:
            seen[t["id"]] += 1
            if seen[t["id"]] > 1:
                t["id"] = g["id"] = f"{t['id']}-{seen[t['id']]}"
            uniq.append((t, g))
        ot.names([t for t, _ in uniq])
        f = wt.WORLD / f"{cc.lower()}.json"
        doc = json.loads(f.read_text(encoding="utf-8"))
        agencies = ("us-nps-", "us-usfs-", "ca-pc-")
        doc["trails"] = [t for t in doc["trails"] if not t["id"].startswith(agencies)] + [t for t, _ in uniq]
        doc["geo"] = {**{k: v for k, v in doc["geo"].items() if not k.startswith(agencies)}, **{t["id"]: g for t, g in uniq}}
        doc["_doc"] += (" Also the official trails of the park agencies (tools/trails/parks_na.py): NPS and Forest "
                        "Service (public domain), Parks Canada (Open Government Licence - Canada).") if "parks_na" not in doc["_doc"] else ""
        f.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{cc}: {len(uniq)} agency trails written", flush=True)
    print(f"dropped {dict(DROPS)}")


def _job(tr):
    ot.MIN_KM = MIN_KM  # the agencies' short trails (a 2 km nature trail to a falls) count here
    try:
        return build(tr, tr["line"])
    except Exception as e:
        print(f"  {tr['name']}: {type(e).__name__}: {e}", flush=True)
        return None


if __name__ == "__main__":
    main(*sys.argv[1:4])
