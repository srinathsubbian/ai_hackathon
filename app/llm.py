"""Thin wrapper around an OpenAI-compatible chat completions API.

This is the ONLY file that talks to your LLM provider. If your API is not
OpenAI-compatible, change `complete()` and keep its return shape:
an object with `.content` (str | None) and `.tool_calls` (list | None, each with
`.id`, `.function.name`, `.function.arguments` as a JSON string).
"""
from openai import OpenAI

from . import config


class LLMConfigError(Exception):
    pass


class LLMClient:
    def __init__(self):
        self._client = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:  # lazy so the app boots (and /health works) without config
            if not config.LLM_MODEL:
                raise LLMConfigError("LLM_MODEL is not set")
            if not config.LLM_API_KEY and not config.LLM_BASE_URL:
                raise LLMConfigError("LLM_API_KEY / LLM_BASE_URL is not set")
            self._client = OpenAI(
                api_key=config.LLM_API_KEY or "not-needed",  # local servers often ignore the key
                base_url=config.LLM_BASE_URL or None,
                timeout=config.LLM_TIMEOUT,
            )
        return self._client

    def complete(self, messages: list, tools: list | None = None):
        kwargs = {
            "model": config.LLM_MODEL,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 1200,
        }
        if tools:
            kwargs["tools"] = tools
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message
