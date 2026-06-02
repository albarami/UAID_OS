"""Sanad provenance: no fact without an isnad (chain of sources).

Enforces the No-Free-Facts rule. Every asserted fact must carry at least
one Source; a Fact built without sources raises NoFreeFactsError.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class NoFreeFactsError(ValueError):
    """Raised when a fact is asserted without any source (isnad)."""


@dataclass(frozen=True)
class Source:
    origin: str            # url, document id, tool, or model that produced it
    locator: str = ""      # page, line, query, timestamp
    confidence: float = 1.0


@dataclass
class Fact:
    claim: str
    sources: list[Source] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.sources:
            raise NoFreeFactsError(f"Fact has no source: {self.claim!r}")

    @property
    def isnad(self) -> str:
        return " <- ".join(s.origin for s in self.sources)


def assert_provenance(facts: list[Fact]) -> None:
    """Fail loudly if any fact in the list lacks provenance."""
    for f in facts:
        if not f.sources:
            raise NoFreeFactsError(f"Fact has no source: {f.claim!r}")
