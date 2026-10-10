"""Provider-agnostic LLM adapter with Pydantic-validated structured output.

Providers: openai, anthropic, groq (free tier), gemini (free tier). Groq and Gemini are
called through their OpenAI-compatible endpoints. If LLM_PROVIDER=none or no key is
configured, ``get_llm`` returns None and the agents use deterministic generators.

The LLM never computes final financial results; it only proposes narrative and
bounded assumptions that are validated and then simulated by Python code.
"""
from __future__ import annotations

import json
import logging
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings

log = logging.getLogger("marketsim.llm")
T = TypeVar("T", bound=BaseModel)

OPENAI_COMPATIBLE_BASES = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-5-5",
    "groq": "llama-3.3-70b-versatile",
    "gemini": "gemini-2.5-flash",
}


class LLMError(RuntimeError):
    pass


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise LLMError("Model response did not contain a JSON object.")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"Model returned invalid JSON: {exc.msg}") from exc


class LLMClient:
    def __init__(self, provider: str, model: str, api_key: str, timeout: float,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.provider = provider
        self.model = model
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"

    def complete_json(self, system: str, user: str) -> dict:
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                if self.provider == "anthropic":
                    resp = client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={"x-api-key": self._api_key, "anthropic-version": "2023-06-01",
                                 "content-type": "application/json"},
                        json={"model": self.model, "max_tokens": 4096, "temperature": 0.2, "system": system,
                              "messages": [{"role": "user", "content": user}]},
                    )
                    self._raise(resp)
                    blocks = resp.json().get("content") or []
                    text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict))
                else:
                    resp = client.post(
                        f"{OPENAI_COMPATIBLE_BASES[self.provider]}/chat/completions",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json={"model": self.model, "temperature": 0.2,
                              "response_format": {"type": "json_object"},
                              "messages": [{"role": "system", "content": system},
                                           {"role": "user", "content": user}]},
                    )
                    self._raise(resp)
                    text = resp.json()["choices"][0]["message"]["content"] or ""
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.provider} request failed: {type(exc).__name__}") from exc
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected {self.provider} response shape.") from exc
        return _extract_json(text)

    def _raise(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            # Never include headers/keys; only the status and a short provider message.
            try:
                detail = resp.json().get("error")
                detail = detail.get("message") if isinstance(detail, dict) else detail
            except ValueError:
                detail = None
            raise LLMError(f"{self.provider} HTTP {resp.status_code}: {str(detail or 'error')[:200]}")

    def structured(self, system: str, user: str, schema: type[T], retries: int = 1) -> T:
        """Request JSON and validate it against ``schema``; retry once with the validation error."""
        prompt = user
        last: Exception | None = None
        for _ in range(retries + 1):
            try:
                payload = self.complete_json(system, prompt)
                return schema.model_validate(payload)
            except ValidationError as exc:
                last = exc
                prompt = (f"{user}\n\nYour previous JSON failed validation:\n{str(exc)[:1500]}\n"
                          "Return corrected JSON only.")
            except LLMError as exc:
                last = exc
        raise LLMError(f"Structured output failed validation: {str(last)[:300]}")


def get_llm(settings: Settings, transport: httpx.BaseTransport | None = None) -> LLMClient | None:
    if not settings.llm_enabled:
        return None
    provider = settings.llm_provider
    model = settings.llm_model or DEFAULT_MODELS[provider]
    return LLMClient(provider, model, settings.llm_key or "", settings.llm_timeout_seconds, transport)
