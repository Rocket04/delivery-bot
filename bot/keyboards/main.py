from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_keyboard() -> InlineKeyboardMarkup:
    """Главное меню (кнопки-заглушки до стадий 2–3)."""
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🍕 Меню", callback_data="main:menu"))
    b.row(InlineKeyboardButton(text="🛒 Корзина", callback_data="main:cart"))
    b.row(InlineKeyboardButton(text="📋 Мои заказы", callback_data="main:orders"))
    b.row(InlineKeyboardButton(text="ℹ️ О нас", callback_data="main:about"))
    return b.as_markup()