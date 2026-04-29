"""Shared pytest fixtures.

Sets up an isolated SQLite test DB before any app modules are imported.
Schema is created with ``Base.metadata.create_all`` (alembic isn't great inside
pytest's running loop). This is safe because the schema we generate matches the
latest alembic migration.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Set env BEFORE importing any app code.
_db_path = Path(tempfile.gettempdir()) / "taxflow_test.db"
if _db_path.exists():
    _db_path.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_db_path}"
os.environ["JWT_SECRET"] = "test-secret-32-bytes-padding-aaaaa"
os.environ["APP_ENV"] = "dev"
os.environ["APP_DEBUG"] = "false"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _initialize_db():
    """Create schema + seed once per test session."""
    from app.db import Base, engine
    from app import models  # noqa: F401  populate metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    from app.scripts.seed import main as seed_main

    await seed_main()
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def http():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_headers(http: AsyncClient):
    r = await http.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "admin1234!"},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
