"""PG-интеграционные тесты (ARCHITECTURE_REVIEW P1: SQLite-тесты не покрывают PG).

Проверяется то, что SQLite не умеет/гарантирует:
- полный прогон миграций alembic 0001..0005 на PostgreSQL,
- настоящие уникальные/CHECK-констрейнты и каскады FK,
- timestamptz-логика TTL-чистки и лимита LLM-вызовов на PG.

Запуск (нужен локальный PostgreSQL; сервис или изолированный инстанс):
    $env:PG_TEST_URL="postgresql+asyncpg://postgres@127.0.0.1:55432/delivery_test"
    .venv\\Scripts\\python.exe -m pytest -m pg -q
Без PG_TEST_URL тесты пропускаются. ДЕФОЛТНЫЙ прогон (pytest -q) их не трогает.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from core.ai_memory import load_history, purge_history, push_history, try_llm_call
from core.cart import change_quantity
from core.ordering import create_order
from data.models import AiChatHistory, AiLlmCall, CartItem, Category, OrderItem, Product, User
from tests.test_ai_assistant import _settings

pytestmark = pytest.mark.pg

TZ = "Asia/Almaty"


async def _seed_base(pg_session) -> tuple[int, int]:
    """Пользователь + категория + плов (весовой, 3 кг) и манты; вернёт id продуктов."""
    user = User(tg_id=5935155979, first_name="Клиент")
    pg_session.add(user)
    cat = Category(name="Пловы", sort_order=0, is_active=True)
    pg_session.add(cat)
    await pg_session.flush()
    plov = Product(category_id=cat.id, name="Плов Факирский (3 кг)", price=15300, is_available=True, sort_order=0)
    manti = Product(category_id=cat.id, name="Манты (50 шт)", price=19500, is_available=True, sort_order=1)
    pg_session.add_all([plov, manti])
    await pg_session.commit()
    return plov.id, manti.id


def _scheduled(gap_days: int = 2) -> datetime:
    d = datetime.now(ZoneInfo(TZ)).date() + timedelta(days=gap_days)
    return datetime(d.year, d.month, d.day, 12, 0, tzinfo=ZoneInfo(TZ))


# --- Миграции ---


async def test_pg_migrations_up_to_head(pg_engine):
    async with pg_engine.connect() as conn:
        version = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
        tables = {
            r[0]
            for r in await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        }
    assert version == "0005", version
    expected = {
        "users", "categories", "products", "cart_items", "orders",
        "order_items", "order_events", "ai_chat_history", "ai_llm_calls",
    }
    assert expected <= tables, expected - tables


# --- Полный флоу заказа на PG ---


async def test_pg_full_order_flow(pg_session):
    plov, manti = await _seed_base(pg_session)
    await change_quantity(pg_session, 1, plov, 2)  # 2 порции из упаковки 3 кг
    await change_quantity(pg_session, 1, manti, 1)
    order = await create_order(
        pg_session,
        1,
        settings=_settings(),
        contact_name="Клиент",
        contact_phone="+77000000000",
        delivery_method="own",
        address="ул. Тестовая, 1",
        scheduled_for=_scheduled(),
        comment=None,
    )
    await pg_session.commit()
    rows = (await pg_session.execute(select(OrderItem).where(OrderItem.order_id == order.id))).all()
    items = [r[0] for r in rows]
    assert len(items) == 2
    plov_item = next(i for i in items if i.name.startswith("Плов"))
    assert plov_item.quantity == 2  # порции
    assert plov_item.product_grams == 3000  # снапшот веса упаковки
    assert plov_item.price == 15300
    assert order.prepay_amount == order.total * 50 // 100
    assert order.number


# --- PG-специфика: констрейнты и каскады ---


async def test_pg_unique_tg_id(pg_session):
    pg_session.add(User(tg_id=111, first_name="А"))
    await pg_session.flush()
    pg_session.add(User(tg_id=111, first_name="Б"))
    with pytest.raises(IntegrityError):
        await pg_session.commit()
    await pg_session.rollback()


async def test_pg_cart_quantity_check(pg_session):
    plov, _ = await _seed_base(pg_session)
    pg_session.add(CartItem(user_id=1, product_id=plov, quantity=0))
    with pytest.raises(IntegrityError):
        await pg_session.commit()
    await pg_session.rollback()


async def test_pg_cascade_delete_user(pg_session):
    plov, _ = await _seed_base(pg_session)
    pg_session.add(CartItem(user_id=1, product_id=plov, quantity=2))
    pg_session.add(AiChatHistory(user_id=1, role="user", text="привет"))
    pg_session.add(AiLlmCall(user_id=1))
    await pg_session.flush()
    user = await pg_session.get(User, 1)
    await pg_session.delete(user)
    await pg_session.commit()
    assert (await pg_session.scalars(select(CartItem))).all() == []
    assert (await pg_session.scalars(select(AiChatHistory))).all() == []
    assert (await pg_session.scalars(select(AiLlmCall))).all() == []


# --- TTL и лимит LLM на timestamptz ---


async def test_pg_ai_memory_ttl(pg_session):
    pg_session.add(User(tg_id=11, first_name="U"))
    await pg_session.commit()
    old = datetime.now().astimezone() - timedelta(hours=30)
    pg_session.add(AiChatHistory(user_id=1, role="user", text="старое", created_at=old))
    await pg_session.commit()
    await push_history(pg_session, 1, "user", "свежее", ttl_hours=24)  # ленивая чистка
    await pg_session.commit()
    assert [t for _, t in await load_history(pg_session, 1)] == ["свежее"]
    removed = await purge_history(pg_session, ttl_hours=24)
    await pg_session.commit()
    assert removed == 0  # старое уже удалено ленивой чисткой


async def test_pg_llm_quota(pg_session):
    u1 = User(tg_id=11, first_name="U1")
    u2 = User(tg_id=12, first_name="U2")
    pg_session.add_all([u1, u2])
    await pg_session.flush()
    # запись старше окна (2 часа) не занимает слот скользящего окна 60 минут
    pg_session.add(AiLlmCall(user_id=u1.id, created_at=datetime.now().astimezone() - timedelta(hours=2)))
    await pg_session.commit()
    assert await try_llm_call(pg_session, u1.id, limit=1, window_minutes=60) is True
    # лимит 2 за окно на «чистом» пользователе: два слота, третий отклоняется
    assert await try_llm_call(pg_session, u2.id, limit=2, window_minutes=60) is True
    assert await try_llm_call(pg_session, u2.id, limit=2, window_minutes=60) is True
    assert await try_llm_call(pg_session, u2.id, limit=2, window_minutes=60) is False
    await pg_session.commit()
    calls = (await pg_session.scalars(select(AiLlmCall))).all()
    assert len(calls) == 4  # 1 старая + 1 (u1) + 2 (u2); отклонённый не записан