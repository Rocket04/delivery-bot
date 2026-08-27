"""Провайдеры LLM (эксперимент exp/ai-assistant).

Тонкая абстракция: бот не знает, какой провайдер стоит — mock (без сети),
DeepSeek напрямую или гейтвей OpenCode Go (OpenAI-совместимый API).
Фабрика get_provider кеширует инстанс.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache


class LLMError(Exception):
    """Провайдер недоступен/ошибка — бот ответит фолбэком (оператор)."""


class LLMProvider(ABC):
    """Минимальный контракт: системный промпт + вопрос → текст ответа."""

    name: str = "base"

    @abstractmethod
    async def complete(self, system: str, user: str, max_tokens: int) -> str:
        """Возвращает ответ модели. При любой ошибке — LLMError."""


@lru_cache(maxsize=8)
def get_provider(
    kind: str, api_key: str = "", model: str = "deepseek-v4-flash", base_url: str = ""
) -> LLMProvider:
    """Фабрика провайдеров по настройкам (env: LLM_PROVIDER/LLM_API_KEY/LLM_MODEL/LLM_BASE_URL)."""
    if kind in ("deepseek", "opencode"):
        from integrations.llm.openai_compat import DEFAULT_BASE_URLS, OpenAICompatibleProvider

        return OpenAICompatibleProvider(
            api_key=api_key,
            model=model,
            base_url=base_url or DEFAULT_BASE_URLS.get(kind),
        )
    from integrations.llm.mock import MockProvider

    return MockProvider()