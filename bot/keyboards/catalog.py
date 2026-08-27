from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.texts import fmt_price
from data.models import Category, Product


def categories_kb(categories: list[Category]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for c in categories:
        b.row(InlineKeyboardButton(text=c.name, callback_data=f"cat:{c.id}"))
    return b.as_markup()


def products_kb(products: list[Product], category_id: int) -> InlineKeyboardMarkup:
    """Кнопки-номера: короткие, чтобы длинные названия не прятали цену из текста."""
    b = InlineKeyboardBuilder()
    for i, p in enumerate(products, 1):
        label = f"{i}. {p.name}"
        if len(label) > 32:
            label = label[:31] + "…"
        b.row(InlineKeyboardButton(text=label, callback_data=f"prod:{p.id}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="cat:open"))
    return b.as_markup()


def product_card_kb(product_id: int, qty: int, category_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="➖", callback_data=f"qty:{product_id}:-1"),
        InlineKeyboardButton(text=f"В корзине: {qty}", callback_data=f"qty:{product_id}:0"),
        InlineKeyboardButton(text="➕", callback_data=f"qty:{product_id}:1"),
    )
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cat:{category_id}"))
    b.row(InlineKeyboardButton(text="🛒 В корзину", callback_data="cart:open"))
    return b.as_markup()