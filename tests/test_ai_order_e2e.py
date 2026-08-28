"""E2E: полный флоу текстового заказа через реальный Dispatcher (exp/ai-assistant).

Сэмулированный пользователь пишет «хотел бы заказать плов праздничный 15 порций»,
проходит уточнения (телефон → адрес → способ → время), подтверждает сводку —
и заказ создаётся в БД с порциями, операторам уходит уведомление (FakeSession
перехватывает — в Telegram ничего не уходит).
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from data.models import Category, Order, OrderItem, Product, User as DbUser

from bot.handlers import ai as ai_router

TZ_OFFSET = timedelta(hours=5)  # Asia/Almaty летом (UTC+5)


class FakeSession(BaseSession):
    """Перехватывает все API-вызовы бота, ничего не шлёт в Telegram."""

    def __init__(self):
        super().__init__()
        self.calls: list[tuple[str, dict]] = []

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout=None):
        payload = method.model_dump(exclude_unset=True)
        payload.pop("conf", None)
        self.calls.append((type(method).__name__, payload))
        returning = getattr(method, "__returning__", None)
        if returning is None or returning is bool:
            return True
        try:
            return returning.model_construct(message_id=1)
        except TypeError:
            return returning.model_construct()

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        return
        yield  # pragma: no cover

    async def close(self) -> None:
        return


def _user_msg(text: str, msg_id: int) -> Update:
    return Update(
        update_id=msg_id,
        message=Message(
            message_id=msg_id,
            date=datetime.now(),
            chat=Chat(id=5935155979, type="private"),
            from_user=User(id=5935155979, is_bot=False, first_name="Владелец"),
            text=text,
        ),
    )


def _callback(data: str, msg_id: int) -> Update:
    return Update(
        update_id=msg_id,
        callback_query=CallbackQuery(
            id=f"q{msg_id}",
            from_user=User(id=5935155979, is_bot=False, first_name="Владелец"),
            chat_instance="inst",
            data=data,
            message=Message(
                message_id=msg_id,
                date=datetime.now(),
                chat=Chat(id=5935155979, type="private"),
                from_user=User(id=5935155979, is_bot=False, first_name="Владелец"),
                text="placeholder",
            ),
        ),
    )


async def _seed(session) -> int:
    user = DbUser(tg_id=5935155979, first_name="Владелец")
    session.add(user)
    cat = Category(name="Горячие блюда", sort_order=0, is_active=True)
    session.add(cat)
    await session.flush()
    prazdnichny = Product(
        category_id=cat.id, name="Плов Праздничный (3 кг)", price=17_550, is_available=True, sort_order=0
    )
    session.add(prazdnichny)
    await session.commit()
    return prazdnichny.id


def _sent_texts(bot: Bot) -> list[str]:
    return [p.get("text", "") for name, p in bot.session.calls if name == "SendMessage"]


def _sent_edits(bot: Bot) -> list[str]:
    return [
        p.get("text", "")
        for name, p in bot.session.calls
        if name == "EditMessageText" and p.get("text")
    ]


async def test_full_text_order_flow(db_session):
    await _seed(db_session)

    bot = Bot(
        token="123456789:AAFakeTokenTestBotE2E",
        session=FakeSession(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(ai_router.router)

    # Шаг 1: свободный текст с заказом
    await dp.feed_update(bot, _user_msg("Здравствуйте, хотел бы заказать плов праздничный 15 порций", 1), session=db_session)
    texts = _sent_texts(bot)
    assert any("В корзине сейчас" in t and "15 порций (4,5 кг)" in t for t in texts)
    assert any("26 325" in t for t in texts)
    assert any("Телефон для связи" in t for t in texts)

    # Шаг 2: телефон
    await dp.feed_update(bot, _user_msg("+7 700 000 00 00", 2), session=db_session)
    assert any("Куда доставить" in t for t in _sent_texts(bot))

    # Шаг 3: адрес
    await dp.feed_update(bot, _user_msg("ул. Лермонтова, 12", 3), session=db_session)
    texts = _sent_texts(bot)
    assert any("Как заберёшь заказ" in t for t in texts)

    # Шаг 4: способ доставки (кнопка)
    await dp.feed_update(bot, _callback("ai:method:own", 4), session=db_session)
    assert any("На какое время" in t for t in _sent_texts(bot))

    # Шаг 5: время — дата через 3 дня, чтобы лид гарантированно сошёлся
    target = (datetime.now() + timedelta(days=3)).date()
    time_text = f"{target.day:02d}.{target.month:02d} 12:00"
    await dp.feed_update(bot, _user_msg(time_text, 5), session=db_session)
    texts = _sent_texts(bot)
    assert any("Проверь заказ" in t for t in texts)
    assert any("15 порций (4,5 кг)" in t for t in texts)

    # Шаг 6: подтвердить
    await dp.feed_update(bot, _callback("ai:confirm", 6), session=db_session)

    # Заказ в БД: порции, вес, сумма
    order = await db_session.scalar(select(Order).order_by(Order.id.desc()).limit(1))
    assert order is not None
    assert order.total == 26_325
    assert order.prepay_amount == 13_162  # 50% c округлением вниз по int-делению
    items = list(await db_session.scalars(select(OrderItem).where(OrderItem.order_id == order.id)))
    assert len(items) == 1
    assert items[0].quantity == 15
    assert items[0].product_grams == 3000
    assert items[0].price == 17_550

    # Пользователю: «Заказ создан» с кнопками «Мои заказы»/«В меню»
    texts = _sent_texts(bot) + _sent_edits(bot)
    assert any("Заказ №" in t and "создан" in t for t in texts)
    keyboard = None
    for name, payload in bot.session.calls:
        if name == "EditMessageText" and "создан" in payload.get("text", ""):
            keyboard = payload.get("reply_markup")
    assert keyboard is not None
    buttons = "".join(
        b.get("text", "") for row in keyboard.get("inline_keyboard", []) for b in row
    )
    assert "Мои заказы" in buttons and "В меню" in buttons

    # Операторам ушла карточка заказа (перехвачена FakeSession)
    sent = [p for name, p in bot.session.calls if name == "SendMessage"]
    assert any("Заказ №" in p.get("text", "") and "порций" in p.get("text", "") for p in sent)

    await bot.session.close()