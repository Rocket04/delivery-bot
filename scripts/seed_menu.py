"""Полный ресид меню из реальных данных сайта (Tilda: test-center-plov.tilda.ws).

Источник данных: .tmp/tilda/menu_parsed.json — результат парсинга страниц сайта
(названия, описания, цены, порядок). Картинки: .tmp/tilda/img/<page>_<idx>.*

Запуск с очисткой старого меню:
    python scripts/seed_menu.py --reset

Без --reset — только добавляет недостающие позиции (идемпотентно).
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, select  # noqa: E402

from config.settings import get_settings  # noqa: E402
from data.db import get_session_maker, init_db  # noqa: E402
from data.models import Category, Product  # noqa: E402

JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".tmp", "tilda", "menu_parsed.json")

# Страница сайта → категория бота. Закуски/напитки дробятся подкатегориями сайта.
PAGE_CATEGORIES = [
    ("meals", "Горячие блюда"),
    ("salads", "Салаты"),
]

# Закуски: индексы на странице snacks (27 позиций)
SNACK_SPLIT = [
    (0, 5, "Закуски мясные"),
    (5, 13, "Закуски рыбные"),
    (13, 21, "Закуски овощные и холодные"),
    (21, 27, "Соусы"),
]

DRINKS_SPLIT_PRICES = {  # «700/1200» → два товара
    "Coca Cola": (700, 1200),
    "Fanta": (700, 1200),
    "Sprite": (700, 1200),
    "Pepsi": (700, 1200),
}


def load_menu() -> dict:
    if not os.path.exists(JSON_PATH):
        raise SystemExit(f"Не найден {JSON_PATH} — сначала спарси сайт (или удали сид-зависимость от файла).")
    return json.load(open(JSON_PATH, encoding="utf-8"))


async def add_items(session, category: Category, items: list[tuple[str, str, int]]) -> None:
    for i, (name, desc, price) in enumerate(items):
        exists = await session.scalar(
            select(Product).where(Product.category_id == category.id, Product.name == name)
        )
        if exists is None:
            session.add(
                Product(
                    category_id=category.id,
                    name=name,
                    description=desc,
                    price=price,
                    sort_order=i,
                    is_available=True,
                )
            )


async def get_category(session, name: str, order: int) -> Category:
    category = await session.scalar(select(Category).where(Category.name == name))
    if category is None:
        category = Category(name=name, sort_order=order, is_active=True)
        session.add(category)
        await session.flush()
    return category


async def main(reset: bool, skip_promo: bool) -> None:
    menu = load_menu()
    init_db(get_settings().db_url)
    async with get_session_maker()() as session:
        if reset:
            await session.execute(delete(Product))
            await session.execute(delete(Category))
            await session.commit()
            print("old menu cleared")

        cat_order = 0

        async def feed(cat_name: str, items: list) -> None:
            nonlocal cat_order
            cat = await get_category(session, cat_name, cat_order)
            cat_order += 1
            baked = []
            for it in items:
                name = (it.get("title") or "").strip()
                price = it.get("price")
                if not name or price is None:
                    continue
                baked.append((name, (it.get("desc") or "").strip(), int(price)))
            await add_items(session, cat, baked)

        for page, cat_name in PAGE_CATEGORIES + [("set_menu", "Фирменные сеты"), ("additional_meals", "Дополнительное меню")]:
            if skip_promo and page in ("new_year_combos",):
                continue
            await feed(cat_name, menu.get(page, []))

        # Закуски по подкатегориям
        snacks = menu.get("snacks", [])
        for start, end, cat_name in SNACK_SPLIT:
            await feed(cat_name, snacks[start:end])

        # Напитки: газировка делится на 0,5/1 л
        drinks = menu.get("drinks", [])
        baked_drinks = []
        for it in drinks:
            name, price = (it.get("title") or "").strip(), it.get("price")
            if not name:
                continue
            if price is None:
                base, small, big = None, None, None
                for brand, (p_small, p_big) in DRINKS_SPLIT_PRICES.items():
                    if name.startswith(brand) or brand in name:
                        base, small, big = brand, p_small, p_big
                        break
                if base:
                    baked_drinks.append((f"{base} 0,5 л", "Газированный напиток, 0,5 л", small))
                    baked_drinks.append((f"{base} 1 л", "Газированный напиток, 1 л", big))
                continue
            baked_drinks.append((name, (it.get("desc") or "").strip(), int(price)))
        await feed("Напитки", [{"title": n, "desc": d, "price": p} for n, d, p in baked_drinks])

        if not skip_promo:
            await feed("Новогодние сеты", menu.get("new_year_combos", []))

        await session.commit()
        from sqlalchemy import func

        cats = await session.scalar(select(func.count(Category.id)))
        prods = await session.scalar(select(func.count(Product.id)))
        print(f"seed done: {cats} categories, {prods} products")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="очистить меню перед заливкой")
    parser.add_argument("--skip-promo", action="store_true", help="не добавлять новогодние сеты")
    args = parser.parse_args()
    asyncio.run(main(args.reset, args.skip_promo))