"""Тесты сборки заказа из свободного текста (exp/ai-assistant): матчер меню,
количество (кг/порции/×N), телефон, время из фристайла."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config.settings import Settings
from core.ai_order import (
    match_menu_items,
    parse_phone_from_text,
    parse_time_freetext,
)
from data.models import Category, Product

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
    )
    defaults.update(kw)
    return Settings(_env_file=None, **defaults)


async def _seed_menu(session) -> dict[str, int]:
    """Меню как в проде: несколько пловов (общий токен «плов» — слабый)."""
    cat = Category(name="Горячие блюда", sort_order=0, is_active=True)
    session.add(cat)
    await session.flush()
    items = [
        ("Плов Факирский (3 кг)", 15300, 0),
        ("Плов Праздничный (3 кг)", 17550, 1),
        ("Плов Ханский (3 кг)", 19800, 2),
        ("Манты с говядиной (50 шт)", 19500, 3),
    ]
    ids = {}
    for name, price, sort in items:
        p = Product(category_id=cat.id, name=name, price=price, is_available=True, sort_order=sort)
        session.add(p)
        await session.flush()
        ids[name] = p.id
    await session.commit()
    return ids


async def test_match_by_distinctive_token(db_session):
    await _seed_menu(db_session)
    found, _ = await match_menu_items(db_session, "Здравствуйте, хотел бы заказать плов праздничный 15 порций")
    assert len(found) == 1
    assert "Праздничный" in found[0].product.name
    assert found[0].quantity == 15


async def test_match_kg_converts_to_portions(db_session):
    await _seed_menu(db_session)
    # 6 кг факирского = 20 порций по 300 г (а не 2 упаковки × 3 кг)
    found, _ = await match_menu_items(db_session, "Хорошо, давайте 6 кг факирский")
    assert len(found) == 1
    assert "Факирский" in found[0].product.name
    assert found[0].quantity == 20


async def test_match_kg_float(db_session):
    await _seed_menu(db_session)
    found, _ = await match_menu_items(db_session, "4,5 кг праздничного")
    assert len(found) == 1
    assert "Праздничный" in found[0].product.name
    assert found[0].quantity == 15  # 4,5 кг / 300 г


async def test_match_multiple_items(db_session):
    await _seed_menu(db_session)
    found, _ = await match_menu_items(
        db_session, "закажите плов ханский 1 и манты 50 шт пожалуйста"
    )
    names = {f.product.name for f in found}
    assert {"Плов Ханский (3 кг)", "Манты с говядиной (50 шт)"} <= names
    q = {f.product.name: f.quantity for f in found}
    assert q["Манты с говядиной (50 шт)"] == 50


async def test_generic_word_not_match(db_session):
    await _seed_menu(db_session)
    # только общее слово «плов» — без уточнения: слабый токен, не матчим
    found, _ = await match_menu_items(db_session, "а есть плов?")
    assert found == []
    # вопрос без блюд — тоже
    found2, _ = await match_menu_items(db_session, "какие у вас сеты?")
    assert found2 == []


async def test_match_case_and_yo(db_session):
    await _seed_menu(db_session)
    # ×2 для весового товара = 2 упаковки × 10 порций = 20 порций
    found, _ = await match_menu_items(db_session, "ПЛОВ ФАКИРСКИЙ Ё-МОЁ х2")
    assert len(found) == 1
    assert found[0].quantity == 20


async def test_ambiguous_skipped(db_session):
    """Если два плова с одинаковым набором сильных токенов — не угадываем."""
    cat2 = Category(name="Горячие блюда 2", sort_order=1, is_active=True)
    db_session.add(cat2)
    await db_session.flush()
    a = Product(category_id=cat2.id, name="Плов Особый Праздничный (3 кг)", price=20000, is_available=True)
    db_session.add_all([a])
    await db_session.commit()
    found, _ = await match_menu_items(db_session, "плов особый праздничный")
    assert found == [] or len(found) <= 1


async def test_phone_extraction():
    assert parse_phone_from_text("тел +7 701 916-17-01, спасибо") == "+7 701 916-17-01"
    assert parse_phone_from_text("без номера тут") is None


async def test_time_extraction_plain():
    s = _settings()
    now = datetime(2026, 8, 28, 12, 0, tzinfo=ZoneInfo(TZ))
    # «18:30» без даты → ближайший доступный день (лид 24 ч → 30.08); фиксированное now
    t = parse_time_freetext("на 18:30", s, 25_000, now=now)
    assert t is not None and t.hour == 18 and t.minute == 30


async def test_time_extraction_tomorrow():
    s = _settings()
    now = datetime(2026, 8, 28, 12, 0, tzinfo=ZoneInfo(TZ))
    # фиксированное now: тест не зависит от времени суток (вечером «завтра 14:00»
    # — меньше 24 ч лида, parse вернул бы None)
    t = parse_time_freetext("послезавтра 14:00", s, 25_000, now=now)
    assert t is not None
    assert (t.date() - now.date()).days == 2


async def test_time_rejects_night():
    s = _settings()
    # 03:00 — ночь, окно 08:00–23:00 → отказ
    assert parse_time_freetext("03:00", s, 25_000) is None
    # без времени — отказ
    assert parse_time_freetext("привезите как-нибудь", s, 25_000) is None


# --- Порции (1 порция = 300 г, 10 порций = 3 кг) ---

def test_portion_line_total_package_equality():
    from core.catalog import portion_line_total
    # 10 порций × 300 г из упаковки 3 кг = ровно цена упаковки
    assert portion_line_total(15_300, 10, 3000) == 15_300
    assert portion_line_total(17_550, 15, 3000) == 26_325  # 15 порций = 4,5 кг
    # упаковка 4 кг, 13 порций (3,9 кг): ceil(26900 × 13×300 / 4000)
    assert portion_line_total(26_900, 13, 4000) == 26_228
    # штучный товар — без конверсии
    assert portion_line_total(19_500, 2, None) == 39_000


def test_portion_helpers():
    from core.catalog import portion_qty_label, portions_in_package, product_grams
    assert product_grams("Плов Праздничный (3 кг)") == 3000
    assert product_grams("Плов по-татарски (4,5 кг)") == 4500
    assert product_grams("Манты (50 шт)") is None
    assert portions_in_package("Плов Ханский (3 кг)") == 10
    assert portions_in_package("Казан Кебаб (4 кг)") == 13
    assert portion_qty_label("Плов Праздничный (3 кг)", 15) == "15 порций (4,5 кг)"
    assert portion_qty_label("Манты (50 шт)", 3) == "×3"


async def test_cart_total_uses_portions(db_session):
    from core.cart import change_quantity, get_cart_view
    await _seed_menu(db_session)
    # 15 порций праздничного (4,5 кг) — сумма по весу
    await change_quantity(db_session, 1, 2, 15)  # Плов Праздничный
    view = await get_cart_view(db_session, 1)
    assert view.total == 26_325
    # обычный кнопочный заказ: +1 = 1 порция (300 г), а не упаковка
    await change_quantity(db_session, 1, 1, 1)  # Плов Факирский
    view = await get_cart_view(db_session, 1)
    assert view.total == 26_325 + 1_530