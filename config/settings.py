from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки из переменных окружения / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Telegram ---
    bot_token: str = ""
    admin_ids: str = ""  # через запятую: 123,456
    operator_chat_id: int | None = None  # группа операторов (стадия 3)
    operator_ids: str = ""  # через запятую: кто может работать кнопками в группе операторов

    @field_validator("operator_chat_id", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v: object) -> object:
        """Пустое значение в .env (OPERATOR_CHAT_ID=) → None, а не ошибка."""
        if v == "":
            return None
        return v

    # --- База данных ---
    db_url: str = "postgresql+asyncpg://delivery:delivery@localhost:5432/delivery"

    # --- Бизнес-правила ---
    min_order_amount: int = 20_000  # мин. заказ, тенге
    prepay_percent: int = 50  # предоплата, %
    large_order_threshold: int = 60_000  # заказ от этой суммы считается «крупным»
    default_lead_minutes: int = 60 * 24  # обычный предзаказ — минимум за это время (сутки)
    large_order_lead_hours: int = 48  # крупный заказ — минимум за это время
    dish_deposit_amount: int = 10_000  # залог за восточную посуду (возвратный), тенге
    app_tz: str = "Asia/Almaty"  # часовой пояс бизнеса

    # Порция весового блюда в граммах (пловы и т.п.: 1 порция = 300 г, 10 порций = 3 кг)
    portion_grams: int = 300  # env: PORTION_GRAMS

    # --- Окно приготовления (время ДОСТАВКИ должно попадать в него — ночью не готовим) ---
    delivery_start_hour: int = 8  # env: DELIVERY_START_HOUR — с какого часа принимаем время
    delivery_end_hour: int = 23  # env: DELIVERY_END_HOUR — до какого часа (включительно)

    # --- ИИ-ассистент (эксперимент exp/ai-assistant) ---
    llm_provider: str = "mock"  # env: LLM_PROVIDER — mock | deepseek | opencode (go-гейтвей)
    llm_api_key: str = ""  # env: LLM_API_KEY — ключ провайдера (в репозиторий НЕ писать)
    llm_model: str = "deepseek-v4-flash"  # env: LLM_MODEL (у opencode-go: deepseek-v4-flash/pro/vision-exp)
    llm_base_url: str = ""  # env: LLM_BASE_URL — пусто = дефолт провайдера (deepseek / opencode-go)
    llm_max_tokens: int = 240  # env: LLM_MAX_TOKENS — лимит ответа (экономия + защита)

    @property
    def admin_id_list(self) -> list[int]:
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip()]

    @property
    def operator_id_list(self) -> list[int]:
        return [int(x.strip()) for x in self.operator_ids.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()