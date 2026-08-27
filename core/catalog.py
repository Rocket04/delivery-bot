"""Сервисы каталога. Не зависят от Telegram."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.models import Category, Product


async def list_active_categories(session: AsyncSession) -> list[Category]:
    return list(
        await session.scalars(
            select(Category)
            .where(Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.id)
        )
    )


async def list_available_products(session: AsyncSession, category_id: int) -> list[Product]:
    return list(
        await session.scalars(
            select(Product)
            .where(Product.category_id == category_id, Product.is_available.is_(True))
            .order_by(Product.sort_order, Product.id)
        )
    )


async def get_product(session: AsyncSession, product_id: int) -> Product | None:
    return await session.get(Product, product_id)


async def get_category(session: AsyncSession, category_id: int) -> Category | None:
    return await session.get(Category, category_id)