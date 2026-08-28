"""Свободный текст → ИИ-ассистент + сборка заказа текстом (exp/ai-assistant).

Два режима:
1. В тексте упомянуты блюда из меню → собираем корзину детерминированным
   матчером (core/ai_order), уточняем детали мини-FSM (телефон → адрес →
   способ → время), показываем сводку с кнопкой подтверждения, создаём заказ
   и шлём операторам (как обычный checkout).
2. Текст без блюд → LLM-FAQ с краткой памятью диалога, эскалацией оператору
   и «где мой заказ» из БД (core/assistant).
"""

import logging
from collections import deque

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.catalog import db_user_id
from bot.notify import notify_ai_escalation, send_order_to_operators
from bot.texts import RU
from config.settings import get_settings
from core.ai_order import (
    build_order_body,
    match_menu_items,
    parse_phone_from_text,
    parse_time_freetext,
)
from core.assistant import answer_freetext
from core.cart import change_quantity, clear_cart, get_cart_view
from core.catalog import portion_line_total, portion_qty_label
from core.constants import DeliveryMethod
from core.ordering import (
    DELIVERY_METHOD_LABELS,
    OrderError,
    create_order,
    format_money,
)
from core.users import get_user_by_tg_id
from core.validation import valid_address, valid_phone, valid_time_hm
from integrations.llm import get_provider

router = Router(name="ai")

log = logging.getLogger(__name__)

# Память FAQ-диалога (in-memory; переживает сообщения, но не рестарт — для эксперимента)
_HISTORY: dict[int, deque[tuple[str, str]]] = {}
HISTORY_LIMIT = 8


class AIOrderState(StatesGroup):
    phone = State()
    address = State()
    method = State()
    time = State()


def _push_history(tg_id: int, user_msg: str, bot_msg: str) -> None:
    _HISTORY.setdefault(tg_id, deque(maxlen=HISTORY_LIMIT)).append(("user", user_msg))
    _HISTORY[tg_id].append(("assistant", bot_msg))


def _method_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚗 Наша доставка", callback_data="ai:method:own")],
            [InlineKeyboardButton(text="🚚 Яндекс.Доставка", callback_data="ai:method:yandex")],
            [InlineKeyboardButton(text="🏠 Самовывоз", callback_data="ai:method:pickup")],
        ]
    )


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить и отправить", callback_data="ai:confirm")],
            [InlineKeyboardButton(text="🧹 Очистить корзину", callback_data="ai:abort")],
        ]
    )


def _cart_menu_kb() -> InlineKeyboardMarkup:
    """После очистки корзины: снова в меню/корзину."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 В корзину", callback_data="cart:open")],
            [InlineKeyboardButton(text="🍕 В меню", callback_data="cat:open")],
        ]
    )


def _terminal_kb() -> InlineKeyboardMarkup:
    """Конец диалога: контроль заказа + выход в меню."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мои заказы", callback_data="main:orders")],
            [InlineKeyboardButton(text="🍕 В меню", callback_data="cat:open")],
        ]
    )


def _cart_lines(view, portion_grams: int = 300) -> str:
    rows = "\n".join(
        f"{r.name} {portion_qty_label(r.name, r.quantity, portion_grams)} — "
        f"{format_money(portion_line_total(r.price, r.quantity, r.grams, portion_grams))}"
        for r in view.rows
    )
    return rows or "—"


async def _start_order_flow(message: Message, session: AsyncSession, state: FSMContext) -> None:
    """Начинает уточнение деталей заказа после добавления корзины."""
    user = await get_user_by_tg_id(session, message.from_user.id)
    data = await state.get_data()
    phone = data.get("phone") or (user.phone if user else None)
    if phone:
        await state.update_data(phone=phone)
        await _ask_address(message, state)
    else:
        await state.set_state(AIOrderState.phone)
        await message.answer(RU["ai_order_phone"])


async def _ask_address(message: Message, state: FSMContext) -> None:
    await state.set_state(AIOrderState.address)
    await message.answer(RU["ai_order_address"])


@router.message(F.text, ~F.text.startswith("/"), StateFilter(None))
async def on_freetext(message: Message, session: AsyncSession, state: FSMContext) -> None:
    settings = get_settings()

    # --- Режим 1: в тексте блюда → заказ ---
    matched, _ = await match_menu_items(session, message.text)
    if matched:
        user_id = await db_user_id(session, message.from_user.id)
        for mi in matched:
            await change_quantity(session, user_id, mi.product.id, mi.quantity)
        view = await get_cart_view(session, user_id)
        await state.clear()
        await state.update_data(added=[mi.display for mi in matched])
        await message.answer(
            RU["ai_order_start"].format(
                items="\n".join(mi.display for mi in matched),
                rows=_cart_lines(view, settings.portion_grams),
                total=format_money(view.total),
            )
        )
        await _start_order_flow(message, session, state)
        return

    # --- Режим 2: FAQ/эскалация/статус ---
    user_id = await db_user_id(session, message.from_user.id)
    provider = get_provider(
        settings.llm_provider, settings.llm_api_key, settings.llm_model, settings.llm_base_url
    )
    history = list(_HISTORY.get(message.from_user.id, []))[-HISTORY_LIMIT:]
    answer = await answer_freetext(session, user_id, message.text, provider, settings, history=history)
    await message.answer(answer.text)
    if answer.action in ("llm", "order_status", "fallback"):
        _push_history(message.from_user.id, message.text, answer.text)
    if answer.action == "operator":
        try:
            await notify_ai_escalation(message.bot, message.from_user, message.text)
        except Exception:
            log.exception("Не удалось уведомить операторов об эскалации")


