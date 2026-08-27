"""Подключение к БД: async-движок и фабрика сессий."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_engine = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def init_db(url: str) -> None:
    """Создаёт движок и фабрику сессий (вызывается один раз при старте бота)."""
    global _engine, _session_maker
    _engine = create_async_engine(url, pool_pre_ping=True)
    _session_maker = async_sessionmaker(_engine, expire_on_commit=False)


async def dispose_db() -> None:
    if _engine is not None:
        await _engine.dispose()


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    assert _session_maker is not None, "init_db() не вызван"
    return _session_maker