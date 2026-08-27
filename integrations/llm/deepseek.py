"""DeepSeek-провайдер (OpenAI-совместимый chat/completions).

Ключ берётся из env LLM_API_KEY — в репозиторий и память не пишется.
Цены (2026): ~$0.28/M вход (без кэша), $0.42/M выход — на наш трафик $2–5/мес.
"""

from __future__ import annotations

import httpx

from integrations.llm import LLMError, LLMProvider

DEFAULT_BASE_URL = "https://api.deepseek.com"


class DeepSeekProvider(LLMProvider):
    name = "deepseek"

    def __init__(self, api_key: str, model: str = "deepseek-chat", base_url: str = DEFAULT_BASE_URL, timeout: float = 20.0):
        if not api_key:
            raise LLMError("LLM_API_KEY не задан — укажи ключ DeepSeek в .env (или поставь LLM_PROVIDER=mock)")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def complete(self, system: str, user: str, max_tokens: int) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
        except httpx.HTTPError as exc:  # сеть/таймаут — не роняем бота
            raise LLMError(f"DeepSeek недоступен: {exc.__class__.__name__}") from exc
        if resp.status_code != 200:
            raise LLMError(f"DeepSeek ответил {resp.status_code}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("DeepSeek: пустой ответ") from exc