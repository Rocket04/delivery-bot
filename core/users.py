"""Сервисы пользователей. Не зависят от Telegram — принимают примитивные значения."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.models import User


async def upsert_user(
    session: AsyncSession,
    tg_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> User:
    """Создаёт пользователя, если его нет, иначе обновляет профильные поля."""
    user = await session.scalar(select(User).where(User.tg_id == tg_id))
    if user is None:
        user = User(tg_id=tg_id, username=username, first_name=first_name, last_name=last_name)
        session.add(user)
        await session.commit()
        return user

    changed = False
    for field, value in (("username", username), ("first_name", first_name), ("last_name", last_name)):
        if value is not None and getattr(user, field) != value:
            setattr(user, field, value)
            changed = True
    if changed:
        await session.commit()
    return user