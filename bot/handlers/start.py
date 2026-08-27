from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.keyboards.main import main_keyboard
from bot.texts import RU

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(RU["start"], reply_markup=main_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(RU["help"])


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer(RU["menu_soon"])