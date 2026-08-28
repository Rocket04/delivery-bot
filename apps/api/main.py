"""Mini App (фаза 2) — подготовительный FastAPI-скелет поверх core, без Telegram.

По ARCHITECTURE_REVIEW (шаг 1 фазы 2): те же core-сервисы, эндпоинты
GET /menu, POST /orders, GET /orders/{id}. Long polling бота не трогаем.

Ограничения подготовки (осознанно вне этого скелета):
- авторизация initData (HMAC-SHA256 бот-токена) — следующий шаг;
- деплой не выполняется: нужен домен + HTTPS на ВМ (владелец);
- Kaspi Pay / webhook — отдельные экспы (идемпотентность payment_events, P0).

Секреты в коде отсутствуют; DB_URL — из .env (как у бота).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.schemas import (
    MenuCategoryOut,
    MenuProductOut,
    OrderCreateIn,
    OrderItemOut,
    OrderOut,
)
from config.settings import get_settings
from core.cart import change_quantity
from core.catalog import (
    get_product,
    list_active_categories,
    list_available_products,
    portions_in_package,
    product_grams,
    product_weight_label,
)
from core.ordering import OrderError, create_order, get_order
from core.users import upsert_user
from data.db import dispose_db, get_session_maker, init_db
from data.models import OrderItem

@asynccontextmanager
async def lifespan(_: FastAPI):
    """При старте uvicorn — движок БД (как у бота); при остановке — dispose."""
    init_db(get_settings().db_url)
    yield
    await dispose_db()


app = FastAPI(title="Food Plov API", version="0.1.0", lifespan=lifespan)


async def get_session() -> AsyncSession:
    async with get_session_maker()() as session:
        yield session


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _product_out(product) -> MenuProductOut:
    grams = product_grams(product.name)
    return MenuProductOut(
        id=product.id,
        name=product.name,
        description=product.description,
        price=product.price,
        weight_label=product_weight_label(product.name, product.description),
        portions=portions_in_package(product.name, get_settings().portion_grams) if grams else None,
    )


@app.get("/menu", response_model=list[MenuCategoryOut])
async def menu(session: AsyncSession = Depends(get_session)) -> list[MenuCategoryOut]:
    """Активные категории с доступными позициями (цены и порции — как в боте)."""
    result: list[MenuCategoryOut] = []
    for category in await list_active_categories(session):
        products = [
            _product_out(p)
            for p in await list_available_products(session, category.id)
        ]
        result.append(MenuCategoryOut(id=category.id, name=category.name, products=products))
    return result


async def _order_items_out(session: AsyncSession, order_id: int) -> list[OrderItemOut]:
    """Позиции заказа (явный select: relationship при lazy-доступе async-недоступен)."""
    rows = (
        await session.scalars(
            select(OrderItem).where(OrderItem.order_id == order_id).order_by(OrderItem.id)
        )
    ).all()
    return [
        OrderItemOut(
            name=it.name, price=it.price, quantity=it.quantity, product_grams=it.product_grams
        )
        for it in rows
    ]


@app.post("/orders", response_model=OrderOut, status_code=201)
async def place_order(
    payload: OrderCreateIn, session: AsyncSession = Depends(get_session)
) -> OrderOut:
    """Создаёт заказ: позиции в корзину → create_order (те же бизнес-правила)."""
    settings = get_settings()
    user = await upsert_user(session, payload.telegram_id)
    for item in payload.items:
        if await get_product(session, item.product_id) is None:
            raise HTTPException(status_code=404, detail=f"Товар {item.product_id} не найден")
        await change_quantity(session, user.id, item.product_id, item.quantity)
    try:
        order = await create_order(
            session,
            user.id,
            settings=settings,
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            delivery_method=payload.delivery_method,
            address=payload.address,
            scheduled_for=payload.scheduled_for,
            comment=None,
            deposit=payload.deposit,
        )
    except OrderError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    items = await _order_items_out(session, order.id)
    return OrderOut(
        id=order.id,
        number=order.number,
        status=order.status,
        total=order.total,
        prepay_amount=order.prepay_amount,
        delivery_method=order.delivery_method,
        scheduled_for=order.scheduled_for,
        items=items,
    )


@app.get("/orders/{order_id}", response_model=OrderOut)
async def order_detail(order_id: int, session: AsyncSession = Depends(get_session)) -> OrderOut:
    """Статус заказа по id (для личного кабинета Mini App)."""
    order = await get_order(session, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    items = await _order_items_out(session, order.id)
    return OrderOut(
        id=order.id,
        number=order.number,
        status=order.status,
        total=order.total,
        prepay_amount=order.prepay_amount,
        delivery_method=order.delivery_method,
        scheduled_for=order.scheduled_for,
        items=items,
    )