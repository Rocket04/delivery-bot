"""OpenAI-совместимый провайдер: DeepSeek напрямую или гейтвей OpenCode Go.

Оба работают по одному протоколу chat/completions:
- deepseek: base https://api.deepseek.com (модель deepseek-v4-flash / -pro / -vision-exp)
- opencode: base https://opencode.ai/zen/go/v1 (гейтвей OpenCode Go, Bearer-ключ,
  те же deepseek-v4-* + glm/kimi/qwen и другие)

Ключ — из env LLM_API_KEY, в репозиторий и память не пишется.
"""

from __future__ import annotations

import httpx

from integrations.llm import LLMError, LLMProvider

DEFAULT_BASE_URLS = {
    "deepseek": "https://api.deepseek.com",
    "opencode": "https://opencode.ai/zen/go/v1",
}

# Без браузерного User-Agent гейтвей opencode.ai отдаёт Cloudflare 403/1010
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


class OpenAICompatibleProvider(LLMProvider):
    name = "openai-compatible"

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-v4-flash",
        base_url: str | None = None,
        timeout: float = 30.0,
    ):
        if not api_key:
            raise LLMError("LLM_API_KEY не задан — укажи ключ в .env (или поставь LLM_PROVIDER=mock)")
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or DEFAULT_BASE_URLS["deepseek"]).rstrip("/")
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
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "User-Agent": BROWSER_UA,
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:  # сеть/таймаут — не роняем бота
            raise LLMError(f"LLM недоступен: {exc.__class__.__name__}") from exc
        if resp.status_code != 200:
            raise LLMError(f"LLM ответил {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM: пустой ответ") from exc