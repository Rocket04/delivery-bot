"""Сервис идемпотентных платёжных событий (ARCHITECTURE_REVIEW P0, фаза 2).

Kaspi (как и любой платёжный API) может прислать один и тот же webhook дважды
(сетевая ретраимость, ручной повтор). Чтобы не начислить предоплату дважды,
каждое событие записывается в payment_events с уникальным ключом
(external_id, type); повторная вставка отбрасывается.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from data.models import PaymentEvent


async def record_payment_event(
    session: AsyncSession, external_id: str, type: str, payload: str | None = None
) -> bool:
    """Записывает событие; True — новое (вставлено), False — дубликат (отброшено)."""
    session.add(PaymentEvent(external_id=external_id, type=type, payload=payload))
    try:
        await session.commit()
        return True
    except IntegrityError:
        await session.rollback()
        return False