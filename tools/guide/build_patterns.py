"""Build backend/app/guide/patterns.json.gz: how organised trips really go (Manu, 2026-11-12).

"The trips you propose are random: take the organised trips we read, see which places matter,
merge them, and remember that in one day I can do many things."

From the inventory manifest (the organised trips read day by day: which places each day names)
we keep derived facts only, no text:

- for every trip, where you sleep and for how many days, in order ("stays"). The place you sleep
  in on a day is the last place of the day where you can sleep (a city, a town, an island, or a
  park trips stay in for nights in a row, like Torres del Paine); a day that names only sights
  is a day out from where you slept the night before;
- for every place you sleep in, the days out from it: the sights trips see on the same day,
  grouped ("Pisac, Ollantaytambo, Chinchero" is one day from Cusco), most done first;
- for every move from one place to the next, what trips see on the way.

The generator (app.services.explore) merges the trips of a region and a length: the places most
of them sleep in, the days they give them, the order most of them follow. Counts stay on the
server: the traveller never sees how many trips include a place (Manu, 2026-10-26).

Usage:
    python tools/guide/build_patterns.py /path/to/manifest.json
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.globe import hierarchy  # noqa: E402

OUT = ROOT / "backend" / "app" / "guide" / "patterns.json.gz"
SLEEP_KINDS = ("city", "town", "island")
MERGE_KM = 20          # two places you sleep in this close are one stay (a suburb, the next village)
PARK_NIGHTS_TRIPS = 3  # a park is somewhere you sleep when this many trips spend days in a row there
GROUP_SHARE = 0.4      # two sights are one day out when trips see them together this often
GROUP_MAX = 5
MIN_GROUP_TRIPS = 2
MAX_GROUPS = 10
WAY_MAX = 4
WAY_SHARE = 0.15  # a sight on the way: seen by this share of the trips making the move
PARK_TOWN_KM = 60
TREK_FAR_KM = 20     # days out this far from where you slept, next to each other, are one trek
TREK_STEP_KM = 35
TREK_SHARE = 0.35  # a sight seen this often on treks belongs to the trek
DAY_OUT_KM = 180  # Colca from Arequipa is about as far as a day out goes


def km(a: dict, b: dict) -> float:
    return hierarchy.km(a["lat"], a["lon"], b["lat"], b["lon"])


def load_places() -> dict[str, dict]:
    g = ROOT / "backend" / "app" / "globe"
    doc = json.loads((g / "places.json").read_text(encoding="utf-8"))
    rows = list(doc["places"])
    ex = g / "extras.json"
    if ex.is_file():
        ids = {r[0] for r in rows}
        rows += [r for r in json.loads(ex.read_text(encoding="utf-8"))["places"] if r[0] not in ids]
    places = {r[0]: dict(zip(doc["fields"], r)) for r in rows}
    par = hierarchy.parents(list(places.values()))
    for pid, p in places.items():
        p["parent"] = par.get(pid)
    return places


def _n(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    for w in (" national park", " national reserve", "parque nacional ", " np"):
        s = s.replace(w, "")
    return " ".join("".join(c if c.isalnum() else " " for c in s).split())


def twins(places: dict[str, dict]) -> dict[str, str]:
    """{id: id of the same place under its more common name}: "Torres del Paine" and "Torres del
    Paine National Park" 300 m apart are one place."""
    grid: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for p in places.values():
        grid[(int(p["lat"] * 10), int(p["lon"] * 10))].append(p)
    out = {}
    for p in places.values():
        np_ = _n(p["name"])
        gy, gx = int(p["lat"] * 10), int(p["lon"] * 10)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for q in grid.get((gy + dy, gx + dx), []):
                    if q is p or q["country"] != p["country"] or km(p, q) > 3:
                        continue
                    nq = _n(q["name"])
                    if np_ != nq or (p["kind"] in SLEEP_KINDS) != (q["kind"] in SLEEP_KINDS):
                        continue
                    if (q["trips"], q["id"]) > (p["trips"], p["id"]):
                        out[p["id"]] = q["id"]
    # chains point to the end
    for k in list(out):
        seen = {k}
        while out[k] in out and out[k] not in seen:
            seen.add(out[k])
            out[k] = out[out[k]]
    return out


