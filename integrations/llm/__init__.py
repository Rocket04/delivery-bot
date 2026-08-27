"""Провайдеры LLM (эксперимент exp/ai-assistant).

Тонкая абстракция: бот не знает, какой провайдер стоит — mock (без сети) или
DeepSeek (OpenAI-совместимый API). Фабрика get_provider кеширует инстанс.
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
def get_provider(kind: str, api_key: str = "", model: str = "deepseek-chat") -> LLMProvider:
    """Фабрика провайдеров по настройкам (env: LLM_PROVIDER/LLM_API_KEY/LLM_MODEL)."""
    if kind == "deepseek":
        from integrations.llm.deepseek import DeepSeekProvider

        return DeepSeekProvider(api_key=api_key, model=model)
    from integrations.llm.mock import MockProvider

    return MockProvider()