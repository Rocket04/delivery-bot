# DeliveryBot

Telegram-бот приёма заказов на доставку еды. Бизнес: **Food Plov / FoodPlovCenter**, Павлодар (плов, манты, пельмени, шашлыки, комплексные обеды).

## Быстрый старт (локальная разработка)

1. `docker compose up -d db` — поднять PostgreSQL.
2. `python -m venv .venv && .venv\Scripts\activate` — виртуальное окружение (Windows).
3. `pip install -e ".[dev]"` — зависимости.
4. `cp .env.example .env` и вставь токен бота (или оставь готовый `.env`).
5. `alembic upgrade head` — применить миграции.
6. `python -m bot` — запустить бота (long polling).

Всё сразу в Docker: `docker compose up --build` (поднимет БД + бота с авто-миграциями).

## Документация

- [План MVP: цели, архитектура, стадии, воркфлоу](docs/PLAN.md)

## Статус

- [x] Stage 0 — план и решения
- [x] Stage 1 — скелет проекта ⏳ на проверке
- [ ] Stage 2 — каталог и корзина
- [ ] Stage 3 — оформление заказа, предоплата Kaspi, операторы
- [ ] Stage 4 — админка в боте
- [ ] Stage 5 — полировка и тесты
- [ ] Stage 6 — деплой и бета