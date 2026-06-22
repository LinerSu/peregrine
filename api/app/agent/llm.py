"""Provider-agnostic LLM client.

Supports anthropic | openai | ollama via HTTP, plus a `mock` provider that needs
no API key so the app boots for demos and local development. The interface is a
single `complete(messages, tools)` call returning either text or tool calls in a
normalized shape.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..config import get_settings
from ..logging_config import get_logger

log = get_logger(__name__)


def active_provider_is_mock() -> bool:
    """True when no real LLM provider is usable, so External-mode calls return
    deterministic mock fallbacks (fit 0.5, "(mock)" text, etc.). The UI surfaces this
    so a keyless user isn't misled into trusting placeholder results as real."""
    s = get_settings()
    provider = s.llm_provider.lower()
    if provider == "anthropic":
        return not s.anthropic_api_key.strip()
    if provider == "openai":
        return not s.openai_api_key.strip()
    if provider == "ollama":
        return False  # local, assume reachable
    return True  # "mock" or any unrecognized provider


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    id: str = ""


@dataclass
class LLMResult:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient:
    def __init__(self) -> None:
        self.s = get_settings()
        self.provider = self.s.llm_provider.lower()
        self.model = self.s.llm_model

    # ------------------------------------------------------------------ #
    def complete(self, messages: list[dict[str, str]], tools: list[dict] | None = None) -> LLMResult:
        try:
            if self.provider == "anthropic":
                return self._anthropic(messages, tools)
            if self.provider == "openai":
                return self._openai(messages, tools)
            if self.provider == "ollama":
                return self._ollama(messages)
            return self._mock(messages)
        except Exception as exc:  # never crash the chat loop on provider errors
            log.exception("LLM provider %s failed; falling back to mock", self.provider)
            res = self._mock(messages)
            res.text = f"(LLM provider error: {exc}. Using mock reply.)\n\n{res.text}"
            return res

    # ------------------------------------------------------------------ #
    def _anthropic(self, messages: list[dict[str, str]], tools: list[dict] | None) -> LLMResult:
        if not self.s.anthropic_api_key.strip():
            return self._mock(messages)
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        convo = [m for m in messages if m["role"] != "system"]
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 1024,
            "system": system,
            "messages": convo,
        }
        if tools:
            payload["tools"] = [
                {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                for t in tools
            ]
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.s.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        out = LLMResult()
        for block in data.get("content", []):
            if block.get("type") == "text":
                out.text += block["text"]
            elif block.get("type") == "tool_use":
                out.tool_calls.append(ToolCall(block["name"], block.get("input", {}), block.get("id", "")))
        return out

    # ------------------------------------------------------------------ #
    def _openai(self, messages: list[dict[str, str]], tools: list[dict] | None) -> LLMResult:
        if not self.s.openai_api_key.strip():
            return self._mock(messages)
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.s.openai_api_key}"},
            json=payload,
            timeout=60,
        )
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        out = LLMResult(text=msg.get("content") or "")
        for tc in msg.get("tool_calls", []) or []:
            fn = tc["function"]
            out.tool_calls.append(
                ToolCall(fn["name"], json.loads(fn.get("arguments") or "{}"), tc.get("id", ""))
            )
        return out

    # ------------------------------------------------------------------ #
    def _ollama(self, messages: list[dict[str, str]]) -> LLMResult:
        r = httpx.post(
            f"{self.s.ollama_base_url}/api/chat",
            json={"model": self.model, "messages": messages, "stream": False},
            timeout=120,
        )
        r.raise_for_status()
        return LLMResult(text=r.json().get("message", {}).get("content", ""))

    # ------------------------------------------------------------------ #
    def _mock(self, messages: list[dict[str, str]]) -> LLMResult:
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return LLMResult(
            text=(
                "Running in **mock** LLM mode (no API key configured). "
                "Set `LLM_PROVIDER` and a key in `.env` for real responses.\n\n"
                f'You said: "{last[:200]}"'
            )
        )
