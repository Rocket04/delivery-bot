"""Сервисы корзины. Не зависят от Telegram. Корзина в БД — переживает рестарты."""

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from data.models import CartItem, Product

MAX_QTY = 99


@dataclass
class CartRow:
    product_id: int
    name: str
    price: int
    quantity: int
    available: bool


@dataclass
class CartView:
    rows: list[CartRow]
    total: int  # сумма только доступных позиций
    unavailable_total: int  # сумма позиций, снятых с продажи


async def _cart_item(session: AsyncSession, user_id: int, product_id: int) -> CartItem | None:
    return await session.scalar(
        select(CartItem).where(CartItem.user_id == user_id, CartItem.product_id == product_id)
    )


async def cart_qty(session: AsyncSession, user_id: int, product_id: int) -> int:
    qty = await session.scalar(
        select(CartItem.quantity).where(CartItem.user_id == user_id, CartItem.product_id == product_id)
    )
    return qty or 0


async def change_quantity(session: AsyncSession, user_id: int, product_id: int, delta: int) -> int:
    """Увеличивает/уменьшает количество на delta. При 0 — позиция удаляется.
    Возвращает новое количество позиции."""
    item = await _cart_item(session, user_id, product_id)
    if item is None:
        if delta <= 0:
            return 0
        item = CartItem(user_id=user_id, product_id=product_id, quantity=delta)
        session.add(item)
        await session.commit()
        return delta

    new_qty = item.quantity + delta
    if new_qty <= 0:
        await session.delete(item)
        await session.commit()
        return 0
    if new_qty > MAX_QTY:
        new_qty = MAX_QTY
    item.quantity = new_qty
    await session.commit()
    return new_qty


async def get_cart_view(session: AsyncSession, user_id: int) -> CartView:
    stmt = (
        select(CartItem.quantity, Product)
        .join(Product, CartItem.product_id == Product.id)
        .where(CartItem.user_id == user_id)
        .order_by(Product.sort_order, Product.id)
    )
    rows: list[CartRow] = []
    total = 0
    unavailable_total = 0
    for quantity, product in (await session.execute(stmt)).all():
        rows.append(CartRow(product.id, product.name, product.price, quantity, product.is_available))
        if product.is_available:
            total += product.price * quantity
        else:
            unavailable_total += product.price * quantity
    return CartView(rows=rows, total=total, unavailable_total=unavailable_total)


async def clear_cart(session: AsyncSession, user_id: int) -> None:
    """Очищает корзину БЕЗ commit — вызывающий решает, когда зафиксировать."""
    await session.execute(delete(CartItem).where(CartItem.user_id == user_id))