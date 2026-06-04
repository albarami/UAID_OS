"""LLM provider boundary (Slice 14a). The ONLY place model providers are called.

`LLMClient` is the narrow protocol the extractor depends on; `FakeLLMClient` is the
deterministic, offline implementation used by ALL tests/CI (no network, no key). Real
adapters (e.g. Anthropic) live in sibling modules and are never exercised in tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str


class LLMClient(Protocol):
    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_output_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse: ...


@dataclass
class FakeLLMClient:
    """Deterministic, offline LLM client for tests. Records every call; optionally raises."""

    response_text: str = ""
    input_tokens: int = 10
    output_tokens: int = 20
    raise_exc: Exception | None = None
    calls: list[dict] = field(default_factory=list)

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_output_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "model": model,
                "max_output_tokens": max_output_tokens,
                "temperature": temperature,
            }
        )
        if self.raise_exc is not None:
            raise self.raise_exc
        return LLMResponse(
            text=self.response_text,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            model=model,
            provider="fake",
        )
