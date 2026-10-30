"""Find reference photo candidates for a place and pick the 4 you use (LANDMARK_STYLE.md section 0, step 2).

    python tools/art/findref.py search <id> "<query>" [--wiki "<Wikipedia title>"] [--dir <batch dir>]
    python tools/art/findref.py pick <id> <n1> <n2> <n3> <n4> [--dir <batch dir>]

`search` gathers up to 16 landscape photos: the Wikipedia article's own images first (lead image, then
the photos used in the article: usually the classic views), then Wikimedia Commons search results, then
Openverse (Flickr and others) when Commons has too few. It saves small thumbnails in
<dir>/cand/<id>/ and one numbered contact sheet <dir>/cand/<id>/sheet.jpg to look at. Run it again
with another query (e.g. "<place> viewpoint", "<place> from <spot>") to add more; numbers keep growing.

`pick` downloads the chosen candidates at 960 px into <dir>/refs/<id>-1.jpg .. -4.jpg in the order
given (the first is photo 1, the postcard view) and writes <dir>/refs/<id>.json with the sources.
Add your "notes" to that json afterwards (what you took from each photo).

The photos are references to look at, never files of the app: they stay in the batch folder.
Needs Pillow for the contact sheet (thumbnails are still saved without it).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "ThruwearArtBot/1.0 (reference only)"
SKIP = ("map", "locator", "logo", "flag", "coat of arms", "diagram", "plan ", "svg", "icon", "seal",
        "banner", "drawing", "interior", "inside", "night", "door", "ceiling", "detail", "museum exhibit",
        "statue of", "portrait", "mosaic", "fresco", "inscription", "sunset", "dusk", "aerial photograph", "painting", "engraving", "stamp", "chart", "location", "relief", "1890",
        "1900", "1910", "1920", "1930", "1940", "1950")


def get(url: str, tries: int = 5) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    wait = 2
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            code = getattr(e, "code", None)
            if i == tries - 1 or (code is not None and code not in (429, 500, 502, 503, 504)):
                raise
            time.sleep(wait)
            wait *= 2
    raise AssertionError


def jget(url: str) -> dict:
    return json.loads(get(url))


def commons_info(titles: list[str]) -> list[dict]:
    out = []
    for i in range(0, len(titles), 40):
        q = urllib.parse.urlencode({"action": "query", "format": "json", "prop": "imageinfo",
                                    "iiprop": "url|size|mime", "iiurlwidth": 960,
                                    "titles": "|".join(titles[i:i + 40])})
        d = jget(f"https://commons.wikimedia.org/w/api.php?{q}")
        pages = {p.get("title"): p for p in d.get("query", {}).get("pages", {}).values()}
        for t in titles[i:i + 40]:
            p = pages.get(t)
            if p and p.get("imageinfo"):
                out.append({"title": t, **p["imageinfo"][0]})
    return out


def usable(title: str, info: dict) -> bool:
    t = title.lower()
    if any(s in t for s in SKIP):
        return False
    if info.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
        return False
    w, h = info.get("width", 0), info.get("height", 0)
    return w >= 800 and w >= h * 1.05  # landscape photos only


def from_wikipedia(title: str, lang: str) -> list[dict]:
    q = urllib.parse.urlencode({"action": "query", "format": "json", "prop": "pageimages|images",
                                "piprop": "name", "imlimit": 60, "redirects": 1, "titles": title})
    try:
        d = jget(f"https://{lang}.wikipedia.org/w/api.php?{q}")
    except Exception:
        return []
    names = []
    page_url = f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
    for p in d.get("query", {}).get("pages", {}).values():
        if p.get("pageimage"):
            names.append("File:" + p["pageimage"].replace("_", " "))
        names += [i["title"] for i in p.get("images", []) if i["title"] not in names]
    names = list(dict.fromkeys("File:" + n.split(":", 1)[1] for n in names))
    res = []
    for info in commons_info(names):
        if usable(info["title"], info):
            u = (info.get("thumburl") or info["url"]).split("?")[0]
            res.append({"thumb": u, "url": u,
                        "page": info.get("descriptionurl", page_url), "title": info["title"], "src": "wikipedia"})
    return res


def from_commons(query: str, limit: int = 30) -> list[dict]:
    q = urllib.parse.urlencode({"action": "query", "format": "json", "generator": "search",
                                "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": limit,
                                "prop": "imageinfo", "iiprop": "url|size|mime", "iiurlwidth": 960})
    d = jget(f"https://commons.wikimedia.org/w/api.php?{q}")
    pages = sorted(d.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    res = []
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        if usable(p["title"], info):
            u = (info.get("thumburl") or info["url"]).split("?")[0]
            res.append({"thumb": u, "url": u,
                        "page": info.get("descriptionurl", ""), "title": p["title"], "src": "commons"})
    return res


def from_openverse(query: str) -> list[dict]:
    q = urllib.parse.urlencode({"q": query, "page_size": 20, "aspect_ratio": "wide"})
    try:
        d = jget(f"https://api.openverse.org/v1/images/?{q}")
    except Exception:
        return []
    return [{"thumb": r.get("thumbnail") or r["url"], "url": r["url"], "page": r.get("foreign_landing_url", ""),
             "title": r.get("title", ""), "src": "openverse"} for r in d.get("results", [])
            if (r.get("width") or 0) >= 800]


def sheet(cdir: Path, items: list[dict]) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    tw, th, cols = 300, 200, 4
    rows = (len(items) + cols - 1) // cols
    img = Image.new("RGB", (cols * tw, rows * th), "white")
    dr = ImageDraw.Draw(img)
    for k, it in enumerate(items):
        f = cdir / f"{it['n']}.jpg"
        x, y = (k % cols) * tw, (k // cols) * th
        try:
            im = Image.open(f).convert("RGB")
            im.thumbnail((tw - 4, th - 4))
            img.paste(im, (x + (tw - im.width) // 2, y + (th - im.height) // 2))
        except Exception:
            continue
        dr.rectangle([x, y, x + 34, y + 24], fill="black")
        dr.text((x + 6, y + 5), str(it["n"]), fill="yellow")
    if items:
        img.save(cdir / "sheet.jpg", quality=80)


def search(a) -> None:
    cdir = Path(a.dir) / "cand" / a.id
    cdir.mkdir(parents=True, exist_ok=True)
    idx_f = cdir / "index.json"
    idx = json.loads(idx_f.read_text()) if idx_f.is_file() else []
    seen = {i["url"] for i in idx}
    wiki = from_wikipedia(a.wiki, a.lang) if a.wiki else []
    found = wiki[:1]  # the article's lead image: often the postcard view
    try:
        com = from_commons(a.query)
    except Exception as e:  # Wikimedia busy (429) even after retries: carry on with what we have
        print(f"Commons search failed ({e}); try again in a minute or use another query", file=sys.stderr)
        com = []
    for k in range(max(len(wiki), len(com))):  # then alternate commons results and article photos
        found += com[k:k + 1] + wiki[k + 1:k + 2]
    if len([f for f in found if f["url"] not in seen]) < 8:
        found += from_openverse(a.query)
    new = []
    for f in found:
        if f["url"] in seen or len(new) >= a.n:
            continue
        seen.add(f["url"])
        n = len(idx) + len(new) + 1
        try:
            data = get(f["thumb"].split("?")[0].replace("/960px-", "/330px-"), tries=3)
        except Exception:
            continue
        (cdir / f"{n}.jpg").write_bytes(data)
        new.append({"n": n, **f})
    idx += new
    idx_f.write_text(json.dumps(idx, indent=1, ensure_ascii=False))
    sheet(cdir, new)
    if not new:
        sys.exit("no new candidates: try another query (local name, '<place> viewpoint', the Wikipedia title)")
    print(f"{len(new)} new candidates ({len(idx)} total). Look at {cdir / 'sheet.jpg'} (this search's numbers "
          f"{new[0]['n']}-{new[-1]['n']}; each search replaces the sheet, pick numbers from any search)")
    for i in new:
        print(f"  {i['n']:>3} {i['src']:9} {i['title'][:90]}")


def pick(a) -> None:
    cdir = Path(a.dir) / "cand" / a.id
    idx = {i["n"]: i for i in json.loads((cdir / "index.json").read_text())}
    refs = Path(a.dir) / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    for old in refs.glob(f"{a.id}-[1-4].jpg"):
        old.unlink()
    meta = {"sources": [], "notes": ""}
    for k, n in enumerate(a.numbers, 1):
        it = idx[n]
        data = get(it["url"])
        try:  # keep refs small: 960 px wide JPEG
            from PIL import Image
            im = Image.open(io.BytesIO(data)).convert("RGB")
            if im.width > 960:
                im = im.resize((960, round(im.height * 960 / im.width)))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=82)
            data = buf.getvalue()
        except Exception:
            pass
        name = f"{a.id}-{k}.jpg"
        (refs / name).write_bytes(data)
        meta["sources"].append({"file": name, "url": it["url"], "page": it["page"], "title": it["title"]})
        print(f"{refs / name}  <- {it['title'][:80]}")
    (refs / f"{a.id}.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("id")
    s.add_argument("query")
    s.add_argument("--wiki", help="Wikipedia article title: its own photos come first")
    s.add_argument("--lang", default="en")
    s.add_argument("--n", type=int, default=16)
    s.add_argument("--dir", default=".")
    p = sub.add_parser("pick")
    p.add_argument("id")
    p.add_argument("numbers", type=int, nargs="+")
    p.add_argument("--dir", default=".")
    a = ap.parse_args()
    if a.cmd == "pick" and len(a.numbers) != 4:
        sys.exit("pick exactly 4 photos (Manu's rule): photo 1 = the postcard view")
    (search if a.cmd == "search" else pick)(a)


if __name__ == "__main__":
    main()
