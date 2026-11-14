"""Write the ranking fields (scores, tier, kinds...) into the hand-written areas, keeping each
file's layout (todo.json: one thing per line; areas/*.json: indent 1).

    python tools/guide/score.py patch.json

patch.json: {"<area id>": {"area": {"nights": [2, 4, 6], "buffer": 1},
                           "items": {"<item id>": {"scores": {...}, "tier": "A", ...}},
                           "add": [<new item>, ...], "after": {"<new item id>": "<item id>"}}}
Fields are merged into the thing as written; nothing else changes. Rubric: docs/RANKING.md.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

GUIDE = Path(__file__).resolve().parents[2] / "backend" / "app" / "guide"
ORDER = ["scores", "tier", "kinds", "alt_of", "cost", "kids", "needs"]


def _merge(it: dict, upd: dict) -> dict:
    out = dict(it)
    for k in ORDER + [k for k in upd if k not in ORDER]:
        if k in upd:
            out[k] = upd[k]
    return out


def _area_patch(a: dict, p: dict) -> dict:
    a = dict(a)
    for k, v in (p.get("area") or {}).items():
        a[k] = v
    items = [_merge(it, (p.get("items") or {}).get(it["id"], {})) for it in a["items"]]
    for new in p.get("add") or []:
        after = (p.get("after") or {}).get(new["id"])
        at = next((i + 1 for i, it in enumerate(items) if it["id"] == after), len(items))
        items.insert(at, new)
    a["items"] = items
    return a


def patch_pretty(path: Path, patch: dict) -> set[str]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    done = set()
    for i, a in enumerate(doc["areas"]):
        if a["id"] in patch:
            doc["areas"][i] = _area_patch(a, patch[a["id"]])
            done.add(a["id"])
    if done:
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return done


def patch_lines(path: Path, patch: dict) -> set[str]:
    """todo.json: areas spread over lines, one thing per line. Rewrite only the touched lines."""
    lines = path.read_text(encoding="utf-8").split("\n")
    doc = json.loads("\n".join(lines))
    done = set()
    for a in doc["areas"]:
        if a["id"] not in patch:
            continue
        p = patch[a["id"]]
        start = next(i for i, l in enumerate(lines) if re.match(rf'^\s*"id": "{re.escape(a["id"])}"', l))
        end = next(i for i in range(start, len(lines)) if lines[i].strip() in ("],",))  # end of items
        for i in range(start, end):
            m = re.match(r'^(\s*)(\{"id": "([a-z0-9-]+)".*\})(,?)$', lines[i])
            if m and m.group(3) in (p.get("items") or {}):
                it = _merge(json.loads(m.group(2)), p["items"][m.group(3)])
                lines[i] = m.group(1) + json.dumps(it, ensure_ascii=False) + m.group(4)
        for new in reversed(p.get("add") or []):
            after = (p.get("after") or {}).get(new["id"])
            at = next(i + 1 for i in range(start, end) if re.match(rf'^\s*\{{"id": "{re.escape(after)}"', lines[i]))
            lines.insert(at, "  " + json.dumps(new, ensure_ascii=False) + ",")
            end += 1
        # the last thing of the list has no comma
        last = max(i for i in range(start, end) if lines[i].lstrip().startswith('{"id"'))
        for i in range(start, end):
            if lines[i].lstrip().startswith('{"id"'):
                lines[i] = lines[i].rstrip(",") + ("" if i == last else ",")
        extra = {k: v for k, v in (p.get("area") or {}).items()}
        if extra:
            j = next(i for i in range(start, end) if lines[i].strip().startswith('"items": ['))
            for k in extra:  # written before: replace it
                old = [i for i in range(start, j) if lines[i].startswith(f' "{k}": ')]
                for i in reversed(old):
                    del lines[i]
                    j -= 1
                    end -= 1
            for k, v in extra.items():
                lines.insert(j, f' "{k}": {json.dumps(v, ensure_ascii=False)},')
                j += 1
        done.add(a["id"])
    if done:
        text = "\n".join(lines)
        json.loads(text)  # still valid
        path.write_text(text, encoding="utf-8")
    return done


def main(patch_file: str) -> None:
    patch = json.loads(Path(patch_file).read_text(encoding="utf-8"))
    done = patch_lines(GUIDE / "todo.json", patch)
    for f in sorted((GUIDE / "areas").glob("*.json")):
        done |= patch_pretty(f, patch)
    missing = set(patch) - done
    if missing:
        sys.exit(f"no such area: {sorted(missing)}")
    print(f"patched {len(done)} areas")


if __name__ == "__main__":
    main(sys.argv[1])
