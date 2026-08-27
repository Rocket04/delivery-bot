"""Эксперимент exp/user-cancel-reorder: отмена заказа клиентом + повторный заказ.

Покрывает core-логику (bot-хендлеры тестируются интеграционно на ВМ/тестовом боте).
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from config.settings import Settings
from core.cart import change_quantity, get_cart_view
from core.ordering import (
    OrderError,
    cancel_order_by_user,
    create_order,
    repeat_order,
    transition,
    user_can_cancel,
)
from data.models import Category, Order, OrderEvent, Product

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
    await change_quantity(session, 1, plov_id, plov_qty)
    await change_quantity(session, 1, manti_id, manti_qty)
    return plov_qty * 1800 + manti_qty * 2500


def _scheduled(days: int = 26, hour: int = 12) -> datetime:
    d = datetime.now(ZoneInfo(TZ)).date() + timedelta(days=days)
    return datetime(d.year, d.month, d.day, hour, 0, tzinfo=ZoneInfo(TZ))


async def _make_order(session, user_id: int = 1) -> Order:
    plov, manti = await _seed(session)
    await _fill_cart(session, plov, manti)
    return await create_order(
        session,
        user_id,
        settings=_settings(),
        contact_name="Пыленок",
        contact_phone="+77000000000",
        delivery_method="own",
        address="ул. 1",
        scheduled_for=_scheduled(),
        comment=None,
    )


# --- Отмена клиентом ---

async def test_user_cancel_created_order(db_session):
    order = await _make_order(db_session)
    assert user_can_cancel(order)
    await cancel_order_by_user(db_session, order)
    fresh = await db_session.get(Order, order.id)
    assert fresh.status == "cancelled"
    assert fresh.cancelled_reason == "Отменён клиентом"
    # событие записано с actor=user
    ev = await db_session.scalar(
        select(OrderEvent).where(OrderEvent.order_id == order.id, OrderEvent.to_status == "cancelled")
    )
    assert ev.actor == "user"
    # повторно отменить нельзя
    assert not user_can_cancel(fresh)
    with pytest.raises(OrderError):
        await cancel_order_by_user(db_session, fresh)


async def test_user_cancel_window_awaiting_prepayment(db_session):
    """Окно отмены расширено: пока чек не прислан, можно отменить и из awaiting_prepayment."""
    order = await _make_order(db_session)
    await transition(db_session, order, "awaiting_prepayment", actor="operator", note="реквизиты")
    assert user_can_cancel(order)
    await cancel_order_by_user(db_session, order)
    assert (await db_session.get(Order, order.id)).status == "cancelled"


async def test_user_cancel_blocked_after_receipt(db_session):
    """Чек уже прислан — отменой занимается оператор (возврат денег)."""
    order = await _make_order(db_session)
    await transition(db_session, order, "awaiting_prepayment", actor="operator")
    order.receipt_photo_file_id = "AgAC_photo_id"
    await db_session.commit()
    assert not user_can_cancel(order)
    with pytest.raises(OrderError):
        await cancel_order_by_user(db_session, order)


async def test_user_cancel_blocked_in_work(db_session):
    """После подтверждения оплаты отмена клиентом запрещена."""
    order = await _make_order(db_session)
    await transition(db_session, order, "awaiting_prepayment", actor="operator")
    await transition(db_session, order, "confirmed", actor="operator")
    assert not user_can_cancel(order)
    with pytest.raises(OrderError):
        await cancel_order_by_user(db_session, order)


# --- Повторный заказ ---

async def test_repeat_order_restores_cart(db_session):
    order = await _make_order(db_session)
    # корзина после оформления пуста
    assert (await get_cart_view(db_session, 1)).rows == []
    result = await repeat_order(db_session, order.id, 1)
    assert len(result.added) == 2
    assert result.skipped == []
    view = await get_cart_view(db_session, 1)
    assert view.total == order.total
    assert {r.name for r in view.rows} == {"Плов", "Манты"}
    assert {r.quantity for r in view.rows} == {10, 1}


async def _first_item_product_id(session, order_id: int) -> int | None:
    """product_id первой позиции заказа (без ленивой загрузки relationship)."""
    from data.models import OrderItem

    return await session.scalar(
        select(OrderItem.product_id).where(OrderItem.order_id == order_id).order_by(OrderItem.id).limit(1)
    )


async def test_repeat_order_skips_unavailable_and_deleted(db_session):
    order = await _make_order(db_session)
    plov_id = await _first_item_product_id(db_session, order.id)
    product = await db_session.get(Product, plov_id)
    product.is_available = False
    await db_session.commit()
    result = await repeat_order(db_session, order.id, 1)
    assert len(result.added) == 1  # только манты
    assert any("Плов" in s for s in result.skipped)


async def test_repeat_order_skips_deleted_product(db_session):
    order = await _make_order(db_session)
    plov_id = await _first_item_product_id(db_session, order.id)
    product = await db_session.get(Product, plov_id)
    await db_session.delete(product)  # product_id в order_items станет NULL (SET NULL)
    await db_session.commit()
    result = await repeat_order(db_session, order.id, 1)
    assert any("Плов" in s and "меню" in s for s in result.skipped)


async def test_repeat_order_denied_for_foreign_user(db_session):
    order = await _make_order(db_session)
    with pytest.raises(OrderError, match="Заказ не найден"):
        await repeat_order(db_session, order.id, 999)