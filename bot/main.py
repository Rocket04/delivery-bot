"""Точка входа бота: конфиг, БД, middleware, роутеры, polling."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.handlers import admin, cart, catalog, checkout, common, operator, orders, start
from bot.middlewares.db_session import DbSessionMiddleware
from bot.middlewares.errors import ErrorHandlingMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.middlewares.user_registration import UserRegistrationMiddleware
from config.settings import get_settings
from data.db import dispose_db, init_db

COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="menu", description="Меню"),
    BotCommand(command="help", description="Помощь"),
]


async def main() -> None:
    settings = get_settings()
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN не задан — скопируй .env.example в .env и вставь токен")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db(settings.db_url)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Порядок (снаружи внутрь): ошибки → throttling → сессия БД → регистрация пользователя
    dp.update.outer_middleware(ErrorHandlingMiddleware())
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())
    dp.message.middleware(DbSessionMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware())
    dp.message.middleware(UserRegistrationMiddleware())
    dp.callback_query.middleware(UserRegistrationMiddleware())

    dp.include_router(start.router)
    dp.include_router(catalog.router)
    dp.include_router(cart.router)
    dp.include_router(checkout.router)
    dp.include_router(operator.router)
    dp.include_router(orders.router)
    dp.include_router(admin.router)
    dp.include_router(common.router)

    await bot.set_my_commands(COMMANDS)
    me = await bot.me()
    logging.info("Бот запущен: @%s", me.username)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await dispose_db()


if __name__ == "__main__":
    asyncio.run(main())