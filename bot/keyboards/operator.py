from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.constants import OrderStatus
from data.models import Order


def operator_kb(order: Order) -> InlineKeyboardMarkup:
    """Кнопки действий для группы операторов — по возможным переходам статус-машины."""
    b = InlineKeyboardBuilder()
    oid = order.id
    if order.status == OrderStatus.CREATED:
        b.row(InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"op:confirm:{oid}"))
        b.row(InlineKeyboardButton(text="❌ Отклонить", callback_data=f"op:cancel:{oid}"))
    elif order.status == OrderStatus.AWAITING_PREPAYMENT:
        b.row(InlineKeyboardButton(text="💳 Оплата получена", callback_data=f"op:paid:{oid}"))
        b.row(InlineKeyboardButton(text="❌ Отменить", callback_data=f"op:cancel:{oid}"))
    elif order.status == OrderStatus.CONFIRMED:
        b.row(InlineKeyboardButton(text="👨🍳 Готовится", callback_data=f"op:preparing:{oid}"))
        b.row(InlineKeyboardButton(text="❌ Отменить", callback_data=f"op:cancel:{oid}"))
    elif order.status == OrderStatus.PREPARING:
        b.row(InlineKeyboardButton(text="🚚 В доставке", callback_data=f"op:delivering:{oid}"))
        b.row(InlineKeyboardButton(text="❌ Отменить", callback_data=f"op:cancel:{oid}"))
    elif order.status == OrderStatus.DELIVERING:
        b.row(InlineKeyboardButton(text="✅ Доставлен", callback_data=f"op:delivered:{oid}"))
    return b.as_markup()


def operator_pay_kb(order_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="💸 Перевод на номер", callback_data=f"op:kaspi_transfer:{order_id}"))
    b.row(InlineKeyboardButton(text="🔗 Ссылка на оплату", callback_data=f"op:kaspi_link:{order_id}"))
    b.row(InlineKeyboardButton(text="📲 Удалённая оплата", callback_data=f"op:kaspi_remote:{order_id}"))
    return b.as_markup()