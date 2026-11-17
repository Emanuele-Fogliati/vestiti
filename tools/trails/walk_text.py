"""Only walks with a real text (Manu, 2026-11-16): "in tutto il mondo solo quelli con del testo".

The generated walks (tier B in backend/app/trails/tail/, the world in backend/app/trails/world/) came
with a "why" made of numbers only (km, metres up). A walk stays only if a real text says why to go,
and that text, in English, becomes its "why", with the page it comes from as its first source.

Where the texts come from (legal sources only; never AllTrails, Komoot, Wikiloc or Outdooractive):
  1. the OSM relation (route) or goal node/way: description:en, description, wikipedia, wikidata, website
  2. Wikidata sitelinks -> the Wikipedia lead (English first, then the local language; bot-written
     stub wikis such as ceb, war, sv are skipped), or Wikivoyage
  3. the official page of the route (park, tourist board, alpine club): its meta description, only
     when it speaks about the walk (no "welcome to", cookies, closures, waymarking notes, GPX)
  4. New Zealand DOC track pages (CC BY 4.0), matched to the DOC track by name
Non-English texts: the 16 priority countries (NO TZ BO AT CH MA NP IT PE CL AR IS VN JP NA NZ) were
translated by hand, dropping stage lists, timetables and notices; the rest of the world by a free
local model (NLLB-200) whose output must keep every rare proper name of the source, or the walk
waits in "pending" for a better translation.

Kept as they are: city walks (-city-), walks to drawn sights (-sight-), the iconic treks
(world/_iconic.json) and the pending ones. Dropped: every other walk without a text, and world
copies of treks written by hand in data/<cc>/ (same OSM relation).

  python tools/trails/walk_text.py apply     # after any rebuild of world/ or tail/
  python tools/trails/world_tail.py dots     # then the globe dots
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAILS = ROOT / "backend/app/trails"
TEXTS = Path(__file__).with_name("walk_text.json")
SEP = (",", ":")


def tier_a_osm() -> set[int]:
    """OSM relations already written by hand as tier A treks (data/<cc>/<id>.json)."""
    out = set()
    for f in TRAILS.glob("data/*/*.json"):
        o = json.loads(f.read_text(encoding="utf-8")).get("osm")
        if o:
            out.add(int(o))
    return out


def apply() -> None:
    doc = json.loads(TEXTS.read_text(encoding="utf-8"))
    texts, pending = doc["texts"], set(doc["pending"])
    iconic = {t["id"] for t in json.loads((TRAILS / "world/_iconic.json").read_text(encoding="utf-8"))["treks"]}
    dup = tier_a_osm()
    files = sorted(TRAILS.glob("world/[a-z][a-z].json")) + sorted(TRAILS.glob("tail/*.json"))
    total, per = Counter(), {}
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        keep, c = [], Counter()
        for t in d["trails"]:
            i = t["id"]
            if "-osm-" in i and t.get("osm") in dup:
                c["copy of tier A"] += 1
                continue
            if i in texts:
                why, src = texts[i]
                t["why"] = why
                t["sources"] = list(dict.fromkeys([src] + [s for s in t.get("sources", []) if s != src]))[:8]
                c["text"] += 1
            elif "-city-" in i or "-sight-" in i or i in iconic or i in pending:
                c["kept as is"] += 1
            else:
                c["no text"] += 1
                continue
            keep.append(t)
        if len(keep) != len(d["trails"]) or c["text"]:
            ids = {t["id"] for t in keep}
            d["trails"] = keep
            d["geo"] = {k: v for k, v in d["geo"].items() if k in ids}
            if keep:
                f.write_text(json.dumps(d, ensure_ascii=False, separators=SEP), encoding="utf-8")
            else:
                f.unlink()
        total.update(c)
        per[f.name] = dict(c)
    print(json.dumps({"total": dict(total), "files": per}, indent=1))


if __name__ == "__main__":
    {"apply": apply}[sys.argv[1]]()
