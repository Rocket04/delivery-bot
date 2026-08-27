"""Тесты ИИ-ассистента (эксперимент exp/ai-assistant): эскалация, статус из БД,
LLM-путь с mock/шпионом, фолбэк при недоступном провайдере."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from config.settings import Settings
from core.assistant import (
    build_system_prompt,
    answer_freetext,
    collect_context,
    escalation_reason,
    last_order_brief,
)
from core.cart import change_quantity
from core.ordering import create_order
from data.models import Category, Product, User
from integrations.llm import LLMError, LLMProvider, get_provider

TZ = "Asia/Almaty"


def _settings(**kw) -> Settings:
    defaults = dict(
        bot_token="test",
        admin_ids="",
        db_url="sqlite+aiosqlite:///:memory:",
        min_order_amount=20_000,
        prepay_percent=50,
        large_order_threshold=60_000,
        default_lead_minutes=60 * 24,
        large_order_lead_hours=48,
        dish_deposit_amount=10_000,
        app_tz=TZ,
        delivery_start_hour=8,
        delivery_end_hour=23,
        llm_provider="mock",
        llm_max_tokens=240,
    )
    defaults.update(kw)
    return Settings(_env_file=None, **defaults)


async def _seed(session):
    user = User(tg_id=5935155979, first_name="Владелец")
    session.add(user)
    cat = Category(name="Пловы", sort_order=0, is_active=True)
    session.add(cat)
    await session.flush()
    plov = Product(category_id=cat.id, name="Плов Факирский (3 кг)", price=15300, is_available=True, sort_order=0)
    manti = Product(category_id=cat.id, name="Манты (50 шт)", price=19500, is_available=True, sort_order=1)
    session.add_all([plov, manti])
    await session.commit()
    return plov.id, manti.id


async def _make_order(session) -> int:
    plov, manti = await _seed(session)
    await change_quantity(session, 1, plov, 2)
    await change_quantity(session, 1, manti, 1)
    d = datetime.now(ZoneInfo(TZ)).date() + timedelta(days=2)
    scheduled = datetime(d.year, d.month, d.day, 12, 0, tzinfo=ZoneInfo(TZ))
    order = await create_order(
        session,
        1,
        settings=_settings(),
        contact_name="Владелец",
        contact_phone="+77000000000",
        delivery_method="own",
        address="ул. 1",
        scheduled_for=scheduled,
        comment=None,
    )
    return order.id


class SpyProvider(LLMProvider):
    """Записывает вызов, отвечает эхом вопроса."""

    name = "spy"

    def __init__(self, fail: bool = False):
        self.calls: list[tuple[str, str]] = []
        self.fail = fail

    async def complete(self, system: str, user: str, max_tokens: int) -> str:
        self.calls.append((system, user))
        if self.fail:
            raise LLMError("boom")
        return f"[spy] {user}"


async def test_escalation_keywords():
    assert escalation_reason("Хочу вернуть деньги за заказ") == "верн"
    assert escalation_reason("Оформите возврат") == "возврат"
    assert escalation_reason("Это жалоба на доставку") == "жалоб"
    assert escalation_reason("Сколько стоит плов?") is None


async def test_escalation_goes_to_operator_without_llm(db_session):
    spy = SpyProvider()
    ans = await answer_freetext(db_session, 1, "верни деньги, пожалуйста", spy, _settings())
    assert ans.action == "operator"
    assert "+7 701 916-17-01" in ans.text
    assert spy.calls == []  # LLM не вызывался


async def test_order_status_intent_no_llm(db_session):
    order_id = await _make_order(db_session)
    spy = SpyProvider()
    ans = await answer_freetext(db_session, 1, "где мой заказ?", spy, _settings())
    assert ans.action == "order_status"
    assert f"Заказ №{order_id}" in ans.text or "Заказ №" in ans.text
    assert spy.calls == []


async def test_order_status_empty(db_session):
    await _seed(db_session)
    spy = SpyProvider()
    ans = await answer_freetext(db_session, 1, "как там мой заказ?", spy, _settings())
    assert ans.action == "order_status"
    assert "пока нет заказов" in ans.text


async def test_llm_path_with_spy(db_session):
    await _seed(db_session)
    spy = SpyProvider()
    ans = await answer_freetext(db_session, 1, "Сколько стоит плов?", spy, _settings())
    assert ans.action == "llm"
    assert "[spy]" in ans.text
    assert len(spy.calls) == 1
    system, user = spy.calls[0]
    assert user == "Сколько стоит плов?"
    # системный промпт содержит жёсткие правила и контекст меню
    assert "Food Plov" in system
    assert "Плов Факирский" in system
    assert "20 000" in system


async def test_mock_provider_answers(db_session):
    """Mock-провайдер — детерминированные ответы без сети и ключа."""
    await _seed(db_session)
    from integrations.llm.mock import MockProvider

    mock = MockProvider()
    ans = await answer_freetext(db_session, 1, "привет!", mock, _settings())
    assert ans.action == "llm"
    assert "Привет" in ans.text
    ans2 = await answer_freetext(db_session, 1, "какая минимальная сумма заказа?", mock, _settings())
    assert "20 000" in ans2.text


async def test_fallback_when_llm_down(db_session):
    await _seed(db_session)
    spy = SpyProvider(fail=True)
    ans = await answer_freetext(db_session, 1, "что-нибудь", spy, _settings())
    assert ans.action == "fallback"
    assert "+7 701 916-17-01" in ans.text


async def test_provider_factory():
    assert get_provider("mock", "", "m").name == "mock"
    with pytest.raises(LLMError, match="LLM_API_KEY"):
        get_provider("deepseek", "", "deepseek-v4-flash")
    with pytest.raises(LLMError, match="LLM_API_KEY"):
        get_provider("opencode", "", "deepseek-v4-flash")
    # opencode-гейтвей: открытый совместимый провайдер с дефолтным URL
    from integrations.llm.openai_compat import OpenAICompatibleProvider

    p = OpenAICompatibleProvider(api_key="k", model="deepseek-v4-flash", base_url="")
    assert p.base_url == "https://api.deepseek.com"
    p2 = OpenAICompatibleProvider(api_key="k", model="deepseek-v4-flash", base_url="https://opencode.ai/zen/go/v1")
    assert p2.base_url == "https://opencode.ai/zen/go/v1"


async def test_last_order_brief(db_session):
    await _make_order(db_session)
    brief = await last_order_brief(db_session, 1)
    assert "Заказ №" in brief
    assert "Ждёт подтверждения" in brief


async def test_context_contains_menu_and_rules(db_session):
    await _seed(db_session)
    context = await collect_context(db_session, 1, _settings())
    prompt = build_system_prompt(context)
    assert "МЕНЮ" in prompt and "Манты (50 шт)" in prompt
    assert "предоплата 50%" in prompt
    assert "08:00" in prompt