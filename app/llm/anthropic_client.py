"""Anthropic adapter for the LLM boundary (Slice 14a).

A concrete :class:`~app.llm.client.LLMClient`. **Never exercised in tests/CI** — all
tests use ``FakeLLMClient``. The API key is read at call time from settings and is
**fail-closed** (empty ⇒ refuse, no call); it is never logged, persisted, or echoed in
error text. Provider error details are redacted so a key can never leak through them.
"""

from __future__ import annotations

from app.config import settings
from app.llm.client import LLMResponse


class AnthropicConfigError(Exception):
    """Raised when the Anthropic API key is not configured (fail closed)."""


class AnthropicClient:
    """Real provider adapter. Construct per call site; reads the key from settings."""

    provider = "anthropic"

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_output_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        key = settings.anthropic_api_key
        if not key:
            raise AnthropicConfigError("anthropic_api_key is not configured (fail closed)")
        # Imported lazily so the module stays import-safe without network/SDK side effects.
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=key)
        try:
            msg = await client.messages.create(
                model=model,
                max_tokens=max_output_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:  # redact: never surface anything that could echo the key
            raise RuntimeError(f"anthropic request failed: {type(exc).__name__}") from None

        text = "".join(
            getattr(block, "text", "") for block in getattr(msg, "content", []) or []
        )
        # Fail closed on missing/invalid usage: do NOT default to zero (zero tokens would
        # masquerade as a valid, near-free successful call). Redacted error (no key echo).
        usage = getattr(msg, "usage", None)
        in_tok = getattr(usage, "input_tokens", None)
        out_tok = getattr(usage, "output_tokens", None)
        if (
            not isinstance(in_tok, int)
            or not isinstance(out_tok, int)
            or in_tok <= 0
            or out_tok <= 0
        ):
            raise RuntimeError("anthropic response missing valid token usage")
        return LLMResponse(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            model=model,
            provider=self.provider,
        )
