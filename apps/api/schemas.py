"""Pydantic-схемы API (фаза 2, Mini App) — версионирование контрактов core (ARCHITECTURE_REVIEW P2).

Деньги — целые тенге; порции — как в Telegram-боте (1 порция = PORTION_GRAMS г).
"""

from datetime import datetime

from pydantic import BaseModel, Field


class MenuProductOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    price: int  # тенге (цена упаковки/штуки)
    weight_label: str | None = None  # «3 кг», «50 шт», «0,5 кг»
    portions: int | None = None  # порций в упаковке (весовые); None — штучный товар


class MenuCategoryOut(BaseModel):
    id: int
    name: str
    products: list[MenuProductOut]


class OrderItemIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)  # порции для весовых, штуки для остальных


class OrderCreateIn(BaseModel):
    telegram_id: int  # позже — из initData Mini App (HMAC-SHA256 от бот-токена)
    contact_name: str = "Клиент"
    contact_phone: str
    delivery_method: str = "own"  # own | yandex | pickup (DeliveryMethod)
    address: str | None = None
    scheduled_for: datetime
    items: list[OrderItemIn] = Field(min_length=1)
    deposit: int = 0  # залог за восточную посуду (возвратный)


class OrderItemOut(BaseModel):
    name: str
    price: int  # снапшот
    quantity: int  # снапшот: порции/штуки
    product_grams: int | None = None  # снапшот веса упаковки


class OrderOut(BaseModel):
    id: int
    number: str
    status: str
    total: int  # тенге
    prepay_amount: int  # 50%, как в боте
    delivery_method: str | None = None
    scheduled_for: datetime | None = None
    items: list[OrderItemOut]