"""Админка в боте: CRUD категорий и товаров (только для ADMIN_IDS)."""

import re

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.adm import (
    adm_cat_kb,
    adm_cats_kb,
    adm_main_kb,
    adm_prod_kb,
    adm_products_kb,
    adm_skip_kb,
)
from bot.texts import RU, fmt_price
from config.settings import get_settings
from core import admin as admin_srv
from core.catalog import get_category, get_product
from data.models import Category, Product

router = Router(name="admin")

_PRICE_RE = re.compile(r"^\d{3,8}$")

CAT_RE = re.compile(r"^adm:cat:(\d+)$")
CAT_RENAME_RE = re.compile(r"^adm:cat_rename:(\d+)$")
CAT_TOGGLE_RE = re.compile(r"^adm:cat_toggle:(\d+)$")
CAT_UP_RE = re.compile(r"^adm:cat_up:(\d+)$")
CAT_DOWN_RE = re.compile(r"^adm:cat_down:(\d+)$")
CAT_DEL_RE = re.compile(r"^adm:cat_del:(\d+)$")
CAT_PRODS_RE = re.compile(r"^adm:cat_products:(\d+)$")
PROD_RE = re.compile(r"^adm:prod:(\d+)$")
PROD_NEW_RE = re.compile(r"^adm:prod_new:(\d+)$")
PROD_NAME_RE = re.compile(r"^adm:prod_name:(\d+)$")
PROD_PRICE_RE = re.compile(r"^adm:prod_price:(\d+)$")
PROD_DESC_RE = re.compile(r"^adm:prod_desc:(\d+)$")
PROD_PHOTO_RE = re.compile(r"^adm:prod_photo:(\d+)$")
PROD_TOGGLE_RE = re.compile(r"^adm:prod_toggle:(\d+)$")
PROD_UP_RE = re.compile(r"^adm:prod_up:(\d+)$")
PROD_DOWN_RE = re.compile(r"^adm:prod_down:(\d+)$")
PROD_DEL_RE = re.compile(r"^adm:prod_del:(\d+)$")


class AdminState(StatesGroup):
    new_cat_name = State()
    cat_rename = State()
    prod_new_name = State()
    prod_new_price = State()
    prod_new_desc = State()
    prod_new_photo = State()
    prod_name = State()
    prod_price = State()
    prod_desc = State()
    prod_photo = State()


def _is_admin(user_id: int) -> bool:
    return user_id in get_settings().admin_id_list


async def _adm_check(obj: Message | CallbackQuery) -> bool:
    if not _is_admin(obj.from_user.id):
        if isinstance(obj, Message):
            await obj.answer(RU["admin_no_access"])
        else:
            await obj.answer()
        return False
    return True


def _cat_view_text(category: Category) -> str:
    count = len(category.products) if category.products else "—"
    hidden = "" if category.is_active else "\n🚫 Скрыта — клиенты её не видят"
    return RU["admin_cat_view"].format(name=category.name, hidden=hidden, count=count)


