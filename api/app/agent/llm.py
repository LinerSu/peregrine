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

# How much room the model gets to answer. Anthropic requires `max_tokens` on every
# request, so this is a number we must pick — and one global number is wrong for
# somebody: a chat reply and a complete one-page LaTeX CV are not the same size. A
# single hardcoded 1024 meant every tailored CV came back cut off mid-document, and
# a cut-off document is indistinguishable from no document at all.
MAX_TOKENS_DEFAULT = 4096  # replies and structured JSON (fit, gaps, CV/posting parse)
MAX_TOKENS_LONG_FORM = 8192  # a whole document: tailored CV, cover letter, posting body

# A long-form generation legitimately runs for minutes. 60s was tuned for a 1024-token
# cap; raising the cap without raising this just trades truncation for a timeout.
_TIMEOUT_S = 180


class LLMUnusable(RuntimeError):
    """The provider answered, but the answer cannot be used: it was cut off at the
    output cap, the call failed, or nothing came back.

    Raised instead of quietly substituting a stub. Every fallback in this app is
    stamped "(mock) … set an LLM provider in .env" — honest when the mock provider is
    what's running, a lie when a real one is configured. Output that reads as genuine
    analysis but isn't is the one failure this product can least afford, so the failure
    is reported to the user rather than papered over.
    """


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
    # Why the text may not be the whole story. Both default to "fine", so a caller that
    # doesn't care is unaffected — but a caller that would otherwise substitute a stub
    # can tell "the model said nothing useful" apart from "the model was interrupted"
    # or "the call never landed". Without them those three are one empty string.
    truncated: bool = False  # stopped at max_tokens: the text is a fragment
    error: str = ""  # the provider call raised; `text` is the mock, not an answer
    # The mock wrote this, not a model — set by `_mock()`, which is also where a keyless
    # "real" provider lands. It is the client (the only component that knows) answering
    # "may a caller substitute a stub for this?", instead of every caller re-deriving it
    # from global settings.
    mocked: bool = False


class LLMClient:
    """One completion call. `max_tokens` is per client (constructed per call site)
    rather than a module-wide constant — see MAX_TOKENS_DEFAULT above."""

    def __init__(self, max_tokens: int = MAX_TOKENS_DEFAULT) -> None:
        self.s = get_settings()
        self.provider = self.s.llm_provider.lower()
        self.model = self.s.llm_model
        self.max_tokens = max_tokens

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
            # The prefixed text keeps the chat readable; `error` is what lets a caller
            # that must not fabricate (evaluate, cover letter, tailored CV) refuse.
            res.error = str(exc)
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
            "max_tokens": self.max_tokens,
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
            timeout=_TIMEOUT_S,
        )
        r.raise_for_status()
        data = r.json()
        # stop_reason "max_tokens" means the model was still writing when it hit the
        # cap: what came back is a fragment, not a short answer. Carrying that on the
        # result is what lets a caller refuse it instead of reading a half-written
        # document as "the model produced nothing useful".
        out = LLMResult(truncated=data.get("stop_reason") == "max_tokens")
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
        # No output cap is sent, deliberately. Unlike Anthropic, OpenAI does not require
        # one — omitting it means "as much as the model allows", which is never too
        # little. Sending `max_tokens` would be rejected outright by reasoning-model
        # configurations (they take `max_completion_tokens`), breaking setups that work
        # today to solve a problem this branch does not have. The half that fixes the
        # bug is reading `finish_reason` below: whatever cap applies, we now notice when
        # the answer stopped at it instead of substituting a placeholder.
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.s.openai_api_key}"},
            json=payload,
            timeout=_TIMEOUT_S,
        )
        r.raise_for_status()
        choice = r.json()["choices"][0]
        msg = choice["message"]
        # OpenAI's spelling of "I stopped because I ran out of room".
        out = LLMResult(text=msg.get("content") or "",
                        truncated=choice.get("finish_reason") == "length")
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
            # Ollama spells the cap `num_predict` and the reason `done_reason`; same
            # rule, third dialect. A local model that stops mid-CV is no more usable
            # than a metered one.
            json={"model": self.model, "messages": messages, "stream": False,
                  "options": {"num_predict": self.max_tokens}},
            timeout=_TIMEOUT_S,
        )
        r.raise_for_status()
        data = r.json()
        return LLMResult(text=data.get("message", {}).get("content", ""),
                         truncated=data.get("done_reason") == "length")

    # ------------------------------------------------------------------ #
    def _mock(self, messages: list[dict[str, str]]) -> LLMResult:
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return LLMResult(
            mocked=True,
            text=(
                "Running in **mock** LLM mode (no API key configured). "
                "Set `LLM_PROVIDER` and a key in `.env` for real responses.\n\n"
                f'You said: "{last[:200]}"'
            )
        )
