"""Point the seed catalog at real shop pages and fill in today's price, picture and stock.

    cd backend && PYTHONPATH=. python ../tools/catalog/refresh_seed.py

- Products listed in bergfreunde_pages.json: their Bergfreunde IT page is read (schema.org
  data), price = cheapest size/colour in stock, picture and rating from the page. Out of stock
  or unreadable -> the product is switched off ("active": false) with the reason.
- Decathlon, Uniqlo, Mountain Warehouse: no page we can read from here (Decathlon and Uniqlo
  block automated requests), so the link opens the model in the shop's own search and the
  price stays indicative ("checked_at": null). Real prices arrive with the Awin feed.
- Any other product with no partner shop selling it today is switched off.

Specs (warmth, waterproofing...) are kept: a page's text is not a reliable source for them.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

import httpx

from app.catalog.pagereader import UA, read

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "backend" / "seed" / "products.json"
PAGES = Path(__file__).with_name("bergfreunde_pages.json")

# Italian words make Decathlon's own search land on the right shelf
IT_WORD = {"base_top": "maglia", "base_bottom": "calzamaglia", "mid_top": "pile",
           "insulation_top": "piumino", "shell_top": "giacca impermeabile",
           "shell_bottom": "sovrapantaloni", "trousers": "pantaloni", "headwear": "berretto",
           "gloves": "guanti", "sun_hat": "cappello", "socks": "calze", "footwear": "scarpe"}
IT_GENDER = {"men": "uomo", "women": "donna"}
DECATHLON_BRANDS = ("Quechua", "Forclaz", "Wedze", "Simond", "Kiprun", "Kalenji", "Solognac",
                    "Tribord", "Olaian", "Domyos", "Van Rysel", "Rockrider")


def decathlon_query(p: dict) -> str:
    name = re.sub(r"\((Men|Women)\)", "", p["name"])
    words = name.split()
    sub = [w for w in words if w in DECATHLON_BRANDS]
    models = [w for w in words if any(c.isdigit() for c in w) and not w.endswith("-pack")]
    q = sub + models + [IT_WORD.get(p["category"], "")] + [IT_GENDER.get(p.get("gender"), "")]
    q = [w for w in q if w]
    return " ".join(q) if len(q) >= 2 else name.strip()


def main() -> int:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    pages = json.loads(PAGES.read_text(encoding="utf-8"))
    shop = pages["shop"]
    today = date.today().isoformat()
    client = httpx.Client(headers={"User-Agent": UA, "Accept-Language": "it,en;q=0.8"},
                          follow_redirects=True, timeout=20)
    counts = {"page": 0, "off": 0, "search": 0}
    for p in data["products"]:
        ext = p["external_id"]
        p.pop("inactive_reason", None)
        p["active"] = True
        if ext in pages["pages"]:
            spec = pages["pages"][ext]
            r = read(spec["url"], client)
            time.sleep(0.7)  # one page at a time, politely
            p.update(merchant=shop["merchant"], network=shop["network"],
                     program_id=shop["program_id"], url=spec["url"])
            if "name" in spec:
                p["name"] = spec["name"]
            if not r.ok:
                p.update(active=False, checked_at=today,
                         inactive_reason=f"{shop['merchant']}: {r.error or 'out of stock'}")
                counts["off"] += 1
                print(f"OFF  {p['brand']} {p['name']}: {p['inactive_reason']}")
                continue
            p.update(price=round(r.price, 2), currency=r.currency or "EUR",
                     image_url=r.image_url, checked_at=today)
            if r.rating is not None and r.review_count >= 3:
                p.update(rating=r.rating, review_count=r.review_count)
            counts["page"] += 1
            print(f"OK   {p['brand']} {p['name']}: {p['price']} {p['currency']}")
        elif p["brand"] == "Decathlon":
            p.update(merchant="Decathlon", network="awin", program_id="9643", checked_at=None,
                     url="https://www.decathlon.it/search?Ntt=" + quote_plus(decathlon_query(p)))
            counts["search"] += 1
        elif p["brand"] == "Uniqlo":
            q = re.sub(r"\((Men|Women)\)", "", p["name"]).strip()
            p.update(merchant="Uniqlo", network="direct", program_id=None, checked_at=None,
                     url="https://www.uniqlo.com/it/it/search?q=" + quote_plus(q))
            counts["search"] += 1
        elif p["brand"] == "Mountain Warehouse":
            q = re.sub(r"\((Men|Women)\)", "", p["name"]).strip()
            p.update(merchant="Mountain Warehouse", network="direct", program_id=None,
                     checked_at=None,
                     url="https://www.mountainwarehouse.com/eu/search/?q=" + quote_plus(q))
            counts["search"] += 1
        else:
            p.update(active=False, checked_at=today,
                     inactive_reason="no partner shop sells this model today")
            counts["off"] += 1
            print(f"OFF  {p['brand']} {p['name']}: {p['inactive_reason']}")
    data["_note"] = (
        "Catalog for development and the first users. Products with checked_at have a real "
        "shop page, and price, picture and stock were read from it that day; the app re-reads "
        "them (python -m app.cli refresh-prices). Products without checked_at link to the "
        "shop's own search and have an indicative price until the shop's affiliate feed is "
        "imported. Specs (clo, waterproof mm, weight) are the app team's estimates. Rebuild "
        f"with tools/catalog/refresh_seed.py. Last rebuilt {today}.")
    SEED.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
