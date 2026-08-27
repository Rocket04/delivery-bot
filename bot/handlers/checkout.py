"""Оформление заказа: FSM-диалог клиента (имя → телефон → способ → дата → время → сводка)."""

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.catalog import db_user_id
from bot.keyboards.cart import cart_empty_kb
from bot.keyboards.checkout import (
    checkout_comment_kb,
    checkout_date_kb,
    checkout_deposit_kb,
    checkout_method_kb,
    checkout_summary_kb,
)
from bot.notify import send_order_to_operators
from bot.texts import RU, fmt_price
from bot.utils import edit_or_answer
from config.settings import get_settings
from core.cart import get_cart_view
from core.constants import DeliveryMethod
from core.ordering import (
    DELIVERY_METHOD_LABELS,
    OrderError,
    build_scheduled,
    create_order,
    validate_schedule,
)
from core.users import get_user_by_tg_id
from core.validation import valid_address, valid_comment, valid_date_ddmm, valid_name, valid_phone, valid_time_hm

router = Router(name="checkout")

METHOD_RE = re.compile(r"^sel_method:(own|yandex|pickup)$")
DATE_SEL_RE = re.compile(r"^sel_date:(0|1|2|custom)$")


class CheckoutState(StatesGroup):
    name = State()
    phone = State()
    method = State()
    address = State()
    date_custom = State()
    time = State()
    comment = State()
    deposit = State()


async def _cart_report(session: AsyncSession, user_id: int) -> str | None:
    """Базовая проверка корзины перед оформлением. Возвращает текст ошибки или None."""
    settings = get_settings()
    view = await get_cart_view(session, user_id)
    if not view.rows:
        return None  # пустую корзину показываем отдельно
    if any(not row.available for row in view.rows):
        return "В корзине есть позиции без наличия — убери их (➖) и попробуй снова."
    if view.total < settings.min_order_amount:
        return f"Минимальный заказ — {fmt_price(settings.min_order_amount)}, сейчас в корзине {fmt_price(view.total)}."
    return None


