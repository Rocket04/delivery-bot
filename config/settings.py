from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки из переменных окружения / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Telegram ---
    bot_token: str = ""
    admin_ids: str = ""  # через запятую: 123,456
    operator_chat_id: int | None = None  # группа операторов (стадия 3)

    # --- База данных ---
    db_url: str = "postgresql+asyncpg://delivery:delivery@localhost:5432/delivery"

    # --- Бизнес-правила ---
    min_order_amount: int = 20_000  # мин. заказ, тенге
    prepay_percent: int = 50  # предоплата, %
    large_order_threshold: int = 60_000  # заказ от этой суммы считается «крупным»
    large_order_lead_hours: int = 24  # крупный заказ — минимум за это время
    default_lead_minutes: int = 120  # обычный предзаказ — минимум за это время
    work_start_hour: int = 10  # часы работы
    work_end_hour: int = 20
    app_tz: str = "Asia/Almaty"  # часовой пояс бизнеса

    @property
    def admin_id_list(self) -> list[int]:
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()