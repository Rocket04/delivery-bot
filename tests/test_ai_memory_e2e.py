"""E2E: персистентная история FAQ через реальный хендлер (exp/ai-memory).

Свободные тексты без блюд (режим 2, FAQ) проходят через Dispatcher и
MockProvider; проверяется, что реплики сохранились в ai_chat_history
именно хендлером (не только core-функциями). Telegram не используется
(FakeSession из test_ai_order_e2e).
"""

from datetime import datetime

from sqlalchemy import select

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, Update, User as TgUser

from bot.handlers import ai as ai_router
from data.models import AiChatHistory, Category, Product, User
from tests.test_ai_order_e2e import FakeSession, _user_msg


def _fresh_ai_router() -> Router:
    """Свежий Router с теми же хендлерами (модульный router нельзя прикрепить
    к двум Dispatcher'ам — он уже занят e2e-тестом заказа в test_ai_order_e2e)."""
    src = ai_router.router
    fresh = Router(name="ai-fresh")
    fresh.message.handlers.extend(src.message.handlers)
    fresh.callback_query.handlers.extend(src.callback_query.handlers)
    return fresh


def _msg(text: str, msg_id: int, tg_id: int, first_name: str) -> Update:
    """Update от конкретного пользователя (в отличие от фиксированного _user_msg)."""
    return Update(
        update_id=msg_id,
        message=Message(
            message_id=msg_id,
            date=datetime.now(),
            chat=Chat(id=tg_id, type="private"),
            from_user=TgUser(id=tg_id, is_bot=False, first_name=first_name),
            text=text,
        ),
    )


async def test_faq_history_persisted_via_handler(db_session):
    # пользователь и меню (чтобы матчер заказов не мешал FAQ-пути)
    db_session.add(User(tg_id=5935155979, first_name="Владелец"))
    cat = Category(name="Пловы", sort_order=0, is_active=True)
    db_session.add(cat)
    await db_session.flush()
    db_session.add(
        Product(category_id=cat.id, name="Плов Факирский (3 кг)", price=15300, is_available=True, sort_order=0)
    )
    await db_session.commit()

    bot = Bot(
        token="123456789:AAFakeTokenTestBotE2E",
        session=FakeSession(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(_fresh_ai_router())

    # два вопроса без упоминания блюд → FAQ: LLM (mock) отвечает, история пишется в БД
    await dp.feed_update(bot, _user_msg("какой у вас минимальный заказ?", 1), session=db_session)
    await dp.feed_update(bot, _user_msg("а доставка платная?", 2), session=db_session)

    rows = list(await db_session.scalars(select(AiChatHistory).order_by(AiChatHistory.id)))
    assert len(rows) == 4  # вопрос + ответ × 2
    assert [r.role for r in rows] == ["user", "assistant", "user", "assistant"]
    assert rows[0].text == "какой у вас минимальный заказ?"
    assert "20 000" in rows[1].text  # mock-ответ про минимальный заказ
    assert rows[2].text == "а доставка платная?"
    assert "Доставка" in rows[3].text

    await bot.session.close()


async def test_faq_history_roundtrip_back_into_context(db_session):
    """Сохранённая история снова подхватывается для контекста следующего ответа."""
    db_session.add(User(tg_id=111, first_name="Клиент"))
    cat = Category(name="Пловы", sort_order=0, is_active=True)
    db_session.add(cat)
    await db_session.flush()
    db_session.add(
        Product(category_id=cat.id, name="Плов Факирский (3 кг)", price=15300, is_available=True, sort_order=0)
    )
    await db_session.commit()

    bot = Bot(
        token="123456789:AAFakeTokenTestBotE2E",
        session=FakeSession(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(_fresh_ai_router())

    # пользователь 111 (не 5935...): диалог из двух реплик
    await dp.feed_update(bot, _msg("привет!", 1, 111, "Клиент"), session=db_session)
    await dp.feed_update(bot, _msg("какой у вас минимальный заказ?", 2, 111, "Клиент"), session=db_session)

    from core.ai_memory import load_history

    history = await load_history(db_session, 1, limit=8)
    assert history[0] == ("user", "привет!")
    assert history[1][0] == "assistant" and "Привет" in history[1][1]
    assert history[-2] == ("user", "какой у вас минимальный заказ?")
    # Косвенное доказательство roundtrip: mock отвечает по user_prompt, куда
    # хендлер уже вложил историю — на второй вопрос «привет» из истории
    # перекрыл кейворд вопроса (иначе был бы ответ про минимальный заказ)
    assert history[-1][0] == "assistant" and history[-1][1].startswith("Привет")

    await bot.session.close()