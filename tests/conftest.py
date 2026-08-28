import os
import subprocess
import sys

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from data.models import Base

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest_asyncio.fixture
async def db_session():
    """In-memory SQLite (та же схема, что в проде). Каждый тест — чистая база."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


# --- PostgreSQL-интеграция (маркер pg) ---

PG_TEST_TABLES = (
    "users, categories, products, cart_items, orders, order_items, "
    "order_events, ai_chat_history, ai_llm_calls"
)


@pytest.fixture(scope="session")
def pg_migrations():
    """Сбрасывает схему и применяет миграции alembic до head на PostgreSQL.

    Запускается ОТДЕЛЬНЫМ процессом (subprocess): alembic env.py использует
    asyncio.run, который нельзя звать внутри работающего event loop pytest'а.
    Требуется PG_TEST_URL (например postgresql+asyncpg://postgres@127.0.0.1:55432/delivery_test).
    Защита от случайного запуска на не-тестовой базе: в имени БД должно быть «test».
    """
    url = os.environ.get("PG_TEST_URL", "")
    if not url:
        pytest.skip("PG_TEST_URL не задан — нужен PostgreSQL (см. докстринг test_pg_integration.py)")
    dbname = url.rstrip("/").rsplit("/", 1)[-1].split("?", 1)[0]
    assert "test" in dbname.lower(), "имя тестовой БД должно содержать 'test'"
    env = dict(os.environ, DB_URL=url)
    # 1) чистая схема (DROP/CREATE) — отдельный процесс, чтобы не зависеть от psql в PATH.
    #    asyncpg-клиенту нужен чистый DSN, без '+asyncpg' в схеме (это SQLAlchemy-нотация).
    dsn = url.replace("postgresql+asyncpg://", "postgresql://")
    subprocess.run(
        [sys.executable, "-c",
         "import asyncio, asyncpg, os\n"
         "async def m():\n"
         "    c = await asyncpg.connect(os.environ['PG_DSN'])\n"
         "    await c.execute('DROP SCHEMA public CASCADE')\n"
         "    await c.execute('CREATE SCHEMA public')\n"
         "    print('schema reset OK')\n"
         "    await c.close()\n"
         "asyncio.run(m())"],
        cwd=REPO_ROOT, env={**env, "PG_DSN": dsn}, check=True, timeout=120,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    # 2) миграции 0001..0005 через alembic CLI (env.py берёт URL из DB_URL)
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=REPO_ROOT, env=env, check=True, timeout=300,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return url


@pytest_asyncio.fixture
async def pg_engine(pg_migrations):
    """Движок к свежемигрированной PG-базе.

    Function-scope: pytest-asyncio создаёт новый event loop на каждый тест,
    а asyncpg-соединения привязаны к loop — сессионный движок «протухал» бы.
    """
    engine = create_async_engine(pg_migrations)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_engine):
    """Сессия на свежемигрированной PG-базе; после теста — TRUNCATE всех таблиц."""
    maker = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    async with pg_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {PG_TEST_TABLES} RESTART IDENTITY"))