"""Checks that a landmark SVG follows docs/LANDMARK_STYLE.md, and that the catalog is consistent.

    python -m app.art.lint                       # the whole library (catalog + every SVG)
    python -m app.art.lint path/to/out/          # a batch: every <cc>-<slug>.svg in the folder
    python -m app.art.lint pe-colca-canyon.svg   # one file

Exit code 1 when anything fails. The same rules run in tests/test_art.py.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

TOKENS = ("sky", "far", "mid", "ice", "water", "near", "sun")
COLOUR = re.compile(r"var\(--il-(%s)\)" % "|".join(TOKENS))
ELEMENTS = {"rect", "circle", "ellipse", "path", "polygon", "polyline", "line", "g", "defs", "clipPath"}
ATTRS = {"d", "x", "y", "width", "height", "rx", "ry", "cx", "cy", "r", "points", "x1", "y1", "x2", "y2",
         "fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-dasharray",
         "fill-rule", "clip-rule", "clip-path", "id", "transform"}
MAX_BYTES = 6144
MAX_ELEMENTS = 90
ID_RE = re.compile(r"[a-z]{2}-[a-z0-9]+(?:-[a-z0-9]+)*")


def lint_svg(landmark_id: str, body: str) -> list[str]:
    """Problems with one SVG fragment (empty list = passes)."""
    p: list[str] = []
    if not ID_RE.fullmatch(landmark_id):
        p.append(f"id '{landmark_id}' must be '<cc>-<slug>' (lowercase, hyphens)")
    if len(body.encode()) > MAX_BYTES:
        p.append(f"{len(body.encode())} bytes, limit {MAX_BYTES}")
    if re.search(r"<svg\b", body):
        p.append("fragment only: no <svg> wrapper")
    try:
        root = ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg">{body}</svg>')
    except ET.ParseError as e:
        return p + [f"not valid XML: {e}"]
    els = [e for e in root.iter() if e is not root]
    tag = lambda e: e.tag.split("}")[-1]  # noqa: E731
    if len(els) > MAX_ELEMENTS:
        p.append(f"{len(els)} elements, limit {MAX_ELEMENTS}: simplify")
    used: set[str] = set()
    for e in els:
        t = tag(e)
        if t not in ELEMENTS:
            p.append(f"<{t}> not allowed")
        for k, v in e.attrib.items():
            if k not in ATTRS:
                p.append(f"<{t}> attribute '{k}' not allowed")
            elif k in ("fill", "stroke"):
                m = COLOUR.fullmatch(v)
                if v != "none" and not m:
                    p.append(f"<{t}> {k}=\"{v}\": only var(--il-*) tokens or none")
                elif m:
                    used.add(m[1])
            elif k == "stroke-width":
                try:
                    if not 0.8 <= float(v) <= 5:
                        p.append(f"stroke-width {v} outside 0.8-5")
                except ValueError:
                    p.append(f"stroke-width '{v}' is not a number")
            elif k == "transform" and not re.fullmatch(r"translate\(-?[\d.]+[ ,]+-?[\d.]+\)", v):
                p.append(f"transform '{v}': only translate(x y)")
            elif k == "id" and not v.startswith(f"il-{landmark_id}-"):
                p.append(f"id '{v}' must start with 'il-{landmark_id}-' (ids are shared by the whole page)")
            elif k == "clip-path" and not re.fullmatch(r"url\(#il-%s-[a-z0-9-]+\)" % re.escape(landmark_id), v):
                p.append(f"clip-path '{v}' must point to an id 'il-{landmark_id}-...'")
    if not els or tag(els[0]) != "rect" or els[0].get("fill") != "var(--il-sky)" \
            or els[0].get("width") != "300" or els[0].get("height") != "200" \
            or els[0].get("x", "0") != "0" or els[0].get("y", "0") != "0":
        p.append('first element must be the sky: <rect width="300" height="200" fill="var(--il-sky)"/>')
    suns = [e for e in els if tag(e) == "circle" and e.get("fill") == "var(--il-sun)"]
    if len(suns) != 1:
        p.append(f"exactly one sun (<circle fill=\"var(--il-sun)\">), found {len(suns)}")
    elif not 10 <= float(suns[0].get("r", 0)) <= 22:
        p.append(f"sun radius {suns[0].get('r')} outside 10-22")
    if "near" not in used:
        p.append("no --il-near: every scene needs a dark foreground or detail")
    if len(used) < 4:
        p.append(f"only {len(used)} colour tokens used ({', '.join(sorted(used))}): use at least 4")
    return p


def lint_catalog(art_dir: Path | None = None) -> list[str]:
    """Catalog and files agree: every place has an SVG, every SVG a place, ids and aliases unique."""
    art_dir = art_dir or Path(__file__).resolve().parent
    p: list[str] = []
    ids: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for f in sorted((art_dir / "catalog").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        cc = d.get("country", "")
        if f.stem != cc.lower() or not re.fullmatch(r"[A-Z]{2}", cc):
            p.append(f"{f.name}: 'country' must be the uppercase ISO code matching the file name")
            continue
        for pl in d.get("places", []):
            lid = f"{cc.lower()}-{pl.get('slug', '')}"
            if not ID_RE.fullmatch(lid):
                p.append(f"{f.name}: bad slug '{pl.get('slug')}'")
            if lid in ids:
                p.append(f"{lid}: listed twice")
            ids[lid] = f.name
            if not (-90 <= pl.get("lat", 999) <= 90 and -180 <= pl.get("lon", 999) <= 180):
                p.append(f"{lid}: lat/lon missing or out of range")
            if not 1 <= pl.get("radius_km", 0) <= 80:
                p.append(f"{lid}: radius_km must be 1-80")
            if not pl.get("label"):
                p.append(f"{lid}: label missing")
            for a in pl.get("aliases", []):
                if a != a.lower() or re.search(r"[^a-z0-9 ]", a):
                    p.append(f"{lid}: alias '{a}' must be lowercase ascii letters, digits, spaces")
                if a in aliases and aliases[a] != lid:
                    p.append(f"{lid}: alias '{a}' already used by {aliases[a]}")
                aliases[a] = lid
            if not (art_dir / "landmarks" / cc.lower() / f"{pl.get('slug')}.svg").is_file():
                p.append(f"{lid}: landmarks/{cc.lower()}/{pl.get('slug')}.svg missing")
    for f in sorted((art_dir / "landmarks").glob("*/*.svg")):
        lid = f"{f.parent.name}-{f.stem}"
        if lid not in ids:
            p.append(f"landmarks/{f.parent.name}/{f.name}: not in catalog/{f.parent.name}.json")
    return p


def _lint_files(paths: list[Path]) -> int:
    from app import art
    existing = {lm.id for lm in art.landmarks()}
    bad = 0
    for f in paths:
        lid = f"{f.parent.name}-{f.stem}" if f.parent.parent.name == "landmarks" else f.stem
        probs = lint_svg(lid, f.read_text(encoding="utf-8"))
        if f.parent.parent.name != "landmarks" and lid in existing:
            probs.append("already in the library: do not redraw")
        print(("FAIL " if probs else "ok   ") + str(f))
        for x in probs:
            print("     - " + x)
        bad += bool(probs)
    return bad


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        here = Path(__file__).resolve().parent
        cat = lint_catalog(here)
        for x in cat:
            print("catalog - " + x)
        return int(bool(cat) or bool(_lint_files(sorted((here / "landmarks").glob("*/*.svg")))))
    files: list[Path] = []
    for a in argv:
        pa = Path(a)
        files += sorted(pa.glob("*.svg")) if pa.is_dir() else [pa]
    return int(bool(_lint_files(files)))


if __name__ == "__main__":
    sys.exit(main())
