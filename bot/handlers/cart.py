import re

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.catalog import db_user_id, show_product_card
from bot.keyboards.cart import cart_empty_kb, cart_kb
from bot.texts import RU, fmt_price
from bot.utils import edit_or_answer
from config.settings import get_settings
from core.cart import CartView, change_quantity, clear_cart, get_cart_view
from core.catalog import get_product

router = Router(name="cart")

ITEM_RE = re.compile(r"^cart:item:(\d+)$")
QTY_RE = re.compile(r"^cart:(inc|dec):(\d+)$")


def _cart_text(view: CartView, min_order: int) -> str:
    parts = [RU["cart_title"]]
    for i, row in enumerate(view.rows, 1):
        line = RU["cart_row"].format(name=row.name, qty=row.quantity, sum=fmt_price(row.price * row.quantity))
        if not row.available:
            line += RU["cart_unavailable_note"]
        parts.append(f"{i}. {line}")
    if view.rows:
        parts.append(RU["cart_total"].format(total=fmt_price(view.total)))
        if view.unavailable_total:
            parts.append(RU["cart_unavailable_total"].format(total=fmt_price(view.unavailable_total)))
        if 0 < view.total < min_order:
            parts.append(RU["cart_min_warn"].format(min=fmt_price(min_order), diff=fmt_price(min_order - view.total)))
    return "\n".join(parts)


async def _show_cart(callback: CallbackQuery, session: AsyncSession) -> None:
    user_id = await db_user_id(session, callback.from_user.id)
    view = await get_cart_view(session, user_id)
    if not view.rows:
        await edit_or_answer(callback.message, RU["cart_empty"], cart_empty_kb())
        return
    kb = cart_kb(view.rows)
    await edit_or_answer(callback.message, _cart_text(view, get_settings().min_order_amount), kb)


@router.callback_query(F.data.in_({"main:cart", "cart:open"}))
async def cb_cart_open(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    await _show_cart(callback, session)


@router.callback_query(F.data.regexp(r"^cart:item:\d+$"))
async def cb_cart_item(callback: CallbackQuery, session: AsyncSession) -> None:
    """Клик по позиции в корзине — карточка товара отдельным сообщением."""
    await callback.answer()
    match = ITEM_RE.match(callback.data)
    product = await get_product(session, int(match.group(1)))
    if product is None:
        await callback.message.answer(RU["product_not_found"])
        return
    qty = await get_cart_view(session, await db_user_id(session, callback.from_user.id))
    qty = next((r.quantity for r in qty.rows if r.product_id == product.id), 0)
    await show_product_card(callback.message, product, qty, edit=False)


@router.callback_query(F.data.regexp(r"^cart:(inc|dec):\d+$"))
async def cb_cart_qty(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    match = QTY_RE.match(callback.data)
    action, product_id = match.group(1), int(match.group(2))
    user_id = await db_user_id(session, callback.from_user.id)
    if action == "inc":
        product = await get_product(session, product_id)
        if product is None or not product.is_available:
            await callback.message.answer(RU["product_unavailable"])
            return
        await change_quantity(session, user_id, product_id, 1)
    else:
        await change_quantity(session, user_id, product_id, -1)
    await _show_cart(callback, session)


@router.callback_query(F.data == "cart:clear")
async def cb_cart_clear(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    user_id = await db_user_id(session, callback.from_user.id)
    await clear_cart(session, user_id)
    await edit_or_answer(callback.message, RU["cart_empty"], cart_empty_kb())


@router.callback_query(F.data == "cart:checkout")
async def cb_cart_checkout(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    await callback.message.answer(RU["checkout_soon"])