@router.callback_query(F.data == "cart:checkout")
async def cb_start_checkout(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await callback.answer()
    user_id = await db_user_id(session, callback.from_user.id)
    view = await get_cart_view(session, user_id)
    if not view.rows:
        await edit_or_answer(callback.message, RU["cart_empty"], cart_empty_kb())
        return
    error = await _cart_report(session, user_id)
    if error:
        await callback.message.answer(RU["checkout_error"].format(error=error))
        return
    await state.set_state(CheckoutState.name)
    await callback.message.answer(RU["checkout_start"])


@router.callback_query(F.data == "checkout:use_tg_name")
async def cb_use_tg_name(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    name = (callback.from_user.first_name or "Друг").strip()
    await state.update_data(name=name)
    await state.set_state(CheckoutState.phone)
    await callback.message.answer(RU["checkout_phone"])


@router.message(StateFilter(CheckoutState.name))
async def on_name(message: Message, state: FSMContext) -> None:
    name, error = valid_name(message.text)
    if error:
        await message.answer(error)
        return
    await state.update_data(name=name)
    await state.set_state(CheckoutState.phone)
    await message.answer(RU["checkout_phone"])


@router.message(StateFilter(CheckoutState.phone))
async def on_phone(message: Message, state: FSMContext) -> None:
    phone, error = valid_phone(message.text)
    if error:
        await message.answer(error)
        return
    await state.update_data(phone=phone)
    await state.set_state(CheckoutState.method)
    await message.answer(RU["checkout_method"], reply_markup=checkout_method_kb())


@router.callback_query(F.data.regexp(METHOD_RE.pattern))
async def cb_method(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    method = callback.data.split(":")[1]
    await state.update_data(method=method)
    if method == DeliveryMethod.PICKUP:
        await state.update_data(address="Самовывоз: Рабочий переулок, 2а-1")
        await callback.message.answer(
            RU["checkout_pickup_note"] + "\n\n" + RU["checkout_date"],
            reply_markup=checkout_date_kb(),
        )
    else:
        await state.set_state(CheckoutState.address)
        await callback.message.answer(RU["checkout_address"])


@router.message(StateFilter(CheckoutState.address))
async def on_address(message: Message, state: FSMContext) -> None:
    address, error = valid_address(message.text)
    if error:
        await message.answer(error)
        return
    await state.update_data(address=address)
    await message.answer(RU["checkout_date"], reply_markup=checkout_date_kb())


@router.callback_query(F.data.regexp(DATE_SEL_RE.pattern))
async def cb_date(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    sel = callback.data.split(":")[1]
    if sel == "custom":
        await state.set_state(CheckoutState.date_custom)
        await callback.message.answer(RU["checkout_date_custom"])
        return
    today = datetime.now(ZoneInfo(get_settings().app_tz)).date()
    day = today + timedelta(days=int(sel))
    await state.update_data(day=day.isoformat())
    await state.set_state(CheckoutState.time)
    await callback.message.answer(RU["checkout_time"])


@router.message(StateFilter(CheckoutState.date_custom))
async def on_date_custom(message: Message, state: FSMContext) -> None:
    day, error = valid_date_ddmm(message.text)
    if error:
        await message.answer(error)
        return
    await state.update_data(day=day.isoformat())
    await state.set_state(CheckoutState.time)
    await message.answer(RU["checkout_time"])


@router.message(StateFilter(CheckoutState.time))
async def on_time(message: Message, state: FSMContext, session: AsyncSession) -> None:
    hhmm, error = valid_time_hm(message.text)
    if error:
        await message.answer(error)
        return
    hour, minute = hhmm
    settings = get_settings()
    data = await state.get_data()
    day = date.fromisoformat(data["day"])
    scheduled = build_scheduled(settings, day, f"{hour:02d}:{minute:02d}")

    user_id = await db_user_id(session, message.from_user.id)
    view = await get_cart_view(session, user_id)
    error = validate_schedule(settings, view.total, scheduled)
    if error:
        await message.answer(RU["checkout_time_error"].format(error=error))
        return
    await state.update_data(scheduled=scheduled.isoformat())
    await state.set_state(CheckoutState.comment)
    await message.answer(RU["checkout_comment"], reply_markup=checkout_comment_kb())


@router.message(StateFilter(CheckoutState.comment))
async def on_comment(message: Message, state: FSMContext) -> None:
    comment, error = valid_comment(message.text)
    if error:
        await message.answer(error)
        return
    await state.update_data(comment=comment)
    await _ask_deposit(message, state)


@router.callback_query(F.data == "checkout:skip_comment")
async def cb_skip_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(comment=None)
    await _ask_deposit(callback.message, state)


async def _ask_deposit(message: Message, state: FSMContext) -> None:
    deposit_text = RU["checkout_deposit"].format(amount=fmt_price(get_settings().dish_deposit_amount))
    await state.set_state(CheckoutState.deposit)
    await message.answer(deposit_text, reply_markup=checkout_deposit_kb())


@router.callback_query(F.data.in_({"checkout:deposit_yes", "checkout:deposit_no"}))
async def cb_deposit(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await callback.answer()
    deposit = get_settings().dish_deposit_amount if callback.data == "checkout:deposit_yes" else 0
    await state.update_data(deposit=deposit)
    await _show_summary(callback.message, state, session)


async def _show_summary(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    scheduled = datetime.fromisoformat(data["scheduled"])
    user_id = await db_user_id(session, message.from_user.id)
    view = await get_cart_view(session, user_id)

    lines = [
        f"👤 {data['name']}",
        f"📞 {data['phone']}",
        f"🚚 {DELIVERY_METHOD_LABELS.get(data['method'], data['method'])}",
        f"🕐 {scheduled.strftime('%d.%m %H:%M')}",
    ]
    if data.get("address"):
        lines.append(f"📍 {data['address']}")
    if data.get("comment"):
        lines.append(f"📝 {data['comment']}")
    if data.get("deposit"):
        lines.append(f"🍽 Восточная посуда — залог {fmt_price(data['deposit'])} (возвратный)")
    lines.append("")
    lines.append("————————————")
    lines.extend(
        f"{row.name} ×{row.quantity} — {fmt_price(row.price * row.quantity)}" for row in view.rows
    )
    lines.append("————————————")
    lines.append(f"<b>Сумма: {fmt_price(view.total)}</b>")
    settings = get_settings()
    lines.append(f"💳 Предоплата 50%: <b>{fmt_price(view.total * settings.prepay_percent // 100)}</b>")

    await message.answer(
        RU["checkout_summary_title"].format(body="\n".join(lines)),
        reply_markup=checkout_summary_kb(),
    )


@router.callback_query(F.data == "checkout:confirm")
async def cb_confirm(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    # защита от двойного клика: первый confirm уже завершил оформление
    if not data.get("scheduled"):
        await callback.message.answer(RU["checkout_created_already"])
        return
    settings = get_settings()
    user_id = await db_user_id(session, callback.from_user.id)
    try:
        order = await create_order(
            session,
            user_id,
            settings=settings,
            contact_name=data["name"],
            contact_phone=data["phone"],
            delivery_method=data["method"],
            address=data["address"],
            scheduled_for=datetime.fromisoformat(data["scheduled"]),
            comment=data.get("comment"),
            deposit=data.get("deposit", 0),
        )
    except OrderError as exc:
        await callback.message.answer(RU["checkout_error"].format(error=str(exc)))
        return

    user = await get_user_by_tg_id(session, callback.from_user.id)
    if user is not None and user.phone != data["phone"]:
        user.phone = data["phone"]
        await session.commit()

    await state.clear()
    await callback.message.answer(RU["checkout_created"].format(number=order.number))
    await send_order_to_operators(callback.bot, session, order)


@router.callback_query(F.data == "checkout:redo")
async def cb_redo(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.answer("Давай заново! " + RU["checkout_start"])