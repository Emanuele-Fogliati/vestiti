from fastapi import APIRouter, Request, Response

from app import globe

router = APIRouter(prefix="/api/globe", tags=["globe"])


@router.get("/places")
def places(request: Request):
    """Every place for the globe in one compact, cacheable response (rows, not objects)."""
    raw, gz = globe.payload_bytes()
    headers = {"Cache-Control": "public, max-age=3600", "Vary": "Accept-Encoding"}
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(gz, media_type="application/json", headers={**headers, "Content-Encoding": "gzip"})
    return Response(raw, media_type="application/json", headers=headers)
