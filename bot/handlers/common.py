from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.texts import RU

router = Router(name="common")

# Кнопки главного меню, работающие как заглушки до стадий 2–3
_PLACEHOLDERS = {
    "main:menu": RU["menu_soon"],
    "main:cart": RU["cart_soon"],
    "main:orders": RU["orders_soon"],
}


@router.callback_query(F.data == "main:about")
async def on_about(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(RU["about"])


@router.callback_query(F.data.in_(_PLACEHOLDERS))
async def on_placeholder(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(_PLACEHOLDERS[callback.data])