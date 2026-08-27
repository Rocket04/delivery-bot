"""Mock-провайдер: работает без ключа и без сети.

Для тестов и демо (тестовый бот). Отвечает по ключевым словам, чтобы
в тестовом режиме было видно, что конвейер «свободный текст → ассистент» жив.
Не использует LLM вообще — поэтому детерминирован.
"""

from __future__ import annotations

import logging

from integrations.llm import LLMProvider

log = logging.getLogger(__name__)


class MockProvider(LLMProvider):
    name = "mock"

    async def complete(self, system: str, user: str, max_tokens: int) -> str:
        text = user.lower()
        log.info("Mock LLM: вопрос %r (системный промпт %d символов)", user[:80], len(system))
        if any(w in text for w in ("привет", "здравствуй", "салам")):
            return "Привет! 👋 Я ассистент Food Plov. Вопросы про меню, заказ и доставку — сюда! (тестовый режим, mock-ответ)"
        if "сколько стоит" in text or "цена" in text or "сколько ст" in text:
            return "Цены — в меню у бота (кнопка 🍕 Меню). Подскажу: цены в тенге, точные значения — из карточки блюда. (тестовый режим, mock-ответ)"
        if "доставк" in text:
            return "Доставка: своя (бесплатно по городу, если курьер успевает) / Яндекс.Доставка / самовывоз с Рабочего переулка, 2а-1. (тестовый режим, mock-ответ)"
        if "мин" in text and "заказ" in text:
            return "Минимальный заказ — 20 000 ₸, предоплата 50% (Kaspi). (тестовый режим, mock-ответ)"
        return "Понял тебя! В тестовом режиме я отвечаю по заготовкам — подключите LLM_API_KEY (DeepSeek), и я смогу отвечать на любые вопросы. (тестовый режим, mock-ответ)"