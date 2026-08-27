from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from config.settings import Settings
from core.cart import change_quantity
from core.ordering import (
    OrderError,
    build_scheduled,
    create_order,
    earliest_allowed,
    get_order,
    suggested_days,
    transition,
    validate_schedule,
)
from data.models import Category, Product

TZ = "Asia/Almaty"


def _settings(**kw) -> Settings:
    defaults = dict(
        bot_token="test",
        admin_ids="",
        db_url="sqlite+aiosqlite:///:memory:",
        min_order_amount=20_000,
        prepay_percent=50,
        large_order_threshold=60_000,
        default_lead_minutes=60 * 24,
        large_order_lead_hours=48,
        dish_deposit_amount=10_000,
        app_tz=TZ,
    )
    defaults.update(kw)
    return Settings(_env_file=None, **defaults)


async def _seed(session):
    category = Category(name="Пловы", sort_order=0, is_active=True)
    session.add(category)
    await session.flush()
    plov = Product(category_id=category.id, name="Плов", price=1800, is_available=True, sort_order=0)
    manti = Product(category_id=category.id, name="Манты", price=2500, is_available=True, sort_order=1)
    session.add_all([plov, manti])
    await session.commit()
    return plov.id, manti.id


async def _fill_cart(session, plov_id, manti_id, plov_qty=10, manti_qty=1) -> int:
    """Наполняет корзину (user_id=1) до суммы ≥ мин. заказа. Возвращает сумму."""
    await change_quantity(session, 1, plov_id, plov_qty)
    await change_quantity(session, 1, manti_id, manti_qty)
    return plov_qty * 1800 + manti_qty * 2500


def _scheduled(days: int = 2, hour: int = 12, minute: int = 0) -> datetime:
    """Будущее время внутри рабочего окна 10:00–20:00 — не зависит от времени суток."""
    d = datetime.now(ZoneInfo(TZ)).date() + timedelta(days=days)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=ZoneInfo(TZ))


async def test_create_order_ok(db_session):
    plov, manti = await _seed(db_session)
    total = await _fill_cart(db_session, plov, manti)
    settings = _settings()
    order = await create_order(
        db_session,
        1,
        settings=settings,
        contact_name="Пыленок",
        contact_phone="+7 700 000 00 00",
        delivery_method="own",
        address="ул. Лермонтова, 12",
        scheduled_for=_scheduled(),
        comment="Без перца",
    )
    assert order.status == "created"
    assert order.number == f"{order.scheduled_for:%Y%m%d}-{order.id}"
    assert order.items_total == total
    assert order.total == total
    assert order.prepay_amount == total * 50 // 100
    # снапшоты позиций
    from data.models import OrderItem

    items = list(
        await db_session.scalars(
            select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)
        )
    )
    assert len(items) == 2
    assert items[0].name == "Плов"
    assert items[0].price == 1800
    # корзина очищена
    from core.cart import get_cart_view

    view = await get_cart_view(db_session, 1)
    assert view.rows == []


async def test_create_order_min_amount(db_session):
    plov, manti = await _seed(db_session)
    await change_quantity(db_session, 1, plov, 1)  # 1800 < 20000
    with pytest.raises(OrderError, match="Минимальный заказ"):
        await create_order(
            db_session, 1,
            settings=_settings(),
            contact_name="А", contact_phone="+77000000000",
            delivery_method="own", address="ул. 1",
            scheduled_for=_scheduled(26), comment=None,
        )


async def test_create_order_blocks_unavailable(db_session):
    plov, manti = await _seed(db_session)
    await change_quantity(db_session, 1, plov, 15)  # достаточно по сумме
    product = await db_session.get(Product, plov)
    product.is_available = False
    await db_session.commit()
    with pytest.raises(OrderError, match="наличии"):
        await create_order(
            db_session, 1,
            settings=_settings(),
            contact_name="А", contact_phone="+77000000000",
            delivery_method="own", address="ул. 1",
            scheduled_for=_scheduled(26), comment=None,
        )


