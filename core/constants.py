"""Доменные константы бизнеса. Чистый Python, без зависимостей от Telegram и БД."""


class OrderStatus:
    CREATED = "created"  # оформлен, ждёт решения оператора
    AWAITING_PREPAYMENT = "awaiting_prepayment"  # подтверждён, ждём предоплату 50%
    CONFIRMED = "confirmed"  # предоплата получена, заказ в работе
    PREPARING = "preparing"  # готовится
    DELIVERING = "delivering"  # в доставке / готов к выдаче
    DELIVERED = "delivered"  # выполнен
    CANCELLED = "cancelled"  # отменён (с причиной)


# Допустимые переходы статус-машины заказа
ORDER_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.CREATED: {OrderStatus.AWAITING_PREPAYMENT, OrderStatus.CANCELLED},
    OrderStatus.AWAITING_PREPAYMENT: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
    OrderStatus.PREPARING: {OrderStatus.DELIVERING, OrderStatus.CANCELLED},
    OrderStatus.DELIVERING: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}

# Статусы, из которых пользователь может отменить заказ сам
USER_CANCELLABLE: set[str] = {OrderStatus.CREATED}


class DeliveryMethod:
    OWN = "own"  # наша доставка
    PICKUP = "pickup"  # самовывоз
    YANDEX = "yandex"  # Яндекс.Доставка


class PaymentMethod:
    """Способы предоплаты (Kaspi), которые оператор отправляет клиенту."""

    KASPI_TRANSFER = "kaspi_transfer"  # перевод на номер Kaspi
    KASPI_LINK = "kaspi_link"  # ссылка на оплату Kaspi (бизнес-счёт)
    KASPI_REMOTE = "kaspi_remote"  # удалённая оплата/счёт на номер


class PaymentStatus:
    NONE = "none"  # предоплата не запрашивалась
    REQUESTED = "requested"  # реквизиты отправлены клиенту, ждём чек
    PAID = "paid"  # чек получен и подтверждён оператором


# Кто готовит заказ
class PrepSite:
    OWN = "own"  # своя кухня
    OUTSOURCED_1 = "outsourced_1"  # первый аутсорс-повар (манты/пельмени)
    OUTSOURCED_2 = "outsourced_2"  # второй аутсорс-повар