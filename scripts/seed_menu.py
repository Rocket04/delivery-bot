"""Заполнение меню стартовыми данными (идемпотентно: повторный запуск безопасен).

Цены и состав — ПЛЕЙСХОЛДЕРЫ под реальный ассортимент Food Plov;
точные значения владелец поправит в админке (стадия 4) или скажет мне.

Запуск:  python scripts/seed_menu.py  (из корня проекта, в venv)
Отдельная команда:  .venv\\Scripts\\python.exe scripts/seed_menu.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select  # noqa: E402

from config.settings import get_settings  # noqa: E402
from data.db import get_session_maker, init_db  # noqa: E402
from data.models import Category, Product  # noqa: E402

# Категория: [(название, описание, цена в тенге), ...]
MENU = {
    "Пловы": [
        ("Плов по-узбекски (порция)", "Рис, баранина, жёлтая морковь, зира, чеснок", 1800),
        ("Плов с курицей (порция)", "Курица, рис, морковь, куркума", 1600),
        ("Плов с бараниной (большая порция)", "Щедрая порция с косточкой", 2600),
        ("Плов «Царский»", "С казы и перепелиным яйцом", 3500),
        ("Плов на компанию (5–6 порций)", "Большой казан, подача к столу", 9000),
    ],
    "Манты и пельмени": [
        ("Манты с мясом (10 шт)", "Сочные, тонкое тесто, готовим на пару", 2500),
        ("Манты с тыквой (10 шт)", "Лёгкий вариант с тыквой", 2200),
        ("Пельмени домашние (0,5 кг)", "Ручная лепка", 2000),
        ("Пельмени домашние (1 кг)", "Ручная лепка, на компанию", 3800),
        ("Манты на заказ (30 шт)", "Под заказ, минимум за 24 часа", 7000),
    ],
    "Шашлыки и мясо": [
        ("Шашлык из баранины (100 г)", "На углях, из свежей баранины", 1200),
        ("Шашлык из курицы (100 г)", "Маринад домашний", 900),
        ("Люля-кебаб (100 г)", "Из бараньего фарша", 1100),
        ("Казы (100 г)", "Домашняя колбаса по-казахски", 1500),
        ("Самса с мясом (шт)", "Слоёная, с луком и мясом", 500),
    ],
    "Комплексные обеды": [
        ("Комплексный обед №1", "Плов + салат + самса + чай", 2500),
        ("Комплексный обед №2", "Плов с курицей + салат + чай", 2300),
        ("Комплексный обед №3", "Манты + салат + чай", 2900),
    ],
    "Салаты и закуски": [
        ("Салат «Ачучук» (300 г)", "Томаты, лук, зелень, перец", 900),
        ("Салат «Цезарь» (250 г)", "Курица, пармезан, соус", 1400),
        ("Лепёшка (шт)", "Только из печи", 300),
        ("Сырники со сметаной (6 шт)", "Домашний творог", 1200),
    ],
    "Напитки": [
        ("Чай чёрный (1 л)", "Завариваем в чайнике", 500),
        ("Чай зелёный (1 л)", "Завариваем в чайнике", 500),
        ("Компот (1 л)", "Из сухофруктов", 700),
        ("Вода 1,5 л", "Без газа", 500),
        ("Квас (1 л)", "Домашний", 800),
    ],
}


async def main() -> None:
    init_db(get_settings().db_url)
    async with get_session_maker()() as session:
        for order, (cat_name, items) in enumerate(MENU.items()):
            category = await session.scalar(select(Category).where(Category.name == cat_name))
            if category is None:
                category = Category(name=cat_name, sort_order=order, is_active=True)
                session.add(category)
                await session.flush()
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
        await session.commit()
        cats = await session.scalar(select(func.count(Category.id)))
        prods = await session.scalar(select(func.count(Product.id)))
        print(f"seed done: {cats} categories, {prods} products")


if __name__ == "__main__":
    asyncio.run(main())