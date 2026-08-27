FROM python:3.12-slim

WORKDIR /app

# Шаг 1: только зависимости — этот слой кешируется, пока requirements.txt не менялся.
# Правка кода НЕ переустанавливает зависимости (быстрые обновления на VPS).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Шаг 2: код приложения (меняется часто — пересборка дешёвая).
COPY pyproject.toml README.md ./
COPY bot/ bot/
COPY core/ core/
COPY data/ data/
COPY config/ config/
COPY scripts/ scripts/
COPY alembic.ini ./

# Запуск: миграции вперёд, потом бот (long polling).
CMD ["sh", "-c", "alembic upgrade head && python -m bot"]