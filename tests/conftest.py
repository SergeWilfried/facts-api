import asyncio

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings
from app.database import Base, get_db
from app.main import app

TEST_DB_URL = settings.database_url.replace("/kaseto", "/kaseto_test")
_test_engine = create_async_engine(TEST_DB_URL, echo=False)
_TestSession = async_sessionmaker(_test_engine, expire_on_commit=False)

_TABLES = ["sources", "claims", "checks", "users"]


# ---------------------------------------------------------------------------
# Session-scoped: create schema once per test run
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    from app import models  # noqa: registers ORM classes

    async def _setup():
        async with _test_engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        # Dispose pool so asyncpg connections from this event loop aren't
        # reused by the per-test event loops that pytest-asyncio creates.
        await _test_engine.dispose()

    asyncio.run(_setup())
    yield
    asyncio.run(_test_engine.dispose())


# ---------------------------------------------------------------------------
# Per-test: wipe tables at the START of each test so teardown never
# competes with open asyncpg connections
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def _clean_state():
    tables = ", ".join(_TABLES)
    async with _test_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    yield


# ---------------------------------------------------------------------------
# Per-test: a committed session for direct test setup (inserts visible to app)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _TestSession() as session:
        yield session


# ---------------------------------------------------------------------------
# Per-test: FastAPI client; each request gets its own session from the pool
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client() -> AsyncClient:
    async def _override():
        async with _TestSession() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Convenience: registered user + bearer auth headers
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    resp = await client.post(
        "/auth/register",
        json={"email": "fixture@kaseto.test", "password": "StrongPass1!"},
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
