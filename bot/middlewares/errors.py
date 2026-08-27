"""Внешний перехватчик ошибок: апдейт не должен ронять бота.
Ошибки логируются и, если настроены админы, присылаются им в Telegram —
чтобы «тихие» сбои было видно сразу."""

import logging

from aiogram import BaseMiddleware

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except Exception as exc:
            logger.exception("Unhandled error in update")
            try:
                bot = data.get("bot")
                if bot is not None:
                    from config.settings import get_settings

                    admins = get_settings().admin_id_list
                    if admins:
                        text = f"⚠️ <b>Ошибка бота</b>\n<code>{str(exc)[:400]}</code>"
                        await bot.send_message(admins[0], text)
            except Exception:
                pass  # не мешаем основной обработке ошибки
            return None