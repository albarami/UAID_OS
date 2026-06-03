"""Tool broker (Slice 5, §11).

A platform-controlled chokepoint for tool calls: deny-by-default catalog, per-agent
allowlist, authority (Slice 3) + approval (Slice 4) composition, and a recorded
decision for every attempt. SKELETON: no real tool execution / connectors. Because
request-auth is out of scope, the success terminal is ``ALLOWED_UNVERIFIED_IDENTITY``
("would be allowed if agent identity were authenticated") — never executable.
"""

from app.tools.broker import BrokerDecision, broker_call
from app.tools.registry import InvalidParams, ToolContract, get_contract, sanitize_params

__all__ = [
    "BrokerDecision",
    "broker_call",
    "ToolContract",
    "get_contract",
    "sanitize_params",
    "InvalidParams",
]
