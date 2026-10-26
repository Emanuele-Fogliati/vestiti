from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import get_settings

COOKIE_NAME = "session"
_ph = PasswordHasher()
# verified when the email is unknown, so a wrong email takes as long as a wrong password
_DUMMY_HASH = _ph.hash("not-a-real-password-just-for-timing")


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str | None) -> bool:
    if not hashed:
        try:
            _ph.verify(_DUMMY_HASH, pw)
        except Exception:
            pass
        return False
    try:
        return _ph.verify(hashed, pw)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def make_token(user_id: str, version: int = 0) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "ver": version, "iat": now, "exp": now + timedelta(days=s.session_days)}
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def read_token(token: str) -> tuple[str, int] | None:
    """(user id, session version) of a valid session cookie, else None."""
    try:
        data = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    sub, ver = data.get("sub"), data.get("ver", 0)
    if not isinstance(sub, str) or not isinstance(ver, int):
        return None
    return sub, ver


def new_link_token() -> tuple[str, str]:
    """A random token for an email link and the hash we store for it."""
    raw = secrets.token_urlsafe(32)
    return raw, link_token_hash(raw)


def link_token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def ua_hash(user_agent: str | None) -> str | None:
    if not user_agent:
        return None
    return hashlib.sha256(user_agent.encode()).hexdigest()[:32]


class RateLimiter:
    """Sliding window, in memory, per process. Good enough for one instance; use Redis
    when running more than one API replica."""

    SWEEP_EVERY = 1000  # calls between clean-ups of keys nobody used in the last window

    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self._calls = 0

    def _sweep(self, now: float, window_s: float) -> None:
        for k in [k for k, q in self._hits.items() if not q or now - q[-1] > window_s]:
            del self._hits[k]

    def allow(self, key: str, limit: int, window_s: float = 60.0) -> bool:
        now = time.monotonic()
        with self._lock:
            self._calls += 1
            if self._calls % self.SWEEP_EVERY == 0:
                self._sweep(now, window_s)  # otherwise one key per IP/email stays forever
            q = self._hits[key]
            while q and now - q[0] > window_s:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True


limiter = RateLimiter()
