import re

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.catalog import categories_kb, product_card_kb, products_kb
from bot.texts import RU, fmt_price
from bot.utils import edit_or_answer
from config.settings import get_settings
from core.cart import cart_qty, change_quantity
from core.catalog import (
    get_category,
    get_product,
    list_active_categories,
    list_available_products,
    portion_line_total,
    portion_qty_label,
    portions_in_package,
    product_grams,
    product_weight_label,
)
from core.users import get_user_by_tg_id
from data.models import Product

router = Router(name="catalog")

CAT_RE = re.compile(r"^cat:(\d+)$")
PROD_RE = re.compile(r"^prod:(\d+)$")
QTY_RE = re.compile(r"^qty:(\d+):(-?\d+)$")


async def db_user_id(session: AsyncSession, tg_id: int) -> int:
    user = await get_user_by_tg_id(session, tg_id)
    return user.id if user else 0


def _product_card_text(product: Product, qty: int) -> str:
    settings = get_settings()
    portion = settings.portion_grams
    if qty:
        in_cart = RU["in_cart"].format(
            label=portion_qty_label(product.name, qty, portion),
            sum=fmt_price(portion_line_total(product.price, qty, product_grams(product.name), portion)),
        )
    else:
        in_cart = "В корзине: 0"
    # подсказка «3 кг = 10 порций · 1 755 ₸/порция» для весовых товаров
    grams = product_grams(product.name)
    pack = ""
    if grams:
        per_portion = round(product.price * portion / grams)
        pack = RU["product_pack_hint"].format(
            grams=f"{grams / 1000:g}".replace(".", ","),
            portions=portions_in_package(product.name, portion),
            per_portion=fmt_price(per_portion),
        )
    return RU["product_card"].format(
        name=product.name,
        desc=product.description or "",
        pack=pack,
        price=fmt_price(product.price),
        in_cart=in_cart,
    )


async def show_product_card(message: Message, product: Product, qty: int, *, edit: bool) -> None:
    """Карточка товара: фото (если есть) + текст + кнопки [- qty +].

    Если photo_file_id недействителен (чужой бот/файл удалён) — Telegram отдаёт
    BadRequest, и карточка показывается текстом, а не «Ошибкой бота».
    """
    kb = product_card_kb(product.id, qty, product.category_id)
    text = _product_card_text(product, qty)
    if product.photo_file_id:
        try:
            if edit:
                try:
                    await message.edit_caption(caption=text, reply_markup=kb)
                    return
                except TelegramBadRequest:
                    pass
            await message.answer_photo(product.photo_file_id, caption=text, reply_markup=kb)
        except TelegramBadRequest as exc:
            if "wrong file identifier" not in str(exc).lower() and "not found" not in str(exc).lower():
                raise
            # file_id устарел/принадлежит другому боту — фолбэк на текстовую карточку
            if edit:
                try:
                    await message.edit_text(text, reply_markup=kb)
                    return
                except TelegramBadRequest:
                    pass
            await message.answer(text, reply_markup=kb)
    else:
        if edit:
            try:
                await message.edit_text(text, reply_markup=kb)
                return
            except TelegramBadRequest:
                pass
        await message.answer(text, reply_markup=kb)


async def _show_categories(message: Message, session: AsyncSession) -> None:
    cats = await list_active_categories(session)
    if not cats:
        await edit_or_answer(message, RU["menu_empty"])
        return
    await edit_or_answer(message, RU["menu_title"], categories_kb(cats))


@router.message(Command("menu"))
async def cmd_menu(message: Message, session: AsyncSession) -> None:
    await _show_categories(message, session)


@router.callback_query(F.data == "main:menu")
async def cb_main_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    await _show_categories(callback.message, session)


@router.callback_query(F.data == "cat:open")
async def cb_categories(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    await _show_categories(callback.message, session)


def _category_list_text(products: list[Product]) -> str:
    """Нумерованный список: название, граммовка (из описания), цена — всё в тексте, ничего не обрезается."""
    lines = []
    for i, p in enumerate(products, 1):
        weight = product_weight_label(p.name, p.description)
        suffix = f" ({weight})" if weight else ""
        lines.append(f"{i}. {p.name}{suffix} — {fmt_price(p.price)}")
    return "\n".join(lines)


@router.callback_query(F.data.regexp(r"^cat:\d+$"))
async def cb_category(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    match = CAT_RE.match(callback.data)
    category = await get_category(session, int(match.group(1)))
    if category is None:
        await _show_categories(callback.message, session)
        return
    products = await list_available_products(session, category.id)
    body = _category_list_text(products)
    title = f"🍛 <b>{category.name}</b>\n\n{body}"
    if not products:
        await edit_or_answer(callback.message, RU["category_empty"], products_kb([], category.id))
        return
    await edit_or_answer(callback.message, title, products_kb(products, category.id))


@router.callback_query(F.data.regexp(r"^prod:\d+$"))
async def cb_product(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    match = PROD_RE.match(callback.data)
    product = await get_product(session, int(match.group(1)))
    if product is None:
        await callback.message.answer(RU["product_not_found"])
        return
    qty = await cart_qty(session, await db_user_id(session, callback.from_user.id), product.id)
    await show_product_card(callback.message, product, qty, edit=True)


@router.callback_query(F.data.regexp(r"^qty:\d+:-?\d+$"))
async def cb_qty(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    match = QTY_RE.match(callback.data)
    product_id, delta = int(match.group(1)), int(match.group(2))
    product = await get_product(session, product_id)
    if product is None:
        await callback.message.answer(RU["product_not_found"])
        return
    if delta == 0:
        return  # информационная кнопка «В корзине: N»
    user_id = await db_user_id(session, callback.from_user.id)
    if delta > 0 and not product.is_available:
        await callback.message.answer(RU["product_unavailable"])
        return
    qty = await change_quantity(session, user_id, product.id, delta)
    await show_product_card(callback.message, product, qty, edit=True)