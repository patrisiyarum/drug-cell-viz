from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from api.config import settings

engine: AsyncEngine = create_async_engine(settings.database_url, echo=False, future=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    # Import models so their tables register on SQLModel.metadata.
    from api import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def check_db() -> bool:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
