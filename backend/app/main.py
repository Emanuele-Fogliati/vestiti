import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, ai, auth, go, meta, plans, profile, trips, wardrobe
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()

if settings.is_production and settings.secret_key == "dev-only-change-me":
    raise RuntimeError("Set SECRET_KEY in production")

app = FastAPI(title=f"{settings.brand_name} API", version="0.1.0",
              docs_url="/api/docs", openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def csrf_and_headers(request: Request, call_next):
    # Cookie auth + a custom header that browsers never send cross-site without CORS
    # approval = cheap, effective CSRF protection.
    if (request.method in UNSAFE and request.url.path.startswith("/api/")
            and request.headers.get("x-requested-with") != "app"
            and not request.headers.get("authorization")):
        return JSONResponse({"detail": "Missing X-Requested-With: app header"}, status_code=403)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    return resp


for r in (meta.router, auth.router, trips.router, wardrobe.router, plans.router, ai.router,
          go.router, admin.router, profile.router):
    app.include_router(r)

# Optional: serve the built frontend from the same process (single-container deploys).
STATIC_DIR = Path(os.environ.get("STATIC_DIR", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if STATIC_DIR.is_dir() and (STATIC_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        f = STATIC_DIR / full_path
        if full_path and f.is_file() and STATIC_DIR in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(STATIC_DIR / "index.html")
