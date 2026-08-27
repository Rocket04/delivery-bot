from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.texts import RU

router = Router(name="common")


@router.callback_query(F.data == "main:about")
async def on_about(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(RU["about"])