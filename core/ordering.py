"""Сервис заказов: бизнес-правила, создание, статус-машина.

Не зависит от Telegram. Для текстов ошибок используется простой русский
(pомечено на i18n на стадии 5).
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from core.cart import clear_cart, get_cart_view
from core.constants import ORDER_TRANSITIONS, PaymentStatus
from data.models import Order, OrderEvent, OrderItem

ORDER_STATUS_LABELS = {
    "created": "⏳ Ждёт подтверждения",
    "awaiting_prepayment": "💳 Ждём предоплату",
    "confirmed": "✅ Подтверждён",
    "preparing": "👨🍳 Готовится",
    "delivering": "🚚 В пути",
    "delivered": "🎉 Доставлен",
    "cancelled": "❌ Отменён",
}

DELIVERY_METHOD_LABELS = {
    "own": "🚗 Наша доставка",
    "yandex": "🚚 Яндекс.Доставка",
    "pickup": "🏠 Самовывоз",
}

PAYMENT_METHOD_LABELS = {
    "kaspi_transfer": "💸 Перевод на номер Kaspi",
    "kaspi_link": "🔗 Ссылка на оплату Kaspi",
    "kaspi_remote": "📲 Удалённая оплата на номер",
}


class OrderError(Exception):
    """Понятное пользователю сообщение об ошибке оформления."""


def _local_now(settings: Settings) -> datetime:
    return datetime.now(ZoneInfo(settings.app_tz))


def build_scheduled(settings: Settings, day: datetime.date, time_str: str) -> datetime:
    """Собирает осознанное локальное время из даты и «ЧЧ:ММ»."""
    hour, minute = map(int, time_str.split(":"))
    return datetime.combine(day, datetime.min.time().replace(hour=hour, minute=minute), tzinfo=ZoneInfo(settings.app_tz))


def validate_schedule(
    settings: Settings,
    total: int,
    scheduled_for: datetime,
    now: datetime | None = None,
) -> str | None:
    """Возвращает текст ошибки или None, если время допустимо.
    Бизнес: приём 24/7, готовим по предзаказу — минимум за сутки (24 ч),
    крупные заказы — минимум за large_order_lead_hours (48 ч по умолчанию).
    now — для тестов; по умолчанию текущее время в tz бизнеса."""
    now = now or _local_now(settings)
    if scheduled_for.tzinfo is None:
        scheduled_for = scheduled_for.replace(tzinfo=ZoneInfo(settings.app_tz))
    if scheduled_for <= now:
        return "⏰ Это время уже прошло — выбери более позднее."
    if total >= settings.large_order_threshold:
        lead = timedelta(hours=settings.large_order_lead_hours)
        if scheduled_for - now < lead:
            return (
                f"📦 Это крупный заказ (от {settings.large_order_threshold:,} ₸) — "
                f"мы принимаем его минимум за {settings.large_order_lead_hours} часа, "
                "чтобы успеть закупить продукты. Выбери время позже."
            )
    else:
        lead = timedelta(minutes=settings.default_lead_minutes)
        if scheduled_for - now < lead:
            hours = settings.default_lead_minutes // 60
            return f"👨🍳 Мы готовим по предзаказу — выбери время минимум за {hours} часа (сутки)."
    return None


def format_money(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " ₸"


def order_summary_text(order: Order, items: list[OrderItem]) -> str:
    """Человекочитаемая сводка заказа — для клиента и группы операторов."""
    lines = [
        f"👤 {order.contact_name}",
        f"📞 {order.contact_phone}",
        f"🚚 {DELIVERY_METHOD_LABELS.get(order.delivery_method, order.delivery_method)}",
        f"🕐 {order.scheduled_for:%d.%m %H:%M}",
    ]
    if order.address:
        lines.append(f"📍 {order.address}")
    if order.comment:
        lines.append(f"📝 {order.comment}")
    lines.append("")
    lines.append("————————————")
    lines.extend(
        f"{item.name} ×{item.quantity} — {format_money(item.price * item.quantity)}"
        for item in sorted(items, key=lambda it: it.id)
    )
    if order.delivery_price:
        lines.append(f"Доставка — {format_money(order.delivery_price)}")
    if order.deposit:
        lines.append(f"🍽 Восточная посуда — залог {format_money(order.deposit)} (возвратный)")
    lines.append("————————————")
    lines.append(f"<b>Сумма: {format_money(order.total)}</b>")
    lines.append(f"💳 Предоплата 50%: <b>{format_money(order.prepay_amount)}</b>")
    return "\n".join(lines)


async def create_order(
    session: AsyncSession,
    user_id: int,
    *,
    settings: Settings,
    contact_name: str,
    contact_phone: str,
    delivery_method: str,
    address: str | None,
    scheduled_for: datetime,
    comment: str | None,
    deposit: int = 0,
) -> Order:
    """Создаёт заказ из корзины одной транзакцией. Очищает корзину."""
    view = await get_cart_view(session, user_id)
    if not view.rows:
        raise OrderError("Корзина пуста.")
    if any(not row.available for row in view.rows):
        raise OrderError(
            "⚠️ В корзине есть позиции, которых сейчас нет в наличии. "
            "Убери их (➖) и попробуй снова."
        )
    if view.total < settings.min_order_amount:
        raise OrderError(
            f"💰 Минимальный заказ — {settings.min_order_amount:,} ₸, "
            f"а в корзине {view.total:,} ₸. Добавь ещё блюд."
        )
    error = validate_schedule(settings, view.total, scheduled_for)
    if error:
        raise OrderError(error)

    order = Order(
        user_id=user_id,
        number="",  # заполняется после flush
        status="created",
        delivery_method=delivery_method,
        delivery_price=0,  # назначит оператор при подтверждении
        scheduled_for=scheduled_for,
        contact_name=contact_name,
        contact_phone=contact_phone,
        address=address,
        comment=comment or None,
        items_total=view.total,
        total=view.total,
        prepay_percent=settings.prepay_percent,
        prepay_amount=view.total * settings.prepay_percent // 100,
        payment_method=None,
        payment_status=PaymentStatus.NONE,
        payment_details=None,
        receipt_photo_file_id=None,
        deposit=deposit,
    )
    session.add(order)
    await session.flush()
    order.number = f"{scheduled_for.astimezone(ZoneInfo(settings.app_tz)):%Y%m%d}-{order.id}"

    for row in view.rows:
        session.add(
            OrderItem(order_id=order.id, product_id=row.product_id, name=row.name, price=row.price, quantity=row.quantity)
        )
    session.add(OrderEvent(order_id=order.id, from_status=None, to_status=order.status, actor="user"))
    await clear_cart(session, user_id)
    await session.commit()
    return order


async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    return await session.get(Order, order_id)


async def latest_awaiting_prepayment(session: AsyncSession, user_id: int) -> Order | None:
    """Последний заказ клиента, ожидающий предоплату (для приёма чека)."""
    return await session.scalar(
        select(Order)
        .where(Order.user_id == user_id, Order.status == "awaiting_prepayment")
        .order_by(Order.id.desc())
        .limit(1)
    )


async def transition(session: AsyncSession, order: Order, to_status: str, actor: str, note: str | None = None) -> None:
    """Перевод статус-машины с записью в order_events."""
    allowed = ORDER_TRANSITIONS.get(order.status, set())
    if to_status not in allowed:
        raise OrderError(f"Переход {order.status!r} -> {to_status!r} недопустим")
    from_status = order.status
    order.status = to_status
    if to_status == "cancelled":
        order.cancelled_reason = note
    session.add(
        OrderEvent(order_id=order.id, from_status=from_status, to_status=to_status, actor=actor, note=note)
    )
    await session.commit()