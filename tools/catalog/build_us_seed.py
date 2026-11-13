"""Build the US catalog (backend/seed/products_us.json) from real US shop pages.

    cd backend && PYTHONPATH=. python ../tools/catalog/build_us_seed.py

Reads every page in us_pages.json (evo, Decathlon US) for today's price in USD, picture and
stock. Specs come from the closest model in the EU seed (the same model when it exists),
or from the entry itself: a shop page is not a reliable source for warmth or waterproofing.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import httpx

from app.catalog.pagereader import UA, read

ROOT = Path(__file__).resolve().parents[2]
EU = ROOT / "backend" / "seed" / "products.json"
OUT = ROOT / "backend" / "seed" / "products_us.json"
PAGES = Path(__file__).with_name("us_pages.json")
EVO_SITEMAP = "https://www.evo.com/custom_sitemap_products_1.xml"
SHOP = {"evo": "www.evo.com", "dec": "www.decathlon.com"}
CUT = {"men": "Men", "women": "Women"}


def clean_name(raw: str, brand: str, gender: str) -> str:
    n = re.sub(r"\s+-\s+(Men's|Women's|Unisex)$", "", raw.strip())
    n = re.sub(r"\b(Men's|Women's|Men’s|Women’s|Adult)\s+", "", n)
    n = re.sub(r"[®™]", "", n).replace("Sweaterr", "Sweater").replace("Capilener", "Capilene")
    if brand != "Decathlon" and n.lower().startswith(brand.lower() + " "):
        n = n[len(brand) + 1:]
    n = re.sub(r"\s{2,}", " ", n).strip()
    return f"{n} ({CUT[gender]})" if gender in CUT else n


def main() -> int:
    cfg = json.loads(PAGES.read_text(encoding="utf-8"))
    eu = {p["external_id"]: p for p in json.loads(EU.read_text(encoding="utf-8"))["products"]}
    client = httpx.Client(headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8"},
                          follow_redirects=True, timeout=30)
    evo = re.findall(r"<loc>([^<]+/products/[^<]+)</loc>", client.get(EVO_SITEMAP).text)
    today = date.today().isoformat()
    out, seen = [], set()
    for item in cfg["items"]:
        ref, brand, slot, gender, like = item[:5]
        override = item[5] if len(item) > 5 else None
        shop, handle = ref.split(":", 1)
        host = SHOP[shop]
        if shop == "evo":
            urls = [u for u in evo if re.sub(r"^\d+-", "", u.rsplit("/", 1)[1]) == handle]
        else:
            urls = [f"https://{host}/products/{handle}"]
        specs = dict(override or (eu[like]["specs"] if like else {}))
        base = eu.get(like) or {}
        row = None
        for url in urls:
            r = read(url, client)
            time.sleep(0.7)
            if r.name and re.search(r"\b(Girls|Boys|Kids|Toddler|Infant)", r.name):
                continue  # a children's page under a similar handle
            row = {"url": url, "r": r}
            if r.ok:
                break
        if row is None:
            print(f"MISS {ref}: not in the shop's sitemap")
            continue
        r = row["r"]
        ext = "us-" + re.sub(r"[^a-z0-9]+", "-", f"{shop}-{handle}".lower()).strip("-")[:180]
        if ext in seen:
            continue
        seen.add(ext)
        name = clean_name(r.name or handle.replace("-", " ").title(), brand, gender)
        p = {"external_id": ext, "market": "us", **cfg["shops"][host], "brand": brand,
             "name": name, "category": slot, "gender": gender,
             "price": round(r.price, 2) if r.ok else float(base.get("price") or 0) or 1.0,
             "currency": r.currency or "USD", "url": row["url"], "image_url": r.image_url,
             "specs": specs, "rating": r.rating if r.review_count >= 3 else base.get("rating"),
             "review_count": r.review_count if r.review_count >= 3 else base.get("review_count", 0),
             "checked_at": today}
        if not r.ok:
            p.update(active=False, inactive_reason=f"{p['merchant']}: {r.error or 'out of stock'}")
            print(f"OFF  {brand} {name}: {p['inactive_reason']}")
        else:
            print(f"OK   {brand} {name}: {p['price']} {p['currency']}")
        out.append(p)
    note = ("US catalog (market 'us', prices in USD). Every product has a real shop page; "
            "price, picture and stock were read from it on checked_at and the app re-reads "
            "them (python -m app.cli refresh-prices). Specs are the app team's estimates, "
            "copied from the same or the closest model in products.json. Rebuild with "
            f"tools/catalog/build_us_seed.py. Last rebuilt {today}.")
    OUT.write_text(json.dumps({"_note": note, "products": out}, indent=1, ensure_ascii=False)
                   + "\n", encoding="utf-8")
    print(len(out), "products,", sum(1 for p in out if p.get("active", True)), "in stock")
    return 0


if __name__ == "__main__":
    sys.exit(main())