@router.message(StateFilter(AIOrderState.phone))
async def on_ai_phone(message: Message, state: FSMContext) -> None:
    phone, error = valid_phone(message.text)
    if error:
        await message.answer(error)
        return
    await state.update_data(phone=phone.strip())
    await _ask_address(message, state)


@router.message(StateFilter(AIOrderState.address))
async def on_ai_address(message: Message, state: FSMContext) -> None:
    address, error = valid_address(message.text)
    if error:
        await message.answer(error)
        return
    await state.update_data(address=address.strip())
    await state.set_state(AIOrderState.method)
    await message.answer(RU["checkout_method"], reply_markup=_method_kb())


@router.callback_query(F.data.startswith("ai:method:"))
async def cb_ai_method(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    method = callback.data.split(":")[2]
    await state.update_data(method=method, method_label=DELIVERY_METHOD_LABELS.get(method, method))
    await state.set_state(AIOrderState.time)
    await callback.message.answer(RU["ai_order_time"])


@router.message(StateFilter(AIOrderState.time))
async def on_ai_time(message: Message, session: AsyncSession, state: FSMContext) -> None:
    settings = get_settings()
    user_id = await db_user_id(session, message.from_user.id)
    view = await get_cart_view(session, user_id)
    if view.total < settings.min_order_amount:
        await message.answer(
            RU["ai_order_time_error"].format(
                error=f"Минимальный заказ — {settings.min_order_amount:,} ₸, сейчас в корзине {view.total:,} ₸. Добавь ещё блюд."
            )
        )
        return
    scheduled = parse_time_freetext(message.text, settings, view.total)
    if scheduled is None:
        hm, hm_err = valid_time_hm(message.text)
        if hm_err:
            await message.answer(RU["ai_order_time_error"].format(error=hm_err))
            return
        await message.answer(
            RU["ai_order_time_error"].format(error="Это время не подходит (лид/окно 08:00–23:00)")
        )
        return
    await state.update_data(scheduled_for=scheduled)
    await _show_summary(message, session, state)


async def _show_summary(message: Message, session: AsyncSession, state: FSMContext) -> None:
    user_id = await db_user_id(session, message.from_user.id)
    view = await get_cart_view(session, user_id)
    if not view.rows:
        await message.answer(RU["cart_empty"])
        await state.clear()
        return
    data = await state.get_data()
    if "contact_name" not in data:
        user = await get_user_by_tg_id(session, message.from_user.id)
        data["contact_name"] = user.contact_name or user.first_name or "Клиент" if user else "Клиент"
        await state.update_data(contact_name=data["contact_name"])
    text = RU["ai_order_summary"].format(body=build_order_body(view, data))
    await message.answer(text, reply_markup=_confirm_kb())


@router.callback_query(F.data == "ai:confirm")
async def cb_ai_confirm(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await callback.answer()
    settings = get_settings()
    user_id = await db_user_id(session, callback.from_user.id)
    data = await state.get_data()
    try:
        order = await create_order(
            session,
            user_id,
            settings=settings,
            contact_name=data.get("contact_name", "Клиент"),
            contact_phone=data.get("phone", ""),
            delivery_method=data.get("method", DeliveryMethod.OWN),
            address=data.get("address"),
            scheduled_for=data["scheduled_for"],
            comment=None,
        )
    except OrderError as exc:
        await callback.message.answer(RU["checkout_error"].format(error=str(exc)))
        return
    await state.clear()
    await send_order_to_operators(callback.bot, session, order)
    try:
        await callback.message.edit_text(
            RU["ai_order_done"].format(number=order.number), reply_markup=_terminal_kb()
        )
    except Exception:
        await callback.message.answer(
            RU["ai_order_done"].format(number=order.number), reply_markup=_terminal_kb()
        )


@router.callback_query(F.data == "ai:abort")
async def cb_ai_abort(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await callback.answer()
    user_id = await db_user_id(session, callback.from_user.id)
    await clear_cart(session, user_id)
    await session.commit()
    await state.clear()
    await callback.message.edit_text(RU["ai_order_cleared"], reply_markup=_cart_menu_kb())