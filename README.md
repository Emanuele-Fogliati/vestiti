# Layerkit (working name)

Free travel outfit planner. You describe a trip; it reads the weather at every stop,
works out the layers you need (worn, at stops, in the pack), and shows the exact pieces
at three budgets, reusing what you already own. Shop links are affiliate links; the
user never pays.

> The name, domain and design are placeholders. Brand name, tagline and theme are
> environment variables (`BRAND_NAME`, `THEME`), so changing them needs no code change.

## Avvio rapido (Windows + Docker Desktop)

1. Installa e apri **Docker Desktop**.
2. (Facoltativo, per l'AI) Installa **Ollama** da https://ollama.com e scarica il modello:
   `ollama pull hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M` — dettagli in [docs/AI_SETUP.md](docs/AI_SETUP.md).
3. In PowerShell, nella cartella del progetto:
   ```powershell
   copy .env.example .env
   docker compose up --build
   ```
4. Apri http://localhost:8000

Senza Ollama l'app funziona lo stesso: il piano è calcolato da regole fisse, l'AI serve
solo a leggere l'itinerario scritto a parole e a spiegare il piano.

Per avere un account admin (statistiche click, import feed), metti in `.env`:
`ADMIN_EMAIL`, `ADMIN_PASSWORD` e `ADMIN_EMAILS=["la-tua@email"]`, poi riavvia.

## What's in it

| Area | What it does |
|---|---|
| Itinerary | Stops with dates, elevation and activities (city, hiking easy→technical, trek, beach, ski, cycling, safari, boat / kayak / rafting, desert & dunes; a "glacier" flag for walking on ice with crampons). "Don't know yet" plans for both the easy and the hard version. Add, edit, reorder, remove stops at any time. Free-text input ("4 days hard hiking in El Chaltén up to 1200 m, then…") parsed by the local AI, with a rule-based fallback (EN/IT). Whole agency programs up to 50,000 characters ("Giorno 1…15"): days in the same place are merged into one stop, and activities and altitudes are kept only when the text backs them. |
| Weather | Open-Meteo forecast (≤ 15 days), observed weather (past dates), or 5-year climate for the same dates. Altitude lapse rate and wind. Cached in the DB. Rough offline estimate if the service is down, clearly labelled. |
| Layer strategy | Heat-balance (clo) model per stage, moving vs. at rest. Cross-section of the layers, a stage × layer matrix (worn / at stops / in pack / not needed), a clickable "why" for every cell, warmth check and the cheapest upgrade when short. See [docs/LAYER_MODEL.md](docs/LAYER_MODEL.md). |
| Kit | Cheap / medium / premium tiers with totals. 1–5 fit stars per product, spec rows, swap any piece (search by brand, sort by price, warmth, weight, waterproofing, rating), skip, use your own, or rent. |
| Wardrobe | What you own is used first in every tier, at zero cost, with an honest "this is fine" or "this falls short". |
| Affiliates | Outbound links go through `/api/go/…`: click logged, tracking added per network (Amazon, Awin, Impact, CJ, AvantLink). Feed import (CSV/TSV/gz/JSON) with automatic slot classification. Rental partners. See [docs/AFFILIATES.md](docs/AFFILIATES.md). |
| Accounts | Start as a guest, upgrade to a free account and keep everything. Data export and deletion (GDPR). |
| AI | Any OpenAI-compatible server, local by default (Ollama + Qwen3 from Unsloth). Used only for parsing, explaining and answering. See [docs/AI_SETUP.md](docs/AI_SETUP.md). |
| Admin | Click stats by network, top products, affiliate status, feed import. |

## Stack

- **Backend**: Python 3.13, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16.
- **Frontend**: React 19, React Router 7, Vite, TypeScript. Themes are CSS tokens in
  `frontend/src/theme/tokens.css` (`yellow-black`, `cobalt`, `ember`).
- **One container** serves the API and the built frontend; Postgres runs next to it.

```
backend/
  app/engine/      thermal model, layer strategy, fit stars, tiers (pure Python, no I/O)
  app/weather/     Open-Meteo client, climate, cache, geocoding
  app/llm/         OpenAI-compatible client, itinerary parser, explanations
  app/catalog/     feed parsing, slot classifier, ingestion, seed
  app/affiliates/  per-network link building
  app/api/         HTTP routes
  alembic/         DB migrations
  seed/            sample catalog (169 products), places, placeholder rental partners
  tests/           pytest
frontend/src/
  pages/ components/ lib/ theme/
docs/
```

## Local development (without Docker)

```bash
# Postgres running locally, then:
cd backend
python -m venv .venv && . .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+psycopg://vestiti:vestiti@localhost:5432/vestiti
python -m app.cli migrate && python -m app.cli seed
uvicorn app.main:app --reload                       # http://localhost:8000/docs

cd ../frontend
npm ci
npm run dev                                         # http://localhost:5173 (proxies /api)
```

Tests:

```bash
cd backend && python -m pytest        # SQLite, no network needed
cd frontend && npm test && npm run build
```

CLI (`python -m app.cli …`, or `docker compose exec app python -m app.cli …`):
`migrate`, `seed`, `ingest --network awin --file feed.csv.gz`, `create-admin`, `check-ai`.

## Before a public launch

Read [docs/LAUNCH_CHECKLIST.md](docs/LAUNCH_CHECKLIST.md). Short version: weather API
licence, real affiliate accounts and feeds, real rental partners, legal review, password
reset email, and validating the warmth model on real trips.
