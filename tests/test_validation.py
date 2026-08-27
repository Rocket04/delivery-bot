from core.validation import (
    valid_address,
    valid_comment,
    valid_date_ddmm,
    valid_delivery_price,
    valid_name,
    valid_phone,
    valid_price,
    valid_required_text,
    valid_time_hm,
)


def test_valid_name():
    assert valid_name("Пыленок") == ("Пыленок", None)
    assert valid_name("  Иван  ") == ("Иван", None)
    assert valid_name("")[1] is not None
    assert valid_name("А")[1] is not None  # слишком коротко
    assert valid_name("Д" * 61)[1] is not None  # слишком длинно
    assert valid_name("Плов по-узбекски", max_len=160) == ("Плов по-узбекски", None)


def test_valid_phone():
    assert valid_phone("+7 700 123 45 67")[1] is None
    assert valid_phone("87001234567")[1] is None
    assert valid_phone("123")[1] is not None
    assert valid_phone("abc")[1] is not None


def test_valid_address():
    assert valid_address("ул. Лермонтова, 12, кв 5")[1] is None
    assert valid_address("дом")[1] is not None  # слишком коротко


def test_valid_comment_and_required():
    assert valid_comment("Без перца") == ("Без перца", None)
    assert valid_comment("") == (None, None)  # пустой — ок, комментарий необязателен
    assert valid_comment("Д" * 501)[1] is not None
    assert valid_required_text("   ")[1] is not None  # пустой обязательный — ошибка
    assert valid_required_text("реквизиты 4400 1234")[1] is None


def test_valid_price():
    assert valid_price("1800") == (1800, None)
    assert valid_price("1 800") == (1800, None)
    assert valid_price("1,800")[1] is not None
    assert valid_price("5")[1] is not None  # ниже минимума
    assert valid_price("")[1] is not None
    assert valid_delivery_price("0") == (0, None)  # бесплатно — можно
    assert valid_delivery_price("1500") == (1500, None)
    assert valid_delivery_price("abc")[1] is not None


def test_valid_date_ddmm():
    day, err = valid_date_ddmm("03.09")
    assert err is None and day.day == 3 and day.month == 9
    assert valid_date_ddmm("31.02")[1] is not None  # такой даты нет
    assert valid_date_ddmm("халява")[1] is not None
    assert valid_date_ddmm("13.13")[1] is not None


def test_valid_time_hm():
    assert valid_time_hm("18:30") == ((18, 30), None)
    assert valid_time_hm("9:05") == ((9, 5), None)
    assert valid_time_hm("25:00")[1] is not None
    assert valid_time_hm("18:75")[1] is not None
    assert valid_time_hm("вечером")[1] is not None