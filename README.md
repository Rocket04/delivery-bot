# DeliveryBot

Telegram-бот приёма заказов на доставку еды. Бизнес: **Food Plov / FoodPlovCenter**, Павлодар (плов, манты, пельмени, шашлыки, комплексные обеды).

## Быстрый старт (локальная разработка, без Docker)

На этой машине Docker Desktop недоступен (Windows 10 1809), поэтому PostgreSQL работает нативно.

**Один раз (нужен админ):**
1. PowerShell от имени администратора → `& C:\Projects\delivery-bot\scripts\setup_db.ps1` — запустит службу PostgreSQL 18 и создаст роль `delivery` + базу `delivery`.

**Каждый запуск:**
2. Если служба PostgreSQL остановлена — запусти её (сервисы → `postgresql-x64-18` или админский `Start-Service postgresql-x64-18`).
3. `powershell -ExecutionPolicy Bypass -File scripts\install.ps1` — установить зависимости.
4. `powershell -ExecutionPolicy Bypass -File scripts\run.ps1` — миграции + запуск бота (long polling).

Docker (`docker compose`) понадобится только на проде (VPS, стадия 6).

## Документация

- [План MVP: цели, архитектура, стадии, воркфлоу](docs/PLAN.md)

## Статус

- [x] Stage 0 — план и решения
- [x] Stage 1 — скелет проекта ✅
- [x] Stage 2 — каталог и корзина ⏳ на проверке
- [ ] Stage 3 — оформление заказа, предоплата Kaspi, операторы
- [ ] Stage 4 — админка в боте
- [ ] Stage 5 — полировка и тесты
- [ ] Stage 6 — деплой и бета