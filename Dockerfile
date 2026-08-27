FROM python:3.12-slim

WORKDIR /app

# Сначала зависимости — слои кешируются
COPY pyproject.toml README.md ./
COPY bot/ bot/
COPY core/ core/
COPY data/ data/
COPY config/ config/
COPY scripts/ scripts/
COPY alembic.ini ./

RUN pip install --no-cache-dir .

CMD ["sh", "-c", "alembic upgrade head && python -m bot"]