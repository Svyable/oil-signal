from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel


class LLMConfig(BaseModel):
    base_url: str
    model: str
    api_key: str | None = None
    timeout_seconds: float = 30.0


class OpenAICompatibleLLM:
    """Minimal opt-in client for local or hosted OpenAI-compatible endpoints.

    The deterministic report path does not depend on this client. Any model-produced market
    narrative must still be converted into typed Claim objects and pass claim validation.
    """

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    async def complete(self, system: str, user: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(
                f"{self.config.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        try:
            return str(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("OpenAI-compatible endpoint returned an unexpected payload") from exc
