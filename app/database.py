from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings


def _strip_sslmode(url: str) -> tuple[str, dict]:
    """Remove sslmode from URL query string and return (clean_url, connect_args)."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    sslmode = params.pop("sslmode", [None])[0]
    clean_query = urlencode({k: v[0] for k, v in params.items()})
    clean_url = urlunparse(parsed._replace(query=clean_query))
    connect_args = {"ssl": True} if sslmode else {}
    return clean_url, connect_args


_async_url, _async_connect_args = _strip_sslmode(settings.database_url)
async_engine = create_async_engine(_async_url, echo=False, connect_args=_async_connect_args)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)

# Sync engine for Celery workers
_sync_url, _sync_connect_args = _strip_sslmode(_async_url.replace("+asyncpg", ""))
sync_engine = create_engine(_sync_url, pool_pre_ping=True, connect_args=_sync_connect_args)
SyncSessionLocal = sessionmaker(sync_engine)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    from app import models  # noqa: F401 — registers ORM classes
    async with async_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
