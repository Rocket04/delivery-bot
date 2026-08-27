from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.cart import CartRow


def cart_kb(rows: list[CartRow]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for r in rows:
        b.row(
            InlineKeyboardButton(text="➖", callback_data=f"cart:dec:{r.product_id}"),
            InlineKeyboardButton(text=f"{r.name} ×{r.quantity}", callback_data=f"prod:{r.product_id}"),
            InlineKeyboardButton(text="➕", callback_data=f"cart:inc:{r.product_id}"),
        )
    b.row(
        InlineKeyboardButton(text="🗑 Очистить", callback_data="cart:clear"),
        InlineKeyboardButton(text="✅ Оформить", callback_data="cart:checkout"),
    )
    b.row(InlineKeyboardButton(text="🍕 В меню", callback_data="cat:open"))
    return b.as_markup()


def cart_empty_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🍕 В меню", callback_data="cat:open"))
    return b.as_markup()