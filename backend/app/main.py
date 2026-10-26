import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, ai, art, auth, globe, go, inspire, meta, plans, profile, trips, wardrobe
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()

# Anyone who knows the signing key can sign in as any user: refuse the known placeholders.
WEAK_KEYS = {"dev-only-change-me", "change-me-to-a-long-random-string", "change-me", "secret"}
if settings.is_production and (settings.secret_key in WEAK_KEYS or len(settings.secret_key) < 32):
    raise RuntimeError("Set SECRET_KEY to a long random value in production "
                       "(python -c \"import secrets; print(secrets.token_urlsafe(48))\")")
if settings.is_production and not settings.cookie_secure:
    logging.getLogger(__name__).warning("COOKIE_SECURE=false in production: the session cookie "
                                        "also travels over plain http")

# the interactive API docs list every endpoint: handy in development, not needed in production
app = FastAPI(title=f"{settings.brand_name} API", version="0.1.0",
              docs_url=None if settings.is_production else "/api/docs",
              redoc_url=None,
              openapi_url=None if settings.is_production else "/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
# Paths with their own, larger upload cap (checked in the endpoint)
BIG_BODY_PATHS = ("/api/admin/feeds/import",)
# The page loads only our own scripts; images can come from shops' CDNs (product photos).
CSP = ("default-src 'self'; script-src 'self'; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' data: https://fonts.gstatic.com; img-src 'self' data: https:; "
       # maps (MapLibre): vector tiles and fonts from OpenFreeMap, relief from AWS terrain
       # tiles, and a worker the library starts from a blob: URL
       "connect-src 'self' https://tiles.openfreemap.org https://s3.amazonaws.com; "
       "worker-src 'self' blob:; child-src 'self' blob:; "
       "object-src 'none'; base-uri 'self'; form-action 'self'; "
       "frame-ancestors 'none'")


class BodyLimit:
    """Refuse request bodies over MAX_BODY_BYTES before they are read into memory. Without
    it one request with a huge JSON body (or a 100 MB 'password') ties up a worker."""

    def __init__(self, app, max_bytes: int):
        self.app, self.max = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"].startswith(BIG_BODY_PATHS):
            return await self.app(scope, receive, send)
        for k, v in scope.get("headers") or []:
            if k == b"content-length" and v.isdigit() and int(v) > self.max:
                return await JSONResponse({"detail": "Request body too large"}, 413)(scope, receive, send)
        seen, over, replaced = 0, False, False

        async def limited():
            nonlocal seen, over
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > self.max:  # chunked upload with no Content-Length
                    over = True
                    raise HTTPException(413, "Request body too large")
            return msg

        async def guarded_send(msg):
            # the app turns the failed read into its own error page: answer 413 instead
            nonlocal replaced
            if over and msg["type"] == "http.response.start":
                replaced = True
                too_big = JSONResponse({"detail": "Request body too large"}, 413)
                await send({"type": "http.response.start", "status": 413,
                            "headers": too_big.raw_headers})
                await send({"type": "http.response.body", "body": too_big.body})
                return
            if not replaced:
                await send(msg)

        return await self.app(scope, limited, guarded_send)


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
    if resp.headers.get("content-type", "").startswith("text/html"):
        resp.headers.setdefault("Content-Security-Policy", CSP)
    if settings.cookie_secure:  # served over https: tell browsers to never use http again
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return resp


app.add_middleware(BodyLimit, max_bytes=settings.max_body_bytes)


for r in (meta.router, auth.router, trips.router, wardrobe.router, plans.router, ai.router,
          go.router, admin.router, art.router, profile.router, inspire.router, globe.router):
    app.include_router(r)

# Optional: serve the built frontend from the same process (single-container deploys).
STATIC_DIR = Path(os.environ.get("STATIC_DIR", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if STATIC_DIR.is_dir() and (STATIC_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "Not found")  # a wrong API path is an error, not the page
        f = STATIC_DIR / full_path
        if full_path and f.is_file() and STATIC_DIR in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(STATIC_DIR / "index.html")
