"""Сервисы админки: CRUD категорий и товаров, сортировка, стоп-лист.

Не зависят от Telegram.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from data.models import Category, Product


async def add_category(session: AsyncSession, name: str) -> Category:
    max_order = await session.scalar(select(func.max(Category.sort_order)))
    category = Category(name=name.strip(), sort_order=(max_order or 0) + 1, is_active=True)
    session.add(category)
    await session.commit()
    return category


async def rename_category(session: AsyncSession, category_id: int, name: str) -> Category | None:
    category = await session.get(Category, category_id)
    if category is None:
        return None
    category.name = name.strip()
    await session.commit()
    return category


async def toggle_category(session: AsyncSession, category_id: int) -> bool | None:
    """Скрывает/показывает категорию. Возвращает новое состояние или None."""
    category = await session.get(Category, category_id)
    if category is None:
        return None
    category.is_active = not category.is_active
    await session.commit()
    return category.is_active


async def delete_category_if_empty(session: AsyncSession, category_id: int) -> bool:
    """Удаляет категорию, только если в ней нет товаров."""
    count = await session.scalar(
        select(func.count(Product.id)).where(Product.category_id == category_id)
    )
    if count:
        return False
    category = await session.get(Category, category_id)
    if category is not None:
        await session.delete(category)
        await session.commit()
    return True


async def move_category(session: AsyncSession, category_id: int, delta: int) -> None:
    categories = list(
        await session.scalars(select(Category).order_by(Category.sort_order, Category.id))
    )
    idx = next((i for i, c in enumerate(categories) if c.id == category_id), None)
    j = idx + delta if idx is not None else -1
    if idx is None or not (0 <= j < len(categories)):
        return
    categories[idx].sort_order, categories[j].sort_order = (
        categories[j].sort_order,
        categories[idx].sort_order,
    )
    await session.commit()


async def add_product(
    session: AsyncSession,
    category_id: int,
    name: str,
    price: int,
    description: str | None = None,
) -> Product:
    max_order = await session.scalar(
        select(func.max(Product.sort_order)).where(Product.category_id == category_id)
    )
    product = Product(
        category_id=category_id,
        name=name.strip(),
        price=price,
        description=description.strip() if description else None,
        sort_order=(max_order or 0) + 1,
        is_available=True,
    )
    session.add(product)
    await session.commit()
    return product


async def update_product(session: AsyncSession, product_id: int, **fields) -> Product | None:
    """Обновляет произвольные поля товара (name, price, description, photo_file_id...)."""
    product = await session.get(Product, product_id)
    if product is None:
        return None
    for key, value in fields.items():
        setattr(product, key, value)
    await session.commit()
    return product


async def toggle_product(session: AsyncSession, product_id: int) -> bool | None:
    """Стоп-лист: скрывает/показывает товар. Возвращает новое состояние или None."""
    product = await session.get(Product, product_id)
    if product is None:
        return None
    product.is_available = not product.is_available
    await session.commit()
    return product.is_available


async def delete_product(session: AsyncSession, product_id: int) -> None:
    product = await session.get(Product, product_id)
    if product is not None:
        await session.delete(product)
        await session.commit()


async def move_product(session: AsyncSession, product_id: int, delta: int) -> None:
    product = await session.get(Product, product_id)
    if product is None:
        return
    products = list(
        await session.scalars(
            select(Product)
            .where(Product.category_id == product.category_id)
            .order_by(Product.sort_order, Product.id)
        )
    )
    idx = next((i for i, p in enumerate(products) if p.id == product_id), None)
    j = idx + delta if idx is not None else -1
    if idx is None or not (0 <= j < len(products)):
        return
    products[idx].sort_order, products[j].sort_order = (
        products[j].sort_order,
        products[idx].sort_order,
    )
    await session.commit()