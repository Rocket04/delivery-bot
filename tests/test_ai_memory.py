"""Тесты персистентной памяти ИИ-ассистента (ARCHITECTURE_REVIEW P1, exp/ai-memory).

- История FAQ: запись/чтение из БД, лимит реплик, TTL-чистка (ленивая и полная),
  переживает «рестарт» (новую сессию на той же БД).
- Лимит LLM-вызовов: скользящее окно, quota-ответ без обращения к провайдеру,
  эскалация/статус лимит не тратят.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from config.settings import Settings
from core.ai_memory import (
    load_history,
    purge_history,
    purge_llm_calls,
    push_history,
    try_llm_call,
)
from core.assistant import answer_freetext
from data.models import AiChatHistory, AiLlmCall, Base, User
from tests.test_ai_assistant import SpyProvider, _settings

HOUR = timedelta(hours=1)
NOW = datetime.now(timezone.utc)


def _old(delta: timedelta) -> datetime:
    return NOW - delta


async def _seed_user(session, tg_id: int = 5935155979) -> int:
    user = User(tg_id=tg_id, first_name="Тест")
    session.add(user)
    await session.commit()
    return user.id


# --- История FAQ ---


async def test_load_history_empty(db_session):
    await _seed_user(db_session)
    assert await load_history(db_session, 1) == []


async def test_push_and_load_roundtrip(db_session):
    await _seed_user(db_session)
    await push_history(db_session, 1, "user", "привет")
    await push_history(db_session, 1, "assistant", "здравствуйте")
    await db_session.commit()
    assert await load_history(db_session, 1) == [("user", "привет"), ("assistant", "здравствуйте")]


async def test_load_history_limit(db_session):
    await _seed_user(db_session)
    for i in range(10):
        await push_history(db_session, 1, "user", f"вопрос {i}")
        await push_history(db_session, 1, "assistant", f"ответ {i}")
    await db_session.commit()
    hist = await load_history(db_session, 1, limit=8)
    assert len(hist) == 8
    # 10 пар (20 реплик), последние 8 → «вопрос 6» .. «ответ 9»
    assert hist[0] == ("user", "вопрос 6")
    assert hist[-1] == ("assistant", "ответ 9")


async def test_history_survives_session_reopen():
    """Данные лежат в БД, а не в deque процесса — проверяем новой сессией."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as s1:
            s1.add(User(tg_id=5935155979, first_name="Тест"))
            await s1.commit()
            await push_history(s1, 1, "user", "привет")
            await s1.commit()
        async with maker() as s2:
            assert await load_history(s2, 1) == [("user", "привет")]
    finally:
        await engine.dispose()


async def test_push_history_lazy_ttl(db_session):
    uid = await _seed_user(db_session)
    db_session.add(AiChatHistory(user_id=uid, role="user", text="старое", created_at=_old(30 * HOUR)))
    await db_session.commit()
    # ленивая чистка при следующей записи
    await push_history(db_session, uid, "user", "свежее", ttl_hours=24)
    await db_session.commit()
    hist = await load_history(db_session, uid)
    assert [t for _, t in hist] == ["свежее"]


async def test_purge_history(db_session):
    uid = await _seed_user(db_session)
    db_session.add(AiChatHistory(user_id=uid, role="user", text="старое", created_at=_old(30 * HOUR)))
    db_session.add(AiChatHistory(user_id=uid, role="user", text="свежее"))
    await db_session.commit()
    removed = await purge_history(db_session, ttl_hours=24)
    await db_session.commit()
    assert removed == 1
    assert [h.text for h in (await db_session.scalars(select(AiChatHistory)))] == ["свежее"]


# --- Лимит LLM-вызовов ---


async def test_try_llm_call_counting(db_session):
    await _seed_user(db_session)
    assert await try_llm_call(db_session, 1, limit=2, window_minutes=60) is True
    assert await try_llm_call(db_session, 1, limit=2, window_minutes=60) is True
    assert await try_llm_call(db_session, 1, limit=2, window_minutes=60) is False
    await db_session.commit()
    assert len((await db_session.scalars(select(AiLlmCall))).all()) == 2


async def test_try_llm_call_window_excludes_old(db_session):
    uid = await _seed_user(db_session)
    # вызов 2 часа назад не входит в окно 60 минут
    db_session.add(AiLlmCall(user_id=uid, created_at=_old(2 * HOUR)))
    await db_session.commit()
    assert await try_llm_call(db_session, uid, limit=1, window_minutes=60) is True


async def test_purge_llm_calls(db_session):
    uid = await _seed_user(db_session)
    db_session.add(AiLlmCall(user_id=uid, created_at=_old(30 * HOUR)))
    db_session.add(AiLlmCall(user_id=uid))
    await db_session.commit()
    removed = await purge_llm_calls(db_session, ttl_hours=24)
    await db_session.commit()
    assert removed == 1


# --- Интеграция с answer_freetext ---


def _limited_settings(limit: int = 2) -> Settings:
    return _settings(llm_limit_per_hour=limit, llm_window_minutes=60)


async def test_quota_after_limit(db_session):
    await _seed_user(db_session)
    spy = SpyProvider()
    s = _limited_settings(limit=2)
    a1 = await answer_freetext(db_session, 1, "сколько стоит плов?", spy, s)
    a2 = await answer_freetext(db_session, 1, "а манты?", spy, s)
    a3 = await answer_freetext(db_session, 1, "а салаты?", spy, s)
    assert a1.action == "llm" and a2.action == "llm"
    assert a3.action == "quota"
    assert "+7 701 916-17-01" in a3.text
    assert len(spy.calls) == 2  # третий запрос до провайдера не дошёл


async def test_quota_resets_with_new_db(db_session):
    """Лимит пер-пользователь: лимит другого юзера не влияет."""
    uid1 = await _seed_user(db_session)
    db_session.add(User(tg_id=777, first_name="Другой"))
    await db_session.commit()
    spy = SpyProvider()
    s = _limited_settings(limit=1)
    assert (await answer_freetext(db_session, uid1, "вопрос", spy, s)).action == "llm"
    assert (await answer_freetext(db_session, uid1, "ещё вопрос", spy, s)).action == "quota"
    # другой пользователь — без ограничения
    assert (await answer_freetext(db_session, 2, "свой вопрос", spy, s)).action == "llm"


async def test_escalation_not_consuming_quota(db_session):
    await _seed_user(db_session)
    spy = SpyProvider()
    s = _limited_settings(limit=1)
    assert (await answer_freetext(db_session, 1, "верни деньги", spy, s)).action == "operator"
    assert (await answer_freetext(db_session, 1, "где мой заказ?", spy, s)).action == "order_status"
    # лимит не тронут — LLM-вопрос ещё доступен
    assert (await answer_freetext(db_session, 1, "сколько стоит плов?", spy, s)).action == "llm"
    assert len(spy.calls) == 1