"""Shared unique-violation classification for concurrent first-write recovery.

One caller-visible unresolved exception, not a writer-domain subclass. SQLSTATE
and constraint names are read from nested DBAPI errors the same way Slice 55
walks ``sqlstate`` / ``pgcode``.
"""

from __future__ import annotations


class ConcurrentWriteUnresolved(Exception):
    """Fail-closed: ON CONFLICT returned no row and the winner re-select was empty."""


def _walk_dbapi(exc: BaseException) -> list[BaseException]:
    """Flatten ``orig`` / ``__cause__`` / ``__context__`` without mutating ``exc``."""
    pending: list[BaseException] = [exc]
    visited: set[int] = set()
    found: list[BaseException] = []
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        found.append(current)
        for attribute in ("orig", "__cause__", "__context__"):
            nested = getattr(current, attribute, None)
            if isinstance(nested, BaseException):
                pending.append(nested)
    return found


def _sqlstate(exc: BaseException) -> str | None:
    """Return a nested PostgreSQL SQLSTATE, or None."""
    for current in _walk_dbapi(exc):
        for attribute in ("sqlstate", "pgcode"):
            value = getattr(current, attribute, None)
            if isinstance(value, str):
                return value
    return None


def is_unique_violation(exc: BaseException) -> bool:
    """True iff ``exc`` carries PostgreSQL unique-violation SQLSTATE ``23505``."""
    return _sqlstate(exc) == "23505"


def unique_violation_constraint(exc: BaseException) -> str | None:
    """Named unique constraint when ``exc`` is SQLSTATE ``23505``; else None.

    Returns None for every other SQLSTATE so a foreign-key, CHECK, or NOT NULL
    failure cannot enter a unique-conflict branch.
    """
    if not is_unique_violation(exc):
        return None
    for current in _walk_dbapi(exc):
        name = getattr(current, "constraint_name", None)
        if isinstance(name, str) and name:
            return name
        diag = getattr(current, "diag", None)
        nested = getattr(diag, "constraint_name", None) if diag is not None else None
        if isinstance(nested, str) and nested:
            return nested
    return None
