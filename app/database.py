from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings

# Async engine for FastAPI
async_engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)

# Sync engine for Celery workers
_sync_url = settings.database_url.replace("+asyncpg", "")
sync_engine = create_engine(_sync_url, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(sync_engine)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    from app import models  # noqa: F401 — registers ORM classes
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
