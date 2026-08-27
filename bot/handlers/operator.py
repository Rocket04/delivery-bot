"""Операторская группа: подтверждение заказа, предоплата Kaspi, статусы, отмена, чек."""

import logging
import re

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.catalog import db_user_id
from bot.keyboards.operator import operator_kb, operator_pay_kb
from bot.notify import update_order_card
from bot.texts import RU, fmt_price
from config.settings import get_settings
from core.constants import PaymentStatus
from core.ordering import (
    ORDER_STATUS_LABELS,
    OrderError,
    get_order,
    latest_awaiting_prepayment,
    transition,
)
from data.models import User

router = Router(name="operator")

logger = logging.getLogger(__name__)

CREATE_RE = re.compile(r"^op:confirm:(\d+)$")
CANCEL_RE = re.compile(r"^op:cancel:(\d+)$")
PAID_RE = re.compile(r"^op:paid:(\d+)$")
PREPARING_RE = re.compile(r"^op:preparing:(\d+)$")
DELIVERING_RE = re.compile(r"^op:delivering:(\d+)$")
DELIVERED_RE = re.compile(r"^op:delivered:(\d+)$")
PAY_METHOD_RE = re.compile(r"^op:(kaspi_transfer|kaspi_link|kaspi_remote):(\d+)$")
_PRICE_RE = re.compile(r"^\d{1,7}$")


class OpState(StatesGroup):
    price = State()
    pay_method = State()
    pay_details = State()
    cancel_reason = State()


async def _op_check(callback: CallbackQuery) -> bool:
    """Кнопки оператора работают только в группе операторов."""
    settings = get_settings()
    if not settings.operator_chat_id or callback.message.chat.id != settings.operator_chat_id:
        await callback.answer(RU["op_chat_only"], show_alert=True)
        return False
    await callback.answer()
    return True


async def _send_user_status(bot, session: AsyncSession, order, text: str) -> None:
    user = await session.get(User, order.user_id)
    if user is None:
        return
    try:
        await bot.send_message(user.tg_id, text)
    except Exception:
        logger.exception("Не удалось уведомить клиента заказа %s", order.number)


