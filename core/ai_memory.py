"""Персистентная память FAQ и лимит LLM-вызовов (ARCHITECTURE_REVIEW P1).

Заменяют in-memory deque истории ассистента: диалог переживает рестарт,
а стоимость LLM ограничена на пользователя (скользящее окно).
Всё в БД — тот же AsyncSession, что и остальной core (без Telegram).

TTL-чистка: лениво при каждой записи (+ полная при старте бота, bot/main).
created_at пишется значением из вызова (timezone-aware) там, где критичен
возраст записи; в остальных случаях — server_default (CURRENT_TIMESTAMP).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from data.models import AiChatHistory, AiLlmCall

# Значения по умолчанию; реальные настройки — в config/settings.py (env).
HISTORY_LIMIT_DEFAULT = 8
HISTORY_TTL_HOURS_DEFAULT = 24
LLM_LIMIT_DEFAULT = 30
LLM_WINDOW_MINUTES_DEFAULT = 60


def _cutoff(**delta: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(**delta)


async def load_history(
    session: AsyncSession, user_id: int, limit: int = HISTORY_LIMIT_DEFAULT
) -> list[tuple[str, str]]:
    """Последние реплики FAQ-диалога (role, text) в хронологическом порядке."""
    rows = (
        await session.scalars(
            select(AiChatHistory)
            .where(AiChatHistory.user_id == user_id)
            .order_by(AiChatHistory.id.desc())
            .limit(limit)
        )
    ).all()
    return [(h.role, h.text) for h in reversed(rows)]


async def push_history(
    session: AsyncSession, user_id: int, role: str, text: str, ttl_hours: int = HISTORY_TTL_HOURS_DEFAULT
) -> None:
    """Добавляет реплику и лениво чистит старые записи этого пользователя (TTL)."""
    session.add(AiChatHistory(user_id=user_id, role=role, text=text))
    await session.execute(
        delete(AiChatHistory).where(
            AiChatHistory.user_id == user_id,
            AiChatHistory.created_at < _cutoff(hours=ttl_hours),
        )
    )


async def purge_history(session: AsyncSession, ttl_hours: int = HISTORY_TTL_HOURS_DEFAULT) -> int:
    """Удаляет все записи истории старше TTL; возвращает число удалённых."""
    result = await session.execute(
        delete(AiChatHistory).where(AiChatHistory.created_at < _cutoff(hours=ttl_hours))
    )
    return result.rowcount or 0


async def try_llm_call(
    session: AsyncSession,
    user_id: int,
    limit: int = LLM_LIMIT_DEFAULT,
    window_minutes: int = LLM_WINDOW_MINUTES_DEFAULT,
) -> bool:
    """Пытается занять слот LLM-вызова для пользователя в скользящем окне.

    True — лимит не исчерпан, вызов записан (коммитит вызвавший код);
    False — лимит исчерпан, LLM вызывать нельзя (отвечаем оператором).
    """
    cutoff = _cutoff(minutes=window_minutes)
    count = await session.scalar(
        select(func.count())
        .select_from(AiLlmCall)
        .where(AiLlmCall.user_id == user_id, AiLlmCall.created_at >= cutoff)
    )
    if (count or 0) >= max(limit, 1):
        return False
    session.add(AiLlmCall(user_id=user_id))
    return True


async def purge_llm_calls(session: AsyncSession, ttl_hours: int = HISTORY_TTL_HOURS_DEFAULT) -> int:
    """Удаляет учёт LLM-вызовов старше TTL (рудименты лимита); возвращает число удалённых."""
    result = await session.execute(
        delete(AiLlmCall).where(AiLlmCall.created_at < _cutoff(hours=ttl_hours))
    )
    return result.rowcount or 0