from __future__ import annotations

import time
from typing import Any

try:
    import requests
except Exception:  # pragma: no cover - optional dependency fallback
    requests = None  # type: ignore[assignment]

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
        if requests is None:
            raise LLMServerError("requests is not installed")

        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
            "temperature": temperature if temperature is not None else self.config.temperature,
        }
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        last_error: Exception | None = None
        attempts = max(1, self.config.retries + 1)
        for attempt in range(attempts):
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
                if attempt < attempts - 1:
                    time.sleep(min(0.5 * (2**attempt), 2.0))
        raise LLMServerError(f"LLM request failed: {last_error}")

    @staticmethod
    def build_user_message(text: str, image_ref: str | None = None) -> dict[str, Any]:
        if not image_ref:
            return {"role": "user", "content": text}
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": image_ref}},
            ],
        }
