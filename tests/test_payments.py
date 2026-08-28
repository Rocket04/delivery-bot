"""Тесты идемпотентности платёжных событий (ARCHITECTURE_REVIEW P0, exp/kaspi-prep).

Повторный webhook с тем же (external_id, type) отбрасывается; разные типы
для одного external_id — разные события (payment.created vs payment.captured).
"""

import json

from sqlalchemy import select

from core.payments import record_payment_event
from data.models import PaymentEvent


async def test_first_event_recorded(db_session):
    assert await record_payment_event(db_session, "ext-1", "payment.created", "{}") is True
    rows = (await db_session.scalars(select(PaymentEvent))).all()
    assert len(rows) == 1
    assert rows[0].external_id == "ext-1" and rows[0].type == "payment.created"


async def test_duplicate_event_rejected(db_session):
    assert await record_payment_event(db_session, "ext-1", "payment.created", '{"a":1}') is True
    assert await record_payment_event(db_session, "ext-1", "payment.created", '{"a":1}') is False
    rows = (await db_session.scalars(select(PaymentEvent))).all()
    assert len(rows) == 1  # дубль не записан
    assert json.loads(rows[0].payload) == {"a": 1}


async def test_same_external_id_different_type(db_session):
    assert await record_payment_event(db_session, "ext-1", "payment.created") is True
    assert await record_payment_event(db_session, "ext-1", "payment.captured") is True
    assert await record_payment_event(db_session, "ext-1", "payment.captured") is False
    rows = (await db_session.scalars(select(PaymentEvent))).all()
    assert len(rows) == 2


async def test_different_external_ids_independent(db_session):
    assert await record_payment_event(db_session, "ext-1", "payment.created") is True
    assert await record_payment_event(db_session, "ext-2", "payment.created") is True
    assert await record_payment_event(db_session, "ext-2", "payment.created") is False
    rows = (await db_session.scalars(select(PaymentEvent))).all()
    assert len(rows) == 2