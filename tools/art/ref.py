"""Fetch the reference photo of a place: every scene starts from the classic photo (LANDMARK_STYLE.md 0).

    python tools/art/ref.py <id> "<Wikipedia title>" [--lang en] [--out refs]
    python tools/art/ref.py <id> --url <direct image url> [--out refs]

With a title it takes the lead image of the Wikipedia article, which is usually the classic view of the
place and is freely licensed (Wikimedia Commons). If that image is not the classic view, find a better
one (web search for the place's most photographed viewpoint) and pass it with --url.
Writes <out>/<id>.jpg (960 px wide) and <out>/<id>.json with where it came from. The photo is a
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
    ap.add_argument("--out", default="refs")
    a = ap.parse_args()
    if not (a.title or a.url):
        ap.error("give a Wikipedia title or --url")
    url, page = (a.url, "") if a.url else lead_image(a.title, a.lang)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{a.id}.jpg").write_bytes(get(url))
    (out / f"{a.id}.json").write_text(json.dumps({"id": a.id, "image": url, "page": page}, indent=1) + "\n")
    print(f"{out / (a.id + '.jpg')}  <- {url}")


if __name__ == "__main__":
    main()
