from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def adm_main_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🏷 Категории", callback_data="adm:cats"))
    b.row(InlineKeyboardButton(text="🧾 Как это работает", callback_data="adm:help"))
    return b.as_markup()


def adm_help_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:main"))
    return b.as_markup()


def adm_cats_kb(categories) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for c in categories:
        label = ("🚫 " if not c.is_active else "") + c.name
        b.row(InlineKeyboardButton(text=label, callback_data=f"adm:cat:{c.id}"))
    b.row(InlineKeyboardButton(text="➕ Новая категория", callback_data="adm:cat_new"))
    b.row(InlineKeyboardButton(text="⬅️ В админку", callback_data="adm:main"))
    return b.as_markup()


def adm_cat_kb(category_id: int, can_delete: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"adm:cat_rename:{category_id}"))
    b.row(
        InlineKeyboardButton(text="👁 Показать/Скрыть", callback_data=f"adm:cat_toggle:{category_id}"),
        InlineKeyboardButton(text="🍛 Товары", callback_data=f"adm:cat_products:{category_id}"),
    )
    b.row(
        InlineKeyboardButton(text="⬆️", callback_data=f"adm:cat_up:{category_id}"),
        InlineKeyboardButton(text="⬇️", callback_data=f"adm:cat_down:{category_id}"),
    )
    if can_delete:
        b.row(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:cat_del:{category_id}"))
    b.row(InlineKeyboardButton(text="⬅️ Категории", callback_data="adm:cats"))
    return b.as_markup()


def adm_products_kb(products, category_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in products:
        label = ("🚫 " if not p.is_available else "") + f"{p.name}"
        b.row(InlineKeyboardButton(text=label, callback_data=f"adm:prod:{p.id}"))
    b.row(InlineKeyboardButton(text="➕ Новый товар", callback_data=f"adm:prod_new:{category_id}"))
    b.row(InlineKeyboardButton(text="⬅️ Категория", callback_data=f"adm:cat:{category_id}"))
    b.row(InlineKeyboardButton(text="🏷 Категории", callback_data="adm:cats"))
    return b.as_markup()


def adm_prod_kb(product_id: int, category_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ Название", callback_data=f"adm:prod_name:{product_id}"))
    b.row(
        InlineKeyboardButton(text="💰 Цена", callback_data=f"adm:prod_price:{product_id}"),
        InlineKeyboardButton(text="📝 Описание", callback_data=f"adm:prod_desc:{product_id}"),
    )
    b.row(
        InlineKeyboardButton(text="🖼 Фото", callback_data=f"adm:prod_photo:{product_id}"),
        InlineKeyboardButton(text="👁 Стоп-лист", callback_data=f"adm:prod_toggle:{product_id}"),
    )
    b.row(
        InlineKeyboardButton(text="⬆️", callback_data=f"adm:prod_up:{product_id}"),
        InlineKeyboardButton(text="⬇️", callback_data=f"adm:prod_down:{product_id}"),
    )
    b.row(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:prod_del:{product_id}"))
    b.row(InlineKeyboardButton(text="⬅️ Товары", callback_data=f"adm:cat_products:{category_id}"))
    return b.as_markup()


def adm_skip_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="Пропустить", callback_data="adm:skip"))
    return b.as_markup()