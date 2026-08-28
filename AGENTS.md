# AGENTS.md — памятка для ИИ-агентов, работающих с DeliveryBot

Краткая карта проекта. Полные детали: `docs/PLAN.md`, `docs/DEPLOY.md`, `docs/RESEARCH.md`,
`docs/ARCHITECTURE_REVIEW.md`. Работа с ВМ/тестовым ботом — скилл `deliverybot-vm`.

## Кто владелец

Пользователь Rocket04; бот представляет ресторан Food Plov (Павлодар, Казахстан).
Рабочий язык общения и текстов бота — русский. Воркфлоу: фичи — через эксперименты
(ветки `exp/*`), в `main` мержим только после «ок» владельца; деплой на ВМ — `update.sh`.

## Стек и структура

- Python 3.12, aiogram 3.31, SQLAlchemy 2 (async), PostgreSQL 16 (прод на ВМ),
  Alembic (0001–0004), pytest (65 зелёных; in-memory SQLite, БД не нужна).
- Тонкие хендлеры (`bot/handlers/`) → сервисы `core/` (без Telegram) → `data/` (модели).
  Интеграции — `integrations/` (LLM: mock|deepseek|opencode-гейтвей, браузерный UA).
- Docker-образ ДОЛЖЕН копировать `integrations/` (см. Dockerfile) — иначе прод не стартует.
- ВАЖНО: sentiment-трюки не нужны; тесты: `.venv\Scripts\python.exe -m pytest -q` из корня репо.
  Кодировка вывода: `$env:PYTHONIOENCODING="utf-8"`.

## Доменные правила (кратко)

- Приём заказов 24/7, готовим с утра до ночи (окно доставки 08:00–23:00, env-параметры).
- Предзаказ: обычные ≥ 24 ч, крупные (≥ 60 000 ₸) ≥ 48 ч; мин. заказ 20 000 ₸.
- Предоплата 50% всегда (Kaspi: перевод/ссылка/удалённая оплата; чек подтверждает оператор).
- Порции: 1 порция = 300 г (`PORTION_GRAMS`); весовые товары («(N кг)» в названии)
  считаются в порциях; сумма = цена упаковки × порции×300 г / вес (ceil).
- ИИ-ассистент: текстовый заказ — детерминированный матчер (НЕ LLM), FAQ — LLM
  с жёстким промптом, эскалация оператору по ключевым словам, память in-memory (8 реплик).
- Секреты: никогда не писать токены/ключи в файлы репо (публичный GitHub!). Только .env на ВМ.

## Конвенции

- Тексты для клиента — в `bot/texts/__init__.py` (RU-словарь); core возвращает русские
  сообщения там, где это удобнее (помечены на i18n).
- callbacks: префикс `name:action:payload`; терминальные сообщения — кнопки
  «📋 Мои заказы» (main:orders) + «🍕 В меню» (cat:open).
- Статус-машина заказов в `core/constants.py` (USER_CANCELLABLE — окно отмены клиентом).
- Миграции: добавлять при изменении схемы; снапшоты в order_items (price/quantity/product_grams)
  не менять постфактум.
- e2e-тесты хендлеров: Dispatcher + FakeSession (см. `tests/test_ai_order_e2e.py`) —
  ничего не уходит в Telegram.

## Полезные команды

```bash
# тесты
.venv\Scripts\python.exe -m pytest -q
# пуш (schannel не работает в песочнице!)
git -C C:\Projects\delivery-bot -c http.sslBackend=openssl push origin main
# деплой на ВМ (через SSH/paramiko, скилл deliverybot-vm)
bash /opt/delivery-bot/scripts/update.sh
# меню на ВМ
docker compose exec -T bot python scripts/menu_sync.py seed --reset
```

## Текущий статус (2026-08-28)

- Прод: main e86cef1, ИИ-ассистент включён (opencode/deepseek-v4-flash), порции, отмена
  клиентом, повторный заказ, фото-фолбэк, окно 08:00–23:00. Контрольная неделя наблюдения.
- Бэклог (фаза 2+): Mini App (нужен домен+HTTPS), Kaspi Merchant API, веб-админка,
  автораспознавание чеков, персистентная история FAQ, лимит LLM-вызовов на пользователя.