@router.callback_query(F.data.regexp(CREATE_RE.pattern))
async def op_confirm(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if not await _op_check(callback):
        return
    order = await get_order(session, int(CREATE_RE.match(callback.data).group(1)))
    if order is None:
        return
    await state.set_state(OpState.price)
    await state.update_data(order_id=order.id, card_msg_id=callback.message.message_id)
    await callback.message.answer(RU["op_price_ask"].format(number=order.number))


@router.message(StateFilter(OpState.price))
async def op_price_text(message: Message, session: AsyncSession, state: FSMContext) -> None:
    text = (message.text or "").strip().replace(" ", "")
    if not _PRICE_RE.match(text):
        await message.answer(RU["op_price_invalid"])
        return
    data = await state.get_data()
    await state.update_data(delivery_price=int(text))
    await state.set_state(OpState.pay_method)
    order = await get_order(session, data["order_id"])
    if order is None:
        await state.clear()
        return
    await message.answer(
        RU["op_pay_method_ask"].format(number=order.number, prepay=fmt_price(order.prepay_amount)),
        reply_markup=operator_pay_kb(order.id),
    )


@router.callback_query(F.data.regexp(PAY_METHOD_RE.pattern))
async def op_pay_method(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if not await _op_check(callback):
        return
    match = PAY_METHOD_RE.match(callback.data)
    method, order_id = match.group(1), int(match.group(2))
    data = await state.get_data()
    if data.get("order_id") != order_id:
        await callback.answer()
        return
    await state.update_data(pay_method=method)
    await state.set_state(OpState.pay_details)
    await callback.message.answer(RU["op_pay_details_ask"])


@router.message(StateFilter(OpState.pay_details))
async def op_pay_details(message: Message, session: AsyncSession, state: FSMContext) -> None:
    details = (message.text or "").strip()
    if not details:
        return
    data = await state.get_data()
    order = await get_order(session, data["order_id"])
    if order is None:
        await state.clear()
        return
    order.delivery_price = data["delivery_price"]
    order.total = order.items_total + order.delivery_price
    order.payment_method = data["pay_method"]
    order.payment_details = details
    try:
        await transition(session, order, "awaiting_prepayment", actor="operator")
    except OrderError:
        await state.clear()
        await message.answer("Статус заказа уже изменился — карточку обновили.")
        return
    settings = get_settings()
    await _send_user_status(
        message.bot,
        session,
        order,
        RU["user_prepay_request"].format(
            number=order.number,
            prepay=fmt_price(order.prepay_amount),
            details=details,
        ),
    )
    await state.clear()
    if settings.operator_chat_id:
        await update_order_card(message.bot, session, order, settings.operator_chat_id, data["card_msg_id"])
    await message.answer(RU["op_pay_details_sent"])


async def _status_action(callback: CallbackQuery, session: AsyncSession, status: str) -> None:
    """Общий шаг: перевод статуса, уведомление клиента, перерисовка карточки."""
    _RE = {
        "confirmed": PAID_RE,
        "preparing": PREPARING_RE,
        "delivering": DELIVERING_RE,
        "delivered": DELIVERED_RE,
    }[status]
    order = await get_order(session, int(_RE.match(callback.data).group(1)))
    if order is None:
        return
    if status == "confirmed":
        order.payment_status = PaymentStatus.PAID
    try:
        await transition(session, order, status, actor="operator")
    except OrderError:
        return
    await _send_user_status(
        callback.bot, session, order,
        RU["user_status"].format(number=order.number, status=ORDER_STATUS_LABELS[status]),
    )
    await update_order_card(callback.bot, session, order, callback.message.chat.id, callback.message.message_id)


@router.callback_query(F.data.regexp(PAID_RE.pattern))
async def op_paid(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _op_check(callback):
        return
    await _status_action(callback, session, "confirmed")
    await callback.message.answer(RU["op_paid_confirm"].format(number=callback.data.split(":")[2]))


@router.callback_query(F.data.regexp(PREPARING_RE.pattern))
async def op_preparing(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _op_check(callback):
        return
    await _status_action(callback, session, "preparing")


@router.callback_query(F.data.regexp(DELIVERING_RE.pattern))
async def op_delivering(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _op_check(callback):
        return
    await _status_action(callback, session, "delivering")


@router.callback_query(F.data.regexp(DELIVERED_RE.pattern))
async def op_delivered(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _op_check(callback):
        return
    await _status_action(callback, session, "delivered")


@router.callback_query(F.data.regexp(CANCEL_RE.pattern))
async def op_cancel(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if not await _op_check(callback):
        return
    order = await get_order(session, int(CANCEL_RE.match(callback.data).group(1)))
    if order is None:
        return
    await state.set_state(OpState.cancel_reason)
    await state.update_data(order_id=order.id, card_msg_id=callback.message.message_id)
    await callback.message.answer(RU["op_cancel_reason_ask"].format(number=order.number))


@router.message(StateFilter(OpState.cancel_reason))
async def op_cancel_reason(message: Message, session: AsyncSession, state: FSMContext) -> None:
    reason = (message.text or "").strip()
    if not reason:
        return
    data = await state.get_data()
    order = await get_order(session, data["order_id"])
    if order is None:
        await state.clear()
        return
    try:
        await transition(session, order, "cancelled", actor="operator", note=reason)
    except OrderError:
        await state.clear()
        return
    settings = get_settings()
    await _send_user_status(message.bot, session, order, RU["user_cancelled"].format(number=order.number, reason=reason))
    await state.clear()
    if settings.operator_chat_id:
        await update_order_card(message.bot, session, order, settings.operator_chat_id, data["card_msg_id"])


@router.message(F.photo)
async def on_receipt_photo(message: Message, session: AsyncSession) -> None:
    """Клиент присылает чек об оплате — прикрепляем к заказу и пересылаем операторам."""
    user_id = await db_user_id(session, message.from_user.id)
    order = await latest_awaiting_prepayment(session, user_id)
    if order is None:
        return  # фото без активной предоплаты — игнорируем
    order.receipt_photo_file_id = message.photo[-1].file_id
    await session.commit()
    await message.answer(RU["user_receipt_sent"])

    settings = get_settings()
    if not settings.operator_chat_id:
        return
    user = await session.get(User, order.user_id)
    name = user.first_name if user and user.first_name else order.contact_name
    paid_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплата получена", callback_data=f"op:paid:{order.id}")]
        ]
    )
    try:
        await message.bot.send_photo(
            settings.operator_chat_id,
            message.photo[-1].file_id,
            caption=RU["user_receipt_forwarded"].format(number=order.number, name=name),
            reply_markup=paid_kb,
        )
    except Exception:
        logger.exception("Не удалось переслать чек в группу операторов")