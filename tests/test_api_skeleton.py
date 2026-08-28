"""Тесты подготовительного FastAPI-скелета Mini App (фаза 2, exp/miniapp-prep).

Проверяются контракты API поверх core: меню (порции/вес как в боте),
создание заказа с бизнес-правилами (мин. сумма, лид) и initData-авторизацией,
чтение заказа. Telegram и сеть не используются (httpx ASGITransport).
"""

import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode
from zoneinfo import ZoneInfo

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from apps.api.main import app, get_session
from config.settings import get_settings
from core.catalog import portion_line_total
from data.models import Base, Category, Product, User

TZ = "Asia/Almaty"
TEST_TOKEN = "12345:TESTBOTTOKEN"


def make_init_data(bot_token: str, user_id: int, auth_date: int | None = None) -> str:
    """Генерирует ПОДПИСАННЫЙ initData как это делает Telegram Mini App."""
    data = {
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps({"id": user_id, "first_name": "Веб", "username": "web"}, separators=(",", ":")),
        "auth_date": str(auth_date or int(time.time())),
    }
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    check_string = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    data["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


@pytest_asyncio.fixture
async def api_env():
    """In-memory SQLite + FastAPI без lifespan и сети; возвращает (client, maker).

    BOT_TOKEN подменяется на тестовый (get_settings кешируется — сбрасываем).
    """
    os.environ["BOT_TOKEN"] = TEST_TOKEN
    get_settings.cache_clear()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _session():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, maker
    app.dependency_overrides.clear()
    get_settings.cache_clear()
    os.environ.pop("BOT_TOKEN", None)
    await engine.dispose()


def _schedule() -> datetime:
    d = datetime.now(ZoneInfo(TZ)).date() + timedelta(days=2)
    return datetime(d.year, d.month, d.day, 12, 0, tzinfo=ZoneInfo(TZ))


async def _seed(maker) -> tuple[int, int]:
    """Пользователь + категория + весовой плов (3 кг) и манты."""
    async with maker() as session:
        session.add(User(tg_id=123456, first_name="Веб"))
        cat = Category(name="Пловы", sort_order=0, is_active=True)
        session.add(cat)
        await session.flush()
        plov = Product(category_id=cat.id, name="Плов Факирский (3 кг)", price=15300, is_available=True, sort_order=0)
        manti = Product(category_id=cat.id, name="Манты (50 шт)", price=19500, is_available=True, sort_order=1)
        session.add_all([plov, manti])
        await session.commit()
        return plov.id, manti.id


def _order_payload(**kw) -> dict:
    payload = dict(
        contact_name="Веб-клиент",
        contact_phone="+77000000000",
        delivery_method="own",
        address="ул. Веб, 1",
        scheduled_for=_schedule().isoformat(),
        items=[{"product_id": 1, "quantity": 2}, {"product_id": 2, "quantity": 1}],
    )
    payload.update(kw)
    return payload


def _headers(user_id: int = 123456) -> dict[str, str]:
    return {"X-Telegram-Init-Data": make_init_data(TEST_TOKEN, user_id)}


# --- Здоровье и меню ---


async def test_api_health(api_env):
    client, _ = api_env
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_api_menu_shape(api_env):
    client, maker = api_env
    await _seed(maker)
    r = await client.get("/menu")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1 and data[0]["name"] == "Пловы"
    by_name = {p["name"]: p for p in data[0]["products"]}
    assert set(by_name) == {"Плов Факирский (3 кг)", "Манты (50 шт)"}
    # весовой товар: порции упаковки (как в боте); граммовка в названии — суффикс не дублируется
    assert by_name["Плов Факирский (3 кг)"]["portions"] == 10
    assert by_name["Плов Факирский (3 кг)"]["price"] == 15300
    # штучный: без порций
    assert by_name["Манты (50 шт)"]["portions"] is None


# --- Заказы с initData-авторизацией ---


async def test_api_create_and_get_order(api_env):
    client, maker = api_env
    await _seed(maker)
    r = await client.post("/orders", json=_order_payload(), headers=_headers())
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["number"].split("-")[-1] == str(order["id"])  # номер: дата доставки-id
    assert order["status"] == "created"
    total = portion_line_total(15300, 2, 3000) + 19500  # 2 порции плова + манты
    assert order["total"] == total
    assert order["prepay_amount"] == total * 50 // 100
    assert len(order["items"]) == 2
    plov_item = next(i for i in order["items"] if "Плов" in i["name"])
    assert plov_item["quantity"] == 2 and plov_item["product_grams"] == 3000
    # чтение заказа
    r2 = await client.get(f"/orders/{order['id']}")
    assert r2.status_code == 200
    assert r2.json()["number"] == order["number"]


async def test_api_order_minimum_amount(api_env):
    client, maker = api_env
    await _seed(maker)
    # одна манты (19 500 ₸) < минимальный заказ 20 000 ₸
    payload = _order_payload(items=[{"product_id": 2, "quantity": 1}])
    r = await client.post("/orders", json=payload, headers=_headers())
    assert r.status_code == 400
    assert "Минимальный заказ" in r.json()["detail"]


async def test_api_order_unknown_product(api_env):
    client, maker = api_env
    await _seed(maker)
    r = await client.post(
        "/orders", json=_order_payload(items=[{"product_id": 999, "quantity": 1}]), headers=_headers()
    )
    assert r.status_code == 404
    assert "не найден" in r.json()["detail"]


async def test_api_order_not_found(api_env):
    client, _ = api_env
    r = await client.get("/orders/999999")
    assert r.status_code == 404


# --- initData-авторизация ---


async def test_api_order_requires_init_data(api_env):
    client, maker = api_env
    await _seed(maker)
    r = await client.post("/orders", json=_order_payload())
    assert r.status_code == 401


async def test_api_order_rejects_forged_init_data(api_env):
    client, maker = api_env
    await _seed(maker)
    forged = urlencode(dict(parse_qsl(make_init_data(TEST_TOKEN, 123456)), hash="0" * 64))
    r = await client.post("/orders", json=_order_payload(), headers={"X-Telegram-Init-Data": forged})
    assert r.status_code == 401


async def test_api_order_wrong_token_rejected(api_env):
    """initData, подписанный НЕ тем токеном (чужой бот) — 401."""
    client, maker = api_env
    await _seed(maker)
    wrong = make_init_data("99999:OTHERBOT", 123456)
    r = await client.post("/orders", json=_order_payload(), headers={"X-Telegram-Init-Data": wrong})
    assert r.status_code == 401


async def test_api_order_stale_init_data_rejected(api_env):
    """auth_date старше суток (максимум WebAppData) — 401."""
    client, maker = api_env
    await _seed(maker)
    stale = make_init_data(TEST_TOKEN, 123456, auth_date=int(time.time()) - 90_000)
    r = await client.post("/orders", json=_order_payload(), headers={"X-Telegram-Init-Data": stale})
    assert r.status_code == 401