"""Открывает сессию БД на каждый апдейт и кладёт её в data['session']."""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from data.db import get_session_maker


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[..., Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        async with get_session_maker()() as session:
            data["session"] = session
            return await handler(event, data)


# Для типизации в хендлерах
__all__ = ["DbSessionMiddleware", "AsyncSession"]