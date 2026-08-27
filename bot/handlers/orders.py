"""История заказов клиента («Мои заказы») + отмена клиентом + повторный заказ."""

import re

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.catalog import db_user_id
from bot.notify import get_order_items, notify_user_cancelled
from bot.texts import RU
from bot.utils import edit_or_answer
from core.constants import OrderStatus
from core.ordering import (
    ORDER_STATUS_LABELS,
    OrderError,
    cancel_order_by_user,
    get_order,
    order_summary_text,
    repeat_order,
    user_can_cancel,
)
from data.models import Order

router = Router(name="orders")

VIEW_RE = re.compile(r"^orders:view:(\d+)$")
CANCEL_RE = re.compile(r"^orders:cancel:(\d+)$")
CANCEL_YES_RE = re.compile(r"^orders:cancel_yes:(\d+)$")
CANCEL_NO_RE = re.compile(r"^orders:cancel_no:(\d+)$")
REPEAT_RE = re.compile(r"^orders:repeat:(\d+)$")

BACK_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📋 К списку", callback_data="main:orders")],
        [InlineKeyboardButton(text="🍕 В меню", callback_data="cat:open")],
    ]
)


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
    rows: list[list[InlineKeyboardButton]] = []
    if user_can_cancel(order):
        rows.append(
            [InlineKeyboardButton(text=RU["order_cancel_btn"], callback_data=f"orders:cancel:{order.id}")]
        )
    if order.status in (OrderStatus.DELIVERED, OrderStatus.CANCELLED):
        rows.append(
            [InlineKeyboardButton(text=RU["order_repeat_btn"], callback_data=f"orders:repeat:{order.id}")]
        )
    rows.append([InlineKeyboardButton(text="📋 К списку", callback_data="main:orders")])
    rows.append([InlineKeyboardButton(text="🍕 В меню", callback_data="cat:open")])
    await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.regexp(CANCEL_RE.pattern))
async def cb_order_cancel_ask(callback: CallbackQuery, session: AsyncSession) -> None:
    """Подтверждение отмены: не даём случайно отменить заказ одним тапом."""
    await callback.answer()
    order = await get_order(session, int(CANCEL_RE.match(callback.data).group(1)))
    if order is None or not user_can_cancel(order):
        await callback.message.answer(RU["order_action_error"].format(error=RU["order_cancel_denied_hint"]))
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=RU["order_cancel_yes_btn"], callback_data=f"orders:cancel_yes:{order.id}")],
            [InlineKeyboardButton(text=RU["order_cancel_no_btn"], callback_data=f"orders:cancel_no:{order.id}")],
        ]
    )
    await callback.message.answer(
        RU["order_cancel_confirm"].format(number=order.number), reply_markup=kb
    )


@router.callback_query(F.data.regexp(CANCEL_YES_RE.pattern))
async def cb_order_cancel_yes(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    order = await get_order(session, int(CANCEL_YES_RE.match(callback.data).group(1)))
    if order is None:
        return
    try:
        await cancel_order_by_user(session, order)
    except OrderError as exc:
        await callback.message.answer(RU["order_action_error"].format(error=str(exc)))
        return
    await notify_user_cancelled(callback.bot, order)
    try:
        await callback.message.edit_text(
            RU["order_cancelled_ok"].format(number=order.number), reply_markup=BACK_KB
        )
    except Exception:
        await callback.message.answer(RU["order_cancelled_ok"].format(number=order.number), reply_markup=BACK_KB)


@router.callback_query(F.data.regexp(CANCEL_NO_RE.pattern))
async def cb_order_cancel_no(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    order = await get_order(session, int(CANCEL_NO_RE.match(callback.data).group(1)))
    number = order.number if order else "?"
    try:
        await callback.message.edit_text(
            RU["order_cancel_keep"].format(number=number), reply_markup=BACK_KB
        )
    except Exception:
        await callback.message.answer(RU["order_cancel_keep"].format(number=number), reply_markup=BACK_KB)


@router.callback_query(F.data.regexp(REPEAT_RE.pattern))
async def cb_order_repeat(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    user_id = await db_user_id(session, callback.from_user.id)
    order_id = int(REPEAT_RE.match(callback.data).group(1))
    try:
        result = await repeat_order(session, order_id, user_id)
    except OrderError as exc:
        await callback.message.answer(RU["order_action_error"].format(error=str(exc)))
        return
    if result.added:
        skipped_note = (
            RU["order_repeat_skipped"].format(skipped="\n".join(result.skipped))
            if result.skipped
            else ""
        )
        order = await get_order(session, order_id)
        text = RU["order_repeat_done"].format(
            number=order.number if order else order_id,
            added="\n".join(result.added),
            skipped_note=skipped_note,
        )
    else:
        text = RU["order_repeat_nothing"]
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=RU["order_go_cart_btn"], callback_data="cart:open")],
            [InlineKeyboardButton(text="🍕 В меню", callback_data="cat:open")],
        ]
    )
    await callback.message.answer(text, reply_markup=kb)