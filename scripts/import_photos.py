"""Заливка фото товаров в бота.

Каждое фото отправляется ботом в чат администратора (как «📸 Название»),
Telegram возвращает file_id — он и сохраняется в БД к товару.
Соответствие «фото → товар» берётся из .tmp/tilda/menu_parsed.json (страница, индекс).

Запуск:  python scripts/import_photos.py
"""

import asyncio
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot  # noqa: E402
from aiogram.types import FSInputFile  # noqa: E402
from sqlalchemy import select  # noqa: E402

from config.settings import get_settings  # noqa: E402
from data.db import get_session_maker, init_db  # noqa: E402
from data.models import Category, Product  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(ROOT, ".tmp", "tilda", "menu_parsed.json")
IMGDIR = os.path.join(ROOT, ".tmp", "tilda", "img")

PAGE_CAT = {
    "meals": "Горячие блюда",
    "salads": "Салаты",
    "set_menu": "Фирменные сеты",
    "additional_meals": "Дополнительное меню",
    "new_year_combos": "Новогодние сеты",
}
SNACK_RANGE = [
    ("Закуски мясные", 0, 5),
    ("Закуски рыбные", 5, 13),
    ("Закуски овощные и холодные", 13, 21),
    ("Соусы", 21, 27),
]
DRINK_SPLIT = ["Coca Cola", "Fanta", "Sprite", "Pepsi"]


def image_for(page: str, idx: int) -> str | None:
    hits = glob.glob(os.path.join(IMGDIR, f"{page}_{idx}.*"))
    return hits[0] if hits else None


async def main() -> None:
    settings = get_settings()
    if not settings.admin_id_list:
        raise SystemExit("ADMIN_IDS пуст — фото некому отправлять")
    menu = json.load(open(JSON_PATH, encoding="utf-8"))
    init_db(settings.db_url)
    bot = Bot(settings.bot_token)
    admin = settings.admin_id_list[0]

    sent = linked = failed = 0
    async with get_session_maker()() as session:
        for page, items in menu.items():
            for idx, item in enumerate(items):
                title = (item.get("title") or "").strip()
                img_path = image_for(page, idx)
                if not title or not img_path:
                    continue
                cat_name = PAGE_CAT.get(page, "")
                if page == "snacks":
                    for cat2, start, end in SNACK_RANGE:
                        if start <= idx < end:
                            cat_name = cat2
                            break
                target_names = None
                if page == "drinks":
                    brand = next((b for b in DRINK_SPLIT if title.startswith(b) or b in title), None)
                    if brand:
                        target_names = [f"{brand} 0,5 л", f"{brand} 1 л"]
                    else:
                        target_names = [title]
                else:
                    target_names = [title]
                if not cat_name:
                    continue

                try:
                    msg = await bot.send_photo(admin, FSInputFile(img_path), caption=f"📸 {title}")
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    print("SEND FAIL:", title, str(exc)[:100])
                    await asyncio.sleep(1)
                    continue
                file_id = msg.photo[-1].file_id
                sent += 1

                category = await session.scalar(select(Category).where(Category.name == cat_name))
                if category is None:
                    print("CAT NOT FOUND:", cat_name)
                    continue
                for name in target_names:
                    product = await session.scalar(
                        select(Product).where(Product.category_id == category.id, Product.name == name)
                    )
                    if product is None:
                        print("PROD NOT FOUND:", cat_name, "/", name)
                        continue
                    product.photo_file_id = file_id
                    linked += 1
                await session.commit()
                await asyncio.sleep(0.35)

    await bot.session.close()
    print(f"photos sent: {sent}, linked: {linked}, fails: {failed}")


if __name__ == "__main__":
    asyncio.run(main())