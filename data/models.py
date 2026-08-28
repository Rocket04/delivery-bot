"""SQLAlchemy-модели. Схема полная, но некоторые поля используются с 2–3 стадий."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from core.constants import OrderStatus, PaymentStatus

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(32))  # заполняется при первом заказе
    contact_name: Mapped[str | None] = mapped_column(String(128))  # имя из последнего заказа
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[int] = mapped_column(Integer)  # тенге
    photo_file_id: Mapped[str | None] = mapped_column(String(255))  # file_id фото из Telegram
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)  # стоп-лист
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category: Mapped[Category] = relationship(back_populates="products")


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_cart_user_product"),
        CheckConstraint("quantity > 0", name="ck_cart_quantity_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(16), unique=True)  # человекочитаемый номер заказа
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(24), default=OrderStatus.CREATED, index=True)

    # Доставка
    delivery_method: Mapped[str | None] = mapped_column(String(16))  # DeliveryMethod
    delivery_price: Mapped[int] = mapped_column(Integer, default=0)  # назначает оператор
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # желаемое время доставки

    # Покупатель
    contact_name: Mapped[str] = mapped_column(String(128))
    contact_phone: Mapped[str] = mapped_column(String(32))
    address: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)

    # Деньги (вся предоплата — 50%, всегда; создаётся при заказе)
    items_total: Mapped[int] = mapped_column(Integer, default=0)  # сумма позиций
    total: Mapped[int] = mapped_column(Integer, default=0)  # итог с доставкой
    prepay_percent: Mapped[int] = mapped_column(Integer, default=50)
    prepay_amount: Mapped[int] = mapped_column(Integer, default=0)
    payment_method: Mapped[str | None] = mapped_column(String(16))  # PaymentMethod
    payment_status: Mapped[str] = mapped_column(String(16), default=PaymentStatus.NONE)
    payment_details: Mapped[str | None] = mapped_column(Text)  # что отправлено клиенту: ссылка/номер
    receipt_photo_file_id: Mapped[str | None] = mapped_column(String(255))  # чек от клиента
    deposit: Mapped[int] = mapped_column(Integer, default=0)  # залог за восточную посуду (возвратный)

    # Прочее
    prep_site: Mapped[str | None] = mapped_column(String(16))  # PrepSite: где готовят
    cancelled_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")
    events: Mapped[list["OrderEvent"]] = relationship(back_populates="order")


class OrderItem(Base):
    """Позиция заказа со снапшотом названия и цены на момент оформления.

    Для весовых товаров quantity хранится в ПОРЦИЯХ, а price — цена упаковки
    (например «(3 кг)»); product_grams — вес упаковки (None — штучный товар).
    Сумма позиции: portion_line_total(price, quantity, product_grams).
    """

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(160))  # снапшот
    price: Mapped[int] = mapped_column(Integer)  # снапшот: цена упаковки/штуки, тенге
    quantity: Mapped[int] = mapped_column(Integer)  # снапшот: порции/штуки
    product_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)  # снапшот веса упаковки

    order: Mapped[Order] = relationship(back_populates="items")


class OrderEvent(Base):
    """История переходов статус-машины заказа."""

    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24))
    actor: Mapped[str] = mapped_column(String(16))  # user / operator / system
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order: Mapped[Order] = relationship(back_populates="events")


class AiChatHistory(Base):
    """Персистентная история FAQ-диалогов ИИ-ассистента (вместо in-memory deque).

    Чистится по TTL (AI_HISTORY_TTL_HOURS): лениво при записи и при старте бота.
    """

    __tablename__ = "ai_chat_history"
    __table_args__ = (
        # чтение последних реплик и TTL-чистка идут по (user_id, created_at)
        Index("ix_ai_chat_history_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiLlmCall(Base):
    """Учёт LLM-вызовов для пер-юзер лимита (скользящее окно, AI_LLM_WINDOW_MINUTES).

    Строка создаётся перед каждым реальным обращением к провайдеру LLM;
    лимит (AI_LLM_LIMIT_PER_HOUR) считается как число строк за окно.
    """

    __tablename__ = "ai_llm_calls"
    __table_args__ = (
        Index("ix_ai_llm_calls_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaymentEvent(Base):
    """Идемпотентность Kaspi-платежей (ARCHITECTURE_REVIEW P0, фаза 2).

    Внешний платёжный webhook может прийти повторно (ретраи, дубли) — ловим
    уникальным ключом (external_id, type) и делаем INSERT ... ON CONFLICT
    DO NOTHING (через core.payments.record_payment_event): двойного
    зачисления/обновления не будет.
    """

    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("external_id", "type", name="uq_payment_events_ext_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64))  # id операции у провайдера
    type: Mapped[str] = mapped_column(String(32))  # payment.created / payment.captured / ...
    payload: Mapped[str | None] = mapped_column(Text)  # сырое тело webhook (для разбора)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())