async def test_validate_schedule_rules():
    s = _settings()
    now = datetime(2026, 6, 1, 12, 0, tzinfo=ZoneInfo(TZ))  # полдень — детерминированно
    # обычный предзаказ: минимум сутки — +90 мин и +3 ч — ошибка, +25 ч — ок
    assert validate_schedule(s, 25_000, now + timedelta(minutes=90), now=now) is not None
    assert validate_schedule(s, 25_000, now + timedelta(minutes=180), now=now) is not None
    assert validate_schedule(s, 25_000, now + timedelta(hours=25), now=now) is None
    # крупный (≥60к): +47 ч — ошибка, +49 ч — ок
    assert validate_schedule(s, 61_000, now + timedelta(hours=47), now=now) is not None
    assert validate_schedule(s, 61_000, now + timedelta(hours=49), now=now) is None
    # прошлое время
    assert validate_schedule(s, 25_000, now - timedelta(minutes=10), now=now) is not None
    # ночью не готовим: время вне окна 08:00–23:00 отклоняется даже при соблюдённом лиде
    assert validate_schedule(s, 25_000, (now + timedelta(days=2)).replace(hour=3, minute=0), now=now) is not None
    assert validate_schedule(s, 25_000, (now + timedelta(days=2)).replace(hour=7, minute=59), now=now) is not None
    assert validate_schedule(s, 25_000, (now + timedelta(days=2)).replace(hour=8, minute=0), now=now) is None
    assert validate_schedule(s, 25_000, (now + timedelta(days=2)).replace(hour=23, minute=0), now=now) is None
    assert validate_schedule(s, 25_000, (now + timedelta(days=2)).replace(hour=23, minute=1), now=now) is not None


async def test_earliest_allowed_lead():
    s = _settings()
    now = datetime(2026, 6, 1, 12, 0, tzinfo=ZoneInfo(TZ))
    # обычный заказ — лид 24 ч, крупный — 48 ч
    assert earliest_allowed(s, 25_000, now=now) == now + timedelta(hours=24)
    assert earliest_allowed(s, 61_000, now=now) == now + timedelta(hours=48)


async def test_suggested_days_starts_from_valid_day():
    s = _settings()
    now = datetime(2026, 6, 1, 23, 50, tzinfo=ZoneInfo(TZ))  # поздний вечер
    # лид заканчивается 02.06 23:50 — после полудня → первый день 03.06
    days = suggested_days(s, 25_000, now=now)
    assert len(days) == 3
    assert days[0].isoformat() == "2026-06-03"
    assert days[1].isoformat() == "2026-06-04"
    assert days[2].isoformat() == "2026-06-05"
    # крупный заказ — лид 48 ч → первый день сдвигается ещё дальше
    big = suggested_days(s, 61_000, now=now)
    assert big[0].isoformat() == "2026-06-04"
    # а если лид заканчивается в первой половине дня — этот же день подходит
    early = datetime(2026, 6, 1, 10, 0, tzinfo=ZoneInfo(TZ))
    assert suggested_days(s, 25_000, now=early)[0].isoformat() == "2026-06-02"


async def test_transitions_state_machine(db_session):
    plov, manti = await _seed(db_session)
    await _fill_cart(db_session, plov, manti)
    order = await create_order(
        db_session, 1,
        settings=_settings(),
        contact_name="Пыленок", contact_phone="+77000000000",
        delivery_method="pickup", address=None,
        scheduled_for=_scheduled(26), comment=None,
    )
    # недопустимый прыжок
    with pytest.raises(OrderError):
        await transition(db_session, order, "preparing", actor="operator")
    # нормальный путь
    await transition(db_session, order, "awaiting_prepayment", actor="operator")
    await transition(db_session, order, "confirmed", actor="operator")
    await transition(db_session, order, "preparing", actor="operator")
    await transition(db_session, order, "delivering", actor="operator")
    await transition(db_session, order, "delivered", actor="operator")
    fresh = await get_order(db_session, order.id)
    assert fresh.status == "delivered"
    # из delivered уже никуда
    with pytest.raises(OrderError):
        await transition(db_session, fresh, "cancelled", actor="operator")


async def test_cancel_with_reason(db_session):
    plov, manti = await _seed(db_session)
    await _fill_cart(db_session, plov, manti)
    order = await create_order(
        db_session, 1,
        settings=_settings(),
        contact_name="Пыленок", contact_phone="+77000000000",
        delivery_method="own", address="ул. 1",
        scheduled_for=_scheduled(26), comment=None,
    )
    await transition(db_session, order, "cancelled", actor="operator", note="Нет продуктов")
    fresh = await get_order(db_session, order.id)
    assert fresh.status == "cancelled"
    assert fresh.cancelled_reason == "Нет продуктов"


async def test_build_scheduled_parses_time():
    s = _settings()
    day = datetime.now(ZoneInfo(TZ)).date()
    scheduled = build_scheduled(s, day, "18:30")
    assert scheduled.hour == 18 and scheduled.minute == 30
    assert scheduled.tzinfo is not None