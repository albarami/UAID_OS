"""Deterministic connector contract checker (Slice 61a, OD-5).

No network, no DB, no LLM, no broker call. Structural Fake conformance plus
symbol resolution. Deliberately no AST analysis of broker usage.
"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from typing import Protocol, get_type_hints

from app.ecosystem.catalog import CHECK_NAMES, ConnectorSpecInput


@dataclass(frozen=True)
class CheckResult:
    """One named boolean result from the contract checker."""

    name: str
    passed: bool


@dataclass(frozen=True)
class ContractTestResult:
    """Frozen five-result checker output. ``passed`` is the conjunction."""

    results: tuple[CheckResult, ...]
    passed: bool


def _load_attr(module_name: str, attr: str) -> object | None:
    try:
        module = importlib.import_module(module_name)
    except (ModuleNotFoundError, ImportError, ValueError):
        return None
    return getattr(module, attr, None)


def _is_protocol(target: object) -> bool:
    return (
        isinstance(target, type)
        and issubclass(target, Protocol)
        and bool(getattr(target, "_is_protocol", False))
    )


def _protocol_methods(proto: type) -> dict[str, inspect.Signature]:
    methods: dict[str, inspect.Signature] = {}
    for name, value in inspect.getmembers(proto, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        methods[name] = inspect.signature(value)
    return methods


def _param_names(signature: inspect.Signature) -> tuple[str, ...]:
    return tuple(p for p in signature.parameters if p != "self")


def _check_tool_scope_nonempty(spec: ConnectorSpecInput) -> bool:
    names = spec.tool_names
    if not names:
        return False
    seen: set[str] = set()
    for name in names:
        if not isinstance(name, str) or not name.strip() or name.strip() != name:
            return False
        if len(name) > 120:
            return False
        if name in seen:
            return False
        seen.add(name)
    return True


def _check_tool_scope_resolves(spec: ConnectorSpecInput) -> bool:
    from app.tools.registry import get_contract

    if not spec.tool_names:
        return False
    return all(get_contract(name) is not None for name in spec.tool_names)


def _check_protocol_resolves(spec: ConnectorSpecInput) -> bool:
    target = _load_attr(spec.protocol_module, spec.protocol_name)
    return _is_protocol(target)


def _check_fake_conforms(spec: ConnectorSpecInput) -> bool:
    proto = _load_attr(spec.protocol_module, spec.protocol_name)
    fake = _load_attr(spec.protocol_module, spec.fake_name)
    if not isinstance(proto, type) or not _is_protocol(proto) or not isinstance(fake, type):
        return False
    try:
        get_type_hints(fake)
    except (NameError, TypeError):
        pass
    for name, proto_sig in _protocol_methods(proto).items():
        impl = getattr(fake, name, None)
        if impl is None or not callable(impl):
            return False
        try:
            impl_sig = inspect.signature(impl)
        except (TypeError, ValueError):
            return False
        if _param_names(impl_sig) != _param_names(proto_sig):
            return False
    return True


def _check_live_adapter_symbol(spec: ConnectorSpecInput) -> bool:
    absent = spec.live_adapter_status == "absent"
    name_missing = spec.live_adapter_name is None
    if absent != name_missing:
        return False
    if absent:
        return True
    return _load_attr(spec.protocol_module, spec.live_adapter_name or "") is not None


_CHECKERS = (
    ("tool_scope_nonempty", _check_tool_scope_nonempty),
    ("tool_scope_resolves", _check_tool_scope_resolves),
    ("protocol_resolves", _check_protocol_resolves),
    ("fake_conforms", _check_fake_conforms),
    ("live_adapter_symbol", _check_live_adapter_symbol),
)


def run_connector_contract_test(spec: ConnectorSpecInput) -> ContractTestResult:
    """Run all five checks and return a frozen result. Always emits every name."""
    results = tuple(CheckResult(name, checker(spec)) for name, checker in _CHECKERS)
    if tuple(r.name for r in results) != CHECK_NAMES:
        raise RuntimeError("contract checker must emit the five OD-5 names in order")
    return ContractTestResult(results=results, passed=all(r.passed for r in results))
