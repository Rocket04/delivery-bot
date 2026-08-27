"""Перенос меню между базами (например, локальная разработка → VPS).

    1) На рабочей машине с полной БД:  python scripts/menu_sync.py export
       → создаёт data/seed/menu.json (категории, товары, цены, фото, стоп-лист).

    2) На сервере (в контейнере или venv): python scripts/menu_sync.py seed --reset
       → полностью заменяет меню данными из data/seed/menu.json.

Скрипт идемпотентен: повторный seed с --reset просто перезаливает меню.
Заказы и корзину не трогает (order_items хранят снапшоты, FK SET NULL).
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, func, select  # noqa: E402

from config.settings import get_settings  # noqa: E402
from data.db import get_session_maker, init_db  # noqa: E402
from data.models import Category, Product  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_PATH = os.path.join(ROOT, "data", "seed", "menu.json")


async def export_menu() -> None:
    init_db(get_settings().db_url)
    os.makedirs(os.path.dirname(SEED_PATH), exist_ok=True)
    async with get_session_maker()() as session:
        cats = list(await session.scalars(select(Category).order_by(Category.sort_order, Category.id)))
        payload = {
            "version": 1,
            "categories": [],
        }
        for cat in cats:
            prods = list(
                await session.scalars(
                    select(Product).where(Product.category_id == cat.id).order_by(Product.sort_order, Product.id)
                )
            )
            payload["categories"].append(
                {
                    "name": cat.name,
                    "sort_order": cat.sort_order,
                    "is_active": cat.is_active,
                    "products": [
                        {
                            "name": p.name,
                            "description": p.description,
                            "price": p.price,
                            "photo_file_id": p.photo_file_id,
                            "is_available": p.is_available,
                            "sort_order": p.sort_order,
                        }
                        for p in prods
                    ],
                }
            )
    with open(SEED_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    total = sum(len(c["products"]) for c in payload["categories"])
    print(f"exported: {len(payload['categories'])} categories, {total} products -> {SEED_PATH}")


async def seed_menu(reset: bool) -> None:
    if not os.path.exists(SEED_PATH):
        raise SystemExit(f"Не найден {SEED_PATH}. Сначала выполни export на машине с меню.")
    payload = json.load(open(SEED_PATH, encoding="utf-8"))
    init_db(get_settings().db_url)
    async with get_session_maker()() as session:
        if reset:
            await session.execute(delete(Product))
            await session.execute(delete(Category))
            await session.commit()
            print("old menu cleared")

        for cat in payload["categories"]:
            category = await session.scalar(select(Category).where(Category.name == cat["name"]))
            if category is None:
                category = Category(
                    name=cat["name"], sort_order=cat["sort_order"], is_active=cat["is_active"]
                )
                session.add(category)
                await session.flush()
            else:
                category.sort_order = cat["sort_order"]
                category.is_active = cat["is_active"]
            for p in cat["products"]:
                product = await session.scalar(
                    select(Product).where(Product.category_id == category.id, Product.name == p["name"])
                )
                fields = dict(
                    description=p.get("description"),
                    price=p["price"],
                    photo_file_id=p.get("photo_file_id"),
                    is_available=p.get("is_available", True),
                    sort_order=p.get("sort_order", 0),
                )
                if product is None:
                    session.add(Product(category_id=category.id, name=p["name"], **fields))
                else:
                    for k, v in fields.items():
                        setattr(product, k, v)
        await session.commit()

        cats_count = await session.scalar(select(func.count(Category.id)))
        prods_count = await session.scalar(select(func.count(Product.id)))
        print(f"seed done: {cats_count} categories, {prods_count} products")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Экспорт/импорт меню между базами")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("export", help="выгрузить меню из БД в data/seed/menu.json")
    seed_p = sub.add_parser("seed", help="залить меню из data/seed/menu.json в БД")
    seed_p.add_argument("--reset", action="store_true", help="очистить меню перед заливкой")
    args = parser.parse_args()

    if args.command == "export":
        asyncio.run(export_menu())
    else:
        asyncio.run(seed_menu(args.reset))