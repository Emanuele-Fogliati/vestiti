"""Fetch the reference photo of a place: every scene starts from the classic photo (LANDMARK_STYLE.md 0).

    python tools/art/ref.py <id> "<Wikipedia title>" [--lang en] [--out refs]
    python tools/art/ref.py <id> --url <direct image url> [--page <page url>] [--out refs]

With a title it takes the lead image of the Wikipedia article, which is usually the classic view of the
place and is freely licensed (Wikimedia Commons). If that image is not the classic view, find a better
one (web search for the place's most photographed viewpoint) and pass it with --url.
Use exactly 4 photos per place (Manu): run it once per photo, the classic view first, then 3 from
other points of view or distances (mountains: clear sky, summer, from far away). Each run writes
the next free <out>/<id>-<n>.jpg (n = 1..4) and adds it to <out>/<id>.json:
{"sources": [{"file", "url", "page"}], "notes": "..."}. Write in "notes" what you took from each
photo; the review tool shows the photos, the notes and the drawing to Manu. The photo is a
reference to look at, never a file of the app: it stays in the batch folder and is not committed.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "ThruwearArt/0.1 (https://github.com/Emanuele-Fogliati/vestiti)"


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for wait in (2, 4, 8, 16, 0):  # Wikimedia rate-limits shared addresses: back off and retry
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or not wait:
                sys.exit(f"{e.code} for {url}")
            time.sleep(wait)
    raise AssertionError


def lead_image(title: str, lang: str) -> tuple[str, str]:
    page = urllib.parse.quote(title.replace(" ", "_"), safe="")
    d = json.loads(get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{page}"))
    thumb = (d.get("thumbnail") or {}).get("source")
    if not thumb:
        sys.exit(f"no lead image on {lang}.wikipedia.org/wiki/{page}: find one and use --url")
    # ask for a 960 px version of the same file
    url = re.sub(r"/\d+px-", "/960px-", thumb.split("?")[0])
    return url, d.get("content_urls", {}).get("desktop", {}).get("page", "")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id")
    ap.add_argument("title", nargs="?")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--url")
    ap.add_argument("--page", default="")
    ap.add_argument("--out", default="refs")
    a = ap.parse_args()
    if not (a.title or a.url):
        ap.error("give a Wikipedia title or --url")
    url, page = (a.url, a.page) if a.url else lead_image(a.title, a.lang)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    meta_file = out / f"{a.id}.json"
    meta = json.loads(meta_file.read_text()) if meta_file.is_file() else {"sources": [], "notes": ""}
    if any(s["url"] == url for s in meta["sources"]):
        sys.exit(f"{url} is already a reference of {a.id}")
    n = next((i for i in range(1, 5) if not (out / f"{a.id}-{i}.jpg").exists()), None)
    if n is None:
        sys.exit(f"{a.id} already has 4 reference photos (the maximum)")
    name = f"{a.id}-{n}.jpg"
    (out / name).write_bytes(get(url))
    meta["sources"].append({"file": name, "url": url, "page": page})
    meta_file.write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{out / name}  <- {url}")


if __name__ == "__main__":
    main()
