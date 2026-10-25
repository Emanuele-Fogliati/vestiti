"""Test setup: a throwaway SQLite database, no network (weather and AI off)."""
import os
import tempfile

_DB = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_DB}",
    "WEATHER_ENABLED": "false",
    "LLM_ENABLED": "false",
    "SECRET_KEY": "test-secret-key-not-for-production-use-0123456789",
    "AUTH_RATE_LIMIT_PER_MINUTE": "1000",
    "AI_RATE_LIMIT_PER_MINUTE": "1000",
    "ADMIN_EMAILS": "[\"admin@example.com\"]",
    "ENVIRONMENT": "test",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.catalog.ingest import seed_all  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

H = {"X-Requested-With": "app"}


@pytest.fixture(scope="session", autouse=True)
def _database():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_all(db)
    yield


@pytest.fixture()
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture()
def client():
    with TestClient(app) as c:
        c.headers.update(H)
        yield c