def _prod_view_text(product: Product) -> str:
    stop = "" if product.is_available else "\n🚫 Стоп-лист — клиенты не видят"
    photo = "✅ есть" if product.photo_file_id else "нет"
    return RU["admin_product_view"].format(
        name=product.name,
        stop=stop,
        price=fmt_price(product.price),
        desc=product.description or "—",
        photo=photo,
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not await _adm_check(message):
        return
    await message.answer(RU["admin_main"], reply_markup=adm_main_kb())


@router.callback_query(F.data == "adm:main")
async def adm_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not await _adm_check(callback):
        return
    await callback.answer()
    await callback.message.answer(RU["admin_main"], reply_markup=adm_main_kb())


@router.callback_query(F.data == "adm:help")
async def adm_help(callback: CallbackQuery) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    await callback.message.answer(
        "🛠 <b>Админка</b>\n\n"
        "• Категории и товары меняются сразу — клиент видит обновления в меню.\n"
        "• 🚫 — элемент скрыт (стоп-лист/скрытая категория).\n"
        "• Фото товара: нажми 🖼 Фото и отправь картинку.\n"
        "• Удаление товара не ломает историю заказов (там снапшоты).",
        reply_markup=adm_help_kb(),
    )


async def _show_cats(target: Message, session: AsyncSession) -> None:
    cats = list(
        await session.scalars(select(Category).order_by(Category.sort_order, Category.id))
    )
    if not cats:
        await target.answer("Категорий пока нет. Создай первую!", reply_markup=adm_cats_kb([]))
        return
    await target.answer(RU["admin_cats_title"], reply_markup=adm_cats_kb(cats))


@router.callback_query(F.data == "adm:cats")
async def adm_cats(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    if not await _adm_check(callback):
        return
    await callback.answer()
    await _show_cats(callback.message, session)


@router.callback_query(F.data.regexp(CAT_RE.pattern))
async def adm_cat_view(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    if not await _adm_check(callback):
        return
    await callback.answer()
    category = await get_category(session, int(CAT_RE.match(callback.data).group(1)))
    if category is None:
        await _show_cats(callback.message, session)
        return
    count = await session.scalar(select(func.count(Product.id)).where(Product.category_id == category.id))
    kb = adm_cat_kb(category.id, can_delete=not count)
    await callback.message.answer(_cat_view_text(category), reply_markup=kb)


@router.callback_query(F.data == "adm:cat_new")
async def adm_cat_new(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    await state.set_state(AdminState.new_cat_name)
    await callback.message.answer(RU["admin_cat_new_prompt"])


@router.message(StateFilter(AdminState.new_cat_name))
async def adm_cat_new_name(message: Message, session: AsyncSession, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not 1 <= len(name) <= 120:
        return
    category = await admin_srv.add_category(session, name)
    await state.clear()
    await message.answer(RU["admin_ok"].format(what=f"Категория «{category.name}» создана"))
    count = await session.scalar(select(func.count(Product.id)).where(Product.category_id == category.id))
    await message.answer(_cat_view_text(category), reply_markup=adm_cat_kb(category.id, can_delete=not count))


@router.callback_query(F.data.regexp(CAT_RENAME_RE.pattern))
async def adm_cat_rename(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    await state.set_state(AdminState.cat_rename)
    await state.update_data(cat_id=int(CAT_RENAME_RE.match(callback.data).group(1)))
    await callback.message.answer(RU["admin_cat_rename_prompt"])


@router.message(StateFilter(AdminState.cat_rename))
async def adm_cat_rename_text(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    category = await admin_srv.rename_category(session, data["cat_id"], (message.text or "").strip())
    await state.clear()
    if category is None:
        return
    await message.answer(RU["admin_ok"].format(what=f"Категория переименована: {category.name}"))


@router.callback_query(F.data.regexp(CAT_TOGGLE_RE.pattern))
async def adm_cat_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    category_id = int(CAT_TOGGLE_RE.match(callback.data).group(1))
    state = await admin_srv.toggle_category(session, category_id)
    label = "показана" if state else "скрыта"
    await callback.message.answer(RU["admin_ok"].format(what=f"Категория {label}"))


@router.callback_query(F.data.regexp(CAT_UP_RE.pattern))
async def adm_cat_up(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    await admin_srv.move_category(session, int(CAT_UP_RE.match(callback.data).group(1)), -1)


@router.callback_query(F.data.regexp(CAT_DOWN_RE.pattern))
async def adm_cat_down(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    await admin_srv.move_category(session, int(CAT_DOWN_RE.match(callback.data).group(1)), 1)


@router.callback_query(F.data.regexp(CAT_DEL_RE.pattern))
async def adm_cat_del(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    category_id = int(CAT_DEL_RE.match(callback.data).group(1))
    if not await admin_srv.delete_category_if_empty(session, category_id):
        await callback.message.answer(RU["admin_cat_has_products"])
        return
    await callback.message.answer(RU["admin_cat_deleted"])
    await _show_cats(callback.message, session)


async def _show_products(target: Message, session: AsyncSession, category_id: int) -> None:
    category = await get_category(session, category_id)
    if category is None:
        await _show_cats(target, session)
        return
    products = list(
        await session.scalars(
            select(Product).where(Product.category_id == category_id).order_by(Product.sort_order, Product.id)
        )
    )
    await target.answer(
        RU["admin_products_title"].format(category=category.name),
        reply_markup=adm_products_kb(products, category_id),
    )


@router.callback_query(F.data.regexp(CAT_PRODS_RE.pattern))
async def adm_cat_products(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    if not await _adm_check(callback):
        return
    await callback.answer()
    await _show_products(callback.message, session, int(CAT_PRODS_RE.match(callback.data).group(1)))


@router.callback_query(F.data.regexp(PROD_RE.pattern))
async def adm_prod_view(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    if not await _adm_check(callback):
        return
    await callback.answer()
    product = await get_product(session, int(PROD_RE.match(callback.data).group(1)))
    if product is None:
        return
    await callback.message.answer(
        _prod_view_text(product),
        reply_markup=adm_prod_kb(product.id, product.category_id),
    )


# --- Новый товар: имя → цена → описание → фото ---


@router.callback_query(F.data.regexp(PROD_NEW_RE.pattern))
async def adm_prod_new(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    category_id = int(PROD_NEW_RE.match(callback.data).group(1))
    category = await get_category(session, category_id)
    if category is None:
        return
    await state.set_state(AdminState.prod_new_name)
    await state.update_data(cat_id=category_id)
    await callback.message.answer(RU["admin_prod_new_name"].format(category=category.name))


@router.message(StateFilter(AdminState.prod_new_name))
async def adm_prod_new_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not 1 <= len(name) <= 160:
        return
    await state.update_data(prod_name=name)
    await state.set_state(AdminState.prod_new_price)
    await message.answer(RU["admin_prod_new_price"])


@router.message(StateFilter(AdminState.prod_new_price))
async def adm_prod_new_price(message: Message, state: FSMContext) -> None:
    digits = re.sub(r"\D", "", message.text or "")
    if not _PRICE_RE.match(digits):
        await message.answer(RU["admin_price_invalid"])
        return
    await state.update_data(prod_price=int(digits))
    await state.set_state(AdminState.prod_new_desc)
    await message.answer(RU["admin_prod_new_desc"], reply_markup=adm_skip_kb())


@router.message(StateFilter(AdminState.prod_new_desc))
async def adm_prod_new_desc(message: Message, state: FSMContext) -> None:
    await state.update_data(prod_desc=(message.text or "").strip() or None)
    await _ask_new_photo(message, state)


@router.callback_query(F.data == "adm:skip", StateFilter(AdminState.prod_new_desc))
async def adm_prod_new_desc_skip(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    await state.update_data(prod_desc=None)
    await _ask_new_photo(callback.message, state)


async def _ask_new_photo(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminState.prod_new_photo)
    await message.answer(RU["admin_prod_new_photo"], reply_markup=adm_skip_kb())


@router.message(StateFilter(AdminState.prod_new_photo))
async def adm_prod_new_photo(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    photo = message.photo[-1].file_id if message.photo else None
    await _create_product_from_state(message, session, state, data, photo)


@router.callback_query(F.data == "adm:skip", StateFilter(AdminState.prod_new_photo))
async def adm_prod_new_photo_skip(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    data = await state.get_data()
    await _create_product_from_state(callback.message, session, state, data, None)


async def _create_product_from_state(target: Message, session: AsyncSession, state: FSMContext, data: dict, photo: str | None) -> None:
    product = await admin_srv.add_product(
        session,
        data["cat_id"],
        data["prod_name"],
        data["prod_price"],
        description=data.get("prod_desc"),
    )
    if photo:
        await admin_srv.update_product(session, product.id, photo_file_id=photo)
    await state.clear()
    await target.answer(
        RU["admin_ok"].format(what=f"Товар «{product.name}» создан"),
        reply_markup=adm_prod_kb(product.id, product.category_id),
    )


# --- Правка существующего товара ---


@router.callback_query(F.data.regexp(PROD_NAME_RE.pattern))
async def adm_prod_name(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    await state.set_state(AdminState.prod_name)
    await state.update_data(prod_id=int(PROD_NAME_RE.match(callback.data).group(1)))
    await callback.message.answer(RU["admin_prod_name_prompt"])


@router.message(StateFilter(AdminState.prod_name))
async def adm_prod_name_text(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    product = await admin_srv.update_product(session, data["prod_id"], name=(message.text or "").strip())
    await state.clear()
    if product:
        await message.answer(RU["admin_ok"].format(what=f"Название обновлено: {product.name}"))


@router.callback_query(F.data.regexp(PROD_PRICE_RE.pattern))
async def adm_prod_price(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    await state.set_state(AdminState.prod_price)
    await state.update_data(prod_id=int(PROD_PRICE_RE.match(callback.data).group(1)))
    await callback.message.answer(RU["admin_prod_price_prompt"])


@router.message(StateFilter(AdminState.prod_price))
async def adm_prod_price_text(message: Message, session: AsyncSession, state: FSMContext) -> None:
    digits = re.sub(r"\D", "", message.text or "")
    if not _PRICE_RE.match(digits):
        await message.answer(RU["admin_price_invalid"])
        return
    data = await state.get_data()
    product = await admin_srv.update_product(session, data["prod_id"], price=int(digits))
    await state.clear()
    if product:
        await message.answer(RU["admin_ok"].format(what=f"Цена: {fmt_price(product.price)}"))


@router.callback_query(F.data.regexp(PROD_DESC_RE.pattern))
async def adm_prod_desc(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    await state.set_state(AdminState.prod_desc)
    await state.update_data(prod_id=int(PROD_DESC_RE.match(callback.data).group(1)))
    await callback.message.answer(RU["admin_prod_desc_prompt"])


@router.message(StateFilter(AdminState.prod_desc))
async def adm_prod_desc_text(message: Message, session: AsyncSession, state: FSMContext) -> None:
    text = (message.text or "").strip()
    description = None if text == "-" else (text or None)
    data = await state.get_data()
    product = await admin_srv.update_product(session, data["prod_id"], description=description)
    await state.clear()
    if product:
        await message.answer(RU["admin_ok"].format(what="Описание обновлено"))


@router.callback_query(F.data.regexp(PROD_PHOTO_RE.pattern))
async def adm_prod_photo(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    await state.set_state(AdminState.prod_photo)
    await state.update_data(prod_id=int(PROD_PHOTO_RE.match(callback.data).group(1)))
    await callback.message.answer(RU["admin_prod_photo_prompt"])


@router.message(StateFilter(AdminState.prod_photo))
async def adm_prod_photo_in(message: Message, session: AsyncSession, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text == "-":
        await _apply_photo(message, session, state, None)
        return
    if not message.photo:
        await message.answer("Жду фото (или отправь «-» чтобы убрать).")
        return
    await _apply_photo(message, session, state, message.photo[-1].file_id)


async def _apply_photo(target: Message, session: AsyncSession, state: FSMContext, file_id: str | None) -> None:
    data = await state.get_data()
    product = await admin_srv.update_product(session, data["prod_id"], photo_file_id=file_id)
    await state.clear()
    if product:
        what = "Фото обновлено" if file_id else "Фото убрано"
        await target.answer(RU["admin_ok"].format(what=what))


@router.callback_query(F.data.regexp(PROD_TOGGLE_RE.pattern))
async def adm_prod_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    product_id = int(PROD_TOGGLE_RE.match(callback.data).group(1))
    available = await admin_srv.toggle_product(session, product_id)
    label = "в продаже" if available else "скрыт (стоп-лист)"
    await callback.message.answer(RU["admin_ok"].format(what=f"Товар: {label}"))


@router.callback_query(F.data.regexp(PROD_UP_RE.pattern))
async def adm_prod_up(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    await admin_srv.move_product(session, int(PROD_UP_RE.match(callback.data).group(1)), -1)


@router.callback_query(F.data.regexp(PROD_DOWN_RE.pattern))
async def adm_prod_down(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    await admin_srv.move_product(session, int(PROD_DOWN_RE.match(callback.data).group(1)), 1)


@router.callback_query(F.data.regexp(PROD_DEL_RE.pattern))
async def adm_prod_del(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _adm_check(callback):
        return
    await callback.answer()
    product = await get_product(session, int(PROD_DEL_RE.match(callback.data).group(1)))
    if product is None:
        return
    category_id = product.category_id
    await admin_srv.delete_product(session, product.id)
    await callback.message.answer(RU["admin_prod_deleted"])
    await _show_products(callback.message, session, category_id)