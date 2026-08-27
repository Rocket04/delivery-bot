"""Регистрирует пользователя в БД (upsert) на каждое событие."""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from core.users import upsert_user


class UserRegistrationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[..., Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        session: AsyncSession | None = data.get("session")
        if from_user is not None and session is not None:
            await upsert_user(
                session,
                tg_id=from_user.id,
                username=from_user.username,
                first_name=from_user.first_name,
                last_name=from_user.last_name,
            )
        return await handler(event, data)