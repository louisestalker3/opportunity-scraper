import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings

# Celery workers spin up a new event loop per task, so connection pooling
# causes connections to leak across loop boundaries. NullPool creates a fresh
# connection per-use and closes it immediately, avoiding exhaustion.
_is_worker = os.environ.get("CELERY_WORKER", "false").lower() == "true"

engine = create_async_engine(
    settings.database_url,
    echo=settings.is_development,
    pool_pre_ping=True,
    **({} if _is_worker else {"pool_size": 10, "max_overflow": 20}),
    **({"poolclass": NullPool} if _is_worker else {}),
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
