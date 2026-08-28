"""Сервисы каталога. Не зависят от Telegram."""

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.models import Category, Product

# Вес/объём/количество: «0,5 кг», «500 г», «1 л», «50 шт», «10-12 шт»
_WEIGHT_RE = re.compile(r"\d+[.,]?-?\d*\s*(кг|г|л|мл|шт)", re.IGNORECASE)
# Вес упаковки в названии товара: «Плов Ханский (3 кг)», «(4,5 кг)»
_PKG_KG_RE = re.compile(r"\((\d+(?:[.,]\d+)?)\s*кг\)", re.IGNORECASE)


def product_grams(name: str) -> int | None:
    """Вес упаковки из названия «(3 кг)» → 3000 г. None — штучный товар (манты и т.п.)."""
    m = _PKG_KG_RE.search(name)
    if not m:
        return None
    return int(round(float(m.group(1).replace(",", ".")) * 1000))


def portions_in_package(name: str, portion_grams: int = 300) -> int:
    """Сколько целых порций в упаковке (для подсказок: 3 кг → 10, 4 кг → 13)."""
    grams = product_grams(name)
    if not grams:
        return 1
    return max(1, round(grams / portion_grams))


def portion_qty_label(name: str, qty: int, portion_grams: int = 300) -> str:
    """Человекочитаемое количество: «15 порций (4,5 кг)» для весовых, «×15» для штучных."""
    grams = product_grams(name)
    if not grams:
        return f"×{qty}"
    kg = qty * portion_grams / 1000
    kg_str = f"{kg:g}".replace(".", ",")
    return f"{qty} порций ({kg_str} кг)"


def portion_line_total(price: int, qty: int, grams: int | None, portion_grams: int = 300) -> int:
    """Сумма строки. Весовой товар: цена упаковки × вес порций / вес упаковки,
    округление вверх до тенге (10 порций по 300 г из «(3 кг)» = ровно цена упаковки).
    Штучный товар: цена × количество."""
    if not grams or grams <= 0:
        return price * qty
    # -(-a // b) — целочисленное деление с округлением вверх
    return -(-price * qty * portion_grams // grams)


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


def extract_weight(description: str | None) -> str | None:
    """Первая граммовка/объём из описания: «0,5 кг», «500 г», «10 шт» или None."""
    if not description:
        return None
    m = _WEIGHT_RE.search(description)
    if not m:
        return None
    return m.group(0).strip().replace(".", ",").lower()


def product_weight_label(name: str, description: str | None) -> str | None:
    """Граммовка для списка меню: из названия или описания, без дублей.

    Если вес уже есть в названии («Плов Ханский (3 кг)») — дополнительный
    суффикс не нужен. Иначе берём первое упоминание из описания.
    """
    if name and _WEIGHT_RE.search(name):
        return None
    return extract_weight(description)