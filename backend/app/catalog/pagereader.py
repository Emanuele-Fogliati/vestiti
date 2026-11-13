"""Read a shop's product page: price, stock, picture and rating from its schema.org data.

Most shops put a JSON-LD "Product" (or "ProductGroup" with variants) on every product page
for Google Shopping. That is the same data an affiliate feed carries, so until a network
approves us we can keep the catalog's prices and links true by reading those pages.

Rules: one plain request per page, our own user agent, no bot-check workarounds. A page we
can't read is reported, never guessed.
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field

import httpx

UA = "ThruwearCatalogBot/1.0 (+price and stock check of products we link to)"
LD_RE = re.compile(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)
GENDER = {"https://schema.org/Male": "men", "https://schema.org/Female": "women",
          "male": "men", "female": "women", "unisex": "unisex"}


@dataclass
class PageProduct:
    url: str
    name: str | None = None
    brand: str | None = None
    price: float | None = None          # lowest price of a variant that is in stock
    currency: str | None = None
    in_stock: bool = False
    image_url: str | None = None
    rating: float | None = None
    review_count: int = 0
    gender: str | None = None
    gtins: list[str] = field(default_factory=list)
    status: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.price is not None


def _blocks(text: str) -> list[dict]:
    out: list[dict] = []
    for raw in LD_RE.findall(text):
        try:
            data = json.loads(raw.strip())
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop(0)
            if isinstance(d, dict):
                if "@graph" in d:
                    stack.extend(d["@graph"] if isinstance(d["@graph"], list) else [d["@graph"]])
                out.append(d)
            elif isinstance(d, list):
                stack.extend(d)
    return out


def _types(d: dict) -> set[str]:
    t = d.get("@type")
    return set(t) if isinstance(t, list) else {t}


def _offers(d: dict) -> list[dict]:
    o = d.get("offers")
    if isinstance(o, dict):
        if "offers" in o and isinstance(o["offers"], list):  # AggregateOffer with a list
            return o["offers"]
        return [o]
    return o if isinstance(o, list) else []


def _img(v) -> str | None:
    if isinstance(v, list):
        v = v[0] if v else None
    if isinstance(v, dict):
        v = v.get("url") or v.get("contentUrl")
    return v if isinstance(v, str) and v.startswith("https://") else None


def _brand(v) -> str | None:
    if isinstance(v, dict):
        v = v.get("name")
    return v if isinstance(v, str) else None


def _in_stock(offer: dict) -> bool:
    return str(offer.get("availability") or "").rstrip("/").split("/")[-1].lower() in (
        "instock", "limitedavailability", "onlineonly", "presale")


def parse(text: str, url: str) -> PageProduct:
    """Pick the main product of the page and the cheapest variant that can be bought."""
    res = PageProduct(url=url)
    blocks = _blocks(text)
    group = next((b for b in blocks if "ProductGroup" in _types(b)), None)
    product = next((b for b in blocks if "Product" in _types(b)), None)
    main = group or product
    if main is None:
        res.error = "no product data on the page"
        return res
    res.name = html.unescape(main.get("name") or "") or None
    res.brand = _brand(main.get("brand")) or (_brand(product.get("brand")) if product else None)
    res.image_url = _img(main.get("image")) or (_img(product.get("image")) if product else None)
    aud = main.get("audience") or {}
    if isinstance(aud, dict):
        res.gender = GENDER.get(str(aud.get("suggestedGender") or ""))
    variants = [v for v in (main.get("hasVariant") or []) if isinstance(v, dict)] or [main]
    best: tuple[float, str] | None = None
    any_offer = False
    for v in variants:
        if not res.image_url:
            res.image_url = _img(v.get("image"))
        if v.get("gtin") or v.get("gtin13"):
            res.gtins.append(str(v.get("gtin") or v.get("gtin13")))
        for o in _offers(v):
            any_offer = True
            try:
                price = float(str(o.get("price") or o.get("lowPrice")).replace(",", "."))
            except (TypeError, ValueError):
                continue
            if price <= 0 or not _in_stock(o):
                continue
            if best is None or price < best[0]:
                best = (price, str(o.get("priceCurrency") or "EUR").upper()[:3])
    if best:
        res.price, res.currency, res.in_stock = best[0], best[1], True
    elif not any_offer:
        res.error = "no price on the page"
    # ratings may sit on the group or on the single product block
    for b in filter(None, [main, product]):
        ar = b.get("aggregateRating")
        if isinstance(ar, dict) and ar.get("ratingValue"):
            try:
                res.rating = round(float(ar["ratingValue"]), 2)
                res.review_count = int(ar.get("reviewCount") or ar.get("ratingCount") or 0)
            except (TypeError, ValueError):
                pass
            break
    if res.rating is None and product:  # some shops list single reviews but no aggregate
        stars = [r.get("reviewRating", {}).get("ratingValue") for r in product.get("review") or []
                 if isinstance(r, dict)]
        stars = [float(s) for s in stars if isinstance(s, (int, float))]
        if len(stars) >= 3:
            res.rating, res.review_count = round(sum(stars) / len(stars), 2), len(stars)
    return res


def read(url: str, client: httpx.Client | None = None, timeout: float = 20.0) -> PageProduct:
    own = client is None
    client = client or httpx.Client(headers={"User-Agent": UA, "Accept-Language": "it,en;q=0.8"},
                                    follow_redirects=True, timeout=timeout)
    try:
        r = client.get(url)
    except httpx.HTTPError as e:
        return PageProduct(url=url, error=f"network: {e.__class__.__name__}")
    finally:
        if own:
            client.close()
    if r.status_code != 200:
        return PageProduct(url=url, status=r.status_code, error=f"HTTP {r.status_code}")
    res = parse(r.text, str(r.url))
    res.status = r.status_code
    return res
