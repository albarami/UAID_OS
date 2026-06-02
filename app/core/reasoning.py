"""Muhasabah gate: a self-audit pass run before any output is returned.

Checks a proposed answer against invariants. Extend `extra_checks` per
project. If any check fails, the gate blocks the output.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.core.provenance import Fact


@dataclass
class GateResult:
    passed: bool
    failures: list[str]


def muhasabah_gate(
    answer: str,
    facts: list[Fact],
    extra_checks: list[Callable[[str, list[Fact]], str | None]] | None = None,
) -> GateResult:
    failures: list[str] = []

    if not answer.strip():
        failures.append("empty answer")

    for f in facts:
        if not f.sources:
            failures.append(f"unsourced fact: {f.claim!r}")

    for check in extra_checks or []:
        msg = check(answer, facts)
        if msg:
            failures.append(msg)

    return GateResult(passed=not failures, failures=failures)
