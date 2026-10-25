# Affiliate links, feeds and rentals

## How a click works

Every Buy / Rent button points to our own URL:

- `/api/go/product/{product_id}?trip_id=…&tier=…&slot=…`
- `/api/go/rental/{partner_id}?slot=…&start=…&end=…&country=…`

The server logs the click (network, tier, slot, price, hashed browser type, no IP),
builds the tracked link for the product's network and answers with a 302 redirect.
Destinations come only from the database, so the endpoint can't be used as an open
redirect.

If a network is not configured, the link still works but is **untracked** (no commission).
The admin page shows which networks are configured and how many clicks were untracked.

## Networks

| Network | Env var | Link built |
|---|---|---|
| Amazon Associates | `AMAZON_ASSOCIATE_TAG`, `AMAZON_DOMAIN` | adds `tag=` and `ascsubtag=<click id>` |
| Awin | `AWIN_PUBLISHER_ID` | `awin1.com/cread.php?awinmid=<merchant>&awinaffid=…&clickref=<click id>&ued=<url>` |
| Impact | `IMPACT_ACCOUNT_SID` | feed URLs are already tracking links; adds `subId1=<click id>` |
| CJ | `CJ_PUBLISHER_ID` | `anrdoezrs.net/links/<pid>/type/dlg/sid/<click id>/<url>` |
| AvantLink | `AVANTLINK_AFFILIATE_ID` | `avantlink.com/click.php?…&ctc=<click id>&url=<url>` |

Adding a network = one class in `backend/app/affiliates/networks.py` plus a column
mapping in `backend/app/catalog/feeds.py`.

The click id passed as sub-id lets you reconcile commissions with clicks later. There is
no automatic commission import yet (see the launch checklist).

## Tours, excursions and group trips (ready-made itineraries)

The "Ideas" pages (`/ideas`, data in `backend/app/inspire/itineraries/*.json`) earn from
two kinds of links, both logged in `affiliate_clicks` like the clothes:

| Link | Endpoint | Network | Env vars | Typical commission (check when you sign up) |
|---|---|---|---|---|
| A tour at one stop | `/api/go/excursion/{itinerary}/{stop}/{n}?provider=getyourguide\|viator` | `getyourguide`, `viator` | `GETYOURGUIDE_PARTNER_ID`; `VIATOR_PID` + `VIATOR_MCID` | about 8% (GetYourGuide), 4-8% (Viator), 30-day cookie |
| A whole organised trip | `/api/go/tour/{itinerary}/{n}` | per trip in the JSON (`network`, `program_id`) | the network's own var (e.g. `CJ_PUBLISHER_ID`, `AWIN_PUBLISHER_ID`) | about 4-6% of a ~2,500 € trip (Intrepid, G Adventures) |

- Excursion links open the marketplace's search for the words in the itinerary file
  (`excursions[].query`). GetYourGuide gets `partner_id` + `cmp=<click id>`; Viator gets
  `pid`, `mcid`, `medium=link`, `campaign=<click id>`.
- Group trips start as `"network": "direct"` (untracked). When a tour operator accepts you,
  set its `network` and `program_id` in the JSON; nothing else changes.
- Commissions are paid after the tour has taken place and was not cancelled.
- The tips ("Worth it" / "Skip") never depend on what pays: same honesty rule as the kit.

## Product feeds

Import from the admin page, or:

```bash
docker compose exec app python -m app.cli ingest --network awin --file /path/feed.csv.gz
```

Formats: CSV, TSV, gzip, or JSON (our seed format). Column mappings exist for `awin`,
`impact`, `cj`, `amazon` (our own export from the Product Advertising API) and `generic`
(our column names: `external_id, name, brand, merchant, program_id, price, currency,
url, image_url, category_text, description, gender, rating, review_count, in_stock`).

For each row we:
1. Skip kids' items, accessories, gear that isn't clothing.
2. Classify the slot from title + category (`catalog/classify.py`), e.g. "Gore-Tex jacket"
   → shell jacket.
3. Extract specs from the text: waterproof mm, breathability g/m²/24h, weight, fill power,
   material. Clo is estimated. Every guessed value is marked "estimated".
4. Upsert on (network, external id). Products missing from a new import of the same
   network are deactivated (turn off with `--keep-missing`).

Run feeds daily (cron or a scheduled task); prices drift.

## Sample catalog

`backend/seed/products.json`: 169 real product names from real brands, with **indicative
prices and approximate specs**, no images, and links to Amazon / Google Shopping
searches. It exists so the app works end to end on day one. Replace it with real feeds
before launch.

## Rental partners

`backend/seed/rental_partners.json`: 4 **placeholder** partners on example.com. Each has a
URL template (`{slot}`, `{start}`, `{end}`, `{days}`, `{country}`), the countries and
categories it covers and daily rates. Real partners need a deal and a real template.

## Disclosure

The app is free. The disclosure is shown in the footer, next to every Buy button and on
`/legal/affiliate`. Ranking never uses commission rates: only fit stars and price.
