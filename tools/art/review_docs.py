"""Build the review-tool documents for a batch of scenes (Manu's review page, see docs/LANDMARK_STYLE.md 0).

    python3 tools/art/review_docs.py <batch dir> <assets.tsv> <out dir> [--round N] [--labels labels.json]

<batch dir>   <id>.svg + <id>.palette.json, and refs/<id>-1..4.jpg + refs/<id>.json (from tools/art/ref.py)
<assets.tsv>  one line per uploaded photo: "<file name> <asset id>" (the ids the Artifact asset upload returned)
<out dir>     gets one <id>.json per place: {label, country, countryName, round, order, svg, refs, notes}

Then write them to the review page's database, collection "places", doc id = place id, with one
ArtifactData batch (50 documents per batch). A redrawn place gets the next --round: its earlier verdict
stays visible as history and the place goes back to "Da rivedere".
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
COUNTRY_IT = {"ar": "Argentina", "bo": "Bolivia", "br": "Brasile", "cl": "Cile", "cn": "Cina", "ec": "Ecuador",
              "in": "India", "is": "Islanda", "it": "Italia", "jo": "Giordania", "mx": "Messico", "pe": "Perù",
              "vn": "Vietnam", "jp": "Giappone", "th": "Thailandia", "kh": "Cambogia", "np": "Nepal"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("batch")
    ap.add_argument("assets")
    ap.add_argument("out")
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--labels", help="JSON {id: label}; default: the id")
    a = ap.parse_args()
    batch, out = Path(a.batch), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    assets = dict(line.split() for line in Path(a.assets).read_text().splitlines() if line.strip())
    labels = json.loads(Path(a.labels).read_text()) if a.labels else {}
    for n, svg_file in enumerate(sorted(batch.glob("*.svg"))):
        pid = svg_file.stem
        svg = subprocess.check_output(["python3", "-m", "app.art.render", str(svg_file.resolve())],
                                      cwd=BACKEND, text=True)
        meta_file = batch / "refs" / f"{pid}.json"
        meta = json.loads(meta_file.read_text()) if meta_file.is_file() else {"sources": [], "notes": ""}
        if len(meta["sources"]) != 4:
            raise SystemExit(f"{pid}: has {len(meta['sources'])} reference photos, Manu wants exactly 4")
        missing = [s["file"] for s in meta["sources"] if s["file"] not in assets]
        if missing:
            raise SystemExit(f"{pid}: upload these photos first: {', '.join(missing)}")
        doc = {
            "label": labels.get(pid, pid), "country": pid[:2].upper(),
            "countryName": COUNTRY_IT.get(pid[:2], pid[:2].upper()), "round": a.round, "order": n, "svg": svg,
            "refs": [{"url": "/_blob/" + assets[s["file"]], "page": s.get("page", ""), "file": s["file"],
                      "took": s.get("took", ""), "license": s.get("license", "")} for s in meta["sources"][:4]],
            "notes": meta.get("notes", ""),
        }
        (out / f"{pid}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        print(out / f"{pid}.json")


if __name__ == "__main__":
    main()