class Builder:
    def __init__(self, manifest: dict, places: dict[str, dict]):
        self.trips = manifest["trips"]
        self.places = places
        self.same = twins(places)
        for t in self.trips:  # one place read under two names is one place
            for d in t["days"]:
                d["places"] = list(dict.fromkeys(self.same.get(p, p) for p in d.get("places", [])))
        self.parks = self._parks()

    def _parks(self) -> set[str]:
        """Parks and lakes trips stay in for nights in a row (Torres del Paine, the Serengeti)."""
        runs: Counter = Counter()
        for t in self.trips:
            days = sorted(t["days"], key=lambda d: d["day"])
            seen = set()
            for a, b in zip(days, days[1:]):
                if b["day"] != a["day"] + 1 or not a["places"] or not b["places"]:
                    continue
                pa, pb = a["places"][-1], b["places"][-1]
                if pa == pb and pa in self.places and self.places[pa]["kind"] in ("nature", "region") \
                        and not self.places[pa]["parent"]:
                    seen.add(pa)
            runs.update(seen)
        towns = [q for q in self.places.values() if q["kind"] in ("city", "town") and not q["parent"]]
        out = set()
        for p, n in runs.items():
            if n < PARK_NIGHTS_TRIPS:
                continue
            q = self.places[p]
            # the Beagle Channel is seen from Ushuaia: a park next to a busier town is a day out
            if any(t["trips"] >= q["trips"] / 2 and km(t, q) <= PARK_TOWN_KM for t in towns):
                continue
            out.add(p)
        return out

    def home(self, pid: str) -> str:
        """The place a place belongs to: the Uffizi is Florence."""
        p = self.places[pid]
        return p["parent"] or pid

    def day_out(self, base: str, pid: str) -> bool:
        """A sight you see in a day from where you sleep: not another city, not too far."""
        p, q = self.places[pid], self.places[base]
        return p["kind"] != "city" and km(p, q) <= DAY_OUT_KM

    def excursions(self, base: str, out: list) -> list[tuple[int, list[str]]]:
        """Days out from a place, as (days, sights). Days in a row far from it, each next to the
        one before, are one trip of several days (the Inca Trail: four days of camps)."""
        q = self.places[base]
        far = lambda seen: bool(seen) and min(km(self.places[x], q) for x in seen) > TREK_FAR_KM  # noqa: E731
        res: list[list] = []  # [last day, n days, sights]
        for d, seen in out:
            if not seen:
                continue
            if res and res[-1][0] == d - 1 and far(seen) and far(res[-1][2]) \
                    and min(km(self.places[x], self.places[y]) for x in seen for y in res[-1][2]) <= TREK_STEP_KM:
                res[-1][0], res[-1][1] = d, res[-1][1] + 1
                res[-1][2] += [x for x in seen if x not in res[-1][2]]
                continue
            res.append([d, 1, list(seen)])
        return [(n, seen) for _, n, seen in res]

    def can_sleep(self, pid: str) -> bool:
        p = self.places[pid]
        return not p["parent"] and (p["kind"] in SLEEP_KINDS or pid in self.parks)

    def read(self, t: dict) -> dict | None:
        """One trip: its stays [[place, days]], days out per stay, sights on the way."""
        days = sorted((d for d in t["days"]), key=lambda d: d["day"])
        if not days or "AQ" in t.get("countries", []):  # a cruise to Antarctica sleeps on the ship
            return None
        first, last = days[0]["day"], days[-1]["day"]
        length = last - first + 1
        if length < 2 or length > 60:
            return None
        per_day: list[tuple[int, str | None, list[str]]] = []
        for d in days:
            ps = [p for p in d.get("places", []) if p in self.places]
            sleep = [p for p in ps if self.can_sleep(p)]
            base = sleep[-1] if sleep else None
            seen = [self.home(p) if self.places[p]["kind"] in ("town",) and self.places[p]["parent"] else p
                    for p in ps if p != base]
            seen = [p for p in dict.fromkeys(seen) if p != base]
            per_day.append((d["day"] - first + 1, base, seen))
        # nights: a day naming only sights is a day out from the night before
        bases = [b for _, b, _ in per_day]
        if not any(bases):
            return None
        firstbase = next(b for b in bases if b)
        cur = firstbase
        stays: list[list] = []  # [place, first day, [(day, [seen])], way]
        for day, b, seen in per_day:
            if b and b != cur and km(self.places[b], self.places[cur]) <= MERGE_KM:
                b = cur
            if b and b != cur:
                if stays and stays[-1][0] == cur:
                    pass
                cur = b
                stays.append([cur, day, [], seen])  # the day you move: seen on the way
                continue
            if not stays:
                stays.append([cur, 1, [], []])
            if seen:
                stays[-1][2].append((day, seen))
        stays[0][1] = 1
        out = []
        for i, s in enumerate(stays):
            end = stays[i + 1][1] if i + 1 < len(stays) else length + 1
            n = end - s[1]
            if n <= 0:
                continue
            if out and out[-1]["p"] == s[0]:
                out[-1]["d"] += n
                out[-1]["out"] += s[2]
                continue
            out.append({"p": s[0], "d": n, "out": s[2], "way": s[3]})
        return {"src": t["source"], "len": length, "stays": out}


