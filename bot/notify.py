"""Отправка заказов в группу операторов и обновление карточки заказа."""

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.operator import operator_kb
from bot.texts import RU
from core.ordering import ORDER_STATUS_LABELS, order_summary_text
from data.models import Order, OrderItem


async def get_order_items(session: AsyncSession, order_id: int) -> list[OrderItem]:
    return list(
        await session.scalars(
            select(OrderItem).where(OrderItem.order_id == order_id).order_by(OrderItem.id)
        )
    )


def order_card_text(order: Order, items: list[OrderItem]) -> str:
    status = ORDER_STATUS_LABELS.get(order.status, order.status)
    return (
        f"🧾 <b>Заказ №{order.number}</b>\n"
        f"Статус: {status}\n\n"
        f"{order_summary_text(order, items)}"
    )


async def send_order_to_operators(bot: Bot, session: AsyncSession, order: Order) -> None:
    """Шлёт новую карточку заказа в группу операторов."""
    from config.settings import get_settings

    chat_id = get_settings().operator_chat_id
    if not chat_id:
        return  # группа ещё не настроена — заказ остаётся только в БД
    items = await get_order_items(session, order.id)
    try:
        await bot.send_message(chat_id, order_card_text(order, items), reply_markup=operator_kb(order))
    except Exception:
        # Группа не найдена/бот не в группе — не роняем оформление клиента
        import logging

        logging.getLogger(__name__).exception("Ошибка отправки заказа в группу операторов")


async def notify_user_cancelled(bot: Bot, order: Order) -> None:
    """Сообщает группе операторов, что клиент сам отменил заказ.

    Карточка в группе остаётся со старыми кнопками — нажатия по ним
    упадут с «переход недопустим», но это не роняет бота; отдельное
    сообщение гарантирует, что оператор не начнёт подтверждать отменённый заказ.
    """
    from config.settings import get_settings

    chat_id = get_settings().operator_chat_id
    if not chat_id:
        return
    try:
        await bot.send_message(chat_id, RU["op_user_cancelled"].format(number=order.number))
    except Exception:
        import logging

        logging.getLogger(__name__).exception("Ошибка уведомления операторов об отмене клиентом")


async def update_order_card(
    bot: Bot,
    session: AsyncSession,
    order: Order,
    chat_id: int,
    message_id: int,
) -> None:
    """Перерисовывает карточку заказа в группе после смены статуса.

    Карточка может быть текстовым сообщением или фото (чек клиента) —
    для фото правим caption, а не text.
    """
    items = await get_order_items(session, order.id)
    text = order_card_text(order, items)
    kb = operator_kb(order)
    try:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=kb)
    except TelegramBadRequest as exc:
        msg = str(exc)
        if "there is no text" in msg:
            # сообщение-фото: у него есть caption, а не text
            await bot.edit_message_caption(chat_id=chat_id, message_id=message_id, caption=text, reply_markup=kb)
            return
        if "message is not modified" in msg:
            return  # повторный клик по той же кнопке — не ошибка
        raise