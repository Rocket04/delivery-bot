from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


def checkout_name_kb(saved_name: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=f"👤 Использовать: {saved_name}", callback_data="checkout:use_last_name"))
    return b.as_markup()


def checkout_phone_reply_kb() -> ReplyKeyboardMarkup:
    """Reply-клавиатура с кнопкой «номер из Telegram» (request_contact)."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер из Telegram", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def checkout_phone_kb(saved_phone: str) -> InlineKeyboardMarkup:
    """Inline-кнопка «использовать прошлый номер» + reply-клавиатура выше."""
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=f"📱 Использовать: {saved_phone}", callback_data="checkout:use_last_phone"))
    return b.as_markup()


def checkout_method_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🚗 Наша доставка", callback_data="sel_method:own"))
    b.row(InlineKeyboardButton(text="🚚 Яндекс.Доставка", callback_data="sel_method:yandex"))
    b.row(InlineKeyboardButton(text="🏠 Самовывоз", callback_data="sel_method:pickup"))
    return b.as_markup()


def checkout_date_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="Сегодня", callback_data="sel_date:0"))
    b.row(InlineKeyboardButton(text="Завтра", callback_data="sel_date:1"))
    b.row(InlineKeyboardButton(text="Послезавтра", callback_data="sel_date:2"))
    b.row(InlineKeyboardButton(text="📅 Другая дата", callback_data="sel_date:custom"))
    return b.as_markup()


def checkout_comment_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="Пропустить", callback_data="checkout:skip_comment"))
    return b.as_markup()


def checkout_deposit_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🍽 Да, добавьте (залог 10 000 ₸)", callback_data="checkout:deposit_yes"))
    b.row(InlineKeyboardButton(text="Нет, спасибо", callback_data="checkout:deposit_no"))
    return b.as_markup()


def checkout_summary_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ Подтвердить и отправить", callback_data="checkout:confirm"))
    b.row(InlineKeyboardButton(text="✏️ Начать заново", callback_data="checkout:redo"))
    return b.as_markup()