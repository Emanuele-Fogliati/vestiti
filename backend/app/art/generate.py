"""Illustrations for places the hand-drawn library does not cover, made by an image model.

Pipeline for one place:
  1. the local LLM names the place's most recognizable sight (fallback: the place name),
  2. ComfyUI renders it with FLUX.1-schnell in the app's flat poster style (768x512),
  3. the raw image is stored once in `place_art`; every trip that visits the same place reuses it,
  4. when served, it is gradient-mapped onto the theme's --il-* palette, so it sits next to the
     vector scenes (dark -> --il-near, light -> --il-sky, the yellow sun -> --il-sun).

Generation runs on one background thread per process, never inside a page request. With
ART_IMAGE_ENABLED=false (production, no GPU) the app only serves images already in the database.
"""
from __future__ import annotations

import hashlib
import io
import logging
import queue
import random
import re
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PlaceArt

log = logging.getLogger(__name__)

STYLE = ("flat vector illustration, minimalist editorial travel poster, simple geometric shapes, "
         "large solid flat colour areas, clean edges, light grey sky with one small yellow sun, "
         "wide landscape composition, no text, no letters, no people, no frame")
NEGATIVE = "photo, photorealistic, text, watermark, signature, people, crowd, frame, border"

# --il-* tokens of each theme (frontend/src/theme/tokens.css). Keep in sync when a theme changes.
PALETTES = {
    "yellow-black": {"near": "#141414", "mid": "#6B6B63", "far": "#C6C6BD", "sky": "#EDEDE6", "sun": "#FFD60A"},
    "cobalt": {"near": "#17215A", "mid": "#5770D6", "far": "#B5C4F4", "sky": "#E4EBFF", "sun": "#FFB070"},
    "ember": {"near": "#1B2330", "mid": "#4E6278", "far": "#A7BDD0", "sky": "#D9E8F5", "sun": "#FF6B3D"},
}
PENDING_STALE = timedelta(minutes=15)  # a pending row older than this was lost (restart): retry
RETRY_AFTER = timedelta(hours=1)
MAX_ATTEMPTS = 3


def _norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def place_key(name: str, country_code: str | None, lat: float, lon: float) -> str:
    """Same place, same key: name + country + coordinates rounded to ~10 km."""
    raw = f"{_norm(name)}|{(country_code or '').upper()}|{round(lat, 1):.1f}|{round(lon, 1):.1f}"
    return hashlib.sha1(raw.encode()).hexdigest()[:24]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d: datetime | None) -> datetime:
    if d is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------ what to draw

SUBJECT_SYSTEM = (
    "You choose what a small travel illustration of a place shows. Pick the single most "
    "recognizable sight of the place: a landmark building, a famous natural feature, or for a "
    "small town the landscape around it. Answer only JSON: "
    '{"subject": "short name of the sight, in English", '
    '"visual": "one sentence in English describing only the shapes to draw: the sight, its '
    'setting, the landscape. No people, no text, no style words."}')


def pick_subject(name: str, country_code: str | None) -> tuple[str, str]:
    """(subject, visual) for the place. Falls back to the place name when the LLM is off."""
    where = f"{name} ({country_code})" if country_code else name
    try:
        from app.llm.client import LLMClient
        d = LLMClient().chat_json(SUBJECT_SYSTEM, f"Place: {where}", max_tokens=200, timeout=60)
        subject = str(d.get("subject") or "").strip()[:120]
        visual = str(d.get("visual") or "").strip()[:400]
        if subject and visual:
            return subject, visual
    except Exception as e:  # LLM off or unreachable: still draw something sensible
        log.info("subject for %s from fallback: %s", where, e)
    return name, f"the most famous landmark and landscape of {where}"


def build_prompt(visual: str) -> str:
    return f"{visual.rstrip('. ')}. {STYLE}"


# ------------------------------------------------------------------ ComfyUI

def workflow(prompt: str, seed: int, width: int = 768, height: int = 512) -> dict:
    """FLUX.1-schnell, single-file fp8 checkpoint (UNet + CLIP + T5 + VAE), 4 steps, no CFG."""
    s = get_settings()
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": s.art_image_checkpoint}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["1", 1]}},
        "4": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
            "seed": seed, "steps": s.art_image_steps, "cfg": 1.0, "sampler_name": "euler",
            "scheduler": "simple", "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "vestiti"}},
    }


class ImageUnavailable(RuntimeError):
    pass


def comfy_generate(prompt: str, seed: int, transport: httpx.BaseTransport | None = None,
                   poll_s: float = 1.0) -> bytes:
    """Queue the workflow on ComfyUI, wait for it, return the PNG bytes."""
    s = get_settings()
    deadline = time.monotonic() + s.art_image_timeout_s
    try:
        with httpx.Client(base_url=s.art_image_url.rstrip("/"), timeout=30, transport=transport,
                          trust_env=False) as c:
            r = c.post("/prompt", json={"prompt": workflow(prompt, seed), "client_id": "vestiti"})
            r.raise_for_status()
            pid = r.json()["prompt_id"]
            while time.monotonic() < deadline:
                h = c.get(f"/history/{pid}")
                h.raise_for_status()
                job = h.json().get(pid)
                if job:
                    st = job.get("status") or {}
                    if st.get("status_str") == "error":
                        raise ImageUnavailable(f"ComfyUI error: {st.get('messages')}"[:500])
                    imgs = [i for out in (job.get("outputs") or {}).values() for i in out.get("images", [])]
                    if imgs:
                        i = imgs[0]
                        v = c.get("/view", params={"filename": i["filename"], "subfolder": i.get("subfolder", ""),
                                                  "type": i.get("type", "output")})
                        v.raise_for_status()
                        return v.content
                time.sleep(poll_s)
    except ImageUnavailable:
        raise
    except Exception as e:
        raise ImageUnavailable(f"{e.__class__.__name__}: {e}"[:500]) from e
    raise ImageUnavailable("timed out waiting for ComfyUI")


