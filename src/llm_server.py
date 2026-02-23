from __future__ import annotations

from typing import Any

import requests

from .config_loader import ModelConfig


class LLMServerError(RuntimeError):
    pass


class LLMServer:
    def __init__(self, config: ModelConfig) -> None:
        self.config = config

    def complete(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
            "temperature": temperature if temperature is not None else self.config.temperature,
        }
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        last_error: Exception | None = None
        for _ in range(max(1, self.config.retries + 1)):
            try:
                resp = requests.post(
                    f"{self.config.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=self.config.timeout_sec,
                )
                if resp.status_code >= 400:
                    raise LLMServerError(f"LLM HTTP {resp.status_code}: {resp.text[:400]}")
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except Exception as exc:  # pragma: no cover - network behavior
                last_error = exc
        raise LLMServerError(f"LLM request failed: {last_error}")

