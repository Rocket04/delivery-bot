"""Сборка заказа из свободного текста (эксперимент exp/ai-assistant).

Почему НЕ через LLM: модель выдумывает/теряет позиции меню (в тесте —
«нет праздничного плова», хотя он в меню). Поэтому:
- поиск позиций и количества — детерминированный матчер по реальному меню;
- уточнение недостающих полей — мини-FSM в bot/handlers/ai.py;
- LLM остаётся на свободных вопросах (FAQ), не имеющих отношения к заказу.

Тексты помечены на i18n, как в core.ordering.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from core.catalog import (
    portion_line_total,
    portion_qty_label,
    portions_in_package,
    product_grams,
)
from core.ordering import earliest_allowed, validate_schedule
from data.models import Category, Product

PHONE_RE = re.compile(r"(?:\+?7|8)\s?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}")
KG_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*кг")
PORTIONS_RE = re.compile(r"(\d+)\s*порци", re.IGNORECASE)
PACKS_RE = re.compile(r"(\d+)\s*(?:упаков|пакет|шт|штук)", re.IGNORECASE)
UNITS_RE = re.compile(r"(\d+)\s*(?:порци|шт|штук|порц)", re.IGNORECASE)
MULT_RE = re.compile(r"[хx×]\s*(\d+)")
# «ЧЧ:ММ» (или «ЧЧ.ММ») — с валидными 24-часовыми значениями, чтобы не хватать
# «31.08» из даты как «31:08»
TIME_RE = re.compile(r"(?<!\d)((?:[01]?\d|2[0-3]))[.:]([0-5]\d)")
DATE_RE = re.compile(r"(\d{1,2})[./](\d{1,2})")


@dataclass
class MatchedItem:
    """Позиция, найденная в свободном тексте."""

    product: Product
    quantity: int

    @property
    def display(self) -> str:
        label = portion_qty_label(self.product.name, self.quantity)
        return f"{self.product.name} {label}"


def _norm(s: str) -> str:
    return s.lower().replace("ё", "е")


def _base_name(name: str) -> str:
    """«Плов Факирский (3 кг)» → «плов факирский» (без веса и скобок)."""
    base = re.sub(r"\([^)]*\)", "", name).strip()
    return _norm(base)


def _product_tokens(base: str) -> list[str]:
    """Стемминг-токены названия: «праздничный» → «праздничн», чтобы матчились
    любые падежные формы («праздничного», «праздничном»)."""
    return [_stem(t) for t in base.split() if len(t) >= 4]


def _stem(token: str) -> str:
    """Короткая основа слова: у токенов длиннее 6 букв отрезаем 2 последних."""
    return token if len(token) <= 6 else token[:-2]


def _quantity_in(text: str, product: Product, portion_grams: int = 300) -> int:
    """Количество в порциях (весовые) или штуках (штучные).

    Весовой товар («Плов Праздничный (3 кг)», 1 порция = 300 г):
    «15 порций» → 15 (4,5 кг); «4,5 кг» → 15; «6 кг» → 20; «2 упаковки/шт» → 20; «×2» → 20.
    Штучный («Манты (50 шт)»): «50 шт» → 50, «×2» → 2.
    """
    lower = text.lower()
    grams = product_grams(product.name)
    if grams:
        m = KG_RE.search(lower)
        if m:
            kg = float(m.group(1).replace(",", "."))
            return max(1, round(kg * 1000 / portion_grams))
        m = PORTIONS_RE.search(lower)
        if m:
            return max(1, int(m.group(1)))
        m = PACKS_RE.search(lower)
        if m:
            return max(1, int(m.group(1)) * portions_in_package(product.name, portion_grams))
        m = MULT_RE.search(lower)
        if m:
            return max(1, int(m.group(1)) * portions_in_package(product.name, portion_grams))
        return 1
    for pat in (UNITS_RE, MULT_RE):
        m = pat.search(lower)
        if m:
            return max(1, int(m.group(1)))
    return 1


async def match_menu_items(session: AsyncSession, text: str) -> tuple[list[MatchedItem], list[str]]:
    """Ищет позиции меню в свободном тексте. Возвращает (найденное, нераспознанное).

    Логика: у каждой позиции есть «сильные» токены (встречаются только у неё).
    Позиция считается упомянутой, если в тексте есть хотя бы один сильный токен
    или полное совпадение базового имени. «плов» один — слабый (у всех пловов),
    а «факирск», «праздничн», «ханск» — сильные. При неоднозначности (равный
    счёт) позиция пропускается — лучше переспросить, чем добавить не то.
    """
    rows = list(
        await session.execute(
            select(Product)
            .join(Category, Product.category_id == Category.id)
            .where(Category.is_active.is_(True), Product.is_available.is_(True))
            .order_by(Category.sort_order, Category.id, Product.sort_order, Product.id)
        )
    )
    products = [row[0] for row in rows]
    norm_text = _norm(text)

    # сила токена: сколько позиций содержат этот токен
    token_freq: dict[str, int] = {}
    for p in products:
        for t in _product_tokens(_base_name(p.name)):
            token_freq[t] = token_freq.get(t, 0) + 1

    best_by_tokens: dict[frozenset, tuple[int, int, Product]] = {}
    for p in products:
        tokens = _product_tokens(_base_name(p.name))
        if not tokens:
            continue
        hits = [t for t in tokens if t in norm_text]
        if not hits:
            continue
        strong = [t for t in hits if token_freq.get(t, 0) == 1]
        full_match = len(hits) == len(tokens)
        if not strong and not full_match:
            continue  # только общие слова («плов» без уточнения)
        key = frozenset(tokens)
        score = (len(strong), len(hits), -len(p.name))
        prev = best_by_tokens.get(key)
        if prev is None or score > prev[0]:
            best_by_tokens[key] = (score, 0, p)
        elif prev is not None and score == prev[0]:
            best_by_tokens[key] = (score, 1, p)  # неоднозначность

    found: list[MatchedItem] = []
    for score, ambiguous, p in best_by_tokens.values():
        if ambiguous:
            continue
        found.append(MatchedItem(product=p, quantity=_quantity_in(text, p)))
    found.sort(key=lambda mi: mi.product.id)
    return found, []


def parse_phone_from_text(text: str) -> str | None:
    m = PHONE_RE.search(text)
    return m.group(0).strip() if m else None


def parse_time_freetext(text: str, settings: Settings, total: int) -> datetime | None:
    """Пытается вытащить время доставки из свободного текста.

    Поддержка: «завтра 18:30», «послезавтра 18:30», «30.08 18:30», просто «18:30»
    (тогда — на ближайший доступный день). Возвращает осознанное локальное
    время, если оно проходит validate_schedule (лид + окно 08:00–23:00).
    """
    m = TIME_RE.search(text)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    lower = _norm(text)
    day_offset = 2 if "послезавтр" in lower else (1 if "завтра" in lower else 0)
    now = datetime.now(ZoneInfo(settings.app_tz))
    if day_offset:
        day = (now + timedelta(days=day_offset)).date()
    else:
        dm = DATE_RE.search(text)
        if dm and (int(dm.group(1)) <= 31 and int(dm.group(2)) <= 12):
            today = now.date()
            day = datetime(today.year, int(dm.group(2)), int(dm.group(1))).date()
            if day <= today:
                day = datetime(today.year + 1, int(dm.group(2)), int(dm.group(1))).date()
        else:
            # просто время — на ближайший реально доступный день
            day = earliest_allowed(settings, total, now).date()
    try:
        scheduled = datetime.combine(day, time(hour, minute), tzinfo=ZoneInfo(settings.app_tz))
    except ValueError:
        return None
    if validate_schedule(settings, total, scheduled, now) is not None:
        return None
    return scheduled


def build_order_body(view, data: dict) -> str:
    """Человекочитаемая сводка перед подтверждением (корзина + поля)."""
    from core.ordering import format_money

    lines = [
        f"👤 {data.get('contact_name', '—')}",
        f"📞 {data.get('phone', '—')}",
        f"🚚 {data.get('method_label', data.get('method', '—'))}",
        f"🕐 {data['scheduled_for']:%d.%m %H:%M}" if data.get("scheduled_for") else "🕐 —",
        f"📍 {data['address']}" if data.get("address") else "",
    ]
    lines = [l for l in lines if l]
    lines.append("")
    lines.append("————————————")
    portion = 300
    lines.extend(
        f"{r.name} {portion_qty_label(r.name, r.quantity, portion)} — "
        f"{format_money(portion_line_total(r.price, r.quantity, r.grams, portion))}"
        for r in view.rows
    )
    if view.unavailable_total:
        lines.append(f"⚠️ Без наличия: {format_money(view.unavailable_total)}")
    lines.append("————————————")
    lines.append(f"<b>Сумма: {format_money(view.total)}</b>")
    lines.append(f"💳 Предоплата 50%: <b>{format_money(view.total * 50 // 100)}</b>")
    return "\n".join(lines)