def status() -> dict:
    s = get_settings()
    if not s.art_image_enabled:
        return {"enabled": False, "available": False, "url": s.art_image_url}
    try:
        with httpx.Client(timeout=3, trust_env=False) as c:
            ok = c.get(s.art_image_url.rstrip("/") + "/system_stats").status_code == 200
    except Exception:
        ok = False
    return {"enabled": True, "available": ok, "url": s.art_image_url, "checkpoint": s.art_image_checkpoint}


# ------------------------------------------------------------------ palette

def _hex(h: str):
    import numpy as np
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float)


def tone(raw: bytes, theme: str) -> bytes:
    """Gradient-map the image onto the theme's illustration palette. Returns WebP bytes."""
    import numpy as np
    from PIL import Image

    pal = PALETTES.get(theme, PALETTES["yellow-black"])
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    a = np.asarray(im, float)
    lum = (0.3 * a[..., 0] + 0.59 * a[..., 1] + 0.11 * a[..., 2]) / 255
    lo, hi = np.percentile(lum, 2), np.percentile(lum, 98)
    lum = np.clip((lum - lo) / max(hi - lo, 1e-3), 0, 1)
    sky = _hex(pal["sky"])
    stops = [(0.0, _hex(pal["near"])), (0.42, _hex(pal["mid"])), (0.78, _hex(pal["far"])),
             (0.93, sky), (1.0, sky + (255 - sky) * 0.4)]
    out = np.zeros_like(a)
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        m = (lum >= p0) & (lum <= p1)
        t = ((lum - p0) / (p1 - p0))[..., None]
        out = np.where(m[..., None], c0 * (1 - t) + c1 * t, out)
    # only a clearly yellow/orange, bright, saturated area (the sun) keeps the accent colour
    hsv = np.asarray(im.convert("HSV"), float) / 255
    hue, sat, val = hsv[..., 0] * 360, hsv[..., 1], hsv[..., 2]
    w = np.clip((sat - 0.6) / 0.15, 0, 1) * np.clip((val - 0.6) / 0.15, 0, 1) * ((hue > 30) & (hue < 60))
    out = out * (1 - w[..., None]) + _hex(pal["sun"]) * w[..., None]
    buf = io.BytesIO()
    Image.fromarray(out.astype("uint8")).save(buf, "WEBP", quality=82, method=4)
    return buf.getvalue()


@lru_cache(maxsize=256)
def _toned(key: str, updated: str, theme: str, raw: bytes) -> bytes:  # updated busts the cache on regen
    return tone(raw, theme)


def toned_image(row: PlaceArt, theme: str) -> bytes:
    return _toned(row.key, str(row.updated_at), theme if theme in PALETTES else "yellow-black", row.image)


def to_webp(png: bytes) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.open(io.BytesIO(png)).convert("RGB").save(buf, "WEBP", quality=90, method=4)
    return buf.getvalue()


# ------------------------------------------------------------------ queue

_jobs: "queue.Queue[str]" = queue.Queue()
_worker: threading.Thread | None = None
_lock = threading.Lock()


def _ensure_worker():
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run, name="place-art", daemon=True)
            _worker.start()


def _run():
    from app.db import SessionLocal
    while True:
        key = _jobs.get()
        try:
            with SessionLocal() as db:
                generate(db, key)
        except Exception:
            log.exception("place art %s failed", key)


def generate(db: Session, key: str, transport: httpx.BaseTransport | None = None) -> PlaceArt | None:
    """Make the image for one row now (blocking). Used by the worker and by the CLI."""
    row = db.get(PlaceArt, key)
    if row is None:
        return None
    row.status, row.updated_at = "pending", _now()
    db.commit()
    try:
        if not row.subject or not row.prompt:
            subject, visual = pick_subject(row.name, row.country_code)
            row.subject, row.prompt = subject, build_prompt(visual)
            db.commit()
        seed = random.Random(key).randrange(2**31) + row.attempts
        png = comfy_generate(row.prompt, seed, transport=transport)
        row.image, row.status, row.error = to_webp(png), "ready", None
    except Exception as e:
        row.status, row.error = "failed", str(e)[:1000]
        log.warning("place art for %s failed: %s", row.name, e)
    row.attempts += 1
    row.updated_at = _now()
    db.commit()
    return row


def request(db: Session, name: str, country_code: str | None, lat: float, lon: float,
            enqueue: bool = True) -> PlaceArt | None:
    """The cached illustration for a place, queuing it when it is missing and generation is on.

    Returns the row (status ready / pending / failed) or None when there is nothing and nothing
    will come (generation off)."""
    s = get_settings()
    key = place_key(name, country_code, lat, lon)
    row = db.get(PlaceArt, key)
    if row is not None and row.status == "ready":
        return row
    if not s.art_image_enabled:
        return row if row is not None and row.status == "ready" else None
    now = _now()
    if row is None:
        row = PlaceArt(key=key, name=name.strip()[:200], country_code=(country_code or None) and country_code.upper(),
                       latitude=lat, longitude=lon, status="pending", attempts=0, updated_at=now)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:  # another process queued it a moment ago
            db.rollback()
            return db.get(PlaceArt, key)
    elif row.status == "pending" and now - _aware(row.updated_at) < PENDING_STALE:
        return row
    elif row.status == "failed" and (row.attempts >= MAX_ATTEMPTS or now - _aware(row.updated_at) < RETRY_AFTER):
        return row
    else:
        row.status, row.updated_at = "pending", now
        db.commit()
    if enqueue:
        _jobs.put(key)
        _ensure_worker()
    return row
