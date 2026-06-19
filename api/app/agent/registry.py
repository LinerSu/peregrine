"""Minimal tool registry.

Tools are plain Python callables registered with a JSON-schema spec so the LLM
can call them by name. The harness dispatches `ToolCall`s against this registry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema
    fn: Callable[..., Any]


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, description: str, parameters: dict[str, Any]):
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._tools[name] = Tool(name, description, parameters, fn)
            return fn

        return deco

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self) -> list[dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in self._tools.values()
        ]

    def names(self) -> list[str]:
        return list(self._tools)


registry = Registry()
