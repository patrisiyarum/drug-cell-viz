"""Shared test fixtures.

Pin the database to an in-memory SQLite DB and initialise it once per
session so tests that hit the DB (streaming analysis endpoint, etc.) work
without needing a running Postgres.

Tests that only exercise service functions (most of the suite) don't care
about this — the env var is set before api.config imports.
"""

from __future__ import annotations

import os

# Must run before any `from api.config import settings` — pydantic-settings
# reads the env once at import time.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("PUBLIC_BASE_URL", "http://test.invalid")

import pytest_asyncio  # noqa: E402


@pytest_asyncio.fixture(autouse=True, scope="session")
async def _init_test_db():
    from api.db import init_db

    await init_db()
    yield
