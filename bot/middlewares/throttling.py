"""Защита от флуда: не чаще одного события от пользователя в интервал."""

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware

_MIN_INTERVAL = 0.35  # секунд


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, min_interval: float = _MIN_INTERVAL) -> None:
        self.min_interval = min_interval
        self._last: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[..., Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is not None:
            now = time.monotonic()
            last = self._last.get(user.id, 0.0)
            if now - last < self.min_interval:
                return None  # тихо отбрасываем дубль
            self._last[user.id] = now
        return await handler(event, data)