from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.keyboards.main import main_keyboard
from bot.texts import RU
from config.settings import get_settings

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(RU["start"], reply_markup=main_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(RU["help"])


@router.message(Command("chatid"))
async def cmd_chatid(message: Message) -> None:
    """Показывает id чата — для настройки OPERATOR_CHAT_ID (только админам)."""
    settings = get_settings()
    if message.from_user.id not in settings.admin_id_list:
        return
    await message.answer(f"Chat ID: <code>{message.chat.id}</code>")