def build(manifest: dict) -> dict:
    places = load_places()
    b = Builder(manifest, places)
    trips = [x for x in (b.read(t) for t in b.trips) if x and x["stays"]]
    ids: dict[str, int] = {}

    def ix(pid: str) -> int:
        if pid not in ids:
            ids[pid] = len(ids)
        return ids[pid]

    ops = sorted({t["src"] for t in trips})
    # days out: per place you sleep in, which sights trips see the same day
    sight_trips: dict[str, Counter] = defaultdict(Counter)
    sight_days: dict[tuple[str, str], list[int]] = defaultdict(list)
    pair: dict[str, Counter] = defaultdict(Counter)
    way: dict[tuple[str, str], Counter] = defaultdict(Counter)
    moves: Counter = Counter()
    for ti, t in enumerate(trips):
        prev = None
        for s in t["stays"]:
            seen_here: set[str] = set()
            pairs_here: set[tuple[str, str]] = set()
            s["out"] = b.excursions(s["p"], [(d, [x for x in seen if b.day_out(s["p"], x)]) for d, seen in s["out"]])
            for n, seen in s["out"]:
                for x in seen:
                    seen_here.add(x)
                    sight_days[(s["p"], x)].append(n)
                for i, x in enumerate(seen):
                    for y in seen[i + 1:]:
                        pairs_here.add((x, y) if x < y else (y, x))
            sight_trips[s["p"]].update(seen_here)
            pair[s["p"]].update(pairs_here)
            if prev:
                moves[(prev, s["p"])] += 1
            if prev and s["way"]:
                a_, c_ = places[prev], places[s["p"]]
                direct = km(a_, c_)
                way[(prev, s["p"])].update({x for x in s["way"]
                                            if km(a_, places[x]) + km(places[x], c_) <= 1.25 * direct + 30})
            prev = s["p"]
    # a sight seen mostly on treks (days in a row away from any bed: the Salkantay or Inca Trail
    # camps) is part of a trek, never a day out of its own nor something seen on the way
    in_trek: Counter = Counter()
    seen_all: Counter = Counter()
    for (base_, x), ns in sight_days.items():
        seen_all[x] += len(ns)
        in_trek[x] += sum(1 for n in ns if n > 1)
    trekky = {x for x, n in seen_all.items() if in_trek[x] >= TREK_SHARE * n}
    outings: dict[str, list] = {}
    for base, cnt in sight_trips.items():
        multi = {x for x in cnt if sorted(sight_days[(base, x)])[len(sight_days[(base, x)]) // 2] > 1}
        left = [x for x, n in cnt.most_common() if n >= MIN_GROUP_TRIPS and x != base
                and (x not in trekky or x in multi)]
        done: set[str] = set()
        groups = []
        def co(x: str, y: str) -> int:
            return pair[base].get((x, y) if x < y else (y, x), 0)

        for seed in left:
            if seed in done:
                continue
            g = [seed]
            mates = sorted(((co(seed, x), x) for x in left if x not in done and x != seed), reverse=True)
            for c, x in mates:
                if len(g) >= GROUP_MAX:
                    break
                # seen together often, from both sides, and with every sight already in the day
                if c < MIN_GROUP_TRIPS or c < GROUP_SHARE * cnt[x] or c < GROUP_SHARE / 2 * cnt[seed]:
                    continue
                if any(co(x, y) < max(MIN_GROUP_TRIPS, GROUP_SHARE / 2 * min(cnt[x], cnt[y])) for y in g[1:]):
                    continue
                g.append(x)
            done.update(g)
            ns = sorted(sight_days[(base, seed)])
            groups.append([[ix(x) for x in g], cnt[seed], ns[len(ns) // 2] if ns else 1])
            if len(groups) >= MAX_GROUPS:
                break
        if groups:
            outings[base] = groups
    ways = {}
    for (a, c), cnt in way.items():
        least = max(MIN_GROUP_TRIPS, WAY_SHARE * moves[(a, c)])
        top = [x for x, n in cnt.most_common(WAY_MAX + 4) if n >= least and x not in (a, c) and x not in trekky][:WAY_MAX]
        if top:
            ways[f"{ix(a)}>{ix(c)}"] = [ix(x) for x in top]
    out_trips = [[ops.index(t["src"]), t["len"], [[ix(s["p"]), s["d"]] for s in t["stays"]]] for t in trips]
    out_outings = {str(ix(k)): v for k, v in outings.items()}
    return {
        "_doc": "Derived from the organised trips read (inventory manifest): stays per trip, days out "
                "per place, sights on the way. tools/guide/build_patterns.py. Counts are internal only.",
        "places": list(ids),
        "operators": ops,
        "trips": out_trips,
        "outings": out_outings,
        "way": ways,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    doc = build(json.loads(Path(a.manifest).read_text(encoding="utf-8")))
    raw = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with gzip.GzipFile(a.out, "wb", mtime=0) as f:
        f.write(raw)
    print(f"{len(doc['trips'])} trips, {len(doc['places'])} places, {len(doc['outings'])} places with days out, "
          f"{len(doc['way'])} moves with sights on the way; {len(raw) // 1024} KB raw")


if __name__ == "__main__":
    main()
