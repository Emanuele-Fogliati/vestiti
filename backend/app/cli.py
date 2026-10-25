"""Operations CLI.

    python -m app.cli migrate                      # alembic upgrade head
    python -m app.cli seed                         # sample products + placeholder rental partners
    python -m app.cli ingest --network awin --file feeds/awin.csv.gz
    python -m app.cli create-admin --email you@example.com --password '...'
    python -m app.cli check-ai                     # is the local model reachable? try a parse
    python -m app.cli art-pregen --file app/art/popular.txt   # draw places with the image model
    python -m app.cli art-export --dir art-export  # copy model-made images out (to ship to production)
    python -m app.cli art-import --dir art-export  # load them into another database
    python -m app.cli art-forget --name "Reykjavik"  # drop an image you don't like; it is redrawn
"""
import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    sub.add_parser("seed")
    p = sub.add_parser("ingest")
    p.add_argument("--network", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--keep-missing", action="store_true", help="do not deactivate missing products")
    p = sub.add_parser("create-admin")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    sub.add_parser("check-ai")
    p = sub.add_parser("art-pregen")
    p.add_argument("--file", required=True, help="one place per line: 'Name' or 'Name, CC'")
    p.add_argument("--redo-failed", action="store_true")
    p = sub.add_parser("art-export")
    p.add_argument("--dir", required=True)
    p = sub.add_parser("art-import")
    p.add_argument("--dir", required=True)
    p = sub.add_parser("art-forget")
    p.add_argument("--name", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "migrate":
        from alembic import command
        from alembic.config import Config
        cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        command.upgrade(cfg, "head")
        print("database migrated")
        return 0

    from app.db import SessionLocal
    db = SessionLocal()
    try:
        if args.cmd == "seed":
            from app.catalog.ingest import seed_all
            print(json.dumps(seed_all(db)))
        elif args.cmd == "ingest":
            from app.catalog.ingest import ingest_bytes
            raw = Path(args.file).read_bytes()
            job = ingest_bytes(db, raw, args.network, Path(args.file).name, not args.keep_missing)
            print(json.dumps({"rows": job.rows, "created": job.created, "updated": job.updated,
                              "skipped": job.skipped, "deactivated": job.deactivated,
                              "errors": job.errors[:10]}, indent=1))
        elif args.cmd == "create-admin":
            from sqlalchemy import select
            from app.models import User
            from app.security import hash_password
            email = args.email.lower()
            u = db.scalar(select(User).where(User.email == email))
            if u is None:
                u = User(email=email)
                db.add(u)
            u.password_hash = hash_password(args.password)
            u.is_admin = True
            u.is_guest = False
            db.commit()
            print(f"admin ready: {email}")
        elif args.cmd == "check-ai":
            from app.llm.client import LLMClient
            from app.llm.itinerary import parse_itinerary
            st = LLMClient().status()
            print(json.dumps(st, indent=1))
            d = parse_itinerary("3 days in Reykjavik then 4 days hard trekking in Landmannalaugar",
                                today=date.today())
            print(f"parser used: {d.parser}")
            for s in d.stops:
                print(f"  {s.name}: {s.start_date} -> {s.end_date} {[a.type for a in s.activities]}")
        elif args.cmd.startswith("art-"):
            return _art(db, args)
    finally:
        db.close()
    return 0


def _art(db, args) -> int:
    from sqlalchemy import select

    from app import art
    from app.art import generate
    from app.models import PlaceArt

    if args.cmd == "art-pregen":
        from app.config import get_settings
        from app.weather import geocode
        if not get_settings().art_image_enabled:
            print("set ART_IMAGE_ENABLED=true (and ART_IMAGE_URL) first", file=sys.stderr)
            return 2
        print(json.dumps(generate.status()))
        for line in Path(args.file).read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            name, _, cc = (x.strip() for x in line.partition(","))
            hits = geocode.search(name, limit=1, country=cc or None)
            if not hits:
                print(f"  ? {line}: not found")
                continue
            h = hits[0]
            if art.match(h["name"], h["latitude"], h["longitude"]):
                print(f"  = {line}: drawn by hand in the library")
                continue
            key = generate.place_key(h["name"], h.get("country_code"), h["latitude"], h["longitude"])
            row = db.get(PlaceArt, key)
            if row is not None and (row.status == "ready" or (row.status == "failed" and not args.redo_failed)):
                print(f"  = {line}: {row.status}")
                continue
            generate.request(db, h["name"], h.get("country_code"), h["latitude"], h["longitude"], enqueue=False)
            t = time.time()
            row = generate.generate(db, key)
            print(f"  + {line}: {row.status} in {time.time() - t:.0f}s, {row.subject!r}"
                  + (f" ({row.error})" if row.error else ""))
    elif args.cmd == "art-export":
        out = Path(args.dir)
        out.mkdir(parents=True, exist_ok=True)
        index = []
        for row in db.scalars(select(PlaceArt).where(PlaceArt.status == "ready")):
            (out / f"{row.key}.webp").write_bytes(row.image)
            index.append({k: getattr(row, k) for k in ("key", "name", "country_code", "latitude", "longitude",
                                                       "subject", "prompt")})
        (out / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"exported {len(index)} images to {out}")
    elif args.cmd == "art-import":
        src = Path(args.dir)
        n = 0
        for d in json.loads((src / "index.json").read_text(encoding="utf-8")):
            img = src / f"{d['key']}.webp"
            if not img.is_file():
                continue
            row = db.get(PlaceArt, d["key"]) or PlaceArt(key=d["key"], attempts=0)
            for k, v in d.items():
                setattr(row, k, v)
            row.image, row.status, row.error = img.read_bytes(), "ready", None
            db.merge(row)
            n += 1
        db.commit()
        print(f"imported {n} images")
    elif args.cmd == "art-forget":
        rows = [r for r in db.scalars(select(PlaceArt)) if r.name.lower() == args.name.lower()]
        for r in rows:
            db.delete(r)
        db.commit()
        print(f"forgot {len(rows)} image(s) for {args.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
