"""История заказов клиента («Мои заказы»)."""

import re

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.catalog import db_user_id
from bot.notify import get_order_items
from bot.texts import RU
from bot.utils import edit_or_answer
from core.ordering import ORDER_STATUS_LABELS, get_order, order_summary_text
from data.models import Order

router = Router(name="orders")

VIEW_RE = re.compile(r"^orders:view:(\d+)$")


@router.callback_query(F.data == "main:orders")
async def cb_my_orders(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    user_id = await db_user_id(session, callback.from_user.id)
    rows = list(
        await session.scalars(
            select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).limit(5)
        )
    )
    if not rows:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🍕 В меню", callback_data="cat:open")]]
        )
        await edit_or_answer(callback.message, RU["my_orders_empty"], kb)
        return

    lines = [RU["my_orders_title"], ""]
    for order in rows:
        lines.append(
            RU["my_order_row"].format(
                number=order.number,
                date=order.created_at.strftime("%d.%m %H:%M"),
                status=ORDER_STATUS_LABELS.get(order.status, order.status),
            )
        )
    keyboard = [
        [InlineKeyboardButton(text=f"№ {order.number}", callback_data=f"orders:view:{order.id}")]
        for order in rows
    ]
    keyboard.append([InlineKeyboardButton(text="🍕 В меню", callback_data="cat:open")])
    await edit_or_answer(callback.message, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.regexp(VIEW_RE.pattern))
async def cb_order_view(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    order = await get_order(session, int(VIEW_RE.match(callback.data).group(1)))
    if order is None:
        return
    items = await get_order_items(session, order.id)
    text = RU["my_order_detail"].format(
        number=order.number,
        summary=order_summary_text(order, items),
        status=ORDER_STATUS_LABELS.get(order.status, order.status),
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 К списку", callback_data="main:orders")],
            [InlineKeyboardButton(text="🍕 В меню", callback_data="cat:open")],
        ]
    )
    await callback.message.answer(text, reply_markup=kb)