"""Readers for affiliate product feeds. Each network names its columns differently, so
each one is a column mapping onto our normalized row:

    external_id, name, brand, merchant, program_id, price, currency, url, image_url,
    category_text, description, gender, rating, review_count, in_stock

Supported: awin (product feed CSV), impact (catalog CSV), cj (product feed CSV/TSV),
amazon (our own CSV export from the Product Advertising API), generic (our column names),
and json (our seed format).
"""
from __future__ import annotations

import csv
import gzip
import io
import json
from collections.abc import Iterator

MAPPINGS: dict[str, dict[str, list[str]]] = {
    "awin": {
        "external_id": ["aw_product_id", "merchant_product_id"],
        "name": ["product_name"],
        "brand": ["brand_name"],
        "merchant": ["merchant_name"],
        "program_id": ["merchant_id"],
        "price": ["search_price", "store_price", "rrp_price"],
        "currency": ["currency"],
        "url": ["merchant_deep_link", "aw_deep_link"],
        "image_url": ["merchant_image_url", "aw_image_url", "large_image"],
        "category_text": ["merchant_category", "category_name"],
        "description": ["description", "product_short_description"],
        "gender": ["Fashion:suitable_for", "suitable_for", "gender"],
        "rating": ["rating", "average_rating"],
        "review_count": ["reviews", "number_of_reviews"],
        "in_stock": ["in_stock", "stock_status"],
    },
    "impact": {
        "external_id": ["Unique Merchant SKU", "SKU", "Catalog Item Id"],
        "name": ["Product Name", "Name"],
        "brand": ["Manufacturer", "Brand"],
        "merchant": ["Campaign Name", "Advertiser"],
        "program_id": ["Campaign Id", "CampaignId"],
        "price": ["Current Price", "Price"],
        "currency": ["Currency"],
        "url": ["Product URL", "Url"],
        "image_url": ["Image URL", "ImageUrl"],
        "category_text": ["Category", "Product Type"],
        "description": ["Product Description", "Description"],
        "gender": ["Gender"],
        "rating": [],
        "review_count": [],
        "in_stock": ["Stock Availability", "Availability"],
    },
    "cj": {
        "external_id": ["ID", "SKU"],
        "name": ["TITLE", "NAME"],
        "brand": ["BRAND", "MANUFACTURER"],
        "merchant": ["PROGRAM_NAME", "ADVERTISERNAME"],
        "program_id": ["CID", "ADVERTISERID"],
        "price": ["SALE_PRICE", "PRICE"],
        "currency": ["CURRENCY"],
        "url": ["LINK", "BUYURL"],
        "image_url": ["IMAGE_LINK", "IMAGEURL"],
        "category_text": ["GOOGLE_PRODUCT_CATEGORY_NAME", "PRODUCT_TYPE", "ADVERTISERCATEGORY"],
        "description": ["DESCRIPTION"],
        "gender": ["GENDER"],
        "rating": [],
        "review_count": [],
        "in_stock": ["AVAILABILITY", "INSTOCK"],
    },
    "amazon": {
        "external_id": ["asin", "ASIN"],
        "name": ["title", "Title"],
        "brand": ["brand", "Brand"],
        "merchant": ["merchant"],
        "program_id": [],
        "price": ["price", "Price"],
        "currency": ["currency"],
        "url": ["url", "detail_page_url", "DetailPageURL"],
        "image_url": ["image_url", "image"],
        "category_text": ["category", "browse_node"],
        "description": ["features", "description"],
        "gender": ["gender"],
        "rating": ["rating"],
        "review_count": ["review_count", "reviews"],
        "in_stock": ["availability"],
    },
}
MAPPINGS["generic"] = {k: [k] for k in MAPPINGS["awin"]}


def _open_text(raw: bytes) -> str:
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _pick(row: dict, keys: list[str]) -> str | None:
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return str(v).strip()
    return None


def _float(v: str | None) -> float | None:
    if v is None:
        return None
    try:
        return float(v.replace(",", ".").replace("€", "").replace("$", "").replace("£", "").strip())
    except ValueError:
        return None


def read_feed(raw: bytes, network: str) -> Iterator[dict]:
    """Yield normalized rows from a raw feed file (CSV/TSV, optionally gzipped, or JSON)."""
    text = _open_text(raw)
    if network == "json" or text.lstrip().startswith(("{", "[")):
        data = json.loads(text)
        items = data.get("products", data) if isinstance(data, dict) else data
        for p in items:
            yield {"external_id": p["external_id"], "name": p["name"], "brand": p.get("brand", ""),
                   "merchant": p.get("merchant", ""), "program_id": p.get("program_id"),
                   "price": float(p["price"]), "currency": p.get("currency", "EUR"),
                   "url": p["url"], "image_url": p.get("image_url"),
                   "category_text": p.get("category", ""), "description": p.get("description", ""),
                   "gender": p.get("gender"), "rating": p.get("rating"),
                   "review_count": p.get("review_count", 0), "in_stock": "1",
                   "_category": p.get("category"), "_specs": p.get("specs"),
                   "_network": p.get("network")}
        return
    mapping = MAPPINGS.get(network, MAPPINGS["generic"])
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    for row in csv.DictReader(io.StringIO(text), dialect=dialect):
        out = {k: _pick(row, keys) for k, keys in mapping.items()}
        out["price"] = _float(out.get("price"))
        out["rating"] = _float(out.get("rating"))
        rc = _float(out.get("review_count"))
        out["review_count"] = int(rc) if rc else 0
        yield out
