"""A real text for every generated walk that has one (Manu, 2026-11-16/17).

The generated walks (tier B in backend/app/trails/tail/, the world in backend/app/trails/world/) came
with a "why" made of numbers only (km, metres up), which the walk card already shows. Where a real
text says why to go, that text, in English, becomes the "why", with the page it comes from as the
first source. Every other generated walk stays, with no text at all (Manu 2026-11-17: "tienili
tutti, anche quelli senza testo, semplicemente non c'è testo").

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
waits in "pending" for a better translation (no text until then).

City walks (-city-) and walks to drawn sights (-sight-) keep the text they were built with. The
only walks dropped are world copies of treks written by hand in data/<cc>/ (same OSM relation, or listed in
the trek's `replaces`).

  python tools/trails/walk_text.py apply     # after any rebuild of world/ or tail/ (idempotent)
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


def tier_a_replaces() -> set[str]:
    """Generated walks a hand-written trek names in `replaces` (the same walk, e.g. an NPS line)."""
    out = set()
    for f in TRAILS.glob("data/*/*.json"):
        out |= set(json.loads(f.read_text(encoding="utf-8")).get("replaces") or [])
    return out


def apply() -> None:
    texts = json.loads(TEXTS.read_text(encoding="utf-8"))["texts"]
    dup = tier_a_osm()
    same = tier_a_replaces()
    files = sorted(TRAILS.glob("world/[a-z][a-z].json")) + sorted(TRAILS.glob("tail/*.json"))
    total, per = Counter(), {}
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        keep, c = [], Counter()
        for t in d["trails"]:
            i = t["id"]
            if ("-osm-" in i and t.get("osm") in dup) or i in same:
                c["copy of tier A"] += 1
                continue
            if i in texts:
                why, src = texts[i]
                t["why"] = why
                t["sources"] = list(dict.fromkeys([src] + [s for s in t.get("sources", []) if s != src]))[:8]
                c["text"] += 1
            elif "-city-" in i or "-sight-" in i:
                c["own text"] += 1
            else:
                t["why"] = ""
                c["no text"] += 1
            keep.append(t)
        ids = {t["id"] for t in keep}
        d["trails"] = keep
        d["geo"] = {k: v for k, v in d["geo"].items() if k in ids}
        f.write_text(json.dumps(d, ensure_ascii=False, separators=SEP), encoding="utf-8")
        total.update(c)
        per[f.name] = dict(c)
    print(json.dumps({"total": dict(total), "files": per}, indent=1))


if __name__ == "__main__":
    {"apply": apply}[sys.argv[1]]()
