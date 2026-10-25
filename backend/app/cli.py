"""Operations CLI.

    python -m app.cli migrate                      # alembic upgrade head
    python -m app.cli seed                         # sample products + placeholder rental partners
    python -m app.cli ingest --network awin --file feeds/awin.csv.gz
    python -m app.cli create-admin --email you@example.com --password '...'
    python -m app.cli check-ai                     # is the local model reachable? try a parse
"""
import argparse
import json
import sys
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
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
