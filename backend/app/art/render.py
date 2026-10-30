"""The official look ("58, la 17 pulita"): turns a flat scene into what the app shows.

A scene in the library is flat: shapes coloured only with var(--il-*) tokens (docs/LANDMARK_STYLE.md).
render() adds, in this order:
  1. the place's own palette (catalog "palette"), as CSS variables on a wrapping <g>;
  2. a comic outline: every filled shape without its own stroke gets a 1 px --il-near stroke,
     and every clipped group gets the outline of its clip shape;
  3. a paper-cut drop shadow under every filled shape except the sky.
So a drawer never draws outlines or shadows by hand, and the look can change in one place.

    python -m app.art.render scene.svg [palette.json] > preview.svg   # a standalone preview file
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SHAPES = {"rect", "circle", "ellipse", "path", "polygon", "polyline", "line"}
TOKEN = re.compile(r"var\(--il-([a-z]+)\)")
OUTLINE_W = "1"
SHADOW = dict(dx="0.8", dy="2.2", stdDeviation="1.6", flood_color="#2a2418", flood_opacity="0.35")


def _token(v: str | None) -> str | None:
    m = TOKEN.fullmatch(v or "")
    return m[1] if m else None


def _is_sky(e: ET.Element) -> bool:
    return (e.tag == "rect" and e.get("width") == "300" and _token(e.get("fill")) == "sky"
            and not e.get("x"))


def _filled(e: ET.Element) -> str | None:
    return _token(e.get("fill")) if e.tag != "line" else None


def render(landmark_id: str, body: str, palette: dict[str, str] | None) -> str:
    """The scene as the app shows it: still a fragment (no <svg> wrapper), ready to inline."""
    root = ET.fromstring(f"<svg>{body}</svg>")
    parent = {c: p for p in root.iter() for c in p}

    def inside(e: ET.Element, test) -> bool:
        p = parent.get(e)
        while p is not None and p is not root:
            if test(p):
                return True
            p = parent.get(p)
        return False

    # 2. outline of clipped groups: the clip shape drawn as a line after the group
    clips = {cp.get("id"): cp for cp in root.iter("clipPath")}
    for g in list(root.iter("g")):
        m = re.fullmatch(r"url\(#([^)]+)\)", g.get("clip-path") or "")
        shape = next(iter(clips[m[1]]), None) if m and m[1] in clips else None
        if shape is None or shape.get("d") is None:
            continue
        line = ET.Element("path", {"d": shape.get("d"), "fill": "none", "stroke": "var(--il-near)",
                                   "stroke-width": OUTLINE_W, "stroke-linejoin": "round"})
        holder = parent[g]
        holder.insert(list(holder).index(g) + 1, line)
        parent[line] = holder

    shadow_id = f"il-{landmark_id}-shadow"
    for e in list(root.iter()):
        if e is root or inside(e, lambda p: p.tag == "clipPath") or e.tag == "clipPath":
            continue
        if _is_sky(e) or not _filled(e):
            continue
        # 2. outline on every filled shape that has no stroke of its own
        if e.tag in SHAPES and not e.get("stroke"):
            e.set("stroke", "var(--il-near)")
            e.set("stroke-width", OUTLINE_W)
            e.set("stroke-linejoin", "round")
        # 3. shadow on top-level filled shapes (a filled group casts one shadow for all its children)
        if e.tag in SHAPES | {"g"} and (e.tag == "g" or not inside(e, lambda p: p.tag == "g" and p.get("fill"))):
            e.set("filter", f"url(#{shadow_id})")

    inner = "".join(ET.tostring(c, encoding="unicode") for c in root)
    style = ";".join(f"--il-{k}:{v}" for k, v in (palette or {}).items())
    shadow = (f'<defs><filter id="{shadow_id}" x="-30%" y="-30%" width="170%" height="185%">'
              f'<feDropShadow dx="{SHADOW["dx"]}" dy="{SHADOW["dy"]}" stdDeviation="{SHADOW["stdDeviation"]}" '
              f'flood-color="{SHADOW["flood_color"]}" flood-opacity="{SHADOW["flood_opacity"]}"/></filter></defs>')
    return shadow + (f'<g style="{style}">' if style else "<g>") + inner + "</g>"


def standalone(landmark_id: str, body: str, palette: dict[str, str] | None) -> str:
    """A complete .svg file, for previews and reviews."""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 200" width="600" height="400">'
            + render(landmark_id, body, palette) + "</svg>\n")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    f = Path(argv[0])
    pal_file = Path(argv[1]) if len(argv) > 1 else f.with_name(f.stem + ".palette.json")
    palette = json.loads(pal_file.read_text(encoding="utf-8")) if pal_file.is_file() else None
    lid = f"{f.parent.name}-{f.stem}" if f.parent.parent.name == "landmarks" else f.stem
    if palette is None and f.parent.parent.name == "landmarks":
        from app import art
        lm = next((x for x in art.landmarks() if x.id == lid), None)
        palette = dict(lm.palette) if lm else None
    sys.stdout.write(standalone(lid, f.read_text(encoding="utf-8"), palette))
    return 0


if __name__ == "__main__":
    sys.exit(main())
