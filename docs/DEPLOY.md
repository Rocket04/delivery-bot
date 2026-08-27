# DeliveryBot — деплой на VPS (Stage 6)

Пошаговая инструкция для владельца. Бот работает через **long polling**, поэтому нужен
постоянно работающий процесс — VPS с Docker Compose и `restart: unless-stopped`.

---

## 0. Что понадобится

- VPS (см. выбор ниже), Ubuntu 22.04/24.04, от 1 CPU / 1 GB RAM / 20 GB SSD.
- SSH-доступ к серверу.
- Файл `.env` с продакшн-значениями (токен бота, пароль БД, админы, операторы).

---

## 1. Выбор VPS

| Провайдер | Минимум | Оплата | Комментарий |
|-----------|---------|--------|-------------|
| **Hetzner** (cloud.hetzner.com) | CX22: 2 vCPU, 4 GB, 40 GB ≈ **€4/мес** | Карта (KZ-карты работают) | Самый дешёвый надёжный вариант |
| **Timeweb** (timeweb.cloud) | 1 vCPU, 1 GB, 10 GB ≈ 300–400₸/мес | В KZ-валюте, Kaspi | Знаком большинству в KZ, оплата проще |
| DigitalOcean / Vultr | Basic 1 GB ≈ $6/мес | Карта | Дороже, для KZ не профильно |

**Рекомендация владельцу:** если есть KZ-карта и хочется платить в тенге — **Timeweb**.
Если не смущает оплата в евро — **Hetzner** (лучше железо за те же деньги).

Создай сервер в регионе, ближайшем к Павлодару (Hetzner: Финляндия/Германия; Timeweb: Россия/Казань —
проверяй задержку, для бота она некритична). Сохрани **root-пароль или SSH-ключ**.

---

## 2. Первые шаги на сервере (по SSH)

```bash
# (одноразово) обновить систему
sudo apt update && sudo apt upgrade -y

# (одноразово) установить Docker + compose-плагин
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker
docker compose version   # должно показать v2.x
```

---

## 3. Положить проект на сервер

Скопируй проект с рабочей машины (Windows PowerShell):

```powershell
# на рабочей машине
scp -r C:\Projects\delivery-bot user@SERVER_IP:/opt/delivery-bot
```

Или через git (если репозиторий доступен с сервера):

```bash
git clone <repo-url> /opt/delivery-bot && cd /opt/delivery-bot
```

---

## 4. Файл `.env` (продакшн)

Создай на сервере `/opt/delivery-bot/.env` — по образцу `.env.example`:

```bash
cd /opt/delivery-bot
cp .env.example .env
nano .env
```

Минимум, что обязательно заполнить:

```dotenv
BOT_TOKEN=...                    # токен из @BotFather (тот же, что локально)
ADMIN_IDS=5935155979,761958359   # ты + Дилором (админка /admin)
OPERATOR_CHAT_ID=-5439223806     # группа операторов
OPERATOR_IDS=5935155979,761958359

# ПРОДАКШН-пароль БД — придумай свой! НЕ delivery
POSTGRES_PASSWORD=сложный-пароль-только-здесь

# Локальный DB_URL из .example не нужен — compose подставит сам
# Остальные бизнес-правила можно оставить как в .env.example (или скопировать из локального .env)
```

⚠️ Никогда не копируй локальный `.env` целиком: там пароль БД `delivery`, который в проде
заменяется на свой, и токен/настройки уже актуальны отдельно. `.env` в git не хранится.

---

## 5. Запуск

```bash
cd /opt/delivery-bot
docker compose up -d --build        # соберёт образ и поднимет db + bot
docker compose logs -f bot          # следить за стартом
```

Проверка:

1. В логах: `Бот запущен: @centerbyfoodplovbot` и `Start polling`.
2. В Telegram: `/start` отвечает, каталог открывается.
3. `/admin` у тебя и у Дилором работает.
4. Новая группа операторов/та же: новый тестовый заказ приходит с кнопками.

---

## 6. Автозапуск и переживание перезагрузок

В `docker-compose.yml` у обоих сервисов стоит `restart: unless-stopped` — после
перезагрузки VPS docker сам поднимет контейнеры. Docker включён в автозагрузку
системы (`systemctl enable --now docker`) — больше ничего делать не нужно.

---

## 7. Бэкапы БД (обязательно с первого дня)

Скрипт `scripts/backup.sh` делает `pg_dump` в `./backups` и хранит 14 дней.

```bash
cd /opt/delivery-bot
chmod +x scripts/backup.sh
./scripts/backup.sh                 # проверка: должен появиться delivery_<дата>.sql.gz

crontab -e
# добавить строку (бэкап каждую ночь в 4:00):
0 4 * * * /opt/delivery-bot/scripts/backup.sh >> /var/log/delivery-backup.log 2>&1
```

Восстановление (если когда-нибудь понадобится):

```bash
cd /opt/delivery-bot
gunzip -c backups/delivery_<дата>.sql.gz | docker compose exec -T db psql -U delivery -d delivery
```

---

## 8. Обновление бота после правок

```bash
cd /opt/delivery-bot
git pull                      # или заново scp изменённых файлов
docker compose up -d --build
```

---

## 9. Бета (2–3 дня)

- Тест с 2 аккаунтов: клиент (заказ до конца + чек) и оператор (все кнопки).
- Проверить «Мои заказы», статусы, отмену, ошибки в личку админу.
- Если всё чисто — давать ссылку на бота первым клиентам.

---

## 10. Частые проблемы

| Симптом | Решение |
|---------|---------|
| `Container ... unhealthy` | Постгресс не успел стартовать — подожди и проверь `docker compose logs db` |
| Бот не стартует: `BOT_TOKEN не задан` | `.env` не заполнен или не на месте |
| `SET %VAR% ... not found` на Windows при scp | Используй PowerShell `scp`, а не cmd |
| Telegram не отвечает | Проверь, что бот живой: `docker compose ps`, логи `docker compose logs -f bot` |
| Изменил `.env` — не применилось | `docker compose up -d` (compose перечитывает .env при каждом up) |