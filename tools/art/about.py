"""What each drawn place is, in a sentence or two, for the small card a drawing on the map opens
(Manu 2026-11-16: "cliccando su ognuna delle immagini ... una piccola descrizione ... cos'è quel
posto ... cosa c'è lì").

From Wikipedia (CC BY-SA 4.0, credited on the card): for each landmark, a search for its name in
its country; a result counts only when its title matches the landmark's name or aliases, and,
when Wikipedia has coordinates for it, it lies near the drawing. No match: the card shows the
drawing's own caption. Output: backend/app/art/about.json {landmark id: [text, title]}.

    cd backend && PYTHONPATH=. python3 ../tools/art/about.py [--only nz,is] [--limit 50] [--workers 2]
Wikimedia rate-limits busy shared addresses hard (429): run it from a home connection.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from app import art

OUT = Path(art.__file__).with_name("about.json")
API = "https://en.wikipedia.org/w/api.php"
UA = "TravelGuideBuild/1.0 (one-off place description fetch; python-httpx)"
MAX_CHARS = 230


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def words(s: str) -> set[str]:
    stop = {"the", "of", "and", "de", "la", "le", "del", "di", "da", "national", "park", "a", "in", "on"}
    return {w for w in fold(s).split() if w not in stop and len(w) > 1}


def km(a, b, c, d) -> float:
    p = math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


def clean(text: str) -> str:
    """The first sentence or two, without pronunciations, other names and footnote leftovers."""
    t = re.sub(r"\s*\([^()]*\)", "", text)
    t = re.sub(r"\s*\([^()]*\)", "", t)  # nested
    t = re.sub(r"\s+", " ", t).replace(" ,", ",").strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", t)
    out = parts[0]
    if len(out) < 60 and len(parts) > 1 and len(out) + len(parts[1]) < MAX_CHARS:
        out += " " + parts[1]
    if len(out) > MAX_CHARS:
        cut = out[:MAX_CHARS].rsplit(" ", 1)[0].rstrip(",;:")
        out = cut + "…"
    return out


def names_of(lm) -> list[str]:
    slug = lm.id.split("-", 1)[1].replace("-", " ")
    return [slug, *lm.aliases, *lm.names]


def query(lm, country: str) -> list[dict]:
    q = f"{lm.id.split('-', 1)[1].replace('-', ' ')} {country}"
    params = {"action": "query", "format": "json", "formatversion": 2, "generator": "search",
              "gsrsearch": q, "gsrlimit": 6, "prop": "coordinates|extracts|pageprops",
              "exintro": 1, "explaintext": 1, "exsentences": 3, "exlimit": 6, "ppprop": "disambiguation"}
    return sorted(get(params).get("query", {}).get("pages", []), key=lambda p: p.get("index", 99))


def get(params: dict) -> dict:
    for attempt in range(30):
        try:
            r = httpx.get(API, params=params, headers={"User-Agent": UA}, timeout=30)
            if r.status_code == 429:
                time.sleep(int(r.headers.get("retry-after") or 20) + 2); continue
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError:
            time.sleep(3 * (attempt + 1))
    return {}


def save(done: dict) -> None:
    OUT.write_text(json.dumps(dict(sorted(done.items())), ensure_ascii=False, separators=(",", ":")))


def by_title(lms: list, done: dict) -> None:
    """First pass, 20 at a time: the landmark's name as a Wikipedia title (redirects followed)."""
    by = {lm.id: lm for lm in lms}
    guess = {lm.id: lm.id.split("-", 1)[1].replace("-", " ").capitalize() for lm in lms}
    out: dict[str, list[dict]] = {}
    ids = list(guess)
    for i in range(0, len(ids), 20):
        chunk = ids[i:i + 20]
        d = get({"action": "query", "format": "json", "formatversion": 2, "redirects": 1,
                 "titles": "|".join(guess[x] for x in chunk), "prop": "coordinates|extracts|pageprops",
                 "exintro": 1, "explaintext": 1, "exsentences": 3, "exlimit": 20, "ppprop": "disambiguation"})
        q = d.get("query", {})
        to = {x["from"]: x["to"] for x in q.get("normalized", []) + q.get("redirects", [])}
        pages = {p["title"]: p for p in q.get("pages", []) if not p.get("missing")}
        for x in chunk:
            t = guess[x]
            while t in to:
                t = to[t]
            if t in pages:
                out[x] = [pages[t]]
        time.sleep(1.0)
        for x in chunk:
            got = pick(by[x], out.get(x, []))
            if got:
                done[x] = list(got)
        if (i // 20) % 10 == 0:
            save(done)
        print(f"titles {i + len(chunk)}/{len(ids)}", file=sys.stderr)
    save(done)


def pick(lm, pages: list[dict]) -> tuple[str, str] | None:
    want = [words(n) for n in names_of(lm)]
    for p in pages:
        if "disambiguation" in p.get("pageprops", {}) or not p.get("extract"):
            continue
        tw = words(p["title"])
        if not tw:
            continue
        # the title is the place: all of its words are in one of the landmark's names, or the
        # other way round (Waitomo Glowworm Caves / "waitomo caves")
        match = any(w and (tw <= w or w <= tw or len(tw & w) >= max(2, min(len(tw), len(w)))) for w in want)
        if not match:
            continue
        co = (p.get("coordinates") or [None])[0]
        if co and km(lm.lat, lm.lon, co["lat"], co["lon"]) > max(40, lm.radius_km * 3):
            continue
        text = clean(p["extract"])
        if len(text) < 30:
            continue
        return text, p["title"]
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--redo", action="store_true", help="look up the ones already done again")
    ap.add_argument("--out", help="write here instead of app/art/about.json")
    ap.add_argument("--pause", type=float, default=1.2, help="seconds between searches, per worker")
    a = ap.parse_args()
    global OUT
    if a.out:
        OUT = Path(a.out)
    names = art.country_names()
    done = json.loads(OUT.read_text()) if OUT.exists() else {}
    todo = [lm for lm in art.landmarks() if (not a.only or lm.country.lower() in a.only.split(","))
            and (a.redo or lm.id not in done)]
    # the pilot countries first (Manu 2026-11-14), then the rest
    pilot = {"PE", "CL", "AR", "IS", "VN", "JP", "NA", "NZ", "BO"}
    todo.sort(key=lambda lm: lm.country not in pilot)
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(todo)} to look up", file=sys.stderr)

    by_title(todo, done)
    todo = [lm for lm in todo if not done.get(lm.id)]
    print(f"{len(todo)} left for the search", file=sys.stderr)

    def one(lm):
        time.sleep(a.pause)
        return lm.id, pick(lm, query(lm, names.get(lm.country, "")))

    n = 0
    with ThreadPoolExecutor(a.workers) as ex:
        for lid, got in ex.map(one, todo):
            n += 1
            done[lid] = list(got) if got else None
            if n % 100 == 0:
                save(done)
                print(n, file=sys.stderr)
    save(done)
    have = sum(1 for v in done.values() if v)
    print(f"{have} of {len(done)} with a Wikipedia sentence", file=sys.stderr)


if __name__ == "__main__":
    main()
