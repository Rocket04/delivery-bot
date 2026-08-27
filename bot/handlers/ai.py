"""Свободный текст клиента → ИИ-ассистент (эксперимент exp/ai-assistant).

Хендлер-фолбэк: ловит любые текстовые сообщения, которые не команды и не
часть FSM-диалога (оформление заказа / админка). Сама логика — в core/assistant.
"""

import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.catalog import db_user_id
from bot.notify import notify_ai_escalation
from config.settings import get_settings
from core.assistant import answer_freetext
from integrations.llm import get_provider

router = Router(name="ai")

log = logging.getLogger(__name__)


@router.message(F.text, ~F.text.startswith("/"), StateFilter(None))
async def on_freetext(message: Message, session: AsyncSession) -> None:
    settings = get_settings()
    user_id = await db_user_id(session, message.from_user.id)
    provider = get_provider(
        settings.llm_provider, settings.llm_api_key, settings.llm_model, settings.llm_base_url
    )
    answer = await answer_freetext(session, user_id, message.text, provider, settings)
    await message.answer(answer.text)
    if answer.action == "operator":
        try:
            await notify_ai_escalation(message.bot, message.from_user, message.text)
        except Exception:
            log.exception("Не удалось уведомить операторов об эскалации")