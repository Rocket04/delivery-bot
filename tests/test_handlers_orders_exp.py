"""Хендлер-тесты эксперимента: отмена клиентом и повторный заказ.

Прогоняют РЕАЛЬНЫЕ хендлеры bot/handlers/orders.py с синтетическими
CallbackQuery (FakeBot — ничего не уходит в Telegram). Дополняют core-тесты:
проверяют обвязку (кнопки, тексты, уведомления операторам).
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config.settings import Settings
from core.cart import change_quantity, get_cart_view
from core.ordering import create_order, transition
from core.constants import OrderStatus
from data.models import Category, Product, User


class FakeBot:
    """Перехватывает отправки — в Telegram ничего не уходит."""

    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


class FakeMessage:
    def __init__(self):
        self.answered = []
        self.edited = []

    async def answer(self, text=None, reply_markup=None, **kw):
        self.answered.append((text, reply_markup))

    async def edit_text(self, text=None, reply_markup=None, **kw):
        self.edited.append((text, reply_markup))


class FakeCallbackQuery:
    def __init__(self, data: str, tg_id: int = 5935155979):
        self.data = data
        self.from_user = type("U", (), {"id": tg_id})()
        self.message = FakeMessage()
        self.bot = FakeBot()
        self._ans = []

    async def answer(self, *a, **kw):
        self._ans.append(True)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        bot_token="test",
        admin_ids="",
        operator_chat_id=None,
        db_url="sqlite+aiosqlite:///:memory:",
        min_order_amount=20_000,
        prepay_percent=50,
        large_order_threshold=60_000,
        default_lead_minutes=60 * 24,
        large_order_lead_hours=48,
        dish_deposit_amount=10_000,
        app_tz="Asia/Almaty",
    )


async def _seed_user(session) -> User:
    user = User(tg_id=5935155979, first_name="Владелец")
    session.add(user)
    await session.flush()
    return user


async def _seed_menu(session):
    cat = Category(name="Горячие блюда", sort_order=0, is_active=True)
    session.add(cat)
    await session.flush()
    plov = Product(category_id=cat.id, name="Плов Факирский (3 кг)", price=15300, is_available=True, sort_order=0)
    manti = Product(category_id=cat.id, name="Манты (50 шт)", price=19500, is_available=True, sort_order=1)
    session.add_all([plov, manti])
    await session.commit()
    return plov.id, manti.id


async def _make_order(session) -> int:
    """Создаёт заказ (user tg 5935155979) с корзиной ≥ мин. заказа. Возвращает order.id."""
    await _seed_user(session)
    plov, manti = await _seed_menu(session)
    await change_quantity(session, 1, plov, 2)  # 30 600 ₸
    await change_quantity(session, 1, manti, 1)
    d = datetime.now(ZoneInfo("Asia/Almaty")).date() + timedelta(days=2)
    scheduled = datetime(d.year, d.month, d.day, 12, 0, tzinfo=ZoneInfo("Asia/Almaty"))
    order = await create_order(
        session,
        1,
        settings=_settings(),
        contact_name="Владелец",
        contact_phone="+77000000000",
        delivery_method="own",
        address="ул. Тестовая, 1",
        scheduled_for=scheduled,
        comment=None,
    )
    return order.id


async def test_order_view_shows_cancel_button_for_created(db_session):
    from bot.handlers.orders import cb_order_view

    order_id = await _make_order(db_session)
    cb = FakeCallbackQuery(f"orders:view:{order_id}")
    await cb_order_view(cb, db_session)
    text, kb = cb.message.answered[0]
    assert "Ждёт подтверждения" in text
    buttons = [b.text for row in kb.inline_keyboard for b in row]
    assert "❌ Отменить заказ" in buttons
    assert "🔁 Заказать снова" not in buttons  # ещё не завершён


async def test_order_view_shows_repeat_for_delivered(db_session):
    from bot.handlers.orders import cb_order_view

    order_id = await _make_order(db_session)
    from data.models import Order

    order = await db_session.get(Order, order_id)
    await transition(db_session, order, "awaiting_prepayment", actor="operator")
    await transition(db_session, order, "confirmed", actor="operator")
    await transition(db_session, order, "preparing", actor="operator")
    await transition(db_session, order, "delivering", actor="operator")
    await transition(db_session, order, "delivered", actor="operator")
    cb = FakeCallbackQuery(f"orders:view:{order_id}")
    await cb_order_view(cb, db_session)
    text, kb = cb.message.answered[0]
    buttons = [b.text for row in kb.inline_keyboard for b in row]
    assert "🔁 Заказать снова" in buttons
    assert "❌ Отменить заказ" not in buttons


async def test_cancel_flow_with_confirmation(db_session):
    """Да-отмена: статус cancelled + уведомление группе операторов (FakeBot)."""
    from bot.handlers.orders import cb_order_cancel_ask, cb_order_cancel_yes
    from data.models import Order

    order_id = await _make_order(db_session)
    cb = FakeCallbackQuery(f"orders:cancel:{order_id}")
    await cb_order_cancel_ask(cb, db_session)
    text, kb = cb.message.answered[0]
    buttons = [b.text for row in kb.inline_keyboard for b in row]
    assert "✅ Да, отменить" in buttons
    # жмём «да»
    cb2 = FakeCallbackQuery(f"orders:cancel_yes:{order_id}")
    await cb_order_cancel_yes(cb2, db_session)
    order = await db_session.get(Order, order_id)
    assert order.status == OrderStatus.CANCELLED
    assert order.cancelled_reason == "Отменён клиентом"
    assert any("клиент" in t.lower() or "отменил" in t.lower() for _, t in cb2.bot.sent)


async def test_cancel_no_keeps_order(db_session):
    from bot.handlers.orders import cb_order_cancel_no
    from data.models import Order

    order_id = await _make_order(db_session)
    cb = FakeCallbackQuery(f"orders:cancel_no:{order_id}")
    await cb_order_cancel_no(cb, db_session)
    order = await db_session.get(Order, order_id)
    assert order.status == OrderStatus.CREATED


async def test_repeat_reorders_into_cart(db_session):
    from bot.handlers.orders import cb_order_repeat
    from data.models import Order

    order_id = await _make_order(db_session)
    order = await db_session.get(Order, order_id)
    await transition(db_session, order, "cancelled", actor="operator", note="тест")
    cb = FakeCallbackQuery(f"orders:repeat:{order_id}")
    await cb_order_repeat(cb, db_session)
    text, kb = cb.message.answered[0]
    assert "снова в корзине" in text
    assert "Плов Факирский" in text
    view = await get_cart_view(db_session, 1)
    assert view.rows and view.total == order.total