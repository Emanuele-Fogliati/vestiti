import hashlib

from fastapi import APIRouter, Request, Response

from app import globe

router = APIRouter(prefix="/api/globe", tags=["globe"])


@router.get("/places")
def places(request: Request):
    """Every place for the globe in one compact, cacheable response (rows, not objects)."""
    raw, gz = globe.payload_bytes()
    # revalidated on every load, so new landmark scenes reach the globe at once (304 when unchanged)
    tag = '"' + hashlib.sha1(raw).hexdigest()[:16] + '"'
    headers = {"Cache-Control": "no-cache", "ETag": tag, "Vary": "Accept-Encoding"}
    if request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers=headers)
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(gz, media_type="application/json", headers={**headers, "Content-Encoding": "gzip"})
    return Response(raw, media_type="application/json", headers=headers)
