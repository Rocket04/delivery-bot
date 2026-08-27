"""Валидаторы пользовательского ввода.

Каждая функция возвращает (значение, ошибка) — ошибка это текст для клиента
или None, если ввод корректен. Не зависят от Telegram и БД.
"""

import re
from datetime import date

DATE_RE = re.compile(r"^\d{2}\.\d{2}$")
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_DIGITS_RE = re.compile(r"\D")

NAME_MIN = 2
NAME_MAX = 60
PRODUCT_NAME_MAX = 160
ADDRESS_MIN = 5
ADDRESS_MAX = 300
COMMENT_MAX = 500
TEXT_MAX = 1000
PHONE_DIGITS_MIN = 7
PHONE_DIGITS_MAX = 15
PRICE_MIN = 10
PRICE_MAX = 9_999_999
DELIVERY_PRICE_MAX = 9_999_999


def valid_name(text: str | None, max_len: int = NAME_MAX) -> tuple[str | None, str | None]:
    """Имя/название: непустое, без лишних пробелов, длина в диапазоне."""
    value = (text or "").strip()
    if not (NAME_MIN <= len(value) <= max_len):
        return None, f"Имя — от {NAME_MIN} до {max_len} символов. Напиши ещё раз:"
    return value, None


def valid_phone(text: str | None) -> tuple[str | None, str | None]:
    value = (text or "").strip()
    digits = _DIGITS_RE.sub("", value)
    if not (PHONE_DIGITS_MIN <= len(digits) <= PHONE_DIGITS_MAX):
        return None, "Телефон не похож на настоящий. Пришли номер в формате +7 700 000 00 00:"
    return value, None


def valid_address(text: str | None) -> tuple[str | None, str | None]:
    value = (text or "").strip()
    if not (ADDRESS_MIN <= len(value) <= ADDRESS_MAX):
        return None, f"Адрес — минимум {ADDRESS_MIN} символов (улица, дом). Максимум {ADDRESS_MAX}. Напиши ещё раз:"
    return value, None


def valid_comment(text: str | None) -> tuple[str | None, str | None]:
    """Комментарий: опциональный, с ограничением длины."""
    value = (text or "").strip() or None
    if value is not None and len(value) > COMMENT_MAX:
        return None, f"Комментарий слишком длинный (максимум {COMMENT_MAX} символов). Сократи:"
    return value, None


def valid_required_text(text: str | None, max_len: int = TEXT_MAX) -> tuple[str | None, str | None]:
    """Обязательный текст (реквизиты, причина отмены): непустой, ограничение длины."""
    value = (text or "").strip()
    if not value:
        return None, "Пустое значение не подходит. Напиши текст (или /cancel, чтобы выйти из диалога):"
    if len(value) > max_len:
        return None, f"Слишком длинно — максимум {max_len} символов. Сократи:"
    return value, None


def valid_price(text: str | None) -> tuple[int | None, str | None]:
    """Цена товара: целое число (разрешены пробелы-разделители «1 800»)."""
    value = re.sub(r"[ \u00a0]", "", text or "")
    if not value.isdigit():
        return None, "Это не похоже на цену. Пришли число в тенге, например: 1800"
    amount = int(value)
    if not (PRICE_MIN <= amount <= PRICE_MAX):
        return None, f"Цена — от {PRICE_MIN} до {PRICE_MAX:,} ₸. Пришли ещё раз:"
    return amount, None


def valid_delivery_price(text: str | None) -> tuple[int | None, str | None]:
    """Цена доставки: 0 допускается (бесплатно/самовывоз)."""
    value = re.sub(r"[ \u00a0]", "", text or "")
    if not value.isdigit():
        return None, "Пришли число в тенге (0 — если бесплатно), например: 1500"
    amount = int(value)
    if amount > DELIVERY_PRICE_MAX:
        return None, f"Цена доставки — максимум {DELIVERY_PRICE_MAX:,} ₸. Пришли ещё раз:"
    return amount, None


def valid_date_ddmm(text: str | None) -> tuple[date | None, str | None]:
    """ДД.ММ → ближайшая такая дата (если в этом году прошла — следующий год).
    Ограничение: не дальше ~14 месяцев вперёд."""
    value = (text or "").strip()
    if not DATE_RE.match(value):
        return None, "Не понял дату. Пришли в формате ДД.ММ, например: 03.09"
    dd, mm = map(int, value.split("."))
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return None, "Такой даты не бывает. Пришли в формате ДД.ММ, например: 03.09"
    today = date.today()
    year = today.year if (mm, dd) > (today.month, today.day) else today.year + 1
    try:
        day = date(year, mm, dd)
    except ValueError:
        return None, "Такой даты не бывает. Пришли в формате ДД.ММ, например: 03.09"
    if (day - today).days > 420:
        return None, "Мы принимаем заказы максимум на ~14 месяцев вперёд. Пришли ближайшую дату:"
    return day, None


def valid_time_hm(text: str | None) -> tuple[tuple[int, int] | None, str | None]:
    """ЧЧ:ММ → (час, минута)."""
    match = TIME_RE.match((text or "").strip())
    if not match:
        return None, "Не понял время. Пришли в формате ЧЧ:ММ, например: 18:30"
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None, "Такого времени не бывает. Пришли в формате ЧЧ:ММ, например: 18:30"
    return (hour, minute), None